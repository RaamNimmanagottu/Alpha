"""Shared chunked historical-candle fetcher, used by fetch_nifty_1000_days.py and
fetch_india_vix_1000_days.py. Splits a long lookback into CHUNK_DAYS-sized requests
(Angel One's getCandleData has an undocumented per-request range limit that 100 days
fits within for FIVE_MINUTE data -- confirmed empirically), pacing CHUNK_GAP_SECONDS
between requests and retrying a failed chunk after RATE_LIMIT_WAIT_SECONDS.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta

import pandas as pd

from alpha.broker import AngelOneBroker, BrokerError

CHUNK_GAP_SECONDS = 5
RATE_LIMIT_WAIT_SECONDS = 3
MAX_RETRIES_PER_CHUNK = 10

logger = logging.getLogger("backtest.chunked_history")


def fetch_chunk_with_retry(
    broker: AngelOneBroker, token: str, interval: str, from_dt: datetime, to_dt: datetime
) -> pd.DataFrame:
    attempt = 0
    while True:
        attempt += 1
        try:
            return broker.get_candle_data(token, interval, from_dt, to_dt)
        except BrokerError as exc:
            if attempt >= MAX_RETRIES_PER_CHUNK:
                logger.error(
                    "Chunk %s -> %s failed after %d attempts, giving up on this chunk: %s",
                    from_dt, to_dt, attempt, exc,
                )
                return pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume"])
            logger.warning(
                "Chunk %s -> %s failed (attempt %d/%d) -- possible rate limit, "
                "waiting %ds and retrying: %s",
                from_dt, to_dt, attempt, MAX_RETRIES_PER_CHUNK, RATE_LIMIT_WAIT_SECONDS, exc,
            )
            time.sleep(RATE_LIMIT_WAIT_SECONDS)


def fetch_chunked_history(
    broker: AngelOneBroker, token: str, interval: str, total_days: int, chunk_days: int
) -> pd.DataFrame:
    now = datetime.now()
    num_chunks = total_days // chunk_days
    all_chunks: list[pd.DataFrame] = []

    for i in range(num_chunks):
        # i=0 is the most recent chunk, i=num_chunks-1 is the oldest -- final
        # dataframe is sorted chronologically regardless of fetch order.
        chunk_to = now - timedelta(days=i * chunk_days)
        chunk_from = now - timedelta(days=(i + 1) * chunk_days)

        logger.info("Fetching chunk %d/%d: %s -> %s", i + 1, num_chunks, chunk_from, chunk_to)
        df = fetch_chunk_with_retry(broker, token, interval, chunk_from, chunk_to)
        logger.info("Chunk %d/%d: %d candles", i + 1, num_chunks, len(df))
        if not df.empty:
            all_chunks.append(df)

        if i < num_chunks - 1:
            time.sleep(CHUNK_GAP_SECONDS)

    if not all_chunks:
        return pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume"])

    combined = pd.concat(all_chunks, ignore_index=True)
    return (
        combined.drop_duplicates(subset="date", keep="last")
        .sort_values("date")
        .reset_index(drop=True)
    )
