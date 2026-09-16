"""Strategy-specific BUY/SELL raw-signal generators.

Each function takes the OHLC+indicator dataframe (sorted ascending) and returns a
`raw_signal` Series (values "BUY", "SELL", or None per row) -- fed into
backtest/trade_simulator.py's shared entry/exit engine, which handles timing,
TP/SL, and same-day-only position management identically for every strategy so
results are comparable on equal footing.
"""
from __future__ import annotations

import sys
from functools import partial
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

from alpha import indicators as ind


def macd_crossover(df: pd.DataFrame) -> pd.Series:
    """BUY when the MACD line crosses above its signal line, SELL on the reverse cross."""
    macd, signal = df["macd"], df["macd_signal"]
    cross_up = (macd > signal) & (macd.shift(1) <= signal.shift(1))
    cross_down = (macd < signal) & (macd.shift(1) >= signal.shift(1))
    result = pd.Series(None, index=df.index, dtype=object)
    result[cross_up] = "BUY"
    result[cross_down] = "SELL"
    return result


def rsi_overbought_oversold(df: pd.DataFrame, oversold: float = 30, overbought: float = 70) -> pd.Series:
    """BUY when RSI crosses UP back through the oversold line (was <=30, now >30) --
    "coming out of oversold", not just "RSI is currently low" (which would re-fire
    on every candle while RSI stays under 30). SELL is the symmetric case crossing
    back down through the overbought line."""
    rsi = df["rsi"]
    cross_up_from_oversold = (rsi > oversold) & (rsi.shift(1) <= oversold)
    cross_down_from_overbought = (rsi < overbought) & (rsi.shift(1) >= overbought)
    result = pd.Series(None, index=df.index, dtype=object)
    result[cross_up_from_oversold] = "BUY"
    result[cross_down_from_overbought] = "SELL"
    return result


def ema_crossover(df: pd.DataFrame, fast_col: str = "ema_9", slow_col: str = "ema_21") -> pd.Series:
    """BUY when the fast EMA crosses above the slow EMA, SELL on the reverse cross.
    Default is the 9/21 pair; pass fast_col="ema_21", slow_col="ema_50" for 21/50."""
    fast, slow = df[fast_col], df[slow_col]
    cross_up = (fast > slow) & (fast.shift(1) <= slow.shift(1))
    cross_down = (fast < slow) & (fast.shift(1) >= slow.shift(1))
    result = pd.Series(None, index=df.index, dtype=object)
    result[cross_up] = "BUY"
    result[cross_down] = "SELL"
    return result


def ema_crossover_periods(df: pd.DataFrame, fast: int, slow: int) -> pd.Series:
    """Same rule as ema_crossover, but computes the two EMAs on the fly for any
    period pair -- not limited to the 9/21/50 columns already baked into the data.
    9/21 is probably the single most-watched EMA pair among retail intraday
    traders; testing less-crowded period pairs checks whether that popularity
    itself works against it (everyone's stop sitting at the same level makes that
    level an easy target)."""
    fast_ema = ind.ema(df["close"], fast)
    slow_ema = ind.ema(df["close"], slow)
    cross_up = (fast_ema > slow_ema) & (fast_ema.shift(1) <= slow_ema.shift(1))
    cross_down = (fast_ema < slow_ema) & (fast_ema.shift(1) >= slow_ema.shift(1))
    result = pd.Series(None, index=df.index, dtype=object)
    result[cross_up] = "BUY"
    result[cross_down] = "SELL"
    return result


