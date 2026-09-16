"""Run each single-indicator strategy (plus two simple majority-vote combinations)
through the shared trade simulator, compare results, and save a per-strategy
Excel output for each one.

Base data: OHLC + all indicators computed in backtest_1000days.py (EMA 9/21/50, SMA,
MACD/signal, ADX, Supertrend, RSI, Stochastic, CCI, Williams %R, Bollinger, ATR,
Keltner, Awesome Oscillator, Momentum) -- no ML, no next_open/next_close targets.

Run with (from the project root E:\\Alpha):
    .venv\\Scripts\\python.exe backtest\\run_strategy_comparison.py

Reads backtest/data/NIFTY_five_minute_1000days_features.xlsx (ML target columns, if
present, are dropped and unused) and writes:
    backtest/data/strategy_comparison.csv
    backtest/data/strategy_<name>.xlsx  (one per strategy, Candles + Trades sheets)
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

BACKTEST_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BACKTEST_DIR))

import pandas as pd

from strategies import STRATEGIES, combine_majority
from trade_simulator import simulate, summarize

DATA_DIR = BACKTEST_DIR / "data"
SOURCE_FILE = DATA_DIR / "NIFTY_five_minute_1000days_features.xlsx"


def _write_with_retry(write_fn, label: str, attempts: int = 12, delay_seconds: float = 10.0) -> None:
    """Retry a write that can transiently fail with PermissionError -- this project
    directory is OneDrive-synced, and OneDrive locks a file while uploading it right
    after it's written, which can outlast a single attempt for a large file."""
    for attempt in range(1, attempts + 1):
        try:
            write_fn()
            return
        except PermissionError as exc:
            if attempt == attempts:
                raise
            print(f"  {label}: locked, likely OneDrive syncing (attempt {attempt}/{attempts}), "
                  f"waiting {delay_seconds:.0f}s...")
            time.sleep(delay_seconds)


def load_base_data() -> pd.DataFrame:
    df = pd.read_excel(SOURCE_FILE)
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)
    # Drop ML-only columns from an earlier iteration of this pipeline if present --
    # this run is pure rule-based, no model involved.
    df = df.drop(columns=[c for c in ("next_open", "next_close") if c in df.columns])
    return df


def _safe_filename(name: str) -> str:
    safe = name.lower().replace(" ", "_")
    for ch in '<>:"/\\|?*()':
        safe = safe.replace(ch, "")
    return safe


def run_one(name: str, df: pd.DataFrame, raw_signal: pd.Series) -> dict:
    work = df.copy()
    work["raw_signal"] = raw_signal
    result_df, trades_df = simulate(work)
    stats = summarize(trades_df)
    stats["strategy"] = name

    out_path = DATA_DIR / f"strategy_{_safe_filename(name)}.xlsx"

    def _write():
        with pd.ExcelWriter(out_path) as writer:
            result_df.sort_values("date", ascending=False).to_excel(writer, sheet_name="Candles", index=False)
            trades_df.to_excel(writer, sheet_name="Trades", index=False)

    _write_with_retry(_write, out_path.name)
    stats["output_file"] = str(out_path)
    return stats


def main() -> int:
    if not SOURCE_FILE.exists():
        print(f"No indicator data found at {SOURCE_FILE}")
        print("Run backtest/build_ml_dataset.py (or backtest_1000days.py) first.")
        return 1

    df = load_base_data()
    print(f"{len(df)} candles loaded\n")

    all_stats = []
    raw_signals = {}
    for name, fn in STRATEGIES.items():
        raw_signals[name] = fn(df)
        stats = run_one(name, df, raw_signals[name])
        all_stats.append(stats)
        print(f"{name:28s} trades={stats['trades']:5d} "
              f"win_rate={stats['win_rate']:5.1f}%  total_points={stats['total_points']:9.2f}")

    for min_agree in (2, 3):
        name = f"Combo ({min_agree} of {len(raw_signals)} agree)"
        combo_signal = combine_majority(*raw_signals.values(), min_agree=min_agree)
        stats = run_one(name, df, combo_signal)
        all_stats.append(stats)
        print(f"{name:28s} trades={stats['trades']:5d} "
              f"win_rate={stats['win_rate']:5.1f}%  total_points={stats['total_points']:9.2f}")

    comparison_df = pd.DataFrame(all_stats).sort_values("total_points", ascending=False).reset_index(drop=True)
    comparison_path = DATA_DIR / "strategy_comparison.csv"
    _write_with_retry(lambda: comparison_df.to_csv(comparison_path, index=False), comparison_path.name)

    print(f"\nRanked by total points:")
    print(comparison_df[["strategy", "trades", "win_rate", "total_points", "avg_points"]].to_string(index=False))
    print(f"\nFull comparison written to {comparison_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
