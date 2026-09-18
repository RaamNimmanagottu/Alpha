from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date

import pandas as pd

logger = logging.getLogger("alpha.opening_range_breakout_signal")

RANGE_CANDLES = 3  # first 3 five-minute candles = first 15 minutes of the day
MIN_CANDLES_REQUIRED = RANGE_CANDLES + 2


@dataclass
class Signal:
    direction: str  # "BUY", "SELL", or "WAIT"
    signal_candle_time: pd.Timestamp | None = None


def get_signal(symbol: str, candles: pd.DataFrame) -> Signal:
    """Opening Range Breakout: the first 3 five-minute candles of today
    (first 15 minutes) define today's range -- high = the max high, low =
    the min low, of just those candles. A later candle's CLOSE confirming a
    break above the range high fires BUY (a wick alone doesn't count); a
    close confirming a break below fires SELL. Only fires on the candle
    where the break first happens, not every candle that remains beyond the
    range afterward -- though a fresh break (out, back in, out again) does
    fire again.

    Backtested as the best of 27+ strategies tested on 1000 days of real
    IDFCFIRSTB 5-min data (TP=1.72/SL=0.82, 50.2% win rate, net of realistic
    F&O costs Rs130.24/trade -- the best net/trade of any instrument tested
    so far, see RULES.md).
    """
    if len(candles) < MIN_CANDLES_REQUIRED:
        logger.warning(
            "%s: only %d candles available (need >=%d), returning WAIT",
            symbol, len(candles), MIN_CANDLES_REQUIRED,
        )
        return Signal("WAIT")

    today: date = candles["date"].iloc[-1].date()
    today_candles = candles[candles["date"].dt.date == today]
    if len(today_candles) <= RANGE_CANDLES:
        # Still within (or before) the opening range itself -- no breakout
        # can be evaluated yet today.
        return Signal("WAIT")

    range_candles = today_candles.iloc[:RANGE_CANDLES]
    range_high = range_candles["high"].max()
    range_low = range_candles["low"].min()

    post_range = today_candles.iloc[RANGE_CANDLES:]
    close_now, close_prev = post_range["close"].iloc[-1], (
        post_range["close"].iloc[-2] if len(post_range) >= 2 else None
    )
    signal_time = today_candles["date"].iloc[-1]

    above_now = close_now > range_high
    below_now = close_now < range_low
    above_prev = close_prev is not None and close_prev > range_high
    below_prev = close_prev is not None and close_prev < range_low

    breakout_up = above_now and not above_prev
    breakout_down = below_now and not below_prev

    logger.info(
        "%s: close=%.2f range_high=%.2f range_low=%.2f breakout_up=%s breakout_down=%s",
        symbol, close_now, range_high, range_low, breakout_up, breakout_down,
    )

    if breakout_up:
        return Signal("BUY", signal_time)
    if breakout_down:
        return Signal("SELL", signal_time)
    return Signal("WAIT")
