from api.angel_one import AngelOneAPi
from api.ploting import CandlePlot
from datetime import datetime,date,time
from Holidays import Holidays
from analysis.Candlesticks import CandlePlot
from analysis.indicators import Indicators
import threading
from api.TradingView import TradingViewSignal
from colorama import Fore, Style
import time
if __name__ =="__main__":

    api=AngelOneAPi()
   
    token_Bank=api.token_lookup("BANKNIFTY",api.instrument_list)
    token_Nifty=api.token_lookup("NIFTY",api.instrument_list)
    

    today = Holidays.todayName()
    isHoliday=Holidays.isHolidayToday()
 
   
    if  today !="sunday" and today !="saturday" and isHoliday ==False:
    #if  True:
        isMarketLive=Holidays.is_market_open()
        while isMarketLive:
        #while True:

            ltp_Bank=api.underlying_price("NSE","BANKNIFTY",token_Bank)
            ltp_Nifty=api.underlying_price("NSE","NIFTY",token_Nifty)
            option_contracts_BankNifty=api.option_contracts_atm("BANKNIFTY",ltp_Bank)
            option_contracts_Nifty=api.option_contracts_atm("NIFTY",ltp_Nifty)
                
            if datetime.strptime(option_contracts_Nifty["expiry"].iloc[0],'%d%b%Y').date() !=  date.today():
                #hist_Nifty=api.hist_data_extended("NIFTY", 1000, "FIVE_MINUTE",api.instrument_list)
                
                anyCurrentTrade=None
                tradedPrice=0
                order_id_Entry=None
                order_id_exit=None
                tradedToken=None
                tradedSymobol=None
                tokens=[]
            
                signal_nifty,Pivot_nifty,R1_nifty,S1_nifty=TradingViewSignal.get_Signal("NIFTY")
                
                print("signal:",signal_nifty)
                print("anyCurrentTrade: ",print(anyCurrentTrade))
                if (signal_nifty =="BUY") and anyCurrentTrade==None :
                    print("BUY NIFTY Entry:")
                    CE_=option_contracts_Nifty[option_contracts_Nifty["symbol"].str.contains('CE')].iloc[0]
                    tokens.append({"exchangeType": 2, "tokens": [CE_["token"]]})
                    
                    order_id_Entry=api.place_market_order(api.instrument_list, CE_["symbol"],CE_["token"], "BUY", 25)

                    orderid,Status,Price=api.get_open_orders(order_id_Entry)
                    if Status =="rejected":
                        order_id_Entry=None
                    elif Status !="rejected":
                        anyCurrentTrade="CE"
                        tradedToken=CE_["token"]
                        tradedSymobol= CE_["symbol"]
                        tradedPrice=Price
                    
                
                elif (signal_nifty =="SELL") and anyCurrentTrade==None :
                    PE_=option_contracts_Nifty[option_contracts_Nifty["symbol"].str.contains('PE')].iloc[0]
                    tokens.append({"exchangeType": 2, "tokens": [PE_["token"]]})
                    
                    order_id_Entry=api.place_market_order(api.instrument_list, PE_["symbol"],PE_["token"], "BUY", 25)
                    orderid,Status,Price=api.get_open_orders(order_id_Entry)
                    if Status =="rejected":
                        order_id_Entry=None
                    elif Status !="rejected":
                        anyCurrentTrade="PE"
                        tradedToken=PE_["token"]
                        tradedSymobol= PE_["symbol"]
                        tradedPrice=Price
                    
                elif  tokens and anyCurrentTrade!=None:

                    thread=threading.Thread(target=api.GetLiveData,args=tokens) 
                    thread.start()
                    
                    last_traded_price=api.last_traded_price
                    print("last_traded_price:",last_traded_price)

                    if (last_traded_price>((tradedPrice*110)/100) or last_traded_price<=((tradedPrice*70)/100)) and last_traded_price !=0 :
                        order_id_exit=api.place_market_order(api.instrument_list,tradedSymobol,tradedToken, "SELL", 25)
                        order_id_Entry=None
                        tradedToken=None
                        tradedSymobol=None
                        print("tradedPrice:", tradedPrice)
                        print("last_traded_price:", last_traded_price)
                        api.closeLive()
                        
                    api.closeLive()
                        

            if datetime.strptime(option_contracts_BankNifty["expiry"].iloc[0],'%d%b%Y').date() !=  date.today():
                #hist_Bank=api.hist_data_extended("BANKNIFTY", 1000, "FIVE_MINUTE",api.instrument_list)
                anyCurrentTrade_bank=None
                tradedPrice_bank=0
                order_id_Entry_bank=None
                order_id_exit_bank=None
                tradedToken_bank=None
                tradedSymobol_bank=None
                tokens_bank=[]

                signal_bank,Pivot_bank,R1_bank,S1_bank=TradingViewSignal.get_Signal("BANKNIFTY")
                if (signal_bank =="BUY") and anyCurrentTrade_bank==None :
                    print("Buy BankNIfty Entry:")
                    CE_bank=option_contracts_BankNifty[option_contracts_BankNifty["symbol"].str.contains('CE')].iloc[0]
                    tokens_bank.append({"exchangeType": 2, "tokens": [CE_bank["token"]]})
                    
                    order_id_Entry_bank=api.place_market_order(api.instrument_list, CE_bank["symbol"],CE_bank["token"], "BUY", 15)

                    orderid,Status,Price=api.get_open_orders(order_id_Entry_bank)
                    if Status =="rejected":
                        order_id_Entry=None
                    elif Status !="rejected":
                        anyCurrentTrade_bank="CE"
                        tradedToken_bank=CE_bank["token"]
                        tradedSymobol_bank= CE_bank["symbol"]
                        tradedPrice_bank=Price
                    
                
                elif (signal_bank =="SELL") and anyCurrentTrade_bank==None :
                    PE_bank=option_contracts_BankNifty[option_contracts_BankNifty["symbol"].str.contains('PE')].iloc[0]
                    tokens_bank.append({"exchangeType": 2, "tokens": [PE_bank["token"]]})
                    
                    order_id_Entry_bank=api.place_market_order(api.instrument_list, PE_bank["symbol"],PE_bank["token"], "BUY", 15)
                    orderid,Status,Price=api.get_open_orders(order_id_Entry_bank)
                    if Status =="rejected":
                        order_id_Entry=None
                    elif Status !="rejected":
                        anyCurrentTrade_bank="PE"
                        tradedToken_bank=PE_bank["token"]
                        tradedSymobol_bank= PE_bank["symbol"]
                        tradedPrice_bank=Price
                    
                elif  tokens_bank and anyCurrentTrade_bank!=None:

                    thread2=threading.Thread(target=api.GetLiveData,args=tokens_bank) 
                    thread2.start()
                    
                    last_traded_price=api.last_traded_price
                    print("last_traded_price:",last_traded_price)

                    if (last_traded_price>((tradedPrice_bank*110)/100) or last_traded_price<=((tradedPrice_bank*70)/100)) and last_traded_price !=0 :
                        order_id_exit_bank=api.place_market_order(api.instrument_list,tradedSymobol_bank,tradedToken_bank, "SELL", 25)
                        order_id_Entry_bank=None
                        tradedToken_bank=None
                        tradedSymobol_bank=None
                        print("tradedPrice_bank:", tradedPrice_bank)
                        print("last_traded_price:", last_traded_price)
                        api.closeLive()
                        
                    api.closeLive()

            time.sleep(1)

            
            