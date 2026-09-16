"""Add a realistic, theta-decay-aware option-premium P&L estimate to an already-run
strategy's trades, and compare it against the raw index-points P&L those trades
were selected on.

The entry/exit trigger logic (100pt TP / 50pt SL on the index, checked via
high/low, same-day only -- see trade_simulator.py) is NOT changed here. This script
only re-prices each already-decided trade's entry and exit using Black-Scholes
(options_pricing.py): same entry/exit timestamps and index prices, but the P&L is
now "what a real ATM option premium would have done", which inherently includes
theta decay, instead of "how many index points did the underlying move".

Volatility input: real India VIX (backtest/data/INDIAVIX_five_minute_1000days.xlsx,
from fetch_india_vix_1000_days.py) matched to each trade's exact entry/exit
timestamp -- NSE's own market-implied volatility, not a retrospective estimate.
Falls back to realized volatility from the strategy's own price data (with a
warning) if that file isn't present.

Run with (from the project root E:\\Alpha):
    .venv\\Scripts\\python.exe backtest\\apply_theta_decay.py ema_crossover_9_21
    .venv\\Scripts\\python.exe backtest\\apply_theta_decay.py ema_crossover_low-adx_filter_20

(the argument is the strategy_<...>.xlsx filename stem, as produced by
run_strategy_comparison.py -- see backtest/data/ for the exact names)

Reads backtest/data/strategy_<name>.xlsx and writes
backtest/data/strategy_<name>_theta_adjusted.xlsx.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

BACKTEST_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BACKTEST_DIR))

import numpy as np
import pandas as pd

from options_pricing import black_scholes_price, nearest_strike, realized_volatility, years_to_expiry

DATA_DIR = BACKTEST_DIR / "data"
VIX_FILE = DATA_DIR / "INDIAVIX_five_minute_1000days.xlsx"
DEFAULT_VOL_FALLBACK = 0.12  # only used if neither VIX nor realized vol is available


def load_vix_series() -> pd.Series | None:
    if not VIX_FILE.exists():
        return None
    df = pd.read_excel(VIX_FILE)
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").set_index("date")
    return df["close"] / 100.0  # VIX is quoted in percent -- Black-Scholes wants a decimal


def load_realized_vol(candles: pd.DataFrame) -> pd.Series:
    daily_close = candles.set_index("date")["close"].resample("1D").last().dropna()
    vol = realized_volatility(daily_close)
    vol = vol.bfill()  # backfill the 20-day warm-up window from the first computable estimate
    if vol.isna().all():
        vol = vol.fillna(DEFAULT_VOL_FALLBACK)
    return vol


def _vol_at(vix_series: pd.Series | None, realized_vol_by_day: pd.Series, ts: pd.Timestamp) -> float:
    if vix_series is not None:
        v = vix_series.asof(ts)  # most recent known VIX reading at or before ts
        if pd.notna(v):
            return float(v)
    v = realized_vol_by_day.get(ts.normalize(), np.nan)
    if pd.notna(v):
        return float(v)
    nonnull = realized_vol_by_day.dropna()
    return float(nonnull.iloc[-1]) if not nonnull.empty else DEFAULT_VOL_FALLBACK


def price_trade(row: pd.Series, vix_series: pd.Series | None, realized_vol_by_day: pd.Series) -> tuple[float, float]:
    strike = nearest_strike(row["entry_price"])
    entry_ts, exit_ts = pd.Timestamp(row["entry_date"]), pd.Timestamp(row["exit_date"])

    entry_vol = _vol_at(vix_series, realized_vol_by_day, entry_ts)
    exit_vol = _vol_at(vix_series, realized_vol_by_day, exit_ts)

    option_type = row["type"]  # "CE" or "PE"
    entry_premium = black_scholes_price(row["entry_price"], strike, years_to_expiry(entry_ts), entry_vol, option_type)
    exit_premium = black_scholes_price(row["exit_price"], strike, years_to_expiry(exit_ts), exit_vol, option_type)
    return entry_premium, exit_premium


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply Black-Scholes theta-decay-aware P&L to a strategy's trades")
    parser.add_argument("strategy_file_stem", help="e.g. ema_crossover_9_21")
    args = parser.parse_args()

    source_path = DATA_DIR / f"strategy_{args.strategy_file_stem}.xlsx"
    if not source_path.exists():
        print(f"No file found at {source_path}")
        print("Available strategy files:")
        for f in sorted(DATA_DIR.glob("strategy_*.xlsx")):
            if "_theta_adjusted" not in f.stem:
                print(f"  {f.stem.removeprefix('strategy_')}")
        return 1

    candles = pd.read_excel(source_path, sheet_name="Candles")
    candles["date"] = pd.to_datetime(candles["date"])
    trades = pd.read_excel(source_path, sheet_name="Trades")
    if trades.empty:
        print("No trades to re-price.")
        return 0
    trades["entry_date"] = pd.to_datetime(trades["entry_date"])
    trades["exit_date"] = pd.to_datetime(trades["exit_date"])

    vix_series = load_vix_series()
    realized_vol_by_day = load_realized_vol(candles)
    if vix_series is not None:
        print(f"Using real India VIX ({len(vix_series)} candles) as the volatility input.")
    else:
        print(f"WARNING: {VIX_FILE.name} not found -- falling back to realized volatility "
              f"from price data. Run fetch_india_vix_1000_days.py for a more realistic result.")

    entry_premiums, exit_premiums = [], []
    for _, row in trades.iterrows():
        entry_p, exit_p = price_trade(row, vix_series, realized_vol_by_day)
        entry_premiums.append(entry_p)
        exit_premiums.append(exit_p)

    trades["entry_premium_bs"] = entry_premiums
    trades["exit_premium_bs"] = exit_premiums
    # Long option either way (CE or PE) -- P&L is simply exit premium minus entry
    # premium, unlike the index-points formula which needed CE/PE to differ because
    # index points don't inherently encode option premium direction the way an
    # actual priced premium already does.
    trades["theta_adjusted_points"] = trades["exit_premium_bs"] - trades["entry_premium_bs"]
    trades["theta_adjusted_cumulative"] = trades["theta_adjusted_points"].cumsum()

    index_total = trades["points"].sum()
    theta_total = trades["theta_adjusted_points"].sum()
    print(f"{len(trades)} trades")
    print(f"Index-points P&L (what run_strategy_comparison.py reported): "
          f"total={index_total:.2f}  avg={trades['points'].mean():.2f}")
    print(f"Theta-adjusted premium P&L (Black-Scholes):                  "
          f"total={theta_total:.2f}  avg={trades['theta_adjusted_points'].mean():.2f}")
    print(f"Difference attributable to theta decay + option pricing: {index_total - theta_total:.2f} points")
    win_rate_index = 100 * (trades["points"] > 0).mean()
    win_rate_theta = 100 * (trades["theta_adjusted_points"] > 0).mean()
    print(f"Win rate: index-points={win_rate_index:.1f}%  theta-adjusted={win_rate_theta:.1f}%")

    out_path = DATA_DIR / f"strategy_{args.strategy_file_stem}_theta_adjusted.xlsx"
    trades.to_excel(out_path, index=False)
    print(f"\nWritten to {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
