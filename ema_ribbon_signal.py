from __future__ import annotations

import logging
from dataclasses import dataclass

import pandas as pd

import indicators as ind

logger = logging.getLogger("alpha.ema_ribbon_signal")

FAST_PERIOD = 9
MID_PERIOD = 21
SLOW_PERIOD = 50
MIN_CANDLES_REQUIRED = SLOW_PERIOD + 2


@dataclass
class Signal:
    direction: str  # "BUY", "SELL", or "WAIT"
    signal_candle_time: pd.Timestamp | None = None


def get_signal(symbol: str, candles: pd.DataFrame) -> Signal:
    """3-EMA Ribbon Alignment (9/21/50): BUY when the three EMAs first align
    bullishly (9 > 21 > 50), SELL when they first align bearishly
    (9 < 21 < 50). Fires only on the candle where full alignment is first
    reached, not every candle it remains aligned.

    Backtested as the best of 27+ strategies tested on 1000 days of real
    BANKBARODA 5-min data (TP=10/SL=4.8, 49.5% win rate, net of realistic
    F&O costs Rs54.63/trade -- see RULES.md).
    """
    if len(candles) < MIN_CANDLES_REQUIRED:
        logger.warning(
            "%s: only %d candles available (need >=%d), returning WAIT",
            symbol, len(candles), MIN_CANDLES_REQUIRED,
        )
        return Signal("WAIT")

    close = candles["close"]
    fast = ind.ema(close, FAST_PERIOD)
    mid = ind.ema(close, MID_PERIOD)
    slow = ind.ema(close, SLOW_PERIOD)

    bullish_now = fast.iloc[-1] > mid.iloc[-1] > slow.iloc[-1]
    bullish_prev = fast.iloc[-2] > mid.iloc[-2] > slow.iloc[-2]
    bearish_now = fast.iloc[-1] < mid.iloc[-1] < slow.iloc[-1]
    bearish_prev = fast.iloc[-2] < mid.iloc[-2] < slow.iloc[-2]
    signal_time = candles["date"].iloc[-1]

    buy_signal = bullish_now and not bullish_prev
    sell_signal = bearish_now and not bearish_prev

    logger.info(
        "%s: ema9=%.2f ema21=%.2f ema50=%.2f bullish=%s bearish=%s buy=%s sell=%s",
        symbol, fast.iloc[-1], mid.iloc[-1], slow.iloc[-1], bullish_now, bearish_now,
        buy_signal, sell_signal,
    )

    if buy_signal:
        return Signal("BUY", signal_time)
    if sell_signal:
        return Signal("SELL", signal_time)
    return Signal("WAIT")
