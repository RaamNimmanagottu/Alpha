"""Mock-broker tests for the "min_premium" strike-selection mode (see
instrument_engine.py's _select_min_premium_contract and RULES.md). No live
API calls -- broker is a MagicMock with canned LTP responses.

Run with: .venv\\Scripts\\python.exe test_min_premium_selection.py
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


def _make_candidates() -> pd.DataFrame:
    # NIFTY-like strikes around ATM=23300, in paise (x100), 50pt steps.
    strikes = [23100, 23150, 23200, 23250, 23300, 23350, 23400, 23450, 23500]
    rows = []
    for s in strikes:
        rows.append({"symbol": f"NIFTY{s}CE", "token": f"T{s}CE", "strike": str(s * 100), "expiry": "25SEP2026"})
        rows.append({"symbol": f"NIFTY{s}PE", "token": f"T{s}PE", "strike": str(s * 100), "expiry": "25SEP2026"})
    return pd.DataFrame(rows)


def _make_engine(min_premium_threshold: float, ltp_by_symbol: dict[str, float]):
    cfg = InstrumentConfig(
        name="NIFTY", exchange_index_symbol="NIFTY", index_token="1", candle_token="1",
        signal_strategy="ema_crossover", lot_size=65, quantity_lots=1,
        buy_strike_offset=0, sell_strike_offset=0,
        take_profit_points=100, take_profit_premium_pct=10, stop_loss_points=50,
        entry_start_time=dtime(9, 30), entry_cutoff_time=dtime(14, 50),
        force_exit_time=dtime(14, 50), force_exit_time_expiry_day=dtime(14, 45),
        min_premium_threshold=min_premium_threshold,
    )
    app_cfg = AppConfig(
        poll_interval_seconds=3, order_fill_timeout_seconds=10, order_fill_poll_seconds=1,
        paper_trading=True, strike_selection_mode="min_premium", target_delta=0.5,
        trailing_stop_enabled=False, trailing_stop_activation_points=50, trailing_stop_distance_points=30,
        signal_reversal_exit_enabled=False, iv_exit_enabled=False, iv_exit_drop_pct=20,
        iv_check_interval_seconds=30, momentum_exit_enabled=False, momentum_window_minutes=10,
        momentum_exit_points=60, pullback_entry_enabled=False, pullback_extended_threshold_points=100,
        starting_capital=200000, shutdown_vm_on_exit=False,
        risk=RiskConfig(5000, 10, 10), market=None,
        historical_data=HistoricalDataConfig("FIVE_MINUTE", 5, 100,
                                              str(Path(tempfile.gettempdir()) / "alpha_test_min_premium")),
        instruments=[cfg], holiday_lists={},
    )
    broker = MagicMock()
    broker.option_contracts_nearest_expiry.return_value = _make_candidates()
    broker.underlying_price.side_effect = lambda ex, symbol, token: ltp_by_symbol.get(symbol, 0.0)

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
    tmp.close()
    store = TradeStore(db_path=Path(tmp.name))
    risk = RiskManager(RiskConfig(5000, 10, 10), store)
    return InstrumentEngine(cfg, app_cfg, broker, store, risk, notifier=MagicMock())


def test_atm_already_clears_threshold():
    engine = _make_engine(120, {"NIFTY23300CE": 150.0})
    candidates = _make_candidates()
    ce = candidates[candidates["symbol"].str.contains("CE")]
    result = engine._select_min_premium_contract(ce, 23300.0, "CE")
    assert result["symbol"] == "NIFTY23300CE"
    print("PASS: ATM used when its own premium already clears the threshold")


def test_ce_walks_itm_to_lower_strikes():
    ltp_map = {"NIFTY23300CE": 80.0, "NIFTY23250CE": 95.0, "NIFTY23200CE": 130.0, "NIFTY23150CE": 180.0}
    engine = _make_engine(120, ltp_map)
    candidates = _make_candidates()
    ce = candidates[candidates["symbol"].str.contains("CE")]
    result = engine._select_min_premium_contract(ce, 23300.0, "CE")
    assert result["symbol"] == "NIFTY23200CE", result["symbol"]
    print("PASS: CE walks ITM to lower strikes, picks the closest one clearing the threshold")


def test_pe_walks_itm_to_higher_strikes():
    ltp_map = {"NIFTY23300PE": 80.0, "NIFTY23350PE": 95.0, "NIFTY23400PE": 140.0}
    engine = _make_engine(120, ltp_map)
    candidates = _make_candidates()
    pe = candidates[candidates["symbol"].str.contains("PE")]
    result = engine._select_min_premium_contract(pe, 23300.0, "PE")
    assert result["symbol"] == "NIFTY23400PE", result["symbol"]
    print("PASS: PE walks ITM to higher strikes, picks the closest one clearing the threshold")


def test_falls_back_to_atm_if_nothing_clears_threshold():
    ltp_map = {s: 10.0 for s in ["NIFTY23300CE", "NIFTY23250CE", "NIFTY23200CE", "NIFTY23150CE", "NIFTY23100CE"]}
    engine = _make_engine(120, ltp_map)
    candidates = _make_candidates()
    ce = candidates[candidates["symbol"].str.contains("CE")]
    result = engine._select_min_premium_contract(ce, 23300.0, "CE")
    assert result["symbol"] == "NIFTY23300CE", result["symbol"]
    print("PASS: falls back to ATM when nothing within the search depth clears the threshold")


def test_zero_threshold_disables_feature():
    engine = _make_engine(0, {"NIFTY23300CE": 5.0})
    candidates = _make_candidates()
    ce = candidates[candidates["symbol"].str.contains("CE")]
    result = engine._select_min_premium_contract(ce, 23300.0, "CE")
    assert result["symbol"] == "NIFTY23300CE", result["symbol"]
    print("PASS: min_premium_threshold=0 disables the feature (always ATM)")


if __name__ == "__main__":
    test_atm_already_clears_threshold()
    test_ce_walks_itm_to_lower_strikes()
    test_pe_walks_itm_to_higher_strikes()
    test_falls_back_to_atm_if_nothing_clears_threshold()
    test_zero_threshold_disables_feature()
    print("\nALL MIN_PREMIUM TESTS PASSED")
