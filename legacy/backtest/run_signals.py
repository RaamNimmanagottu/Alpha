"""Simulate the BUY/SELL/WAIT signal from alpha/local_signals.py over stored
historical candles, and compute points profit/loss per closed trade.

This is an options-buying strategy: a BUY signal means buying a CE, a SELL signal
means buying a PE -- never shorting the index directly. There's no historical option
premium data available here (only index OHLC candles), so this backtest uses the
underlying index's own price movement as a points-based proxy for the option's P&L:

    CE trade (from a BUY signal):  points = exit_price - entry_price
    PE trade (from a SELL signal): points = entry_price - exit_price

This ignores real option mechanics (premium, theta decay, IV, strike selection) --
it answers "does the signal call direction correctly", in index points, not "what
would this have actually earned in rupees on a real option."

Position rule: one position at a time. A CE position stays open through WAIT signals
and closes only when a SELL signal appears -- at which point that same SELL signal
immediately opens the new PE position (and symmetrically for PE -> CE). So once the
first signal fires, the backtest is always in the market.

Run with (from the project root E:\\Alpha):
    .venv\\Scripts\\python.exe backtest\\run_signals.py NIFTY
    .venv\\Scripts\\python.exe backtest\\run_signals.py BANKNIFTY

Reads backtest/data/<INSTRUMENT>_five_minute_with_indicators.xlsx (from
prepare_data.py) and writes backtest/data/<INSTRUMENT>_five_minute_signals.xlsx with
`signal`, `position`, and `profit_loss` columns added, plus a separate "Trades" sheet
listing each closed trade.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd

from alpha.local_signals import vote_direction

DATA_DIR = Path(__file__).resolve().parent / "data"


def generate_signals(df: pd.DataFrame) -> pd.DataFrame:
    """`df` must be sorted ASCENDING by date with rsi/stoch_k/cci20/adx/awesome_oscillator/
    momentum columns already computed (see prepare_data.py). Adds `signal`."""
    df = df.copy()
    df["signal"] = [
        vote_direction(row.rsi, row.stoch_k, row.cci20, row.adx, row.awesome_oscillator, row.momentum)
        for row in df.itertuples()
    ]
    return df


def simulate_trades(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Walk the (ascending) signal series and simulate one-position-at-a-time trading.

    Returns (df with `position` and `profit_loss` columns added, a separate trades log).
    """
    position: str | None = None  # "CE" or "PE"
    entry_price = None
    entry_date = None

    position_col = [None] * len(df)
    profit_loss_col = [None] * len(df)
    trades = []

    for i, row in enumerate(df.itertuples()):
        signal = row.signal
        price = row.close

        if position is None:
            if signal == "BUY":
                position, entry_price, entry_date = "CE", price, row.date
            elif signal == "SELL":
                position, entry_price, entry_date = "PE", price, row.date

        elif position == "CE" and signal == "SELL":
            points = price - entry_price  # CE: sell - buy
            trades.append({
                "type": "CE", "entry_date": entry_date, "entry_price": entry_price,
                "exit_date": row.date, "exit_price": price, "points": points,
            })
            profit_loss_col[i] = points
            position, entry_price, entry_date = "PE", price, row.date  # same signal opens the new leg

        elif position == "PE" and signal == "BUY":
            points = entry_price - price  # PE: buy - sell
            trades.append({
                "type": "PE", "entry_date": entry_date, "entry_price": entry_price,
                "exit_date": row.date, "exit_price": price, "points": points,
            })
            profit_loss_col[i] = points
            position, entry_price, entry_date = "CE", price, row.date

        position_col[i] = position

    df = df.copy()
    df["position"] = position_col
    df["profit_loss"] = profit_loss_col

    if position is not None:
        print(f"Note: a {position} position opened {entry_date} at {entry_price} is still "
              f"open at the end of the data (no closing signal yet) -- not counted as a trade.")

    trades_df = pd.DataFrame(trades)
    if not trades_df.empty:
        trades_df["cumulative_points"] = trades_df["points"].cumsum()
    return df, trades_df


def print_summary(trades_df: pd.DataFrame) -> None:
    if trades_df.empty:
        print("No closed trades.")
        return
    total = trades_df["points"].sum()
    wins = (trades_df["points"] > 0).sum()
    losses = (trades_df["points"] <= 0).sum()
    win_rate = 100 * wins / len(trades_df)
    print(f"Trades: {len(trades_df)}  Wins: {wins}  Losses: {losses}  Win rate: {win_rate:.1f}%")
    print(f"Total points: {total:.2f}  Avg points/trade: {total / len(trades_df):.2f}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Backtest the BUY/SELL/WAIT signal over stored candles")
    parser.add_argument("instrument", nargs="?", default="NIFTY", help="e.g. NIFTY or BANKNIFTY")
    args = parser.parse_args()

    source_path = DATA_DIR / f"{args.instrument}_five_minute_with_indicators.xlsx"
    if not source_path.exists():
        print(f"No enriched data found at {source_path}")
        print("Run backtest/prepare_data.py first.")
        return 1

    df = pd.read_excel(source_path)
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)  # signals must be walked chronologically

    df = generate_signals(df)
    df, trades_df = simulate_trades(df)

    print_summary(trades_df)

    out_path = DATA_DIR / f"{args.instrument}_five_minute_signals.xlsx"
    with pd.ExcelWriter(out_path) as writer:
        df.sort_values("date", ascending=False).to_excel(writer, sheet_name="Candles", index=False)
        trades_df.to_excel(writer, sheet_name="Trades", index=False)
    print(f"Written to {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
