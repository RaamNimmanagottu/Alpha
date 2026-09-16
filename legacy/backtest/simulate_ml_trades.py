"""Simulate CE/PE trades driven by the ML model's predicted signal, with realistic
entry timing and points-based take-profit/stop-loss exits.

Rules:
  - A BUY/SELL signal on candle i (predicted from candle i's own indicators) triggers
    entry at candle i+1's OPEN -- not candle i's close. You can't act on a signal
    before the candle that produced it has actually closed.
  - BUY -> CE (long call), SELL -> PE (long put).
  - Once in a position, new signals are ignored (an explicit WAIT state) until the
    position exits on take-profit or stop-loss. TP/SL are POINTS on the underlying,
    not percentages -- 10% of NIFTY's ~23,000 level would be ~2,300 points, wildly
    unrealistic for an intraday move.
  - Every candle while a position is open is checked with its HIGH/LOW (not just
    close) against the TP/SL thresholds, catching an intracandle touch -- closer to
    how the live bot's frequent LTP polling actually behaves. If both TP and SL are
    crossed within the same candle, STOP-LOSS takes priority (conservative).
  - Exit price is taken as the exact TP/SL threshold value (assumes a fill exactly at
    the trigger price -- no slippage modeled).
  - CE points = exit - entry.  PE points = entry - exit.
  - No new entries before ENTRY_START_TIME (9:30 AM). Any position still open at
    FORCE_EXIT_TIME (2:50 PM) is squared off at that candle's close regardless of
    TP/SL -- every trade must open and close within the same day.

Reads backtest/data/NIFTY_five_minute_1000days_ml_signals.xlsx (produced by
train_ml_models.py -- has ml_signal and dataset_split columns already) and writes
backtest/data/NIFTY_five_minute_1000days_ml_trades.xlsx (Candles sheet with
`position`, `profit_loss`, `total_points_earned` columns added; Trades sheet, one
row per closed trade).

Run with (from the project root E:\\Alpha):
    .venv\\Scripts\\python.exe backtest\\simulate_ml_trades.py
"""
from __future__ import annotations

import sys
from datetime import time as dtime
from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).resolve().parent / "data"
SOURCE_FILE = DATA_DIR / "NIFTY_five_minute_1000days_ml_signals.xlsx"
OUTPUT_FILE = DATA_DIR / "NIFTY_five_minute_1000days_ml_trades.xlsx"

TAKE_PROFIT_POINTS = 100
STOP_LOSS_POINTS = 50
ENTRY_START_TIME = dtime(9, 30)   # no new entries before this
FORCE_EXIT_TIME = dtime(14, 50)   # any open position is squared off at/after this, same day


