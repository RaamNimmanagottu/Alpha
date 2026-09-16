"""Load a historical candle Excel file, compute every indicator, and save it back out
sorted with the most recent candle first.

Run with (from the project root E:\\Alpha):
    .venv\\Scripts\\python.exe backtest\\prepare_data.py NIFTY
    .venv\\Scripts\\python.exe backtest\\prepare_data.py BANKNIFTY

Reads from ../data/historical/<INSTRUMENT>_five_minute.xlsx (produced by
tools/fetch_historical_data.py) and writes the enriched result to
backtest/data/<INSTRUMENT>_five_minute_with_indicators.xlsx -- a separate file, so
this never touches the raw cache the live trading bot's incremental fetch depends on.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# alpha/indicators.py holds the same indicator formulas the live bot uses -- imported
# here rather than re-implemented, so backtests and live trading always agree on how
# RSI/MACD/etc. are calculated.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd

from alpha import indicators as ind

SOURCE_DIR = PROJECT_ROOT / "data" / "historical"
OUTPUT_DIR = Path(__file__).resolve().parent / "data"


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Compute every indicator onto `df`.

    `df` must already be sorted ASCENDING by date -- rolling/ewm windows read
    backward in time, so computing them on descending-sorted data would silently
    produce wrong values (each "trailing" window would actually look into the
    future). Sort ascending, compute, and only reverse to descending afterward.
    """
    df = df.sort_values("date").reset_index(drop=True)
    close, high, low = df["close"], df["high"], df["low"]

    df["rsi"] = ind.rsi(close)
    df["stoch_k"] = ind.stochastic_k(high, low, close)
    df["cci20"] = ind.cci(high, low, close)
    df["adx"] = ind.adx(high, low, close)
    df["awesome_oscillator"] = ind.awesome_oscillator(high, low)
    df["momentum"] = ind.momentum(close)
    df["macd"], df["macd_signal"] = ind.macd(close)
    df["atr"] = ind.atr(high, low, close)
    df["bb_middle"], df["bb_upper"], df["bb_lower"] = ind.bollinger_bands(close)

    # Classic pivot points: one value per calendar day, computed from the PREVIOUS
    # completed day's H/L/C, then broadcast onto every intraday candle of the next day.
    daily = (
        df.set_index("date")
        .resample("1D")
        .agg({"high": "max", "low": "min", "close": "last"})
        .dropna()
    )
    prev_high, prev_low, prev_close = daily["high"].shift(1), daily["low"].shift(1), daily["close"].shift(1)
    daily["pivot"] = (prev_high + prev_low + prev_close) / 3
    daily["r1"] = 2 * daily["pivot"] - prev_low
    daily["s1"] = 2 * daily["pivot"] - prev_high
    daily["r2"] = daily["pivot"] + (prev_high - prev_low)
    daily["s2"] = daily["pivot"] - (prev_high - prev_low)

    df["_day"] = df["date"].dt.normalize()
    df = df.merge(daily[["pivot", "r1", "s1", "r2", "s2"]], left_on="_day", right_index=True, how="left")
    df = df.drop(columns="_day")

    return df.sort_values("date", ascending=False).reset_index(drop=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Add indicators to stored historical candles")
    parser.add_argument("instrument", nargs="?", default="NIFTY", help="e.g. NIFTY or BANKNIFTY")
    args = parser.parse_args()

    source_path = SOURCE_DIR / f"{args.instrument}_five_minute.xlsx"
    if not source_path.exists():
        print(f"No historical data found at {source_path}")
        print("Run tools/fetch_historical_data.py first.")
        return 1

    df = pd.read_excel(source_path)
    df["date"] = pd.to_datetime(df["date"])

    enriched = add_indicators(df)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / f"{args.instrument}_five_minute_with_indicators.xlsx"
    enriched.to_excel(out_path, index=False)

    print(f"{len(enriched)} rows, most recent first, written to {out_path}")
    print(enriched.head(5).to_string())
    return 0


if __name__ == "__main__":
    sys.exit(main())
