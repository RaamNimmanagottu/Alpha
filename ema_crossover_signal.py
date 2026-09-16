from __future__ import annotations

import logging
from dataclasses import dataclass

import pandas as pd

import indicators as ind

logger = logging.getLogger("alpha.ema_crossover_signal")

FAST_PERIOD = 9
SLOW_PERIOD = 21
MIN_CANDLES_REQUIRED = SLOW_PERIOD + 2  # need at least one full prior EMA21 to compare against


@dataclass
class Signal:
    direction: str  # "BUY", "SELL", or "WAIT"
    signal_candle_time: pd.Timestamp | None = None
    """Timestamp of the candle the crossover was detected on, if any -- lets the
    caller avoid acting on the same crossover event more than once."""


def get_signal(symbol: str, candles: pd.DataFrame) -> Signal:
    """EMA(9)/EMA(21) crossover: BUY when the fast EMA crosses above the slow EMA,
    SELL when it crosses below, WAIT otherwise.

    This is the strategy backtested in backtest/run_strategy_comparison.py: the
    single best performer out of 23 strategies/variants tested on 1000 days of
    NIFTY 5-minute data (6,350 points, 46.8% win rate) -- unfiltered, no additional
    support/resistance or trend gate, since the raw crossover was what actually won.
    Replaces the old RSI/Stochastic/CCI/ADX/AO/Momentum vote in the retired
    alpha/local_signals.py (see legacy/local_signals.py).
    """
    if len(candles) < MIN_CANDLES_REQUIRED:
        logger.warning(
            "%s: only %d candles available (need >=%d), returning WAIT",
            symbol, len(candles), MIN_CANDLES_REQUIRED,
        )
        return Signal("WAIT")

    close = candles["close"]
    fast = ind.ema(close, FAST_PERIOD)
    slow = ind.ema(close, SLOW_PERIOD)

    fast_now, slow_now = fast.iloc[-1], slow.iloc[-1]
    fast_prev, slow_prev = fast.iloc[-2], slow.iloc[-2]
    signal_time = candles["date"].iloc[-1]

    cross_up = fast_now > slow_now and fast_prev <= slow_prev
    cross_down = fast_now < slow_now and fast_prev >= slow_prev

    logger.info(
        "%s: ema9=%.2f ema21=%.2f (prev ema9=%.2f ema21=%.2f) cross_up=%s cross_down=%s",
        symbol, fast_now, slow_now, fast_prev, slow_prev, cross_up, cross_down,
    )

    if cross_up:
        return Signal("BUY", signal_time)
    if cross_down:
        return Signal("SELL", signal_time)
    return Signal("WAIT")
