from __future__ import annotations

import logging
from dataclasses import dataclass

from tradingview_ta import Interval, TA_Handler

logger = logging.getLogger("alpha.signals")


@dataclass
class Signal:
    direction: str  # "BUY", "SELL", or "WAIT"
    pivot: float
    resistance: float
    support: float


def get_signal(symbol: str, ltp: float) -> Signal:
    handler = TA_Handler(
        symbol=symbol,
        screener="india",
        exchange="NSE",
        interval=Interval.INTERVAL_5_MINUTES,
    )
    analysis = handler.get_analysis()

    rsi = analysis.indicators["RSI"]
    stoch = analysis.indicators["Stoch.K"]
    cci20 = analysis.indicators["CCI20"]
    adx = analysis.indicators["ADX"]
    ao = analysis.indicators["AO"]
    mom = analysis.indicators["Mom"]

    pivot = analysis.indicators["Pivot.M.Classic.Middle"]
    r1 = analysis.indicators["Pivot.M.Classic.R1"]
    s1 = analysis.indicators["Pivot.M.Classic.S1"]
    r2 = analysis.indicators["Pivot.M.Classic.R2"]
    s2 = analysis.indicators["Pivot.M.Classic.S2"]

    # Widen the support/resistance band we trade against as price extends away from
    # the pivot, using the *instrument's own* ltp only (the original code accidentally
    # compared BankNifty's price against Nifty's pivot levels in one branch).
    support, resistance = s1, r1
    if ltp > r1 + 50:
        support, resistance = s2, s1
    elif ltp - 50 > s1:
        support, resistance = r1, r2

    buy_votes = 0
    sell_votes = 0

    if rsi > 70:
        sell_votes += 1
    elif rsi < 30:
        buy_votes += 1

    if stoch > 80:
        sell_votes += 1
    elif stoch < 20:
        buy_votes += 1

    if cci20 > 100:
        sell_votes += 1
    elif cci20 < -100:
        buy_votes += 1

    strong_trend = adx > 25 or ao > 0
    uptrend = mom > 0

    logger.info(
        "%s: rsi=%.1f stoch=%.1f cci20=%.1f adx=%.1f ao=%.1f mom=%.1f "
        "buy_votes=%d sell_votes=%d strong_trend=%s uptrend=%s "
        "pivot=%.1f r1=%.1f s1=%.1f r2=%.1f s2=%.1f",
        symbol, rsi, stoch, cci20, adx, ao, mom,
        buy_votes, sell_votes, strong_trend, uptrend,
        pivot, r1, s1, r2, s2,
    )

    if buy_votes > 1 and (strong_trend or uptrend):
        direction = "BUY"
    elif sell_votes > 1 and (strong_trend or not uptrend):
        direction = "SELL"
    else:
        direction = "WAIT"

    return Signal(direction=direction, pivot=pivot, resistance=resistance, support=support)
