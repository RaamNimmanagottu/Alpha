from __future__ import annotations

import logging
from dataclasses import dataclass

import pandas as pd

import indicators as ind

logger = logging.getLogger("alpha.rsi_oversold_signal")

RSI_PERIOD = 14
OVERSOLD = 30
OVERBOUGHT = 70
MIN_CANDLES_REQUIRED = RSI_PERIOD + 2


@dataclass
class Signal:
    direction: str  # "BUY", "SELL", or "WAIT"
    signal_candle_time: pd.Timestamp | None = None


def get_signal(symbol: str, candles: pd.DataFrame) -> Signal:
    """RSI(14) overbought/oversold: BUY when RSI crosses back UP through 30
    ("coming out of oversold"), SELL when it crosses back DOWN through 70
    ("coming out of overbought") -- not just "RSI is currently past the line",
    which would re-fire every candle while it stays there.

    Backtested as the best of 26 strategies tested on ~100 days of real
    BANKNIFTY 5-min data -- the EMA9/21 crossover that wins for NIFTY actually
    LOSES money on BANKNIFTY (see instrument_engine.py's per-instrument
    signal_strategy dispatch, config.yaml's signal_strategy field). Sample-size
    caveat: 100 days, not NIFTY's 1000-day validation -- a starting point to
    refine with more live/paper data over time, not NIFTY-level evidence.
    """
    if len(candles) < MIN_CANDLES_REQUIRED:
        logger.warning(
            "%s: only %d candles available (need >=%d), returning WAIT",
            symbol, len(candles), MIN_CANDLES_REQUIRED,
        )
        return Signal("WAIT")

    rsi = ind.rsi(candles["close"], RSI_PERIOD)
    rsi_now, rsi_prev = rsi.iloc[-1], rsi.iloc[-2]
    signal_time = candles["date"].iloc[-1]

    cross_up_from_oversold = rsi_now > OVERSOLD and rsi_prev <= OVERSOLD
    cross_down_from_overbought = rsi_now < OVERBOUGHT and rsi_prev >= OVERBOUGHT

    logger.info(
        "%s: rsi=%.2f (prev=%.2f) cross_up_from_oversold=%s cross_down_from_overbought=%s",
        symbol, rsi_now, rsi_prev, cross_up_from_oversold, cross_down_from_overbought,
    )

    if cross_up_from_oversold:
        return Signal("BUY", signal_time)
    if cross_down_from_overbought:
        return Signal("SELL", signal_time)
    return Signal("WAIT")
