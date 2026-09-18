from __future__ import annotations

import logging
from dataclasses import dataclass

import pandas as pd

import indicators as ind

logger = logging.getLogger("alpha.stochastic_signal")

K_PERIOD = 14
K_SMOOTH = 3
OVERSOLD = 20
OVERBOUGHT = 80
MIN_CANDLES_REQUIRED = K_PERIOD + K_SMOOTH + 2


@dataclass
class Signal:
    direction: str  # "BUY", "SELL", or "WAIT"
    signal_candle_time: pd.Timestamp | None = None


def get_signal(symbol: str, candles: pd.DataFrame) -> Signal:
    """Stochastic %K(14,3) overbought/oversold: BUY when %K crosses back UP
    through 20 (recovering from oversold), SELL when it crosses back DOWN
    through 80 (falling from overbought).

    Backtested as the best of 27+ strategies tested on 1000 days of real
    FEDERALBNK and TATAPOWER 5-min data (FEDERALBNK: TP=10/SL=4.8, 51.1% win
    rate, net of realistic F&O costs Rs93.34/trade -- see RULES.md).
    """
    if len(candles) < MIN_CANDLES_REQUIRED:
        logger.warning(
            "%s: only %d candles available (need >=%d), returning WAIT",
            symbol, len(candles), MIN_CANDLES_REQUIRED,
        )
        return Signal("WAIT")

    k = ind.stochastic_k(candles["high"], candles["low"], candles["close"], n=K_PERIOD, smooth=K_SMOOTH)
    k_now, k_prev = k.iloc[-1], k.iloc[-2]
    signal_time = candles["date"].iloc[-1]

    cross_up = k_now > OVERSOLD and k_prev <= OVERSOLD
    cross_down = k_now < OVERBOUGHT and k_prev >= OVERBOUGHT

    logger.info(
        "%s: stoch_k=%.2f (prev=%.2f) cross_up=%s cross_down=%s",
        symbol, k_now, k_prev, cross_up, cross_down,
    )

    if cross_up:
        return Signal("BUY", signal_time)
    if cross_down:
        return Signal("SELL", signal_time)
    return Signal("WAIT")
