from __future__ import annotations

import logging
from dataclasses import dataclass

import pandas as pd

import indicators as ind

logger = logging.getLogger("alpha.momentum_zero_cross_signal")

MOMENTUM_PERIOD = 10
MIN_CANDLES_REQUIRED = MOMENTUM_PERIOD + 2


@dataclass
class Signal:
    direction: str  # "BUY", "SELL", or "WAIT"
    signal_candle_time: pd.Timestamp | None = None


def get_signal(symbol: str, candles: pd.DataFrame) -> Signal:
    """Momentum(10) zero-cross: BUY when momentum crosses above zero, SELL
    when it crosses below.

    Backtested as the best of 27+ strategies tested on 1000 days of real TCS
    5-min data (TP=90/SL=45, 48.87% win rate, +1244.60 points, avg 0.85
    pts/trade) -- noisier/less monotonic across TP/SL than most other
    instruments tuned so far (see RULES.md), so treat with a bit more
    caution than the cleaner single-peak results on other instruments.
    """
    if len(candles) < MIN_CANDLES_REQUIRED:
        logger.warning(
            "%s: only %d candles available (need >=%d), returning WAIT",
            symbol, len(candles), MIN_CANDLES_REQUIRED,
        )
        return Signal("WAIT")

    mom = ind.momentum(candles["close"], n=MOMENTUM_PERIOD)
    mom_now, mom_prev = mom.iloc[-1], mom.iloc[-2]
    signal_time = candles["date"].iloc[-1]

    cross_up = mom_now > 0 and mom_prev <= 0
    cross_down = mom_now < 0 and mom_prev >= 0

    logger.info(
        "%s: momentum=%.2f (prev=%.2f) cross_up=%s cross_down=%s",
        symbol, mom_now, mom_prev, cross_up, cross_down,
    )

    if cross_up:
        return Signal("BUY", signal_time)
    if cross_down:
        return Signal("SELL", signal_time)
    return Signal("WAIT")
