"""Smoke test for the trading engine using a fake broker -- no live API calls.

Verifies: entry on BUY signal, take-profit exit, stop-loss exit, time-based forced
exit, and that the risk manager halts new entries once the daily loss cap is hit.

Run with: .venv\\Scripts\\python.exe tests\\test_engine_smoke.py
"""
import os
import sys
import tempfile
from datetime import date, time as dtime
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

from alpha.config import AppConfig, HistoricalDataConfig, InstrumentConfig, RiskConfig
from alpha.ema_crossover_signal import Signal
from alpha.instrument_engine import InstrumentEngine
from alpha.risk import RiskManager
from alpha.state import TradeStore

SIGNAL_TIME = pd.Timestamp("2024-01-01 09:35:00")


class FakeBroker:
    def __init__(self):
        self.ltp = 100.0
        self.next_order_id = 1
        self.placed_orders = []
        # Default to a non-today expiry so ordinary tests aren't accidentally
        # tripping the "no new entries on expiry day" rule -- only
        # test_expiry_day_blocks_new_entries deliberately sets this to today.
        self.expiry_str = _future_expiry_str()

    def token_lookup(self, *a, **k):
        return "TOKEN1"

    def underlying_price(self, exchange, ticker, token):
        return self.ltp

    def option_contracts_atm(self, ticker, price):
        return pd.DataFrame([
            {"symbol": f"{ticker}CE", "token": "CE_TOKEN", "expiry": self.expiry_str, "strike": "1000000"},
            {"symbol": f"{ticker}PE", "token": "PE_TOKEN", "expiry": self.expiry_str, "strike": "1000000"},
        ])

    def get_candle_data(self, token, interval, from_dt, to_dt, exchange="NSE"):
        # get_signal is patched directly in every test below, so the actual candle
        # content here is irrelevant -- an empty frame keeps update_historical_data
        # a no-op without touching the network or any real Excel file.
        return pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume"])

    def place_market_order(self, symbol, token, txn_type, qty, exchange="NFO"):
        order_id = f"ORD{self.next_order_id}"
        self.next_order_id += 1
        self.placed_orders.append((symbol, txn_type, qty))
        return order_id

    def wait_for_order_result(self, order_id, timeout, poll):
        from alpha.broker import OrderResult
        return OrderResult(order_id=order_id, status="complete", price=self.ltp)


def _today_expiry_str():
    return date.today().strftime("%d%b%Y").upper()


def _future_expiry_str():
    from datetime import timedelta
    return (date.today() + timedelta(days=7)).strftime("%d%b%Y").upper()


def make_engine(broker, store, risk, cfg_overrides=None):
    cfg = InstrumentConfig(
        name="NIFTY",
        exchange_index_symbol="NIFTY",
        index_token="1",
        candle_token="1",
        lot_size=25,
        quantity_lots=1,
        buy_strike_offset=0,
        sell_strike_offset=0,
        take_profit_points=10,
        stop_loss_points=5,
        entry_start_time=dtime(0, 0),
        # Widened to 23:59 (not a "real" cutoff) so tests aren't flaky depending on
        # what time of day they happen to run -- only test_time_based_force_exit
        # deliberately overrides this to something early.
        entry_cutoff_time=dtime(23, 59),
        force_exit_time=dtime(23, 59),
        force_exit_time_expiry_day=dtime(23, 59),
    )
    if cfg_overrides:
        cfg = cfg_overrides(cfg)
    app_cfg = AppConfig(
        poll_interval_seconds=0,
        order_fill_timeout_seconds=1,
        order_fill_poll_seconds=0.1,
        # False: these tests exercise the real order-placement path (FakeBroker's
        # place_market_order/wait_for_order_result) -- paper_trading=True would
        # bypass that entirely in favor of the LTP-simulated fill path instead.
        # See test_paper_trading_mode for coverage of that path.
        paper_trading=False,
        risk=RiskConfig(daily_loss_limit=1000, max_trades_per_day=10, max_trades_per_instrument=10),
        market=None,
        historical_data=HistoricalDataConfig(
            interval="FIVE_MINUTE",
            interval_minutes=5,
            lookback_days=100,
            # Absolute path so ROOT_DIR / storage_dir resolves to this temp dir
            # instead of writing test artifacts into the real project's data/ folder.
            storage_dir=str(Path(tempfile.gettempdir()) / "alpha_test_historical"),
        ),
        instruments=[cfg],
        holiday_lists={},
    )
    return InstrumentEngine(cfg, app_cfg, broker, store, risk), app_cfg


def _temp_store():
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
    tmp.close()
    return TradeStore(db_path=Path(tmp.name)), tmp.name


def test_entry_and_take_profit():
    broker = FakeBroker()
    store, path = _temp_store()
    risk = RiskManager(RiskConfig(1000, 10, 10), store)
    engine, _ = make_engine(broker, store, risk)

    with patch("alpha.instrument_engine.get_signal", return_value=Signal("BUY", SIGNAL_TIME)):
        broker.ltp = 100.0
        engine.run_once()

    open_trade = store.get_open_trade("NIFTY")
    assert open_trade is not None, "expected an open trade after BUY signal"
    assert broker.placed_orders[-1][1] == "BUY"
    print("PASS: entry on BUY signal")

    broker.ltp = 100.0 * 1.15
    engine.run_once()
    assert store.get_open_trade("NIFTY") is None, "expected trade to be closed on take-profit"
    assert broker.placed_orders[-1][1] == "SELL"
    pnl = store.realized_pnl_today()
    assert pnl > 0, f"expected positive pnl, got {pnl}"
    print(f"PASS: take-profit exit, pnl={pnl}")
    os.unlink(path)


