from __future__ import annotations

import logging
from dataclasses import dataclass

import pandas as pd

import indicators as ind

logger = logging.getLogger("alpha.keltner_channel_signal")

EMA_PERIOD = 20
ATR_PERIOD = 10
MULTIPLIER = 2.0
MIN_CANDLES_REQUIRED = max(EMA_PERIOD, ATR_PERIOD) + 2


@dataclass
class Signal:
    direction: str  # "BUY", "SELL", or "WAIT"
    signal_candle_time: pd.Timestamp | None = None


def get_signal(symbol: str, candles: pd.DataFrame) -> Signal:
    """Keltner Channel breakout: BUY when close crosses above the upper band,
    SELL when close crosses below the lower band -- a trend/breakout
    confirmation signal (not mean-reversion, unlike Bollinger).

    Backtested as the best of 27 strategies tested on 1000 days of real
    FINNIFTY 5-min data -- both EMA9/21 crossover (NIFTY's winner) and RSI
    overbought/oversold (BANKNIFTY's winner) underperform this on FINNIFTY, a
    THIRD distinct result across our three index instruments so far. See
    RULES.md and instrument_engine.py's per-instrument signal_strategy dispatch.
    """
    if len(candles) < MIN_CANDLES_REQUIRED:
        logger.warning(
            "%s: only %d candles available (need >=%d), returning WAIT",
            symbol, len(candles), MIN_CANDLES_REQUIRED,
        )
        return Signal("WAIT")

    _, upper, lower = ind.keltner_channels(
        candles["high"], candles["low"], candles["close"], ema_n=EMA_PERIOD, atr_n=ATR_PERIOD, multiplier=MULTIPLIER
    )
    close = candles["close"]
    close_now, close_prev = close.iloc[-1], close.iloc[-2]
    upper_now, upper_prev = upper.iloc[-1], upper.iloc[-2]
    lower_now, lower_prev = lower.iloc[-1], lower.iloc[-2]
    signal_time = candles["date"].iloc[-1]

    cross_up = close_now > upper_now and close_prev <= upper_prev
    cross_down = close_now < lower_now and close_prev >= lower_prev

    logger.info(
        "%s: close=%.2f upper=%.2f lower=%.2f cross_up=%s cross_down=%s",
        symbol, close_now, upper_now, lower_now, cross_up, cross_down,
    )

    if cross_up:
        return Signal("BUY", signal_time)
    if cross_down:
        return Signal("SELL", signal_time)
    return Signal("WAIT")
