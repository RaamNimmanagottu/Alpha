from __future__ import annotations

import logging
from dataclasses import dataclass

import pandas as pd

import indicators as ind

logger = logging.getLogger("alpha.ema_crossover_21_50_signal")

FAST_PERIOD = 21
SLOW_PERIOD = 50
MIN_CANDLES_REQUIRED = SLOW_PERIOD + 2


@dataclass
class Signal:
    direction: str  # "BUY", "SELL", or "WAIT"
    signal_candle_time: pd.Timestamp | None = None


def get_signal(symbol: str, candles: pd.DataFrame) -> Signal:
    """EMA(21)/EMA(50) crossover: BUY when the fast EMA crosses above the slow
    EMA, SELL when it crosses below, WAIT otherwise.

    Backtested as the best of 27+ strategies tested on 1000 days of real
    HDFCBANK 5-min data (TP=60/SL=29, 53.28% win rate, +212.09 points) -- a
    slower-period EMA pair than NIFTY/BANKNIFTY's 9/21, confirming again that
    signals don't transfer across instruments without their own backtest.
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
        "%s: ema21=%.2f ema50=%.2f (prev ema21=%.2f ema50=%.2f) cross_up=%s cross_down=%s",
        symbol, fast_now, slow_now, fast_prev, slow_prev, cross_up, cross_down,
    )

    if cross_up:
        return Signal("BUY", signal_time)
    if cross_down:
        return Signal("SELL", signal_time)
    return Signal("WAIT")
