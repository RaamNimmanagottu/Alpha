"""Tests for the Extreme Point Rule entry path in instrument_engine.py (Phase 3.2: production
implementation of research/extreme_point_rule_study.py's backtested finding). Mirrors the
existing pullback-pending-entry mechanism's structure but with the opposite trigger (confirm by
BREAKING the signal candle's own extreme, not retracing to it) and a bar-count-based expiry
instead of only expiring at entry_cutoff_time.

Run with: .venv\\Scripts\\python.exe test_extreme_point_pending_entry.py
"""
from __future__ import annotations

import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, time as dtime
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pandas as pd

from config import AppConfig, HistoricalDataConfig, InstrumentConfig, RiskConfig
from instrument_engine import InstrumentEngine
from risk import RiskManager
from state import TradeStore


@dataclass
class _FakeSignal:
    direction: str
    signal_candle_time: pd.Timestamp | None = None


def _make_engine(extreme_point_rule_enabled: bool, max_wait_bars: int = 3):
    cfg = InstrumentConfig(
        name="TESTIDX", exchange_index_symbol="TESTIDX", index_token="1", candle_token="1",
        signal_strategy="ema_crossover", lot_size=50, quantity_lots=1,
        buy_strike_offset=0, sell_strike_offset=0,
        take_profit_points=100, take_profit_premium_pct=10, stop_loss_points=50,
        entry_start_time=dtime(9, 30), entry_cutoff_time=dtime(14, 50),
        force_exit_time=dtime(14, 50), force_exit_time_expiry_day=dtime(14, 45),
        underlying_exchange="NSE", options_exchange="NFO",
    )
    app_cfg = AppConfig(
        poll_interval_seconds=3, order_fill_timeout_seconds=10, order_fill_poll_seconds=1,
        paper_trading=True, strike_selection_mode="atm", target_delta=0.5,
        trailing_stop_enabled=False, trailing_stop_activation_points=50, trailing_stop_distance_points=30,
        trailing_stop_mode="points", trailing_stop_step_pct=5,
        signal_reversal_exit_enabled=False, iv_exit_enabled=False, iv_exit_drop_pct=20,
        iv_check_interval_seconds=30, momentum_exit_enabled=False, momentum_window_minutes=10,
        momentum_exit_points=60, pullback_entry_enabled=False, pullback_extended_threshold_points=100,
        extreme_point_rule_enabled=extreme_point_rule_enabled, extreme_point_rule_max_wait_bars=max_wait_bars,
        rsi_confirm_widened_tp_enabled=False, rsi_confirm_widened_tp_checkpoint_bars=6,
        starting_capital=200000, shutdown_vm_on_exit=False,
        risk=RiskConfig(5000, 10, 10), market=None,
        historical_data=HistoricalDataConfig("FIVE_MINUTE", 5, 100,
                                              str(Path(tempfile.mkdtemp()) / "hist")),
        instruments=[cfg], holiday_lists={},
    )
    broker = MagicMock()
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
    tmp.close()
    store = TradeStore(db_path=Path(tmp.name))
    risk = RiskManager(RiskConfig(5000, 10, 10), store)
    engine = InstrumentEngine(cfg, app_cfg, broker, store, risk, notifier=MagicMock())
    engine._enter = MagicMock()
    return engine


