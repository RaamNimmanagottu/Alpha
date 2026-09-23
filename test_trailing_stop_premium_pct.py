"""Tests for the premium-percent step-ladder trailing stop (trailing_stop_mode="premium_pct_step",
added 2026-09-22, user-requested: "5% of premium, ratcheting up every 5%").

Mechanics under test: step = trailing_stop_step_pct% of the ENTRY premium (fixed). Every time the
PEAK premium crosses another whole step, the stop locks the PREVIOUS step (one behind the new peak,
not the just-crossed level). The lock level is driven by the PEAK, not the current price -- a dip
within a step must not move the lock; only a dip back through the locked level (after a HIGHER step
has already been reached) should exit. Identical for CE and PE. Purely additive to the existing
index-based static stop-loss (that floor is untouched by this feature).

Run with: .venv\\Scripts\\python.exe test_trailing_stop_premium_pct.py   (no live API calls; broker is a MagicMock)
"""
from __future__ import annotations

import sys
import tempfile
from datetime import time as dtime
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pandas as pd

import instrument_engine
from config import AppConfig, HistoricalDataConfig, InstrumentConfig, RiskConfig
from instrument_engine import InstrumentEngine
from risk import RiskManager
from state import TradeStore

CAPITAL = 200000
UNDERLYING = 23000.0     # kept constant across every cycle -- isolates the premium-side logic from
                          # the index-based static stop-loss/take-profit (never triggers on its own)
ENTRY = 500.0
QTY = 65
STEP_PCT = 5             # -> step = 25


def _make_engine(mode="premium_pct_step", step_pct=STEP_PCT, enabled=True):
    cfg = InstrumentConfig(
        name="NIFTY", exchange_index_symbol="NIFTY", index_token="1", candle_token="1",
        signal_strategy="ema_crossover", lot_size=QTY, quantity_lots=1,
        buy_strike_offset=0, sell_strike_offset=0,
        take_profit_points=100000, take_profit_premium_pct=100000, stop_loss_points=100000,
        # ^ index TP/SL and the premium%-TP are all set effectively unreachable, so only the
        # trailing stop under test can end a trade in these tests.
        entry_start_time=dtime(9, 30), entry_cutoff_time=dtime(14, 50),
        force_exit_time=dtime(23, 59), force_exit_time_expiry_day=dtime(23, 59),
        min_premium_threshold=0,
    )
    app_cfg = AppConfig(
        poll_interval_seconds=3, order_fill_timeout_seconds=10, order_fill_poll_seconds=1,
        paper_trading=True, strike_selection_mode="atm", target_delta=0.5,
        trailing_stop_enabled=enabled, trailing_stop_activation_points=50, trailing_stop_distance_points=30,
        trailing_stop_mode=mode, trailing_stop_step_pct=step_pct,
        signal_reversal_exit_enabled=False, iv_exit_enabled=False, iv_exit_drop_pct=20,
        iv_check_interval_seconds=30, momentum_exit_enabled=False, momentum_window_minutes=10,
        momentum_exit_points=60, pullback_entry_enabled=False, pullback_extended_threshold_points=100,
        extreme_point_rule_enabled=False, extreme_point_rule_max_wait_bars=3,
        starting_capital=CAPITAL, shutdown_vm_on_exit=False,
        risk=RiskConfig(5000, 10, 10), market=None,
        historical_data=HistoricalDataConfig("FIVE_MINUTE", 5, 100,
                                              str(Path(tempfile.gettempdir()) / "alpha_test_trail_pct")),
        instruments=[cfg], holiday_lists={},
    )
    price = {"option": ENTRY}
    broker = MagicMock()
    atm = pd.DataFrame([{"symbol": "NIFTY23000CE", "token": "T1", "strike": "2300000", "expiry": "25SEP2099"}])
    broker.option_contracts_atm.return_value = atm
    broker.underlying_price.side_effect = lambda ex, symbol, token: UNDERLYING if symbol == "NIFTY" else price["option"]

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
    tmp.close()
    store = TradeStore(db_path=Path(tmp.name))
    store.get_capital(CAPITAL)
    risk = RiskManager(RiskConfig(5000, 10, 10), store)
    engine = InstrumentEngine(cfg, app_cfg, broker, store, risk, notifier=MagicMock())
    engine._get_candles = MagicMock(return_value=pd.DataFrame())
    engine._get_signal = MagicMock(return_value=None)
    engine._maybe_fetch_iv = MagicMock(return_value=None)
    return engine, store, price


def _open(store, trade_type="CE", symbol="NIFTY23000CE", entry=ENTRY):
    return store.open_trade("NIFTY", "PAPER-x", symbol, trade_type, "T1", entry, QTY, UNDERLYING, 23000.0, mode="PAPER")


def _tick(engine, price, option_ltp):
    price["option"] = option_ltp
    engine.run_once(allow_new_entries=False)


