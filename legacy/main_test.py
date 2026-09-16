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

if __name__ =="__main__":

    api=AngelOneAPi()
   
    token_Bank=api.token_lookup("BANKNIFTY",api.instrument_list)
    token_Nifty=api.token_lookup("NIFTY",api.instrument_list)
    
    today = Holidays.todayName()
    isHoliday=Holidays.isHolidayToday()
    now = datetime.now()
    time_limit = datetime.now().replace(hour=15, minute=10, second=0, microsecond=0)
    time_to_exit=datetime.now().replace(hour=15, minute=18, second=0, microsecond=0)
    
   
   
    if  today !="sunday" and today !="saturday" and isHoliday ==False:
        isMarketLive=Holidays.is_market_open()
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

        #orderid,Status,Price=api.get_open_orders("240701000683699")
        #print(Status)
       
        while isMarketLive:
            ltp_Bank=api.underlying_price("NSE","BANKNIFTY",token_Bank)
            ltp_Nifty=api.underlying_price("NSE","NIFTY",token_Nifty)
            option_contracts_BankNifty=api.option_contracts_atm("BANKNIFTY",ltp_Bank)
            option_contracts_Nifty=api.option_contracts_atm("NIFTY",ltp_Nifty)

            if datetime.strptime(option_contracts_Nifty["expiry"].iloc[0],'%d%b%Y').date() !=  date.today():
                
                signal_nifty,Pivot_nifty,R1_nifty,S1_nifty=TradingViewSignal.get_Signal("NIFTY")
                openOrders_Nifty=Orders.get_open_orders('NIFTY')

                if not openOrders_Nifty.empty:
                    Orders.update_order_status_in_excel(openOrders_Nifty["Order_ID"],"CLOSE",200)
                    print("Order Id:",openOrders_Nifty["Order_ID"])
                else:
                    print("No orders found")
                

                print(openOrders_Nifty["Order_ID"])
                print("signal:",signal_nifty)
                print("anyCurrentTrade: ",print(anyCurrentTrade))
                #if True:
                if (signal_nifty =="BUY") and anyCurrentTrade==None and  ltp_Nifty>=S1_nifty+15 and time_limit>now:
                    print("BUY NIFTY Entry:")
                    CE_=option_contracts_Nifty[option_contracts_Nifty["symbol"].str.contains('CE')].iloc[0]
                    tokens.append({"exchangeType": 2, "tokens": [CE_["token"]]})
                    
                    order_id_Entry=api.place_market_order(api.instrument_list, CE_["symbol"],CE_["token"], "BUY", 25)
                    
                    orderid,Status,Price=api.get_open_orders(order_id_Entry)
                    if Status =="rejected":
                        anyCurrentTrade="CE"
                        tradedToken=CE_["token"]
                        tradedSymobol= CE_["symbol"]
                        tradedPrice=Price
                        Orders.append_order_to_excel(order_id_Entry,"NIFTY",tradedSymobol,anyCurrentTrade,tradedToken,tradedPrice,25)
                        order_id_Entry=None
                    elif Status !="rejected":
                        anyCurrentTrade="CE"
                        tradedToken=CE_["token"]
                        tradedSymobol= CE_["symbol"]
                        tradedPrice=Price
                        Orders.append_order_to_excel(order_id_Entry,"NIFTY",tradedSymobol,anyCurrentTrade,tradedToken,tradedPrice,25)
                
                elif (signal_nifty =="SELL") and anyCurrentTrade==None  and ltp_Nifty<=R1_nifty-15 and time_limit>now:
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
                    try:
                        if (last_traded_price>((tradedPrice*110)/100) or last_traded_price<=((tradedPrice*90)/100) or now>=time_to_exit) and last_traded_price !=0 :
                            order_id_exit=api.place_market_order(api.instrument_list,tradedSymobol,tradedToken, "SELL", 25)
                            orderid_exit_n,Status_ext_n,Price_exit_n=api.get_open_orders(order_id_exit)
                            if Status_ext_n !="rejected":
                                order_id_Entry=None
                                tradedToken=None
                                tradedSymobol=None
                                anyCurrentTrade=None
                                print("tradedPrice:", tradedPrice)
                                print("last_traded_price:", last_traded_price)
                    except Exception as e:
                        logging.error(f"Error in live data handling for NIFTY: {e}")
                            
                      
                time.sleep(3) 
                      

            if datetime.strptime(option_contracts_BankNifty["expiry"].iloc[0],'%d%b%Y').date() !=  date.today():
                #hist_Bank=api.hist_data_extended("BANKNIFTY", 1000, "FIVE_MINUTE",api.instrument_list)
            

                signal_bank,Pivot_bank,R1_bank,S1_bank=TradingViewSignal.get_Signal("BANKNIFTY")
                if (signal_bank =="BUY") and anyCurrentTrade_bank==None  and ltp_Bank>=S1_bank+15 and time_limit>now:
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
                    
                
                elif (signal_bank =="SELL") and anyCurrentTrade_bank==None and ltp_Bank<=R1_bank-15 and time_limit>now:
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
                    try:
                        if (last_traded_price>((tradedPrice_bank*110)/100) or last_traded_price<=((tradedPrice_bank*90)/100) or now>=time_to_exit) and last_traded_price !=0  :
                            order_id_exit_bank=api.place_market_order(api.instrument_list,tradedSymobol_bank,tradedToken_bank, "SELL", 15)
                            orderid_exit_b,Status_ext_b,Price_exit_b=api.get_open_orders(order_id_exit_bank)
                            if Status_ext_b !="rejected":
                                order_id_Entry_bank=None
                                tradedToken_bank=None
                                tradedSymobol_bank=None
                                anyCurrentTrade_bank=None
                                print("tradedPrice_bank:", tradedPrice_bank)
                                print("last_traded_price:", last_traded_price)
                                Orders.append_order_to_excel(order_id_Entry,"BANK",tradedSymobol_bank,anyCurrentTrade_bank,tradedToken_bank,tradedPrice_bank,15)
                    except Exception as e:
                        logging.error(f"Error in live data handling for BANK NIFTY: {e}")
                            
                time.sleep(3)


        
            
            