def ema_crossover_confirmed(
    df: pd.DataFrame, fast_col: str = "ema_9", slow_col: str = "ema_21", confirm_candles: int = 2
) -> pd.Series:
    """Same idea as ema_crossover, but requires the fast EMA to stay on the same
    side of the slow EMA for `confirm_candles` consecutive candles before firing --
    filters out single-candle whipsaws that cross and immediately reverse, at the
    cost of entering a few candles later than the raw crossover on a genuine move.
    """
    fast, slow = df[fast_col], df[slow_col]
    above, below = fast > slow, fast < slow
    confirmed_above = above.rolling(confirm_candles).sum() == confirm_candles
    confirmed_below = below.rolling(confirm_candles).sum() == confirm_candles

    # Fire only on the candle where confirmation completes, not on every candle
    # while it remains confirmed.
    buy_signal = confirmed_above & ~confirmed_above.shift(1, fill_value=False)
    sell_signal = confirmed_below & ~confirmed_below.shift(1, fill_value=False)

    result = pd.Series(None, index=df.index, dtype=object)
    result[buy_signal] = "BUY"
    result[sell_signal] = "SELL"
    return result


def adx_atr_trend(df: pd.DataFrame, adx_threshold: float = 25) -> pd.Series:
    """Trend-following: only act when ADX confirms a strong trend (> threshold),
    direction comes from Supertrend flipping, and ATR is above its own 20-period
    rolling median (skip unusually quiet, low-volatility chop where a trend signal
    is less trustworthy). BUY on a flip to uptrend, SELL on a flip to downtrend,
    both gated by the ADX/ATR filters.
    """
    strong_trend = df["adx"] > adx_threshold
    atr_elevated = df["atr"] > df["atr"].rolling(20).median()
    direction = df["supertrend_direction"]
    flip_up = (direction == 1) & (direction.shift(1) == -1)
    flip_down = (direction == -1) & (direction.shift(1) == 1)

    result = pd.Series(None, index=df.index, dtype=object)
    result[flip_up & strong_trend & atr_elevated] = "BUY"
    result[flip_down & strong_trend & atr_elevated] = "SELL"
    return result


def ema_crossover_low_adx(df: pd.DataFrame, fast_col: str = "ema_9", slow_col: str = "ema_21", adx_max: float = 20) -> pd.Series:
    """Same raw EMA crossover, but only taken when ADX at the crossover candle is
    BELOW adx_max. This is the opposite filter direction from adx_atr_trend --
    backed by analyze_ema_false_crossovers.py, which found win rate on this
    strategy's actual trades *drops* as ADX rises (52.4% at ADX 0-15 down to 39.7%
    at ADX 30+), the reverse of the usual "high ADX confirms the signal" assumption.
    """
    raw = ema_crossover(df, fast_col, slow_col)
    return raw.where(df["adx"] < adx_max)


def opening_range_breakout(df: pd.DataFrame, range_candles: int = 3) -> pd.Series:
    """Opening Range Breakout: the first `range_candles` candles of each trading
    day (3 five-minute candles = the first 15 minutes) define that day's range --
    high = the max high, low = the min low, of just those candles. A LATER candle's
    CLOSE confirming a break above the range high fires BUY (a wick alone doesn't
    count -- the close must actually hold beyond it); a close confirming a break
    below the range low fires SELL. Entry happens at the next candle's open, same
    as every other strategy here (see trade_simulator.py). The candles forming the
    range itself never generate a signal, and only the candle where the break
    first happens fires -- not every candle that remains beyond the range
    afterward, though a fresh break (out, back in, out again) does fire again.
    """
    day = df["date"].dt.date
    is_range_candle = df.groupby(day).cumcount() < range_candles

    range_high = df["high"].where(is_range_candle).groupby(day).transform("max")
    range_low = df["low"].where(is_range_candle).groupby(day).transform("min")

    above_range = (~is_range_candle) & (df["close"] > range_high)
    below_range = (~is_range_candle) & (df["close"] < range_low)

    breakout_up = above_range & ~above_range.groupby(day).shift(1, fill_value=False)
    breakout_down = below_range & ~below_range.groupby(day).shift(1, fill_value=False)

    result = pd.Series(None, index=df.index, dtype=object)
    result[breakout_up] = "BUY"
    result[breakout_down] = "SELL"
    return result


