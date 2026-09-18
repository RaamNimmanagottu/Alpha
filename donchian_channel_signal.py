from __future__ import annotations

import logging
from dataclasses import dataclass

import pandas as pd

logger = logging.getLogger("alpha.donchian_channel_signal")

CHANNEL_PERIOD = 20
MIN_CANDLES_REQUIRED = CHANNEL_PERIOD + 2


@dataclass
class Signal:
    direction: str  # "BUY", "SELL", or "WAIT"
    signal_candle_time: pd.Timestamp | None = None


def get_signal(symbol: str, candles: pd.DataFrame) -> Signal:
    """Donchian Channel(20) breakout: BUY when close breaks above the prior
    20-candle high, SELL when it breaks below the prior 20-candle low.

    Backtested as the best of 27+ strategies tested on 1000 days of real
    CRUDEOIL 5-min data (TP=150/SL=75, 45.96% win rate, +6092.00 points).
    Note (see RULES.md): ~88-98% of trades exit on time rather than TP/SL,
    and the real worst-case single-trade loss (128pts) exceeds the nominal
    stop-loss at every TP/SL setting tested -- day-end force-exit risk is
    much more pronounced here than on index instruments. Treat with extra
    caution even in paper mode.
    """
    if len(candles) < MIN_CANDLES_REQUIRED:
        logger.warning(
            "%s: only %d candles available (need >=%d), returning WAIT",
            symbol, len(candles), MIN_CANDLES_REQUIRED,
        )
        return Signal("WAIT")

    high, low, close = candles["high"], candles["low"], candles["close"]
    # Prior N candles' high/low, excluding the current candle -- shift(1)
    # before taking .iloc[-1] would double-shift, so slice the window ending
    # at the second-to-last row instead.
    prior_high = high.iloc[-CHANNEL_PERIOD - 1:-1].max()
    prior_low = low.iloc[-CHANNEL_PERIOD - 1:-1].min()
    close_now = close.iloc[-1]
    signal_time = candles["date"].iloc[-1]

    breakout_up = close_now > prior_high
    breakout_down = close_now < prior_low

    logger.info(
        "%s: close=%.2f prior_high=%.2f prior_low=%.2f breakout_up=%s breakout_down=%s",
        symbol, close_now, prior_high, prior_low, breakout_up, breakout_down,
    )

    if breakout_up:
        return Signal("BUY", signal_time)
    if breakout_down:
        return Signal("SELL", signal_time)
    return Signal("WAIT")
