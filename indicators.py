from __future__ import annotations

import numpy as np
import pandas as pd


def sma(close: pd.Series, n: int = 20) -> pd.Series:
    return close.rolling(n).mean()


def ema(close: pd.Series, n: int) -> pd.Series:
    return close.ewm(span=n, adjust=False, min_periods=n).mean()


def rsi(close: pd.Series, n: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / n, min_periods=n).mean()
    avg_loss = loss.ewm(alpha=1 / n, min_periods=n).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def stochastic_k(high: pd.Series, low: pd.Series, close: pd.Series, n: int = 14, smooth: int = 3) -> pd.Series:
    lowest_low = low.rolling(n).min()
    highest_high = high.rolling(n).max()
    raw_k = 100 * (close - lowest_low) / (highest_high - lowest_low)
    return raw_k.rolling(smooth).mean()


def cci(high: pd.Series, low: pd.Series, close: pd.Series, n: int = 20) -> pd.Series:
    typical_price = (high + low + close) / 3
    sma = typical_price.rolling(n).mean()
    mean_dev = typical_price.rolling(n).apply(lambda x: np.abs(x - x.mean()).mean(), raw=True)
    return (typical_price - sma) / (0.015 * mean_dev)


def adx(high: pd.Series, low: pd.Series, close: pd.Series, n: int = 14) -> pd.Series:
    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = pd.Series(np.where((up_move > down_move) & (up_move > 0), up_move, 0.0), index=high.index)
    minus_dm = pd.Series(np.where((down_move > up_move) & (down_move > 0), down_move, 0.0), index=high.index)

    tr = pd.concat(
        [high - low, (high - close.shift(1)).abs(), (low - close.shift(1)).abs()], axis=1
    ).max(axis=1)
    atr = tr.ewm(alpha=1 / n, min_periods=n).mean()

    plus_di = 100 * plus_dm.ewm(alpha=1 / n, min_periods=n).mean() / atr
    minus_di = 100 * minus_dm.ewm(alpha=1 / n, min_periods=n).mean() / atr
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di)
    return dx.ewm(alpha=1 / n, min_periods=n).mean()


def awesome_oscillator(high: pd.Series, low: pd.Series, fast: int = 5, slow: int = 34) -> pd.Series:
    median_price = (high + low) / 2
    return median_price.rolling(fast).mean() - median_price.rolling(slow).mean()


def momentum(close: pd.Series, n: int = 10) -> pd.Series:
    return close - close.shift(n)


def macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> tuple[pd.Series, pd.Series]:
    ema_fast = close.ewm(span=fast, min_periods=fast).mean()
    ema_slow = close.ewm(span=slow, min_periods=slow).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, min_periods=signal).mean()
    return macd_line, signal_line


def atr(high: pd.Series, low: pd.Series, close: pd.Series, n: int = 14) -> pd.Series:
    tr = pd.concat(
        [high - low, (high - close.shift(1)).abs(), (low - close.shift(1)).abs()], axis=1
    ).max(axis=1)
    return tr.ewm(alpha=1 / n, min_periods=n).mean()


def bollinger_bands(close: pd.Series, n: int = 20, num_std: float = 2) -> tuple[pd.Series, pd.Series, pd.Series]:
    middle = close.rolling(n).mean()
    std = close.rolling(n).std(ddof=0)
    upper = middle + num_std * std
    lower = middle - num_std * std
    return middle, upper, lower


def williams_r(high: pd.Series, low: pd.Series, close: pd.Series, n: int = 14) -> pd.Series:
    highest_high = high.rolling(n).max()
    lowest_low = low.rolling(n).min()
    return -100 * (highest_high - close) / (highest_high - lowest_low)


def keltner_channels(
    high: pd.Series, low: pd.Series, close: pd.Series, ema_n: int = 20, atr_n: int = 10, multiplier: float = 2
) -> tuple[pd.Series, pd.Series, pd.Series]:
    middle = ema(close, ema_n)
    band = multiplier * atr(high, low, close, atr_n)
    return middle, middle + band, middle - band


def supertrend(
    high: pd.Series, low: pd.Series, close: pd.Series, n: int = 10, multiplier: float = 3.0
) -> tuple[pd.Series, pd.Series]:
    """Returns (supertrend_line, direction) where direction is +1 (uptrend, price
    above the line) or -1 (downtrend, price below the line).

    Unlike the other indicators here, Supertrend is recursive -- each bar's final
    upper/lower band and trend flip depend on the previous bar's values, not just a
    fixed rolling window -- so it's computed with an explicit loop rather than
    vectorized pandas/numpy ops.
    """
    atr_series = atr(high, low, close, n)
    hl2 = (high + low) / 2
    basic_upper = (hl2 + multiplier * atr_series).to_numpy()
    basic_lower = (hl2 - multiplier * atr_series).to_numpy()
    close_arr = close.to_numpy()
    n_rows = len(close_arr)

    final_upper = np.full(n_rows, np.nan)
    final_lower = np.full(n_rows, np.nan)
    st = np.full(n_rows, np.nan)
    direction = np.zeros(n_rows)

    for i in range(n_rows):
        if np.isnan(basic_upper[i]) or np.isnan(basic_lower[i]):
            continue
        if np.isnan(st[i - 1]) if i > 0 else True:
            final_upper[i] = basic_upper[i]
            final_lower[i] = basic_lower[i]
            st[i] = final_upper[i]
            direction[i] = -1
            continue

        final_upper[i] = (
            basic_upper[i]
            if (basic_upper[i] < final_upper[i - 1] or close_arr[i - 1] > final_upper[i - 1])
            else final_upper[i - 1]
        )
        final_lower[i] = (
            basic_lower[i]
            if (basic_lower[i] > final_lower[i - 1] or close_arr[i - 1] < final_lower[i - 1])
            else final_lower[i - 1]
        )

        if st[i - 1] == final_upper[i - 1]:
            if close_arr[i] <= final_upper[i]:
                st[i], direction[i] = final_upper[i], -1
            else:
                st[i], direction[i] = final_lower[i], 1
        else:
            if close_arr[i] >= final_lower[i]:
                st[i], direction[i] = final_lower[i], 1
            else:
                st[i], direction[i] = final_upper[i], -1

    return pd.Series(st, index=close.index), pd.Series(direction, index=close.index)


def classic_pivot_points(prev_day_high: float, prev_day_low: float, prev_day_close: float) -> dict[str, float]:
    """Standard floor/classic pivot points computed from one completed day's H/L/C."""
    pivot = (prev_day_high + prev_day_low + prev_day_close) / 3
    r1 = 2 * pivot - prev_day_low
    s1 = 2 * pivot - prev_day_high
    r2 = pivot + (prev_day_high - prev_day_low)
    s2 = pivot - (prev_day_high - prev_day_low)
    return {"pivot": pivot, "r1": r1, "s1": s1, "r2": r2, "s2": s2}
