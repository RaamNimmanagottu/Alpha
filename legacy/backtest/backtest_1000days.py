"""Full-indicator backtest over the 1000-day NIFTY dataset (backtest/fetch_nifty_1000_days.py).

Reads the 1000-day candle file, computes a broad indicator set, and generates
signals + trade P&L exactly the same way as the 100-day backtest
(backtest/run_signals.py) -- the extra indicators added here (EMA/SMA/Supertrend/
Williams %R/Keltner Channels) are reference columns only and do NOT change what
drives the BUY/SELL signal, which still comes from alpha.local_signals.vote_direction
(RSI/Stochastic/CCI/ADX/Awesome Oscillator/Momentum) -- the same rule the live bot
uses.

Indicators computed:
  Trend:               EMA(9,21,50), SMA(20), MACD+signal, ADX, Supertrend
  Momentum/Oscillators: RSI, Stochastic %K, CCI, Williams %R
  Volatility:           Bollinger Bands, ATR, Keltner Channels
  (plus Awesome Oscillator, Momentum, and classic pivot points, needed for the signal
  itself and for parity with backtest/prepare_data.py)

Run with (from the project root E:\\Alpha):
    .venv\\Scripts\\python.exe backtest\\backtest_1000days.py

Reads backtest/data/NIFTY_five_minute_1000days.xlsx and writes
backtest/data/NIFTY_five_minute_1000days_signals.xlsx (Candles + Trades sheets).
"""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BACKTEST_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(BACKTEST_DIR))

import pandas as pd

from alpha import indicators as ind
from run_signals import generate_signals, print_summary, simulate_trades

SOURCE_FILE = Path(__file__).resolve().parent / "data" / "NIFTY_five_minute_1000days.xlsx"
OUTPUT_FILE = Path(__file__).resolve().parent / "data" / "NIFTY_five_minute_1000days_signals.xlsx"


def add_full_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """`df` must be sorted ASCENDING by date -- see the note in
    backtest/prepare_data.py about why rolling/ewm indicators require that."""
    df = df.sort_values("date").reset_index(drop=True)
    close, high, low = df["close"], df["high"], df["low"]

    # Trend
    df["ema_9"] = ind.ema(close, 9)
    df["ema_21"] = ind.ema(close, 21)
    df["ema_50"] = ind.ema(close, 50)
    df["sma_20"] = ind.sma(close, 20)
    df["macd"], df["macd_signal"] = ind.macd(close)
    df["adx"] = ind.adx(high, low, close)
    df["supertrend"], df["supertrend_direction"] = ind.supertrend(high, low, close)

    # Momentum / oscillators
    df["rsi"] = ind.rsi(close)
    df["stoch_k"] = ind.stochastic_k(high, low, close)
    df["cci20"] = ind.cci(high, low, close)
    df["williams_r"] = ind.williams_r(high, low, close)

    # Volatility
    df["bb_middle"], df["bb_upper"], df["bb_lower"] = ind.bollinger_bands(close)
    df["atr"] = ind.atr(high, low, close)
    df["kc_middle"], df["kc_upper"], df["kc_lower"] = ind.keltner_channels(high, low, close)

    # Needed by alpha.local_signals.vote_direction (the actual signal source)
    df["awesome_oscillator"] = ind.awesome_oscillator(high, low)
    df["momentum"] = ind.momentum(close)

    return df


def main() -> int:
    if not SOURCE_FILE.exists():
        print(f"No 1000-day data found at {SOURCE_FILE}")
        print("Run backtest/fetch_nifty_1000_days.py first.")
        return 1

    df = pd.read_excel(SOURCE_FILE)
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)

    df = add_full_indicators(df)
    df = generate_signals(df)
    df, trades_df = simulate_trades(df)

    print_summary(trades_df)

    with pd.ExcelWriter(OUTPUT_FILE) as writer:
        df.sort_values("date", ascending=False).to_excel(writer, sheet_name="Candles", index=False)
        trades_df.to_excel(writer, sheet_name="Trades", index=False)
    print(f"Written to {OUTPUT_FILE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