def simulate(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """`df` must be sorted ASCENDING by date with an `ml_signal` column already
    present (BUY/SELL/None-ish per row, from train_ml_models.py)."""
    position = None  # "CE" or "PE"
    entry_price = entry_date = entry_split = None

    position_col = [None] * len(df)
    profit_loss_col = [None] * len(df)
    trades = []

    dates = df["date"].to_numpy()
    days = df["date"].dt.date.to_numpy()
    times = df["date"].dt.time.to_numpy()
    opens = df["open"].to_numpy()
    highs = df["high"].to_numpy()
    lows = df["low"].to_numpy()
    closes = df["close"].to_numpy()
    signals = df["ml_signal"].to_numpy()
    splits = df["dataset_split"].to_numpy()

    def _record_exit(idx: int, exit_price: float, reason: str) -> None:
        nonlocal position
        points = (exit_price - entry_price) if position == "CE" else (entry_price - exit_price)
        trades.append({
            "type": position, "entry_date": entry_date, "entry_price": entry_price,
            "entry_split": entry_split, "exit_date": dates[idx], "exit_price": exit_price,
            "reason": reason, "points": points,
        })
        profit_loss_col[idx] = points
        position_col[idx] = None
        position = None

    for i in range(1, len(df)):
        if position is not None and days[i] != days[i - 1]:
            # No candle on the previous day ever reached FORCE_EXIT_TIME -- an early
            # close or a data gap. Fall back to squaring off at that day's last known
            # close so a trade can never silently carry into the next day.
            _record_exit(i - 1, closes[i - 1], "day_end_gap")

        prev_signal = signals[i - 1]

        if position is None and times[i] >= ENTRY_START_TIME:
            if prev_signal == "BUY":
                position, entry_price, entry_date, entry_split = "CE", opens[i], dates[i], splits[i]
            elif prev_signal == "SELL":
                position, entry_price, entry_date, entry_split = "PE", opens[i], dates[i], splits[i]

        if position is not None and times[i] >= FORCE_EXIT_TIME:
            # Every trade must open and close within the same day -- this overrides
            # TP/SL for this candle regardless of what the high/low would say.
            _record_exit(i, closes[i], "time_exit")

        elif position == "CE":
            tp_price, sl_price = entry_price + TAKE_PROFIT_POINTS, entry_price - STOP_LOSS_POINTS
            hit_tp, hit_sl = highs[i] >= tp_price, lows[i] <= sl_price
            if hit_tp or hit_sl:
                _record_exit(i, sl_price if hit_sl else tp_price, "stop_loss" if hit_sl else "take_profit")

        elif position == "PE":
            tp_price, sl_price = entry_price - TAKE_PROFIT_POINTS, entry_price + STOP_LOSS_POINTS
            hit_tp, hit_sl = lows[i] <= tp_price, highs[i] >= sl_price
            if hit_tp or hit_sl:
                _record_exit(i, sl_price if hit_sl else tp_price, "stop_loss" if hit_sl else "take_profit")

        position_col[i] = position

    if position is not None:
        print(f"Note: a {position} position opened {entry_date} at {entry_price} is still "
              f"open at the end of the data (no TP/SL hit yet) -- not counted as a trade.")

    df = df.copy()
    df["position"] = position_col
    df["profit_loss"] = profit_loss_col
    df["total_points_earned"] = pd.Series(profit_loss_col, dtype="float64").fillna(0).cumsum()

    trades_df = pd.DataFrame(trades)
    if not trades_df.empty:
        trades_df["cumulative_points"] = trades_df["points"].cumsum()
    return df, trades_df


def print_summary(label: str, trades_df: pd.DataFrame) -> None:
    if trades_df.empty:
        print(f"{label}: no closed trades.")
        return
    total = trades_df["points"].sum()
    wins = (trades_df["points"] > 0).sum()
    win_rate = 100 * wins / len(trades_df)
    tp_exits = (trades_df["reason"] == "take_profit").sum()
    sl_exits = (trades_df["reason"] == "stop_loss").sum()
    time_exits = (trades_df["reason"] == "time_exit").sum()
    gap_exits = (trades_df["reason"] == "day_end_gap").sum()
    print(f"{label}: {len(trades_df)} trades, {wins} wins ({win_rate:.1f}%), "
          f"{tp_exits} TP / {sl_exits} SL / {time_exits} time-forced / {gap_exits} day-gap exits, "
          f"total points = {total:.2f}, avg points/trade = {total / len(trades_df):.2f}")


def main() -> int:
    if not SOURCE_FILE.exists():
        print(f"No ML signal data found at {SOURCE_FILE}")
        print("Run backtest/train_ml_models.py first.")
        return 1

    df = pd.read_excel(SOURCE_FILE, sheet_name=0)
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)

    df, trades_df = simulate(df)

    print(f"TP={TAKE_PROFIT_POINTS} points, SL={STOP_LOSS_POINTS} points\n")
    print_summary("All trades (train+test combined)", trades_df)
    if not trades_df.empty:
        print_summary("Test-split entries only (genuinely out-of-sample)",
                       trades_df[trades_df["entry_split"] == "test"])
        print_summary("Train-split entries only (in-sample, optimistic -- model saw this data)",
                       trades_df[trades_df["entry_split"] == "train"])

    with pd.ExcelWriter(OUTPUT_FILE) as writer:
        df.sort_values("date", ascending=False).to_excel(writer, sheet_name="Candles", index=False)
        trades_df.to_excel(writer, sheet_name="Trades", index=False)
    print(f"\nWritten to {OUTPUT_FILE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
