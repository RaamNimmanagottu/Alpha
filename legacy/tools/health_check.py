"""End-to-end health check against the REAL broker -- no orders are ever placed.

Exercises every component the live bot depends on and reports pass/fail for each:
broker login, instrument master download, index token lookup, live LTP fetch, ATM
option contract resolution, the EMA crossover signal, the SQLite trade store, and
the risk manager. Safe to run any day, market open or closed -- it never calls
place_market_order.

Run with: .venv\\Scripts\\python.exe tools\\health_check.py
"""
from __future__ import annotations

import sys
import tempfile
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

results: list[tuple[str, bool, str]] = []


def check(name):
    def decorator(fn):
        def wrapper(*args, **kwargs):
            try:
                detail = fn(*args, **kwargs)
                results.append((name, True, detail or "ok"))
                print(f"[PASS] {name}: {detail or 'ok'}")
                return True, fn
            except Exception as exc:
                results.append((name, False, f"{type(exc).__name__}: {exc}"))
                print(f"[FAIL] {name}: {type(exc).__name__}: {exc}")
                traceback.print_exc(limit=2)
                return False, None
        return wrapper
    return decorator


def main() -> int:
    from alpha.config import AppConfig, Credentials

    @check("load config.yaml")
    def _load_config():
        nonlocal_config[0] = AppConfig.load()
        return f"{len(nonlocal_config[0].instruments)} instruments configured"
    nonlocal_config = [None]
    ok, _ = _load_config()
    if not ok:
        return _summary()
    config = nonlocal_config[0]

    @check("load .env credentials")
    def _load_creds():
        nonlocal_creds[0] = Credentials.from_env()
        return "loaded (values not shown)"
    nonlocal_creds = [None]
    ok, _ = _load_creds()
    if not ok:
        return _summary()
    credentials = nonlocal_creds[0]

    from alpha.broker import AngelOneBroker

    broker = AngelOneBroker(credentials)

    @check("broker login + instrument master download")
    def _connect():
        broker.connect()
        return f"{len(broker.instrument_list)} instruments loaded"
    connected, _ = _connect()

    if connected:
        for inst in config.instruments:
            symbol = inst.exchange_index_symbol

            @check(f"token_lookup({symbol})")
            def _lookup(symbol=symbol):
                token = broker.token_lookup(symbol)
                if not token:
                    raise ValueError("no token resolved")
                return f"token={token}"
            token_ok, _ = _lookup()

            @check(f"underlying_price({symbol})")
            def _price(symbol=symbol):
                token = broker.token_lookup(symbol)
                price = broker.underlying_price("NSE", symbol, token)
                return f"ltp={price} (0 is expected/normal outside market hours)"
            _price()

            @check(f"option_contracts_atm({symbol})")
            def _atm(symbol=symbol):
                # 0 ltp (outside market hours) still exercises the instrument-master
                # filtering/expiry logic even though the strike picked won't be meaningful.
                token = broker.token_lookup(symbol)
                price = broker.underlying_price("NSE", symbol, token) or 20000
                df = broker.option_contracts_atm(symbol, price)
                if df.empty:
                    raise ValueError("no ATM contracts resolved")
                return f"{len(df)} contracts, expiry={df['expiry'].iloc[0]}"
            _atm()

    if connected:
        for inst in config.instruments:
            @check(f"historical data + EMA crossover signal ({inst.name})")
            def _hist_signal(inst=inst):
                from alpha.ema_crossover_signal import get_signal
                from alpha.historical_data import update_historical_data

                excel_path = (
                    Path(__file__).resolve().parent.parent
                    / config.historical_data.storage_dir
                    / f"{inst.name}_{config.historical_data.interval.lower()}.xlsx"
                )
                candles = update_historical_data(
                    broker, inst.candle_token, excel_path,
                    interval=config.historical_data.interval,
                    interval_minutes=config.historical_data.interval_minutes,
                    lookback_days=config.historical_data.lookback_days,
                )
                if candles.empty:
                    raise ValueError("no historical candles returned")
                sig = get_signal(inst.exchange_index_symbol, candles)
                return f"{len(candles)} candles, direction={sig.direction}"
            _hist_signal()

    @check("SQLite trade store (open/close a scratch trade)")
    def _store():
        from alpha.state import TradeStore
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
        tmp.close()
        store = TradeStore(db_path=Path(tmp.name))
        trade_id = store.open_trade(
            "HEALTHCHECK", "TEST1", "TESTSYM", "CE", "TOK1",
            entry_price=100.0, quantity=25, entry_underlying_price=20000.0,
            strike=20000.0, mode="PAPER",
        )
        store.close_trade(trade_id, 110.0)
        pnl = store.realized_pnl_today()
        Path(tmp.name).unlink()
        return f"round-tripped a trade, pnl={pnl}"
    _store()

    @check("risk manager")
    def _risk():
        from alpha.risk import RiskManager
        from alpha.state import TradeStore
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
        tmp.close()
        store = TradeStore(db_path=Path(tmp.name))
        risk = RiskManager(config.risk, store)
        allowed, reason = risk.can_open_new_trade("NIFTY")
        Path(tmp.name).unlink()
        if not allowed:
            raise ValueError(f"unexpectedly blocked: {reason}")
        return "allows a fresh trade as expected"
    _risk()

    @check("holiday calendar for current year")
    def _holidays():
        from datetime import date
        from alpha.market_calendar import non_trading_reason
        holidays = config.holidays_for_year(date.today().year)
        if not holidays:
            raise ValueError(f"no holiday_list_{date.today().year} block in config.yaml")
        reason = non_trading_reason(holidays)
        return f"{len(holidays)} holidays loaded; today -> {reason or 'trading day'}"
    _holidays()

    return _summary()


def _summary() -> int:
    print("\n" + "=" * 60)
    passed = sum(1 for _, ok, _ in results if ok)
    print(f"{passed}/{len(results)} checks passed")
    failed = [n for n, ok, _ in results if not ok]
    if failed:
        print("FAILED:", ", ".join(failed))
        return 1
    print("ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
