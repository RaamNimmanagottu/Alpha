"""Black-Scholes option pricing, used to estimate a realistic premium P&L (theta
decay included) for the index-points trades this project's backtests simulate.

There is no real historical NIFTY option premium/IV data available here. These
functions price a THEORETICAL option using the underlying's own realized volatility
as an implied-volatility stand-in -- a standard technique for this kind of backtest,
but still a model, not real market prices: actual IV moves with supply, demand, and
sentiment in ways realized volatility doesn't capture. Treat results as directional,
not a rupee-accurate P&L.

Expiry convention: NIFTY weekly/monthly derivatives expire on Tuesday (per NSE's
current cycle). If a trade's own day is a Tuesday, that's 0-days-to-expiry.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import norm

RISK_FREE_RATE = 0.065  # approximate India short-term risk-free rate
STRIKE_INTERVAL = 50    # NIFTY weekly strike spacing


def nearest_strike(spot: float, interval: float = STRIKE_INTERVAL) -> float:
    return round(spot / interval) * interval


def realized_volatility(daily_close: pd.Series, window: int = 20) -> pd.Series:
    """Annualized realized volatility from daily closes, rolling `window` days.
    The first `window` days have no estimate yet (NaN) -- callers should backfill
    from the first available value rather than assume a value exists everywhere.
    """
    log_returns = np.log(daily_close / daily_close.shift(1))
    return log_returns.rolling(window).std() * np.sqrt(252)


def next_tuesday_expiry(timestamp: pd.Timestamp) -> pd.Timestamp:
    """The upcoming Tuesday expiry for `timestamp` (same day if it's already a
    Tuesday -- 0DTE). Expiry is treated as market close, 15:30, that day."""
    days_ahead = (1 - timestamp.weekday()) % 7  # Monday=0 ... Tuesday=1 in Python's weekday()
    expiry_date = timestamp.normalize() + pd.Timedelta(days=days_ahead)
    return expiry_date.replace(hour=15, minute=30)


def years_to_expiry(timestamp: pd.Timestamp, min_years: float = 1e-6) -> float:
    expiry = next_tuesday_expiry(timestamp)
    seconds_remaining = max((expiry - timestamp).total_seconds(), 0)
    years = seconds_remaining / (365.25 * 24 * 3600)
    return max(years, min_years)  # keep strictly positive to avoid a divide-by-zero right at expiry


def black_scholes_price(
    spot: float, strike: float, years: float, vol: float, option_type: str, r: float = RISK_FREE_RATE
) -> float:
    """Theoretical CE/PE premium. Falls back to intrinsic value if vol or time
    remaining is effectively zero (right at/after expiry), where Black-Scholes'
    own formula would otherwise divide by zero."""
    if vol <= 0 or years <= 1e-6:
        return max(spot - strike, 0) if option_type == "CE" else max(strike - spot, 0)

    d1 = (np.log(spot / strike) + (r + 0.5 * vol ** 2) * years) / (vol * np.sqrt(years))
    d2 = d1 - vol * np.sqrt(years)

    if option_type == "CE":
        return spot * norm.cdf(d1) - strike * np.exp(-r * years) * norm.cdf(d2)
    return strike * np.exp(-r * years) * norm.cdf(-d2) - spot * norm.cdf(-d1)
