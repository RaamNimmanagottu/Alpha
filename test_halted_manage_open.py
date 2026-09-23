"""Tests for the "halt must not strand an open position" fix (2026-09-21).

Incident: the daily loss limit tripped at 14:15, main.py then skipped every engine for the rest of the
day, and FINNIFTY paper trade #22 sat open past its 14:50 forced exit. Now a halt only blocks NEW
entries; open positions keep being managed.

Run with: .venv\\Scripts\\python.exe test_halted_manage_open.py   (no live API calls; broker is a MagicMock)
"""
from __future__ import annotations

import sys
import tempfile
from datetime import time as dtime
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pandas as pd

import main as bot_main
from config import AppConfig, HistoricalDataConfig, InstrumentConfig, RiskConfig
from instrument_engine import InstrumentEngine
from risk import RiskManager
from state import TradeStore

CAPITAL = 200000
ENTRY = 100.0
QTY = 65
EXIT_LTP = 95.0          # below entry but no TP/SL trigger -> only the forced (time) exit can close it
HEALTHY_LTP = 101.0      # +1%: below the +10% premium take-profit


def _make_engine(force_exit: dtime, option_ltp: float = EXIT_LTP):
    cfg = InstrumentConfig(
        name="NIFTY", exchange_index_symbol="NIFTY", index_token="1", candle_token="1",
        signal_strategy="ema_crossover", lot_size=QTY, quantity_lots=1,
        buy_strike_offset=0, sell_strike_offset=0,
        take_profit_points=100, take_profit_premium_pct=10, stop_loss_points=50,
        entry_start_time=dtime(9, 30), entry_cutoff_time=dtime(14, 50),
        force_exit_time=force_exit, force_exit_time_expiry_day=force_exit,
        min_premium_threshold=0,
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
        rsi_confirm_widened_tp_enabled=False, rsi_confirm_widened_tp_checkpoint_bars=6,
        starting_capital=CAPITAL, shutdown_vm_on_exit=False,
        risk=RiskConfig(5000, 10, 10), market=None,
        historical_data=HistoricalDataConfig("FIVE_MINUTE", 5, 100,
                                              str(Path(tempfile.gettempdir()) / "alpha_test_halted")),
        instruments=[cfg], holiday_lists={},
    )
    broker = MagicMock()
    atm = pd.DataFrame([{"symbol": "NIFTY23000CE", "token": "T1", "strike": "2300000", "expiry": "25SEP2030"}])
    broker.option_contracts_atm.return_value = atm
    broker.underlying_price.side_effect = lambda ex, symbol, token: 23000.0 if symbol == "NIFTY" else option_ltp

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
    tmp.close()
    store = TradeStore(db_path=Path(tmp.name))
    store.get_capital(CAPITAL)
    risk = RiskManager(RiskConfig(5000, 10, 10), store)
    engine = InstrumentEngine(cfg, app_cfg, broker, store, risk, notifier=MagicMock())
    engine._get_candles = MagicMock(return_value=pd.DataFrame())
    engine._get_signal = MagicMock(return_value=None)
    engine._maybe_fetch_iv = MagicMock(return_value=None)
    return engine, store, risk


def _open_paper_trade(store) -> int:
    return store.open_trade("NIFTY", "PAPER-x", "NIFTY23000CE", "CE", "T1", ENTRY, QTY, 23000.0, 23000.0, mode="PAPER")


# ---------------------------------------------------------------- engine level
def test_open_trade_is_still_managed_and_exited_when_halted():
    engine, store, risk = _make_engine(force_exit=dtime(0, 1))          # forced-exit time already passed
    tid = _open_paper_trade(store)
    risk.halt("Daily loss limit breached (test)")
    engine.run_once(allow_new_entries=False)
    assert store.get_open_trade("NIFTY") is None, "open trade must be force-closed even while halted"
    closed = [t for t in store.trades_today() if t.id == tid][0]
    assert closed.status == "CLOSED" and closed.exit_price == EXIT_LTP
    assert closed.pnl < 0        # a time exit at a loss, not a take-profit
    assert abs(closed.pnl - (EXIT_LTP - ENTRY) * QTY) < 1e-6
    assert abs(store.get_capital(CAPITAL) - (CAPITAL + (EXIT_LTP - ENTRY) * QTY)) < 1e-6
    print("PASS: halted -> open trade still force-exited, pnl + capital updated")


def test_open_trade_kept_when_halted_and_no_exit_condition():
    engine, store, risk = _make_engine(force_exit=dtime(23, 59), option_ltp=HEALTHY_LTP)   # not yet time to force-exit
    _open_paper_trade(store)
    engine.run_once(allow_new_entries=False)
    assert store.get_open_trade("NIFTY") is not None, "must not close a healthy trade just because halted"
    print("PASS: halted -> healthy open trade left alone (still monitored)")


def test_no_new_entries_and_pending_entry_dropped_when_halted():
    engine, store, risk = _make_engine(force_exit=dtime(23, 59))
    engine._consider_entry = MagicMock()
    engine._pending_entry = object()
    engine.run_once(allow_new_entries=False)
    engine._consider_entry.assert_not_called()
    assert engine._pending_entry is None
    print("PASS: halted -> no entry considered, pending pullback entry dropped")


def test_normal_operation_unchanged_when_not_halted():
    engine, store, risk = _make_engine(force_exit=dtime(23, 59))
    engine._consider_entry = MagicMock()
    engine.run_once()
    assert engine._consider_entry.call_count == 1
    print("PASS: not halted -> entries considered exactly as before")


# ---------------------------------------------------------------- main-loop helper
def _eng(name):
    e = MagicMock()
    e.cfg.name = name
    return e


def test_main_helper_halted_runs_only_instruments_with_open_trades_and_disables_entries():
    a, b = _eng("A"), _eng("B")
    store = MagicMock()
    store.get_open_trade.side_effect = lambda n: object() if n == "A" else None
    bot_main._run_engines_once([a, b], store, halted=True)
    a.run_once.assert_called_once_with(allow_new_entries=False)
    b.run_once.assert_not_called()
    print("PASS: main helper (halted) -> open-trade instrument managed with entries off, idle one skipped")


def test_main_helper_not_halted_runs_everything_with_entries_on():
    a, b = _eng("A"), _eng("B")
    store = MagicMock()
    store.get_open_trade.return_value = None
    bot_main._run_engines_once([a, b], store, halted=False)
    a.run_once.assert_called_once_with(allow_new_entries=True)
    b.run_once.assert_called_once_with(allow_new_entries=True)
    print("PASS: main helper (not halted) -> every instrument runs with entries on")


def test_main_helper_one_engine_crash_does_not_stop_the_others():
    a, b = _eng("A"), _eng("B")
    a.run_once.side_effect = RuntimeError("boom")
    store = MagicMock()
    store.get_open_trade.return_value = None
    bot_main._run_engines_once([a, b], store, halted=False)
    b.run_once.assert_called_once_with(allow_new_entries=True)
    print("PASS: main helper -> an exception in one instrument doesn't block the rest")


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
    print(f"\nALL {len(tests)} HALTED-MANAGE TESTS PASSED")
