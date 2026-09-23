"""Tests for the RSI-confirm widened-TP feature in instrument_engine.py (production
implementation of research/rsi_confirm_widened_tp_study.py's backtested finding, translated to
the live bot's index-points take-profit -- the premium-pct take-profit is deliberately left
untouched, see InstrumentConfig.rsi_confirm_widened_tp_points's docstring).

Run with: .venv\\Scripts\\python.exe test_rsi_confirm_widened_tp_live.py
"""
from __future__ import annotations

import sys
import tempfile
from datetime import time as dtime
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np
import pandas as pd

from config import AppConfig, HistoricalDataConfig, InstrumentConfig, RiskConfig
from instrument_engine import InstrumentEngine
from risk import RiskManager
from state import TradeStore


def _make_engine(rsi_enabled: bool, instrument_points: float = 400.0, checkpoint_bars: int = 6):
    cfg = InstrumentConfig(
        name="TESTIDX", exchange_index_symbol="TESTIDX", index_token="1", candle_token="1",
        signal_strategy="ema_crossover", lot_size=50, quantity_lots=1,
        buy_strike_offset=0, sell_strike_offset=0,
        take_profit_points=100, take_profit_premium_pct=10, stop_loss_points=50,
        entry_start_time=dtime(9, 30), entry_cutoff_time=dtime(14, 50),
        force_exit_time=dtime(14, 50), force_exit_time_expiry_day=dtime(14, 45),
        underlying_exchange="NSE", options_exchange="NFO",
        rsi_confirm_widened_tp_points=instrument_points,
    )
    app_cfg = AppConfig(
        poll_interval_seconds=3, order_fill_timeout_seconds=10, order_fill_poll_seconds=1,
        paper_trading=True, strike_selection_mode="atm", target_delta=0.5,
        trailing_stop_enabled=False, trailing_stop_activation_points=50, trailing_stop_distance_points=30,
        trailing_stop_mode="points", trailing_stop_step_pct=5,
        signal_reversal_exit_enabled=False, iv_exit_enabled=False, iv_exit_drop_pct=20,
        iv_check_interval_seconds=30, momentum_exit_enabled=False, momentum_window_minutes=10,
        momentum_exit_points=60, pullback_entry_enabled=False, pullback_extended_threshold_points=100,
        extreme_point_rule_enabled=False, extreme_point_rule_max_wait_bars=3,
        rsi_confirm_widened_tp_enabled=rsi_enabled, rsi_confirm_widened_tp_checkpoint_bars=checkpoint_bars,
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
    return engine, store


def _rising_rsi_candles(n: int, start="2026-01-05 09:15"):
    """Enough bars, with a genuinely rising close, that indicators.rsi warms up and reads
    meaningfully above 50 for the whole window -- used for the "RSI confirms a CE" cases."""
    dates = pd.date_range(start, periods=n, freq="5min")
    close = 100 + np.arange(n) * 0.5
    return pd.DataFrame({"date": dates, "open": close, "high": close + 0.2, "low": close - 0.2, "close": close})


def _falling_rsi_candles(n: int, start="2026-01-05 09:15"):
    dates = pd.date_range(start, periods=n, freq="5min")
    close = 100 - np.arange(n) * 0.5
    return pd.DataFrame({"date": dates, "open": close, "high": close + 0.2, "low": close - 0.2, "close": close})


_CANDLE_START = pd.Timestamp("2026-01-05 09:15")


def _open_ce_trade(store: TradeStore, entry_rsi: float | None):
    """Opens a trade and backdates opened_at to just before _CANDLE_START, so every row in
    a candles frame built from _CANDLE_START (via _rising_rsi_candles/_falling_rsi_candles)
    counts as "after entry" -- bars_since_entry is then simply len(candles), which each test
    controls directly by how many candles it hands to _maybe_widen_take_profit."""
    trade_id = store.open_trade(
        instrument="TESTIDX", order_id="O1", symbol="TESTIDXCE", trade_type="CE", token="T1",
        entry_price=100.0, quantity=50, entry_underlying_price=100.0, strike=100.0,
        mode="PAPER", entry_rsi=entry_rsi,
    )
    with store._connect() as conn:
        conn.execute("UPDATE trades SET opened_at=? WHERE id=?",
                     ((_CANDLE_START - pd.Timedelta(5, unit="min")).isoformat(timespec="seconds"), trade_id))
    return store.get_open_trade("TESTIDX")


def test_disabled_globally_returns_base_take_profit_unchanged():
    engine, store = _make_engine(rsi_enabled=False)
    trade = _open_ce_trade(store, entry_rsi=40.0)
    candles = _rising_rsi_candles(30)
    result = engine._maybe_widen_take_profit(trade, candles)
    assert result == 100.0
    trade2 = store.get_open_trade("TESTIDX")
    assert trade2.tp_widen_checked == 0, "must not even evaluate the checkpoint when disabled globally"
    print("PASS: rsi_confirm_widened_tp_enabled=False leaves take_profit_points untouched, never checks")


def test_instrument_not_configured_returns_base_take_profit_unchanged():
    engine, store = _make_engine(rsi_enabled=True, instrument_points=0.0)  # not configured for this instrument
    trade = _open_ce_trade(store, entry_rsi=40.0)
    candles = _rising_rsi_candles(30)
    result = engine._maybe_widen_take_profit(trade, candles)
    assert result == 100.0
    print("PASS: an instrument with rsi_confirm_widened_tp_points=0 is untouched even when the global flag is on")


def test_before_checkpoint_stays_undecided():
    engine, store = _make_engine(rsi_enabled=True, checkpoint_bars=6)
    trade = _open_ce_trade(store, entry_rsi=40.0)
    candles = _rising_rsi_candles(3)  # fewer than 6 bars since entry
    result = engine._maybe_widen_take_profit(trade, candles)
    assert result == 100.0
    trade2 = store.get_open_trade("TESTIDX")
    assert trade2.tp_widen_checked == 0, "must stay undecided (not memoized) before the checkpoint"
    print("PASS: before the checkpoint, take_profit_points is unchanged and the decision is NOT yet memoized")


def test_confirms_at_checkpoint_widens_and_memoizes():
    engine, store = _make_engine(rsi_enabled=True, checkpoint_bars=6, instrument_points=400.0)
    trade = _open_ce_trade(store, entry_rsi=40.0)  # low entry RSI, rising afterward -> confirms a CE
    candles = _rising_rsi_candles(30)  # RSI will read well above 40 by the checkpoint
    result = engine._maybe_widen_take_profit(trade, candles)
    assert result == 400.0, f"RSI rose after a low entry_rsi -- must widen to 400, got {result}"
    trade2 = store.get_open_trade("TESTIDX")
    assert trade2.tp_widen_checked == 1
    assert trade2.tp_widened_points == 400.0

    # a SECOND call (simulating the next poll cycle) must reuse the memoized decision,
    # not recompute -- even if we hand it different candles
    result2 = engine._maybe_widen_take_profit(trade2, _falling_rsi_candles(30))
    assert result2 == 400.0, "must return the memoized widened value, not re-derive from new candles"
    print("PASS: RSI confirming at the checkpoint widens the target and memoizes the decision")


def test_denies_at_checkpoint_keeps_base_and_memoizes():
    engine, store = _make_engine(rsi_enabled=True, checkpoint_bars=6, instrument_points=400.0)
    trade = _open_ce_trade(store, entry_rsi=80.0)  # high entry RSI, falling afterward -> denies a CE
    candles = _falling_rsi_candles(30)
    result = engine._maybe_widen_take_profit(trade, candles)
    assert result == 100.0, f"RSI denied -- must keep the base 100, got {result}"
    trade2 = store.get_open_trade("TESTIDX")
    assert trade2.tp_widen_checked == 1
    assert trade2.tp_widened_points is None
    print("PASS: RSI denying at the checkpoint keeps the base take-profit and still memoizes (checked=1, widened=None)")


def test_missing_entry_rsi_never_widens_but_also_never_permanently_blocks():
    """If entry_rsi couldn't be captured (e.g. too little candle history at entry), the
    feature must degrade safely: never widen (nothing to compare against), and must NOT
    memoize a false "checked" state that would be wrong if entry_rsi later became knowable
    -- it simply keeps returning the base target forever for this trade, which is exactly
    equivalent to the feature being off for it."""
    engine, store = _make_engine(rsi_enabled=True, checkpoint_bars=6)
    trade = _open_ce_trade(store, entry_rsi=None)
    candles = _rising_rsi_candles(30)
    result = engine._maybe_widen_take_profit(trade, candles)
    assert result == 100.0
    trade2 = store.get_open_trade("TESTIDX")
    assert trade2.tp_widen_checked == 0
    print("PASS: a missing entry_rsi never widens and never falsely memoizes a decision")


def test_current_rsi_helper_handles_empty_and_none_candles():
    engine, _ = _make_engine(rsi_enabled=True)
    assert engine._current_rsi(None) is None
    assert engine._current_rsi(pd.DataFrame(columns=["close"])) is None
    print("PASS: _current_rsi degrades to None for missing/empty candles instead of raising")


def test_enter_captures_entry_rsi_from_candles():
    engine, store = _make_engine(rsi_enabled=True)
    engine._select_contract = MagicMock(return_value=(
        {"symbol": "TESTIDXCE", "token": "T1", "strike": "10000"}, None
    ))
    engine._execute_order = MagicMock(return_value=MagicMock(order_id="O1", status="complete", price=100.0))
    candles = _rising_rsi_candles(30)

    engine._enter(100.0, "CE", underlying_ltp=100.0, candles=candles)

    trade = store.get_open_trade("TESTIDX")
    assert trade is not None
    assert trade.entry_rsi is not None and trade.entry_rsi > 50, \
        "a steadily-rising close series must produce an entry_rsi comfortably above 50"
    print(f"PASS: _enter() captured entry_rsi={trade.entry_rsi:.1f} from the candles passed to it")


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
    print(f"\nALL {len(tests)} RSI-CONFIRM-WIDENED-TP-LIVE TESTS PASSED")