def test_stop_loss_and_risk_halt():
    broker = FakeBroker()
    store, path = _temp_store()
    risk_cfg = RiskConfig(daily_loss_limit=100, max_trades_per_day=10, max_trades_per_instrument=10)
    risk = RiskManager(risk_cfg, store)
    engine, _ = make_engine(broker, store, risk)

    with patch("alpha.instrument_engine.get_signal", return_value=Signal("BUY", SIGNAL_TIME)):
        broker.ltp = 100.0
        engine.run_once()
    assert store.get_open_trade("NIFTY") is not None

    broker.ltp = 100.0 * 0.94
    engine.run_once()
    assert store.get_open_trade("NIFTY") is None
    pnl = store.realized_pnl_today()
    assert pnl < 0, f"expected negative pnl, got {pnl}"
    print(f"PASS: stop-loss exit, pnl={pnl}")

    risk.refresh()
    allowed, reason = risk.can_open_new_trade("NIFTY")
    assert risk.is_halted, "expected daily loss limit to halt trading"
    assert not allowed
    print("PASS: risk manager halts on daily loss limit")
    os.unlink(path)


def test_time_based_force_exit():
    broker = FakeBroker()
    store, path = _temp_store()
    risk = RiskManager(RiskConfig(1000, 10, 10), store)

    def force_exit_now(cfg):
        return InstrumentConfig(**{**cfg.__dict__, "force_exit_time": dtime(0, 0),
                                    "force_exit_time_expiry_day": dtime(0, 0)})

    engine, _ = make_engine(broker, store, risk, cfg_overrides=force_exit_now)

    with patch("alpha.instrument_engine.get_signal", return_value=Signal("BUY", SIGNAL_TIME)):
        broker.ltp = 100.0
        engine.run_once()
    assert store.get_open_trade("NIFTY") is not None

    engine.run_once()
    assert store.get_open_trade("NIFTY") is None, "expected time-based force exit to close the trade"
    print("PASS: time-based force exit fires even with flat price")
    os.unlink(path)


def test_expiry_day_blocks_new_entries_but_still_manages_open_ones():
    broker = FakeBroker()
    store, path = _temp_store()
    risk = RiskManager(RiskConfig(1000, 10, 10), store)
    engine, _ = make_engine(broker, store, risk)

    # Not expiry today -- open a position normally first.
    with patch("alpha.instrument_engine.get_signal", return_value=Signal("BUY", SIGNAL_TIME)):
        broker.ltp = 100.0
        engine.run_once()
    assert store.get_open_trade("NIFTY") is not None, "expected entry with a non-expiry contract"

    # Now it becomes expiry day (e.g. the position rolled into today's expiry).
    # A held position must still be managed -- take-profit here -- never abandoned.
    broker.expiry_str = _today_expiry_str()
    broker.ltp = 100.0 * 1.15
    engine.run_once()
    assert store.get_open_trade("NIFTY") is None, "expected an existing position to still exit on expiry day"
    print("PASS: an open position is still managed (and can exit) on expiry day")

    # With no position open and it being expiry day, a fresh BUY signal must be ignored.
    broker.ltp = 100.0
    with patch("alpha.instrument_engine.get_signal", return_value=Signal("BUY", SIGNAL_TIME.replace(hour=10))):
        engine.run_once()
    assert store.get_open_trade("NIFTY") is None, "expected no new entry to be taken on expiry day"
    print("PASS: no new entries are taken on expiry day")
    os.unlink(path)


def test_paper_trading_mode_never_calls_real_broker_order_methods():
    broker = FakeBroker()
    store, path = _temp_store()
    risk = RiskManager(RiskConfig(1000, 10, 10), store)

    def paper_mode(cfg):
        return cfg  # InstrumentConfig unchanged; paper_trading lives on AppConfig

    engine, app_cfg = make_engine(broker, store, risk, cfg_overrides=paper_mode)
    # make_engine defaults to paper_trading=False; flip it for this test via the
    # frozen dataclass's replace-by-reconstruction, mirroring how AppConfig is built.
    from dataclasses import replace
    engine.app_cfg = replace(app_cfg, paper_trading=True)

    with patch("alpha.instrument_engine.get_signal", return_value=Signal("BUY", SIGNAL_TIME)):
        broker.ltp = 100.0
        engine.run_once()

    open_trade = store.get_open_trade("NIFTY")
    assert open_trade is not None, "expected a simulated entry in paper mode"
    assert open_trade.mode == "PAPER"
    assert open_trade.order_id.startswith("PAPER-")
    assert broker.placed_orders == [], "paper trading must never call place_market_order"
    print("PASS: paper trading simulates a fill without touching the real order-placement path")
    os.unlink(path)


if __name__ == "__main__":
    test_entry_and_take_profit()
    test_stop_loss_and_risk_halt()
    test_time_based_force_exit()
    test_expiry_day_blocks_new_entries_but_still_manages_open_ones()
    test_paper_trading_mode_never_calls_real_broker_order_methods()
    print("ALL SMOKE TESTS PASSED")
