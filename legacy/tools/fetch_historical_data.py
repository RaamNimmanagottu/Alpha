"""Fetch/refresh historical OHLC candles into Excel for every configured instrument.

Standalone from the trading loop -- runs regardless of market hours or the
weekend/holiday check, since this is just downloading data, not trading. Safe to run
any time; never places an order.

Run with: .venv\\Scripts\\python.exe tools\\fetch_historical_data.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from alpha.broker import AngelOneBroker
from alpha.config import AppConfig, Credentials, ROOT_DIR
from alpha.historical_data import update_historical_data
from alpha.logging_setup import setup_logging

logger = setup_logging("fetch_historical_data")


def main() -> int:
    config = AppConfig.load()
    credentials = Credentials.from_env()

    broker = AngelOneBroker(credentials)
    broker.connect()

    hist_cfg = config.historical_data
    for inst in config.instruments:
        excel_path = (
            ROOT_DIR / hist_cfg.storage_dir / f"{inst.name}_{hist_cfg.interval.lower()}.xlsx"
        )
        candles = update_historical_data(
            broker,
            inst.candle_token,
            excel_path,
            interval=hist_cfg.interval,
            interval_minutes=hist_cfg.interval_minutes,
            lookback_days=hist_cfg.lookback_days,
        )
        if candles.empty:
            logger.error("%s: no candles retrieved", inst.name)
            continue
        logger.info(
            "%s: %d candles stored, range %s -> %s, file: %s",
            inst.name, len(candles), candles["date"].min(), candles["date"].max(), excel_path,
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
