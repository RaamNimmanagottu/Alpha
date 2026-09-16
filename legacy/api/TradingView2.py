from tradingview_ta import TA_Handler, Interval, Exchange


class TradingViewSignal:
    def get_Signal(symbol,ltp):
        nifty = TA_Handler(
            symbol=symbol,
            screener="india",
            exchange="NSE",
            interval=Interval.INTERVAL_5_MINUTES,
        )
        
        # Get summary and indicator dat
        analysis = nifty.get_analysis()
    
        RSI = analysis.indicators["RSI"]
        Stoch=analysis.indicators["Stoch.K"]
        CCI20=analysis.indicators["CCI20"]
        ADX=analysis.indicators["ADX"]
        AO=analysis.indicators["AO"]
        Mom=analysis.indicators["Mom"]

        EMA = analysis.moving_averages["COMPUTE"]["EMA10"]

        BUYCount = 0
        SellCount = 0
        # Initialize signals
        RsiSignal = StochasticSignal = CCI20Signal = ADXSignal = AOSignal = MomSignal = ""

        Pivot =analysis.indicators["Pivot.M.Classic.Middle"]
        R1 = analysis.indicators["Pivot.M.Classic.R1"]
        S1 = analysis.indicators['Pivot.M.Classic.S1']

        R2 = analysis.indicators["Pivot.M.Classic.R2"]
        S2 = analysis.indicators['Pivot.M.Classic.S2']

        EMA20=analysis.indicators["EMA20"]
        EMA50=analysis.indicators["EMA50"]
        
        if(analysis.moving_averages["RECOMMENDATION"]=="STRONG_SELL" or analysis.moving_averages["RECOMMENDATION"]=="SELL" ):
            MASignal="DOWNTREND"
       
        elif (analysis.moving_averages["RECOMMENDATION"]=="STRONG_BUY" or analysis.moving_averages["RECOMMENDATION"]=="BUY" ):
            MASignal="UPTREND"
        else:
            MASignal=None
            

        Pivot_Siganl=None
        Support=S1
        Resistance=R1

        if(ltp>R1+10):
            Support=R1
            Resistance=R2
        elif (S1-10>ltp):
            Support=S2
            Resistance=S1
            
        # Determine RSI signal
        if RSI > 70:
            RsiSignal = "SELL"
            SellCount += 1
        elif RSI < 30:
            RsiSignal = "BUY"
            BUYCount += 1
        else:
            RsiSignal = "Neutral"

        # Determine Stochastic Oscillator signal
        if Stoch > 80:
            StochasticSignal = "SELL"
            SellCount += 1
        elif Stoch < 20:
            StochasticSignal = "BUY"
            BUYCount += 1
        

        # Determine CCI signal
        if CCI20 > 100:
            CCI20Signal = "SELL"
            SellCount += 1
        elif CCI20 < -100:
            CCI20Signal = "BUY"
            BUYCount += 1
        else:
            CCI20Signal = "Neutral"

        # Determine ADX signal
        if ADX > 25:
            ADXSignal = "Strong Trend"
        else:
            ADXSignal = "Weak or No Trend"

        # Determine AO signal
        if AO > 0:
            AOSignal = "Strong Trend"
        else:
            AOSignal = "Weak or No Trend"

        # Determine Momentum signal
        if Mom > 0:
            MomSignal = "Uptrend"
        else:
            MomSignal = "Downtrend"

        # Decision logic
        if BUYCount > 1 and MASignal=="UPTREND"  and (ADXSignal == "Strong Trend" or AOSignal == "Strong Trend" or MomSignal == "Uptrend"):
            return "BUY",Pivot,Resistance,Support
        elif SellCount > 1 and MASignal=="DOWNTREND"  and(ADXSignal == "Strong Trend" or AOSignal == "Strong Trend" or MomSignal == "Downtrend"):
            return "SELL",Pivot,Resistance,Support
        else:
            return "Wait for Signal.....",Pivot,Resistance,Support