def _candles(n: int, start="2026-01-05 09:15"):
    dates = pd.date_range(start, periods=n, freq="5min")
    return pd.DataFrame({"date": dates, "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0})


def test_signal_sets_pending_entry_instead_of_entering_immediately():
    engine = _make_engine(extreme_point_rule_enabled=True)
    candles = _candles(1)
    signal_time = candles["date"].iloc[-1]
    engine._get_candles = lambda: candles
    engine._get_signal = lambda *a, **k: _FakeSignal("BUY", signal_time)

    engine._consider_entry(ltp=100.0, now=datetime(2026, 1, 5, 9, 35), entry_cutoff=dtime(14, 50))

    assert not engine._enter.called, "must NOT enter immediately when the Extreme Point Rule is enabled"
    assert engine._pending_entry is not None
    assert engine._pending_entry["kind"] == "extreme_point"
    assert engine._pending_entry["direction"] == "CE"
    assert engine._pending_entry["extreme_price"] == candles["high"].iloc[-1]
    print("PASS: a BUY signal sets a pending extreme-point entry (signal candle's own high) instead of entering immediately")


def test_confirmed_break_triggers_entry():
    engine = _make_engine(extreme_point_rule_enabled=True, max_wait_bars=3)
    signal_time = pd.Timestamp("2026-01-05 09:15")
    engine._pending_entry = {"kind": "extreme_point", "direction": "CE", "extreme_price": 101.0,
                              "signal_candle_time": signal_time}
    later_candles = _candles(3, start="2026-01-05 09:20")  # 2 candles after the signal candle
    engine._get_candles = lambda: later_candles
    engine._get_signal = lambda *a, **k: _FakeSignal("WAIT", None)

    engine._check_extreme_point_pending_entry(ltp=101.5, now=datetime(2026, 1, 5, 9, 30), entry_cutoff=dtime(14, 50))

    assert engine._enter.called, "price broke above the extreme (101.0) -- must enter"
    assert engine._pending_entry is None
    print("PASS: price breaking the signal candle's high confirms and triggers entry")


def test_never_confirmed_within_window_expires_without_entering():
    engine = _make_engine(extreme_point_rule_enabled=True, max_wait_bars=2)
    signal_time = pd.Timestamp("2026-01-05 09:15")
    engine._pending_entry = {"kind": "extreme_point", "direction": "CE", "extreme_price": 101.0,
                              "signal_candle_time": signal_time}
    # 3 candles have formed after the signal candle -- exceeds max_wait_bars=2
    later_candles = _candles(4, start="2026-01-05 09:20")
    engine._get_candles = lambda: later_candles
    engine._get_signal = lambda *a, **k: _FakeSignal("WAIT", None)

    engine._check_extreme_point_pending_entry(ltp=100.5, now=datetime(2026, 1, 5, 9, 35), entry_cutoff=dtime(14, 50))

    assert not engine._enter.called, "extreme was never broken -- must NOT enter"
    assert engine._pending_entry is None, "must expire (treated as a false/whipsaw signal), not linger forever"
    print("PASS: a signal that never confirms within max_wait_bars expires without entering")


def test_opposite_signal_cancels_pending_entry():
    engine = _make_engine(extreme_point_rule_enabled=True, max_wait_bars=5)
    signal_time = pd.Timestamp("2026-01-05 09:15")
    engine._pending_entry = {"kind": "extreme_point", "direction": "CE", "extreme_price": 101.0,
                              "signal_candle_time": signal_time}
    later_candles = _candles(2, start="2026-01-05 09:20")
    opposite_signal_time = pd.Timestamp("2026-01-05 09:25")
    engine._get_candles = lambda: later_candles
    engine._get_signal = lambda *a, **k: _FakeSignal("SELL", opposite_signal_time)

    engine._check_extreme_point_pending_entry(ltp=100.5, now=datetime(2026, 1, 5, 9, 30), entry_cutoff=dtime(14, 50))

    assert not engine._enter.called
    assert engine._pending_entry is None
    assert engine._last_acted_signal_time == opposite_signal_time
    print("PASS: a fresh opposite signal cancels the pending extreme-point entry")


def test_disabled_flag_preserves_original_immediate_entry_behavior():
    """Regression guard: with extreme_point_rule_enabled=False (the shipped default), a normal
    (non-extended) signal must still enter immediately, exactly as before this feature existed."""
    engine = _make_engine(extreme_point_rule_enabled=False)
    candles = _candles(1)
    signal_time = candles["date"].iloc[-1]
    engine._get_candles = lambda: candles
    engine._get_signal = lambda *a, **k: _FakeSignal("BUY", signal_time)

    engine._consider_entry(ltp=100.0, now=datetime(2026, 1, 5, 9, 35), entry_cutoff=dtime(14, 50))

    assert engine._enter.called, "with the flag off, entry must still be immediate"
    assert engine._pending_entry is None
    print("PASS: extreme_point_rule_enabled=False preserves the original immediate-entry behavior")


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
    print(f"\nALL {len(tests)} EXTREME-POINT-PENDING-ENTRY TESTS PASSED")
