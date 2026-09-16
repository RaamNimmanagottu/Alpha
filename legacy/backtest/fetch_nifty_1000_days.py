"""Fetch ~1000 days of NIFTY 50 five-minute historical candles from Angel One.

Requests are split into 100-day chunks (10 requests total) with a 5-second pause
between each to stay under the broker's rate limit. If a chunk request fails (rate
limited or otherwise), it waits 3 seconds and retries the same chunk, up to
MAX_RETRIES_PER_CHUNK times before giving up on that chunk and moving on.

This is separate from data/historical/NIFTY_five_minute.xlsx (the live bot's rolling
100-day cache maintained by alpha/historical_data.py) -- this script is purely for
building a much deeper dataset for backtesting and never touches that file.

Run with (from the project root E:\\Alpha):
    .venv\\Scripts\\python.exe backtest\\fetch_nifty_1000_days.py

Writes backtest/data/NIFTY_five_minute_1000days.xlsx.
"""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BACKTEST_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(BACKTEST_DIR))

from alpha.config import AppConfig, Credentials
from alpha.broker import AngelOneBroker
from alpha.logging_setup import setup_logging
from chunked_history import fetch_chunked_history

logger = setup_logging("fetch_nifty_1000_days")

TOTAL_DAYS = 1000
CHUNK_DAYS = 100

OUTPUT_DIR = BACKTEST_DIR / "data"
OUTPUT_FILE = OUTPUT_DIR / "NIFTY_five_minute_1000days.xlsx"


def main() -> int:
    config = AppConfig.load()
    nifty_cfg = next((i for i in config.instruments if i.name == "NIFTY"), None)
    if nifty_cfg is None:
        logger.error("No NIFTY instrument configured in config.yaml")
        return 1

    credentials = Credentials.from_env()
    broker = AngelOneBroker(credentials)
    broker.connect()

    combined = fetch_chunked_history(broker, nifty_cfg.candle_token, config.historical_data.interval, TOTAL_DAYS, CHUNK_DAYS)
    if combined.empty:
        logger.error("No data retrieved at all.")
        return 1

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    combined.to_excel(OUTPUT_FILE, index=False)

    logger.info(
        "%d total candles, range %s -> %s, written to %s",
        len(combined), combined["date"].min(), combined["date"].max(), OUTPUT_FILE,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