def test_no_exit_below_first_step():
    engine, store, price = _make_engine()
    _open(store)
    for p in (505, 510, 515, 520, 524.99):
        _tick(engine, price, p)
        assert store.get_open_trade("NIFTY") is not None, f"must not touch the trade below the first 5% step (p={p})"
    print("PASS: below the first step (peak<525), never active -- trade held throughout")


def test_first_step_locks_at_entry_breakeven():
    engine, store, price = _make_engine()
    _open(store)
    _tick(engine, price, 525.0)          # steps_crossed=1 -> lock = entry (500)
    assert store.get_open_trade("NIFTY") is not None, "at the lock level itself (525>500), must not exit"
    _tick(engine, price, 500.0)          # dip to exactly the locked level
    assert store.get_open_trade("NIFTY") is None, "a dip back to the locked level (500) must exit"
    t = store.trades_today()[-1]
    assert t.exit_price == 500.0 and abs(t.pnl - 0.0) < 1e-6
    print("PASS: first step (peak 525) locks the stop at entry (500, breakeven)")


def test_second_step_locks_previous_not_current():
    """User's own worked example: entry=500, step=25. Peak touching 550 locks the stop at 525."""
    engine, store, price = _make_engine()
    _open(store)
    _tick(engine, price, 550.0)          # steps_crossed=2 -> lock = 500 + 1*25 = 525
    assert store.get_open_trade("NIFTY") is not None
    _tick(engine, price, 530.0)          # above the locked level (525) -- must NOT exit yet
    assert store.get_open_trade("NIFTY") is not None, "530 > locked 525, must still be held"
    _tick(engine, price, 525.0)          # back down to the locked level
    assert store.get_open_trade("NIFTY") is None
    t = store.trades_today()[-1]
    assert t.exit_price == 525.0 and abs(t.pnl - (525 - 500) * QTY) < 1e-6
    print("PASS: peak 550 locks stop at 525 (previous step, not the just-crossed 550)")


def test_lock_uses_peak_not_current_price_after_a_pullback():
    """The critical ratchet property: once a higher step has been reached, a pullback that stays
    ABOVE the locked level must not re-lower the lock, and the lock must reflect the PEAK ever
    seen, not whatever the current premium happens to be on this cycle."""
    engine, store, price = _make_engine()
    _open(store)
    _tick(engine, price, 575.0)          # peak=575 -> steps_crossed=3 -> lock = 500 + 2*25 = 550
    assert store.get_open_trade("NIFTY") is not None
    _tick(engine, price, 530.0)          # big pullback, but STILL above the locked level (550)? No:
    # 530 < 550 -- this pullback is BELOW the level locked in when the peak hit 575, so it must exit.
    # (If the code wrongly used the CURRENT price 530 instead of the peak 575 to size the ladder,
    # it would compute steps_crossed=(530-500)//25=1 -> lock=500, and 530<=500 would be False --
    # i.e. it would wrongly stay open. This test fails under that bug and passes under the correct,
    # peak-driven implementation.)
    assert store.get_open_trade("NIFTY") is None, "peak 575 already locked the stop at 550; 530 must trigger it"
    t = store.trades_today()[-1]
    assert t.exit_price == 530.0 and abs(t.pnl - (530 - 500) * QTY) < 1e-6
    print("PASS: lock level is driven by the PEAK (575->550), not the current price on the exit tick")


def test_holds_within_a_step_range_without_unlocking():
    engine, store, price = _make_engine()
    _open(store)
    _tick(engine, price, 575.0)          # peak=575 -> lock=550
    _tick(engine, price, 560.0)          # dips, but stays above the lock (550) -- must hold
    assert store.get_open_trade("NIFTY") is not None
    _tick(engine, price, 590.0)          # recovers, new peak -- still steps_crossed=3 (590<600), lock stays 550
    assert store.get_open_trade("NIFTY") is not None
    _tick(engine, price, 552.0)          # still above 550 -- must hold
    assert store.get_open_trade("NIFTY") is not None
    print("PASS: fluctuating within a step range (between locked level and next step) never exits")


def test_works_identically_for_pe():
    """This bot only ever BUYS options (CE or PE); pnl = (exit-entry)*qty regardless of type, so a
    premium rise is favorable for PE exactly like CE -- the ladder must behave identically."""
    engine, store, price = _make_engine()
    _open(store, trade_type="PE", symbol="NIFTY23000PE")
    _tick(engine, price, 550.0)          # peak=550 -> lock=525
    assert store.get_open_trade("NIFTY") is not None
    _tick(engine, price, 525.0)
    assert store.get_open_trade("NIFTY") is None
    t = store.trades_today()[-1]
    assert t.trade_type == "PE" and t.exit_price == 525.0 and abs(t.pnl - (525 - 500) * QTY) < 1e-6
    print("PASS: PE trades ratchet identically to CE (premium-based, direction-agnostic)")


def test_disabled_never_fires():
    engine, store, price = _make_engine(enabled=False)
    _open(store)
    for p in (525, 550, 575, 600, 530, 500, 1):
        _tick(engine, price, p)
    assert store.get_open_trade("NIFTY") is not None, "trailing_stop_enabled=False must never touch the trade"
    print("PASS: trailing_stop_enabled=False -> premium ladder never active, no matter the price path")


