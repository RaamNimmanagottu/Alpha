from __future__ import annotations

import logging
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

logger = logging.getLogger("alpha.historical")

CANDLE_COLUMNS = ["date", "open", "high", "low", "close", "volume"]


class HistoricalDataStore:
    """Excel-backed cache of OHLC candles for one instrument.

    Reading/writing the whole file on every update (rather than the row-by-row Excel
    appends the old bot did) is simple and safe at this data volume: ~75 five-minute
    candles/day * 100 days is a few thousand rows, well within what pandas/openpyxl
    round-trips quickly.
    """

    def __init__(self, excel_path: Path):
        self.excel_path = excel_path
        self.excel_path.parent.mkdir(parents=True, exist_ok=True)

    def load(self) -> pd.DataFrame:
        if not self.excel_path.exists():
            return pd.DataFrame(columns=CANDLE_COLUMNS)
        df = pd.read_excel(self.excel_path)
        df["date"] = pd.to_datetime(df["date"])
        return df

    def save(self, df: pd.DataFrame) -> None:
        df.to_excel(self.excel_path, index=False)

    def last_timestamp(self) -> datetime | None:
        df = self.load()
        if df.empty:
            return None
        return df["date"].max().to_pydatetime()


def update_historical_data(
    broker,
    candle_token: str,
    excel_path: Path,
    interval: str = "FIVE_MINUTE",
    interval_minutes: int = 5,
    lookback_days: int = 100,
    exchange: str = "NSE",
) -> pd.DataFrame:
    """Incrementally refresh the local candle cache and return the full history.

    First call for an instrument (no Excel file yet): fetches `lookback_days` of
    history in one request. Every later call fetches only from the last stored
    candle's timestamp onward. A fetch is skipped entirely if less than one full
    candle interval has elapsed since the last stored candle -- there is no point
    asking the broker for a candle that can't exist yet, and this keeps the bot from
    hammering the historical-data endpoint on every 3-second poll cycle.
    """
    store = HistoricalDataStore(excel_path)
    existing = store.load()
    now = datetime.now()

    last_ts = store.last_timestamp()
    if last_ts is None:
        from_dt = now - timedelta(days=lookback_days)
    else:
        if now - last_ts < timedelta(minutes=interval_minutes):
            return existing
        from_dt = last_ts + timedelta(minutes=1)

    new_df = broker.get_candle_data(candle_token, interval, from_dt, now, exchange=exchange)
    if new_df.empty:
        return existing

    combined = new_df if existing.empty else pd.concat([existing, new_df], ignore_index=True)
    combined = (
        combined.drop_duplicates(subset="date", keep="last")
        .sort_values("date")
        .reset_index(drop=True)
    )
    store.save(combined)
    logger.info(
        "%s: +%d new candle(s), %d total stored", excel_path.stem, len(new_df), len(combined)
    )
    return combined
