import pandas as pd
import numpy as np

class Indicators:
    def __init__(self) -> None:
        pass

    @staticmethod
    def MACD(data, a=12, b=26, c=9):
        df = data.copy()
        df["MACD_fast"] = df["Adj Close"].ewm(span=a, min_periods=a).mean()
        df["MACD_slow"] = df["Adj Close"].ewm(span=b, min_periods=b).mean()
        df["MACD"] = df["MACD_fast"] - df["MACD_slow"]
        df["Signal"] = df["MACD"].ewm(span=c, min_periods=c).mean()
        return df[["MACD", "Signal"]]

    @staticmethod
    def ATR(data, n=14):
        df = data.copy()
        df["H-L"] = df["High"] - df["Low"]
        df["H-PC"] = df["High"] - df["Adj Close"].shift(1)
        df["L-PC"] = df["Low"] - df["Adj Close"].shift(1)
        df["TR"] = df[["H-L", "H-PC", "L-PC"]].max(axis=1, skipna=False)
        df["ATR"] = df["TR"].ewm(com=n, min_periods=n).mean()
        return df["ATR"]

    @staticmethod
    def Bollinger_Band(data, n=14):
        df = data.copy()
        df["MiddleBand"] = df["Adj Close"].rolling(n).mean()
        df["UpperBand"] = df["MiddleBand"] + 2 * df["Adj Close"].rolling(n).std(ddof=0)
        df["LowerBand"] = df["MiddleBand"] - 2 * df["Adj Close"].rolling(n).std(ddof=0)
        df["BB_Width"] = df["UpperBand"] - df["LowerBand"]
        return df[["MiddleBand", "UpperBand", "LowerBand", "BB_Width"]]

    @staticmethod
    def RSI(data, n=14):
        df = data.copy()
        df["Change"] = df["Adj Close"] - df["Adj Close"].shift(1)
        df["Gain"] = np.where(df["Change"] >= 0, df["Change"], 0)
        df["Loss"] = np.where(df["Change"] < 0, -1 * df["Change"], 0)
        df["AvgGain"] = df["Gain"].ewm(alpha=1/n, min_periods=n).mean()
        df["AvgLoss"] = df["Loss"].ewm(alpha=1/n, min_periods=n).mean()
        df["rs"] = df["AvgGain"] / df["AvgLoss"]
        df["RSI"] = 100 - (100 / (1 + df["rs"]))
        return df["RSI"]

    @staticmethod
    def ADX(data, n=20):
        df = data.copy()
        df["ATR"] = Indicators.ATR(data, n)
        df["upmove"] = df["High"] - df["High"].shift(1)
        df["downmove"] = df["Low"].shift(1) - df["Low"]
        df["+dm"] = np.where((df["upmove"] > df["downmove"]) & (df["upmove"] > 0), df["upmove"], 0)
        df["-dm"] = np.where((df["downmove"] > df["upmove"]) & (df["downmove"] > 0), df["downmove"], 0)
        df["+di"] = 100 * (df["+dm"] / df["ATR"]).ewm(com=n, min_periods=n).mean()
        df["-di"] = 100 * (df["-dm"] / df["ATR"]).ewm(com=n, min_periods=n).mean()
        df["ADX"] = 100 * abs((df["+di"] - df["-di"]) / (df["+di"] + df["-di"])).ewm(com=n, min_periods=n).mean()
        return df["ADX"]

    @staticmethod
    def strategy_builder(data, take_profit=50, stop_loss=100, initial_capital=10000):
        data[["MACD", "Signal"]] = Indicators.MACD(data)
        data["ADX"] = Indicators.ADX(data)
        data["RSI"] = Indicators.RSI(data)
        data["ATR"] = Indicators.ATR(data)

        positions = []
        capital = initial_capital
        open_trade = None

        for index, row in data.iterrows():
            if open_trade is None:
                if row['MACD'] > row['Signal'] and row['ADX'] > 25 and row['RSI'] < 30:
                    # Buy signal
                    open_trade = {
                        'Type': 'Long',
                        'EntryDate': index,
                        'EntryPrice': row['Adj Close'],
                        'TakeProfit': row['Adj Close'] + take_profit,
                        'StopLoss': row['Adj Close'] - stop_loss
                    }
                elif row['MACD'] < row['Signal'] and row['ADX'] > 25 and row['RSI'] > 70:
                    # Sell signal
                    open_trade = {
                        'Type': 'Short',
                        'EntryDate': index,
                        'EntryPrice': row['Adj Close'],
                        'TakeProfit': row['Adj Close'] - take_profit,
                        'StopLoss': row['Adj Close'] + stop_loss
                    }

            if open_trade is not None:
                if open_trade['Type'] == 'Long':
                    if row['High'] >= open_trade['TakeProfit']:
                        # Close long position with profit
                        exit_price = open_trade['TakeProfit']
                        capital += exit_price - open_trade['EntryPrice']
                        open_trade['ExitDate'] = index
                        open_trade['ExitPrice'] = exit_price
                        open_trade['Profit'] = exit_price - open_trade['EntryPrice']
                        positions.append(open_trade)
                        open_trade = None
                    elif row['Low'] <= open_trade['StopLoss']:
                        # Close long position with loss
                        exit_price = open_trade['StopLoss']
                        capital += exit_price - open_trade['EntryPrice']
                        open_trade['ExitDate'] = index
                        open_trade['ExitPrice'] = exit_price
                        open_trade['Profit'] = exit_price - open_trade['EntryPrice']
                        positions.append(open_trade)
                        open_trade = None

                elif open_trade['Type'] == 'Short':
                    if row['Low'] <= open_trade['TakeProfit']:
                        # Close short position with profit
                        exit_price = open_trade['TakeProfit']
                        capital += open_trade['EntryPrice'] - exit_price
                        open_trade['ExitDate'] = index
                        open_trade['ExitPrice'] = exit_price
                        open_trade['Profit'] = open_trade['EntryPrice'] - exit_price
                        positions.append(open_trade)
                        open_trade = None
                    elif row['High'] >= open_trade['StopLoss']:
                        # Close short position with loss
                        exit_price = open_trade['StopLoss']
                        capital += open_trade['EntryPrice'] - exit_price
                        open_trade['ExitDate'] = index
                        open_trade['ExitPrice'] = exit_price
                        open_trade['Profit'] = open_trade['EntryPrice'] - exit_price
                        positions.append(open_trade)
                        open_trade = None

        positions_df = pd.DataFrame(positions)
        total_profit = positions_df['Profit'].sum()
        total_trades = len(positions_df)
        winning_trades = positions_df[positions_df['Profit'] > 0].shape[0]
        losing_trades = positions_df[positions_df['Profit'] <= 0].shape[0]
        win_rate = (winning_trades / total_trades) * 100 if total_trades > 0 else 0

        print(f"Initial Capital: {initial_capital}")
        print(f"Final Capital: {capital}")
        print(f"Total Profit: {total_profit}")
        print(f"Total Trades: {total_trades}")
        print(f"Winning Trades: {winning_trades}")
        print(f"Losing Trades: {losing_trades}")
        print(f"Win Rate: {win_rate:.2f}%")

        positions_df.to_csv('positions_with_signal.csv')