def test_points_mode_unaffected_by_premium_logic():
    """Regression: with trailing_stop_mode='points', the new premium block must be a complete
    no-op (the original points-based trailing stop is what's under test elsewhere, in
    test_halted_manage_open.py's fixtures) -- a large premium swing must not exit anything."""
    engine, store, price = _make_engine(mode="points")
    _open(store)
    for p in (525, 600, 700, 501):       # would have triggered several premium-mode locks/exits
        _tick(engine, price, p)
    assert store.get_open_trade("NIFTY") is not None, "mode='points' must ignore the premium ladder entirely"
    print("PASS: trailing_stop_mode='points' -> premium-based block never engages")


def test_reason_is_trailing_stop_loss_premium():
    engine, store, price = _make_engine()
    _open(store)
    _tick(engine, price, 550.0)
    with patch.object(instrument_engine, "logger") as mock_logger:
        _tick(engine, price, 525.0)
    exit_calls = [c for c in mock_logger.info.call_args_list if "exiting" in c.args[0]]
    assert len(exit_calls) == 1, exit_calls
    assert exit_calls[0].args[3] == "trailing_stop_loss_premium", exit_calls[0].args
    print("PASS: the logged exit reason is exactly 'trailing_stop_loss_premium'")


def test_never_removes_the_index_based_static_stop_loss():
    """The premium ladder is additive: an index-based stop-loss hit must still fire on its own,
    completely independent of the premium mode/ladder state."""
    cfg = InstrumentConfig(
        name="NIFTY", exchange_index_symbol="NIFTY", index_token="1", candle_token="1",
        signal_strategy="ema_crossover", lot_size=QTY, quantity_lots=1,
        buy_strike_offset=0, sell_strike_offset=0,
        take_profit_points=100000, take_profit_premium_pct=100000, stop_loss_points=50,  # a REAL, reachable SL
        entry_start_time=dtime(9, 30), entry_cutoff_time=dtime(14, 50),
        force_exit_time=dtime(23, 59), force_exit_time_expiry_day=dtime(23, 59), min_premium_threshold=0,
    )
    app_cfg = AppConfig(
        poll_interval_seconds=3, order_fill_timeout_seconds=10, order_fill_poll_seconds=1,
        paper_trading=True, strike_selection_mode="atm", target_delta=0.5,
        trailing_stop_enabled=True, trailing_stop_activation_points=50, trailing_stop_distance_points=30,
        trailing_stop_mode="premium_pct_step", trailing_stop_step_pct=STEP_PCT,
        signal_reversal_exit_enabled=False, iv_exit_enabled=False, iv_exit_drop_pct=20,
        iv_check_interval_seconds=30, momentum_exit_enabled=False, momentum_window_minutes=10,
        momentum_exit_points=60, pullback_entry_enabled=False, pullback_extended_threshold_points=100,
        extreme_point_rule_enabled=False, extreme_point_rule_max_wait_bars=3,
        starting_capital=CAPITAL, shutdown_vm_on_exit=False,
        risk=RiskConfig(5000, 10, 10), market=None,
        historical_data=HistoricalDataConfig("FIVE_MINUTE", 5, 100,
                                              str(Path(tempfile.gettempdir()) / "alpha_test_trail_pct2")),
        instruments=[cfg], holiday_lists={},
    )
    underlying = {"v": 23000.0}
    broker = MagicMock()
    atm = pd.DataFrame([{"symbol": "NIFTY23000CE", "token": "T1", "strike": "2300000", "expiry": "25SEP2099"}])
    broker.option_contracts_atm.return_value = atm
    broker.underlying_price.side_effect = lambda ex, symbol, token: underlying["v"] if symbol == "NIFTY" else 501.0
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
    tmp.close()
    store = TradeStore(db_path=Path(tmp.name))
    store.get_capital(CAPITAL)
    risk = RiskManager(RiskConfig(5000, 10, 10), store)
    engine = InstrumentEngine(cfg, app_cfg, broker, store, risk, notifier=MagicMock())
    engine._get_candles = MagicMock(return_value=pd.DataFrame())
    engine._get_signal = MagicMock(return_value=None)
    engine._maybe_fetch_iv = MagicMock(return_value=None)
    _open(store)                          # entry_underlying=23000, static SL=22950 (CE)
    underlying["v"] = 22940.0             # index has fallen through the static SL; premium never moved (501, below even the first 5% step)
    engine.run_once(allow_new_entries=False)
    assert store.get_open_trade("NIFTY") is None, "the index-based static stop-loss must still fire on its own"
    t = store.trades_today()[-1]
    assert t.exit_price == 501.0
    print("PASS: index-based static stop-loss still fires independently (premium ladder never activated here)")


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
    print(f"\nALL {len(tests)} PREMIUM-PCT-STEP TRAILING STOP TESTS PASSED")
