"""Diagnose what separates winning EMA crossovers from false ones (whipsaws) in the
already-run EMA Crossover (9/21) backtest, using the actual trade outcomes rather
than guessing at a filter threshold.

For each trade, looks at the crossover candle itself (one candle before entry, since
entry happens at the next candle's open) and compares ADX, ATR, and the EMA9/EMA21
separation (in points and as a % of price) between winning and losing trades.

Run with (from the project root E:\\Alpha):
    .venv\\Scripts\\python.exe backtest\\analyze_ema_false_crossovers.py

Reads backtest/data/strategy_ema_crossover_9_21.xlsx (from run_strategy_comparison.py).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).resolve().parent / "data"
SOURCE_FILE = DATA_DIR / "strategy_ema_crossover_9_21.xlsx"


def main() -> int:
    if not SOURCE_FILE.exists():
        print(f"No data found at {SOURCE_FILE}")
        print("Run backtest/run_strategy_comparison.py first.")
        return 1

    candles = pd.read_excel(SOURCE_FILE, sheet_name="Candles")
    candles["date"] = pd.to_datetime(candles["date"])
    candles = candles.sort_values("date").reset_index(drop=True)

    trades = pd.read_excel(SOURCE_FILE, sheet_name="Trades")
    trades["entry_date"] = pd.to_datetime(trades["entry_date"])

    # The crossover was detected on the candle BEFORE entry (entry happens at the
    # next candle's open) -- look up that candle's indicators by position.
    date_to_pos = pd.Series(candles.index, index=candles["date"])
    signal_positions = (date_to_pos.reindex(trades["entry_date"]) - 1).to_numpy()

    trades["signal_adx"] = candles["adx"].to_numpy()[signal_positions]
    trades["signal_atr"] = candles["atr"].to_numpy()[signal_positions]
    trades["ema_gap_points"] = (
        candles["ema_9"].to_numpy()[signal_positions] - candles["ema_21"].to_numpy()[signal_positions]
    ).__abs__()
    trades["ema_gap_pct"] = 100 * trades["ema_gap_points"] / candles["close"].to_numpy()[signal_positions]

    trades["outcome"] = trades["points"].apply(lambda p: "WIN" if p > 0 else "LOSS")

    print(f"{len(trades)} total trades\n")
    summary = trades.groupby("outcome")[["signal_adx", "signal_atr", "ema_gap_points", "ema_gap_pct", "points"]].mean()
    print("Average metrics at the crossover candle, by outcome:")
    print(summary.to_string())

    print("\nWin rate by ADX bucket at the crossover candle:")
    trades["adx_bucket"] = pd.cut(trades["signal_adx"], bins=[0, 15, 20, 25, 30, 100])
    print(trades.groupby("adx_bucket", observed=True).apply(
        lambda g: pd.Series({
            "trades": len(g),
            "win_rate": 100 * (g["points"] > 0).mean(),
            "total_points": g["points"].sum(),
        }),
        include_groups=False,
    ).to_string())

    print("\nWin rate by EMA gap (% of price) bucket at the crossover candle:")
    trades["gap_bucket"] = pd.cut(trades["ema_gap_pct"], bins=[0, 0.05, 0.1, 0.15, 0.2, 10])
    print(trades.groupby("gap_bucket", observed=True).apply(
        lambda g: pd.Series({
            "trades": len(g),
            "win_rate": 100 * (g["points"] > 0).mean(),
            "total_points": g["points"].sum(),
        }),
        include_groups=False,
    ).to_string())

    return 0


if __name__ == "__main__":
    sys.exit(main())