def stochastic_overbought_oversold(df: pd.DataFrame, oversold: float = 20, overbought: float = 80) -> pd.Series:
    """BUY when Stochastic %K crosses UP back through the oversold line, SELL
    crossing back down through the overbought line -- same "coming out of the
    extreme" pattern as rsi_overbought_oversold, applied to stoch_k."""
    k = df["stoch_k"]
    cross_up = (k > oversold) & (k.shift(1) <= oversold)
    cross_down = (k < overbought) & (k.shift(1) >= overbought)
    result = pd.Series(None, index=df.index, dtype=object)
    result[cross_up] = "BUY"
    result[cross_down] = "SELL"
    return result


def cci_overbought_oversold(df: pd.DataFrame, oversold: float = -100, overbought: float = 100) -> pd.Series:
    """BUY when CCI crosses UP back through -100 (oversold), SELL crossing back
    down through +100 (overbought)."""
    cci = df["cci20"]
    cross_up = (cci > oversold) & (cci.shift(1) <= oversold)
    cross_down = (cci < overbought) & (cci.shift(1) >= overbought)
    result = pd.Series(None, index=df.index, dtype=object)
    result[cross_up] = "BUY"
    result[cross_down] = "SELL"
    return result


def williams_r_overbought_oversold(df: pd.DataFrame, oversold: float = -80, overbought: float = -20) -> pd.Series:
    """Williams %R ranges -100 (most oversold) to 0 (most overbought). BUY when it
    crosses UP back through -80, SELL crossing back down through -20."""
    wr = df["williams_r"]
    cross_up = (wr > oversold) & (wr.shift(1) <= oversold)
    cross_down = (wr < overbought) & (wr.shift(1) >= overbought)
    result = pd.Series(None, index=df.index, dtype=object)
    result[cross_up] = "BUY"
    result[cross_down] = "SELL"
    return result


def bollinger_bands_reversal(df: pd.DataFrame) -> pd.Series:
    """Mean-reversion: BUY when close crosses back ABOVE the lower band after
    having been at/below it (a bounce off the bottom), SELL when close crosses
    back BELOW the upper band after having been at/above it (a bounce off the
    top)."""
    close, lower, upper = df["close"], df["bb_lower"], df["bb_upper"]
    was_below_lower = close.shift(1) <= lower.shift(1)
    was_above_upper = close.shift(1) >= upper.shift(1)
    cross_up = (close > lower) & was_below_lower
    cross_down = (close < upper) & was_above_upper
    result = pd.Series(None, index=df.index, dtype=object)
    result[cross_up] = "BUY"
    result[cross_down] = "SELL"
    return result


def keltner_channel_breakout(df: pd.DataFrame) -> pd.Series:
    """Breakout (not reversion, unlike Bollinger here): BUY when close crosses
    above the upper Keltner band, SELL when close crosses below the lower band --
    Keltner's ATR-based bands are conventionally used for trend/breakout
    confirmation rather than mean reversion."""
    close, lower, upper = df["close"], df["kc_lower"], df["kc_upper"]
    cross_up = (close > upper) & (close.shift(1) <= upper.shift(1))
    cross_down = (close < lower) & (close.shift(1) >= lower.shift(1))
    result = pd.Series(None, index=df.index, dtype=object)
    result[cross_up] = "BUY"
    result[cross_down] = "SELL"
    return result


def awesome_oscillator_zero_cross(df: pd.DataFrame) -> pd.Series:
    """BUY when the Awesome Oscillator crosses above zero, SELL crossing below --
    the standard AO zero-line-crossover rule."""
    ao = df["awesome_oscillator"]
    cross_up = (ao > 0) & (ao.shift(1) <= 0)
    cross_down = (ao < 0) & (ao.shift(1) >= 0)
    result = pd.Series(None, index=df.index, dtype=object)
    result[cross_up] = "BUY"
    result[cross_down] = "SELL"
    return result


