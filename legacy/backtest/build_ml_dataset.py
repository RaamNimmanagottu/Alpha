"""Add next-candle open/close as output/target columns to the enriched candle data.

Input features: OHLC (open, high, low, close, volume) + every indicator column
already in the source file (EMA/SMA/MACD/ADX/Supertrend/RSI/Stochastic/CCI/
Williams %R/Bollinger/ATR/Keltner/Awesome Oscillator/Momentum).
Output/target features: next_open, next_close -- the immediately following candle's
open and close, i.e. what a model would be trained to predict from the current row's
input features.

Reads backtest/data/NIFTY_five_minute_1000days_signals.xlsx (the "Candles" sheet --
OHLC + indicators only, after signal/position/profit_loss were removed) and writes
backtest/data/NIFTY_five_minute_1000days_features.xlsx. backtest-only; nothing under
alpha/ or main.py is touched.

Run with (from the project root E:\\Alpha):
    .venv\\Scripts\\python.exe backtest\\build_ml_dataset.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

SOURCE_FILE = Path(__file__).resolve().parent / "data" / "NIFTY_five_minute_1000days_signals.xlsx"
OUTPUT_FILE = Path(__file__).resolve().parent / "data" / "NIFTY_five_minute_1000days_features.xlsx"


def add_next_candle_targets(df: pd.DataFrame) -> pd.DataFrame:
    """`df` must be sorted ASCENDING by date: shift(-1) pulls each row's value from
    the chronologically next row, so this would silently give the wrong candle as
    "next" if run on descending-sorted data."""
    df = df.sort_values("date").reset_index(drop=True)
    df["next_open"] = df["open"].shift(-1)
    df["next_close"] = df["close"].shift(-1)
    return df


def main() -> int:
    if not SOURCE_FILE.exists():
        print(f"No data found at {SOURCE_FILE}")
        print("Run backtest/backtest_1000days.py first.")
        return 1

    df = pd.read_excel(SOURCE_FILE, sheet_name="Candles")
    df["date"] = pd.to_datetime(df["date"])

    df = add_next_candle_targets(df)

    output_cols = ["next_open", "next_close"]
    input_cols = [c for c in df.columns if c not in ("date", *output_cols)]
    print(f"Input features ({len(input_cols)}): {input_cols}")
    print(f"Output/target features: {output_cols}")
    print(f"Rows: {len(df)} -- the most recent row has NaN targets "
          f"(no future candle exists yet to supply next_open/next_close)")

    df = df.sort_values("date", ascending=False).reset_index(drop=True)
    df.to_excel(OUTPUT_FILE, index=False)
    print(f"Written to {OUTPUT_FILE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
