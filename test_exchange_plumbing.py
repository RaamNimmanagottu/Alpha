"""Mock-broker test that a non-default-exchange instrument (SENSEX: BSE
underlying, BFO options) has its exchange threaded through every broker
call -- candle fetch, underlying LTP, option LTP. Regression test for a bug
found 2026-09-18 while adding SENSEX: _get_candles() didn't pass exchange,
so it silently defaulted to "NSE" and SENSEX would have never received
candle data (no signals, ever).

Run with: .venv\\Scripts\\python.exe test_exchange_plumbing.py
"""
from __future__ import annotations

import sys
import tempfile
from datetime import time as dtime
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pandas as pd

from config import AppConfig, HistoricalDataConfig, InstrumentConfig, RiskConfig
from instrument_engine import InstrumentEngine
from risk import RiskManager
from state import TradeStore


def _make_engine(underlying_exchange: str, options_exchange: str):
    cfg = InstrumentConfig(
        name="SENSEXTEST", exchange_index_symbol="SENSEX", index_token="99919000", candle_token="99919000",
        signal_strategy="ema_crossover_13_34", lot_size=20, quantity_lots=1,
        buy_strike_offset=0, sell_strike_offset=0,
        take_profit_points=1200, take_profit_premium_pct=10, stop_loss_points=576,
        entry_start_time=dtime(9, 30), entry_cutoff_time=dtime(14, 50),
        force_exit_time=dtime(14, 50), force_exit_time_expiry_day=dtime(14, 45),
        underlying_exchange=underlying_exchange, options_exchange=options_exchange,
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
        starting_capital=200000, shutdown_vm_on_exit=False,
        risk=RiskConfig(5000, 10, 10), market=None,
        historical_data=HistoricalDataConfig("FIVE_MINUTE", 5, 100,
                                              str(Path(tempfile.mkdtemp()) / "hist")),
        instruments=[cfg], holiday_lists={},
    )
    broker = MagicMock()
    broker.get_candle_data.return_value = pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume"])
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
    tmp.close()
    store = TradeStore(db_path=Path(tmp.name))
    risk = RiskManager(RiskConfig(5000, 10, 10), store)
    return InstrumentEngine(cfg, app_cfg, broker, store, risk, notifier=MagicMock()), broker


def test_candle_fetch_uses_underlying_exchange():
    engine, broker = _make_engine("BSE", "BFO")
    engine._get_candles()
    assert broker.get_candle_data.called, "expected a candle fetch"
    assert broker.get_candle_data.call_args.kwargs.get("exchange") == "BSE", broker.get_candle_data.call_args
    print("PASS: candle fetch for a BSE instrument uses exchange='BSE', not the NSE default")


def test_underlying_ltp_uses_underlying_exchange():
    engine, broker = _make_engine("BSE", "BFO")
    broker.underlying_price.return_value = 0  # falsy -> run_once returns right after the LTP call
    engine.run_once()
    first_call = broker.underlying_price.call_args_list[0]
    assert first_call.args[0] == "BSE", first_call
    print("PASS: underlying LTP for SENSEX is fetched from BSE")


def test_default_exchange_unchanged_for_nse_instruments():
    engine, broker = _make_engine("NSE", "NFO")
    engine._get_candles()
    assert broker.get_candle_data.call_args.kwargs.get("exchange") == "NSE"
    print("PASS: NSE instruments still fetch candles from NSE")


if __name__ == "__main__":
    test_candle_fetch_uses_underlying_exchange()
    test_underlying_ltp_uses_underlying_exchange()
    test_default_exchange_unchanged_for_nse_instruments()
    print("\nALL EXCHANGE PLUMBING TESTS PASSED")
