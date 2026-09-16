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
from ExcelUpdate import Orders
import logging
import warnings

warnings.filterwarnings("ignore", category=UserWarning, message="Could not infer format")
# Configure logging
logging.basicConfig(filename='trading_script.log', level=logging.ERROR, format='%(asctime)s %(levelname)s:%(message)s')

if __name__ =="__main__":

    api=AngelOneAPi()
   
    token_Bank=api.token_lookup("BANKNIFTY",api.instrument_list)
    #token_Nifty=api.token_lookup("NIFTY",api.instrument_list)
    token_Nifty="99926000"
    
    today = Holidays.todayName()
    isHoliday=Holidays.isHolidayToday()
    now = datetime.now()
    time_limit_nifty = datetime.now().replace(hour=15, minute=10, second=0, microsecond=0)
    time_to_exit_nifty=datetime.now().replace(hour=15, minute=18, second=0, microsecond=0)
    time_limit_bank = datetime.now().replace(hour=15, minute=10, second=0, microsecond=0)
    time_to_exit_bank=datetime.now().replace(hour=15, minute=18, second=0, microsecond=0)
    niftyLots=25
    
    #if  today !="sunday" and today !="saturday" and isHoliday ==False:
    if  today !="sunday" and today !="saturday" and isHoliday ==False:
        isMarketLive=Holidays.is_market_open()
        
        
        while isMarketLive:

            anyCurrentTrade=None
            tradedPrice=0
            order_id_Entry=None
            order_id_exit=None
            tradedToken=None
            tradedSymobol=None
            tokens=[]

            anyCurrentTrade_bank=None
            tradedPrice_bank=0
            order_id_Entry_bank=None
            order_id_exit_bank=None
            tradedToken_bank=None
            tradedSymobol_bank=None
            tokens_bank=[]

            ltp_Bank=api.underlying_price("NSE","BANKNIFTY",token_Bank)
            ltp_Nifty=api.underlying_price("NSE","NIFTY",token_Nifty)
            option_contracts_BankNifty=api.option_contracts_atm("BANKNIFTY",ltp_Bank)
            option_contracts_Nifty=api.option_contracts_atm("NIFTY",ltp_Nifty)

           
            if datetime.strptime(option_contracts_Nifty["expiry"].iloc[0],'%d%b%Y').date() !=  date.today():
                
                print("----------------------------**************-----------------------")
                tokens=[]
                if datetime.strptime(option_contracts_Nifty["expiry"].iloc[0],'%d%b%Y').date() ==  date.today():
                    time_limit_nifty=datetime.now().replace(hour=14, minute=30, second=0, microsecond=0)
                    time_to_exit_nifty=datetime.now().replace(hour=14, minute=45, second=0, microsecond=0)

                signal_nifty,Pivot_nifty,R1_nifty,S1_nifty=TradingViewSignal.get_Signal("NIFTY",ltp_Nifty)
                
                print("signal:",signal_nifty)
                
                openOrders_Nifty=Orders.get_open_orders('NIFTY')
                if not openOrders_Nifty.empty:
                    order_id_Entry=openOrders_Nifty["Order_ID"].astype(str).iloc[0]
                    anyCurrentTrade=openOrders_Nifty["TradeType"].astype(str).iloc[0]
                    tradedToken=openOrders_Nifty["Token"].astype(str).iloc[0]
                    tradedSymobol=openOrders_Nifty["Symbol"].astype(str).iloc[0]
                    tradedPrice=openOrders_Nifty["Entry_Price"].astype(str).iloc[0]
                   
                    tokens.append({"exchangeType": 2, "tokens": [tradedToken]})

                print("Nift current Trade:",anyCurrentTrade)
                if (signal_nifty =="BUY") and anyCurrentTrade==None and  ltp_Nifty>=S1_nifty+15 and time_limit_nifty>now:

                    print("BUY NIFTY Entry:")
                    option_contracts_Nifty=api.option_contracts_atm("NIFTY",ltp_Nifty-50)
                    CE_=option_contracts_Nifty[option_contracts_Nifty["symbol"].str.contains('CE')].iloc[0]
                    tokens.append({"exchangeType": 2, "tokens": [CE_["token"]]})
                    
                    order_id_Entry=api.place_market_order(api.instrument_list, CE_["symbol"],CE_["token"], "BUY", niftyLots)

                    orderid,Status,Price=api.get_open_orders(order_id_Entry)
                    if Status =="rejected":
                        order_id_Entry=None
                    elif Status !="rejected":
                        anyCurrentTrade="CE"
                        tradedToken=CE_["token"]
                        tradedSymobol= CE_["symbol"]
                        tradedPrice=Price
                        Orders.append_order_to_excel(order_id_Entry,"NIFTY",tradedSymobol,anyCurrentTrade,tradedToken,tradedPrice,niftyLots)
                
                elif (signal_nifty =="SELL") and anyCurrentTrade==None  and ltp_Nifty<=R1_nifty and time_limit_nifty>now:

                    option_contracts_Nifty=api.option_contracts_atm("NIFTY",ltp_Nifty+100)
                    PE_=option_contracts_Nifty[option_contracts_Nifty["symbol"].str.contains('PE')].iloc[0]
                    tokens.append({"exchangeType": 2, "tokens": [PE_["token"]]})
                    
                    order_id_Entry=api.place_market_order(api.instrument_list, PE_["symbol"],PE_["token"], "BUY", niftyLots)
                    orderid,Status,Price=api.get_open_orders(order_id_Entry)
                    if Status =="rejected":
                        order_id_Entry=None
                    elif Status !="rejected":
                        anyCurrentTrade="PE"
                        tradedToken=PE_["token"]
                        tradedSymobol= PE_["symbol"]
                        tradedPrice=Price
                        Orders.append_order_to_excel(order_id_Entry,"NIFTY",tradedSymobol,anyCurrentTrade,tradedToken,tradedPrice,niftyLots)
                elif  tokens and anyCurrentTrade!=None:

                    last_traded_price=0
                    print( print("Nift current tokens:",tokens))
                    
                    ltp_ = api.underlying_price("NFO", tradedSymobol, tradedToken)
                    last_traded_price = float(ltp_)
                   
                    print("last_traded_price of Nifty foe exit:",last_traded_price)
                    if (last_traded_price>((float(tradedPrice)*110)/100) or last_traded_price<=((float(tradedPrice)*95)/100) or now>=time_to_exit_nifty) and last_traded_price !=0 :
                        order_id_exit=api.place_market_order(api.instrument_list,tradedSymobol,tradedToken, "SELL", niftyLots)
                        orderid_exit_n,Status_ext_n,Price_exit_n=api.get_open_orders(order_id_exit)
                        if Status_ext_n !="rejected":
                            if order_id_Entry!=None:
                                Orders.update_order_status_in_excel(order_id_Entry,"CLOSE",last_traded_price)
                                order_id_Entry=None
                                tradedToken=None
                                tradedSymobol=None
                                anyCurrentTrade=None
                                print("tradedPrice:", tradedPrice)
                                print("last_traded_price:", last_traded_price)
                           
                     
                print("----------------------------**************-----------------------")
                print("            ")
                      

            if datetime.strptime(option_contracts_BankNifty["expiry"].iloc[0],'%d%b%Y').date() !=  date.today():

                print("            ")
                print("----------------------------**************-----------------------")
                tokens_bank=[]
                if datetime.strptime(option_contracts_BankNifty["expiry"].iloc[0],'%d%b%Y').date() ==  date.today():
                    time_limit_bank=datetime.now().replace(hour=14, minute=30, second=0, microsecond=0)
                    time_to_exit_bank=datetime.now().replace(hour=14, minute=45, second=0, microsecond=0)
                openOrders_Bank=Orders.get_open_orders('BANK')
                if not openOrders_Bank.empty:
                    order_id_Entry=openOrders_Bank["Order_ID"].astype(str).iloc[0]
                    anyCurrentTrade_bank=openOrders_Bank["TradeType"].astype(str).iloc[0]
                    tradedToken_bank=openOrders_Bank["Token"].astype(str).iloc[0]
                    tradedSymobol_bank=openOrders_Bank["Symbol"].astype(str).iloc[0]
                    tradedPrice_bank=openOrders_Bank["Entry_Price"].astype(str).iloc[0]
                    
                    tokens_bank.append({"exchangeType": 2, "tokens": [tradedToken_bank]})

                signal_bank,Pivot_bank,R1_bank,S1_bank=TradingViewSignal.get_Signal("BANKNIFTY",ltp_Bank)

                print("Bank Nifty Signal:", signal_bank)
                if (signal_bank =="BUY") and anyCurrentTrade_bank==None and time_limit_bank>now and  ltp_Bank>=S1_bank:
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
                        Orders.append_order_to_excel(order_id_Entry_bank,"BANK",tradedSymobol_bank,anyCurrentTrade_bank,tradedToken_bank,tradedPrice_bank,15)
                    
                
                elif (signal_bank =="SELL") and anyCurrentTrade_bank==None and time_limit_bank>now and ltp_Nifty<=R1_bank:
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
                        Orders.append_order_to_excel(order_id_Entry_bank,"BANK",tradedSymobol_bank,anyCurrentTrade_bank,tradedToken_bank,tradedPrice_bank,15)
                    
                elif  tokens_bank and anyCurrentTrade_bank!=None:
                    last_traded_price_bank=0
                    print(tokens_bank, anyCurrentTrade_bank)
                   
                    ltp_b = api.underlying_price("NFO", tradedSymobol_bank, tradedToken_bank)
                    last_traded_price_bank = float(ltp_b)
                    
                    print("last_traded_price_bank for Bank:",last_traded_price_bank)

                    if (last_traded_price_bank>((float(tradedPrice_bank)*110)/100) or last_traded_price_bank<=((float(tradedPrice_bank)*95)/100) or now>=time_to_exit_bank) and last_traded_price_bank !=0  :
                        order_id_exit_bank=api.place_market_order(api.instrument_list,tradedSymobol_bank,tradedToken_bank, "SELL", 15)
                        orderid_exit_b,Status_ext_b,Price_exit_b=api.get_open_orders(order_id_exit_bank)
                        if Status_ext_b !="rejected":
                            if last_traded_price_bank!=None:
                                Orders.update_order_status_in_excel(order_id_Entry_bank,"CLOSE",last_traded_price_bank)
                                order_id_Entry_bank=None
                                tradedToken_bank=None
                                tradedSymobol_bank=None
                                anyCurrentTrade_bank=None
                                print("tradedPrice_bank:", tradedPrice_bank)
                                print("last_traded_price_bank:", last_traded_price_bank)                                                                                   
                    
                
                print("----------------------------**************-----------------------")
                print("            ")


        
            
            