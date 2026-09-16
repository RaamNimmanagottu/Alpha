"""Shared trade-simulation engine used by every strategy in backtest/strategies.py.

Takes any OHLC dataframe with a `raw_signal` column (BUY/SELL/None per candle,
produced by a strategy-specific generator) and applies the same realistic
entry/exit rules:

  - A BUY/SELL raw_signal on candle i triggers entry at candle i+1's OPEN -- never
    the same candle's close, since you can't act on a signal before that candle has
    actually closed.
  - BUY -> CE (long call), SELL -> PE (long put).
  - While a position is open, new raw signals are ignored (WAIT) until it exits.
  - Exit on take-profit or stop-loss, in POINTS on the underlying (not percent --
    10% of NIFTY's ~23,000 level would be ~2,300 points, unrealistic for intraday).
    Checked against each candle's HIGH/LOW so an intracandle touch isn't missed.
    Stop-loss takes priority if both are crossed within the same candle.
  - No entries before ENTRY_START_TIME. Any open position is forced closed at
    FORCE_EXIT_TIME, or at the previous day's last available candle if that day
    never reaches FORCE_EXIT_TIME (early close / data gap) -- every trade opens and
    closes within the same day, never carries overnight.

Output: a single `signal` column with one of BUY, SELL, EXIT_PROFIT, EXIT_SL,
EXIT_TIME, WAIT (or None when flat with nothing happening); `points` (populated
only on exit rows); `total_points_earned` (running cumulative total, forward-filled
across every row).
"""
from __future__ import annotations

from datetime import time as dtime

import pandas as pd

TAKE_PROFIT_POINTS = 100
STOP_LOSS_POINTS = 50
ENTRY_START_TIME = dtime(9, 30)
FORCE_EXIT_TIME = dtime(14, 50)


def simulate(
    df: pd.DataFrame,
    take_profit_points: float = TAKE_PROFIT_POINTS,
    stop_loss_points: float = STOP_LOSS_POINTS,
    entry_start_time: dtime = ENTRY_START_TIME,
    force_exit_time: dtime = FORCE_EXIT_TIME,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """`df` must be sorted ASCENDING by date and have a `raw_signal` column
    ("BUY"/"SELL"/anything else means no signal that candle)."""
    df = df.sort_values("date").reset_index(drop=True)

    position = None  # "CE" or "PE"
    entry_price = entry_date = None

    signal_col: list[str | None] = [None] * len(df)
    points_col: list[float | None] = [None] * len(df)
    trades = []

    dates = df["date"].to_numpy()
    days = df["date"].dt.date.to_numpy()
    times = df["date"].dt.time.to_numpy()
    opens = df["open"].to_numpy()
    highs = df["high"].to_numpy()
    lows = df["low"].to_numpy()
    closes = df["close"].to_numpy()
    raw_signals = df["raw_signal"].to_numpy()

    def _record_exit(idx: int, exit_price: float, exit_label: str) -> None:
        nonlocal position
        points = (exit_price - entry_price) if position == "CE" else (entry_price - exit_price)
        trades.append({
            "type": position, "entry_date": entry_date, "entry_price": entry_price,
            "exit_date": dates[idx], "exit_price": exit_price, "reason": exit_label,
            "points": points,
        })
        points_col[idx] = points
        signal_col[idx] = exit_label
        position = None

    for i in range(1, len(df)):
        if position is not None and days[i] != days[i - 1]:
            # That day never produced a candle at/after force_exit_time (early
            # close / data gap) -- square off at the last known close so nothing
            # ever silently carries into the next day.
            _record_exit(i - 1, closes[i - 1], "EXIT_TIME")

        prev_raw = raw_signals[i - 1]

        if position is None and times[i] >= entry_start_time:
            if prev_raw == "BUY":
                position, entry_price, entry_date = "CE", opens[i], dates[i]
                signal_col[i] = "BUY"
            elif prev_raw == "SELL":
                position, entry_price, entry_date = "PE", opens[i], dates[i]
                signal_col[i] = "SELL"

        if position is not None and times[i] >= force_exit_time:
            _record_exit(i, closes[i], "EXIT_TIME")

        elif position == "CE":
            tp_price, sl_price = entry_price + take_profit_points, entry_price - stop_loss_points
            hit_tp, hit_sl = highs[i] >= tp_price, lows[i] <= sl_price
            if hit_tp or hit_sl:
                _record_exit(i, sl_price if hit_sl else tp_price, "EXIT_SL" if hit_sl else "EXIT_PROFIT")

        elif position == "PE":
            tp_price, sl_price = entry_price - take_profit_points, entry_price + stop_loss_points
            hit_tp, hit_sl = lows[i] <= tp_price, highs[i] >= sl_price
            if hit_tp or hit_sl:
                _record_exit(i, sl_price if hit_sl else tp_price, "EXIT_SL" if hit_sl else "EXIT_PROFIT")

        if signal_col[i] is None and position is not None:
            signal_col[i] = "WAIT"

    df = df.copy()
    df["signal"] = signal_col
    df["points"] = points_col
    df["total_points_earned"] = pd.Series(points_col, dtype="float64").fillna(0).cumsum()

    trades_df = pd.DataFrame(trades)
    if not trades_df.empty:
        trades_df["cumulative_points"] = trades_df["points"].cumsum()
    return df, trades_df


def summarize(trades_df: pd.DataFrame) -> dict:
    if trades_df.empty:
        return {"trades": 0, "win_rate": 0.0, "total_points": 0.0, "avg_points": 0.0}
    total = trades_df["points"].sum()
    wins = (trades_df["points"] > 0).sum()
    return {
        "trades": len(trades_df),
        "wins": int(wins),
        "win_rate": 100 * wins / len(trades_df),
        "tp_exits": int((trades_df["reason"] == "EXIT_PROFIT").sum()),
        "sl_exits": int((trades_df["reason"] == "EXIT_SL").sum()),
        "time_exits": int((trades_df["reason"] == "EXIT_TIME").sum()),
        "total_points": float(total),
        "avg_points": float(total / len(trades_df)),
    }
