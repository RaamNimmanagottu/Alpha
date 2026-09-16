from __future__ import annotations

import logging
from dataclasses import dataclass

import pandas as pd

from alpha import indicators as ind

logger = logging.getLogger("alpha.local_signals")

MIN_CANDLES_REQUIRED = 60  # enough for ADX(14)/CCI(20) warm-up with a safety margin


@dataclass
class Signal:
    direction: str  # "BUY", "SELL", or "WAIT"
    pivot: float
    resistance: float
    support: float


def _previous_completed_day_ohlc(candles: pd.DataFrame) -> tuple[float, float, float] | None:
    daily = (
        candles.set_index("date")
        .resample("1D")
        .agg({"open": "first", "high": "max", "low": "min", "close": "last"})
        .dropna()
    )
    today = pd.Timestamp.now().normalize()
    completed = daily[daily.index < today]
    if completed.empty:
        if daily.empty:
            return None
        completed = daily  # not enough history for a "previous" day yet; use what we have
    last = completed.iloc[-1]
    return float(last["high"]), float(last["low"]), float(last["close"])


def vote_direction(rsi: float, stoch: float, cci20: float, adx: float, ao: float, mom: float) -> str:
    """Pure BUY/SELL/WAIT decision from indicator values -- no data fetching, no
    pivot/support-resistance involved. Factored out so the live signal and the
    backtest engine (backtest/run_signals.py) apply the exact same rule instead of
    two copies that could quietly drift apart.
    """
    buy_votes = 0
    sell_votes = 0

    if rsi > 70:
        sell_votes += 1
    elif rsi < 30:
        buy_votes += 1

    if stoch > 80:
        sell_votes += 1
    elif stoch < 20:
        buy_votes += 1

    if cci20 > 100:
        sell_votes += 1
    elif cci20 < -100:
        buy_votes += 1

    strong_trend = adx > 25 or ao > 0
    uptrend = mom > 0

    if buy_votes > 1 and (strong_trend or uptrend):
        return "BUY"
    elif sell_votes > 1 and (strong_trend or not uptrend):
        return "SELL"
    return "WAIT"


def get_signal(symbol: str, ltp: float, candles: pd.DataFrame) -> Signal:
    """Locally-computed replacement for the old TradingView-based signal.

    Same voting logic as before (RSI/Stochastic/CCI votes, ADX/AO/Momentum for trend
    confirmation, classic pivot points for support/resistance) but every indicator is
    computed here from broker-sourced historical candles instead of querying
    TradingView's website. Formulas are standard textbook technical-analysis
    definitions and will not be bit-identical to TradingView's own (undisclosed)
    smoothing -- directionally comparable, not a guaranteed numeric match.
    """
    if len(candles) < MIN_CANDLES_REQUIRED:
        logger.warning(
            "%s: only %d candles available (need >=%d), returning WAIT",
            symbol, len(candles), MIN_CANDLES_REQUIRED,
        )
        return Signal("WAIT", ltp, ltp, ltp)

    close, high, low = candles["close"], candles["high"], candles["low"]

    rsi = ind.rsi(close).iloc[-1]
    stoch = ind.stochastic_k(high, low, close).iloc[-1]
    cci20 = ind.cci(high, low, close).iloc[-1]
    adx = ind.adx(high, low, close).iloc[-1]
    ao = ind.awesome_oscillator(high, low).iloc[-1]
    mom = ind.momentum(close).iloc[-1]

    prev_day = _previous_completed_day_ohlc(candles)
    if prev_day is None:
        return Signal("WAIT", ltp, ltp, ltp)
    prev_high, prev_low, prev_close = prev_day
    pivots = ind.classic_pivot_points(prev_high, prev_low, prev_close)
    pivot, r1, s1, r2, s2 = pivots["pivot"], pivots["r1"], pivots["s1"], pivots["r2"], pivots["s2"]

    support, resistance = s1, r1
    if ltp > r1 + 50:
        support, resistance = s2, s1
    elif ltp - 50 > s1:
        support, resistance = r1, r2

    direction = vote_direction(rsi, stoch, cci20, adx, ao, mom)

    logger.info(
        "%s: rsi=%.1f stoch=%.1f cci20=%.1f adx=%.1f ao=%.1f mom=%.1f direction=%s "
        "pivot=%.1f r1=%.1f s1=%.1f r2=%.1f s2=%.1f",
        symbol, rsi, stoch, cci20, adx, ao, mom, direction,
        pivot, r1, s1, r2, s2,
    )

    return Signal(direction=direction, pivot=pivot, resistance=resistance, support=support)