def momentum_zero_cross(df: pd.DataFrame) -> pd.Series:
    """BUY when Momentum crosses above zero, SELL crossing below."""
    mom = df["momentum"]
    cross_up = (mom > 0) & (mom.shift(1) <= 0)
    cross_down = (mom < 0) & (mom.shift(1) >= 0)
    result = pd.Series(None, index=df.index, dtype=object)
    result[cross_up] = "BUY"
    result[cross_down] = "SELL"
    return result


def sma_price_cross(df: pd.DataFrame) -> pd.Series:
    """BUY when close crosses above its own 20-period SMA, SELL crossing below --
    the simplest possible trend-following rule, included as a baseline."""
    close, sma = df["close"], df["sma_20"]
    cross_up = (close > sma) & (close.shift(1) <= sma.shift(1))
    cross_down = (close < sma) & (close.shift(1) >= sma.shift(1))
    result = pd.Series(None, index=df.index, dtype=object)
    result[cross_up] = "BUY"
    result[cross_down] = "SELL"
    return result


def supertrend_standalone(df: pd.DataFrame) -> pd.Series:
    """BUY when Supertrend flips to uptrend, SELL when it flips to downtrend --
    same flip logic as adx_atr_trend but without the ADX/ATR gating, to see what
    Supertrend alone is worth."""
    direction = df["supertrend_direction"]
    flip_up = (direction == 1) & (direction.shift(1) == -1)
    flip_down = (direction == -1) & (direction.shift(1) == 1)
    result = pd.Series(None, index=df.index, dtype=object)
    result[flip_up] = "BUY"
    result[flip_down] = "SELL"
    return result


STRATEGIES = {
    "MACD Crossover": macd_crossover,
    "RSI Overbought/Oversold": rsi_overbought_oversold,
    "EMA Crossover (9/21)": ema_crossover,
    "EMA Crossover Confirmed (2-candle)": ema_crossover_confirmed,
    "EMA Crossover Low-ADX Filter (<20)": ema_crossover_low_adx,
    "ADX/ATR Trend": adx_atr_trend,
    "Opening Range Breakout (15min)": opening_range_breakout,
    "Stochastic Overbought/Oversold": stochastic_overbought_oversold,
    "CCI Overbought/Oversold": cci_overbought_oversold,
    "Williams %R Overbought/Oversold": williams_r_overbought_oversold,
    "Bollinger Bands Reversal": bollinger_bands_reversal,
    "Keltner Channel Breakout": keltner_channel_breakout,
    "Awesome Oscillator Zero-Cross": awesome_oscillator_zero_cross,
    "Momentum Zero-Cross": momentum_zero_cross,
    "SMA(20) Price Cross": sma_price_cross,
    "Supertrend Standalone": supertrend_standalone,
    "EMA Crossover (3/8)": partial(ema_crossover_periods, fast=3, slow=8),
    "EMA Crossover (5/13)": partial(ema_crossover_periods, fast=5, slow=13),
    "EMA Crossover (8/17)": partial(ema_crossover_periods, fast=8, slow=17),
    "EMA Crossover (10/20)": partial(ema_crossover_periods, fast=10, slow=20),
    "EMA Crossover (13/34)": partial(ema_crossover_periods, fast=13, slow=34),
    "EMA Crossover (21/50)": partial(ema_crossover_periods, fast=21, slow=50),
}


def combine_majority(*signals: pd.Series, min_agree: int = 2) -> pd.Series:
    """Combination strategy: fire BUY/SELL only when at least `min_agree` of the
    given strategy signals agree on the same direction at the same candle."""
    combined = pd.concat(signals, axis=1)
    buy_votes = (combined == "BUY").sum(axis=1)
    sell_votes = (combined == "SELL").sum(axis=1)
    result = pd.Series(None, index=combined.index, dtype=object)
    result[buy_votes >= min_agree] = "BUY"
    result[sell_votes >= min_agree] = "SELL"
    return result
