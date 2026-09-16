"""Fetch ~1000 days of India VIX five-minute historical data from Angel One.

India VIX is NSE's own market-implied-volatility index, derived from real NIFTY
option prices -- a much better implied-volatility stand-in for options pricing than
the realized volatility this project used before, since it's the market's actual
forward-looking IV expectation rather than our own retrospective estimate from spot
price history. Token 99926017, confirmed empirically the same way the special NIFTY
(99926000) / BANKNIFTY (99926009) index tokens were: the historical-data token
differs from any LTP-quote token for the same underlying.

Same chunking approach as fetch_nifty_1000_days.py (see chunked_history.py): 100-day
chunks, 5s pacing between requests, retries a failed chunk after 3s.

Run with (from the project root E:\\Alpha):
    .venv\\Scripts\\python.exe backtest\\fetch_india_vix_1000_days.py

Writes backtest/data/INDIAVIX_five_minute_1000days.xlsx.
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

logger = setup_logging("fetch_india_vix_1000_days")

INDIA_VIX_TOKEN = "99926017"
TOTAL_DAYS = 1000
CHUNK_DAYS = 100

OUTPUT_DIR = BACKTEST_DIR / "data"
OUTPUT_FILE = OUTPUT_DIR / "INDIAVIX_five_minute_1000days.xlsx"


def main() -> int:
    config = AppConfig.load()
    credentials = Credentials.from_env()
    broker = AngelOneBroker(credentials)
    broker.connect()

    combined = fetch_chunked_history(
        broker, INDIA_VIX_TOKEN, config.historical_data.interval, TOTAL_DAYS, CHUNK_DAYS
    )
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
