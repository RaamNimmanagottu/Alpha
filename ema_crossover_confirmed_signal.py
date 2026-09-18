from __future__ import annotations

import logging
from dataclasses import dataclass

import pandas as pd

import indicators as ind

logger = logging.getLogger("alpha.ema_crossover_confirmed_signal")

FAST_PERIOD = 9
SLOW_PERIOD = 21
CONFIRM_CANDLES = 2
MIN_CANDLES_REQUIRED = SLOW_PERIOD + CONFIRM_CANDLES + 2


@dataclass
class Signal:
    direction: str  # "BUY", "SELL", or "WAIT"
    signal_candle_time: pd.Timestamp | None = None


def get_signal(symbol: str, candles: pd.DataFrame) -> Signal:
    """EMA(9)/EMA(21) crossover, but requires the fast EMA to stay on the same
    side of the slow EMA for 2 consecutive candles before firing -- filters
    out single-candle whipsaws that cross and immediately reverse, at the
    cost of entering one candle later than the raw crossover.

    Backtested as the best of 27+ strategies tested on 1000 days of real
    INFY 5-min data (TP=35/SL=17, 51.57% win rate, +613.60 points). Note this
    is the OPPOSITE conclusion from what 2026-09-18's NIFTY-specific testing
    found (there, ANY confirmation delay made results worse, see RULES.md
    Lesson #3) -- yet another instrument-specific result, not a general rule.
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
    above = fast > slow

    # Confirmed at candle i if `above` (or its negation) has held for the last
    # CONFIRM_CANDLES candles including i. Fire only on the candle where
    # confirmation just completed, not on every candle it remains true.
    confirmed_above_now = bool(above.iloc[-CONFIRM_CANDLES:].all())
    confirmed_above_prev = bool(above.iloc[-CONFIRM_CANDLES - 1:-1].all())
    below = ~above
    confirmed_below_now = bool(below.iloc[-CONFIRM_CANDLES:].all())
    confirmed_below_prev = bool(below.iloc[-CONFIRM_CANDLES - 1:-1].all())

    signal_time = candles["date"].iloc[-1]

    buy_signal = confirmed_above_now and not confirmed_above_prev
    sell_signal = confirmed_below_now and not confirmed_below_prev

    logger.info(
        "%s: ema9=%.2f ema21=%.2f confirmed_above=%s confirmed_below=%s buy=%s sell=%s",
        symbol, fast.iloc[-1], slow.iloc[-1], confirmed_above_now, confirmed_below_now,
        buy_signal, sell_signal,
    )

    if buy_signal:
        return Signal("BUY", signal_time)
    if sell_signal:
        return Signal("SELL", signal_time)
    return Signal("WAIT")
