import requests
from SmartApi import SmartConnect
import urllib
import json
import os
from pyotp import TOTP
import pandas as pd
import datetime as dt
from SmartApi.smartWebSocketV2 import SmartWebSocketV2
import threading
from datetime import datetime,date
import time
class AngelOneAPi:

    url = 'https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json'
    key_secret = open("ApiKeys.txt").read().split()
    #key_secret = open("ApiKeys_test.txt").read().split()
    obj = SmartConnect(api_key=key_secret[0])
    max_websocket_connections = 3
    tiks=None
    def __init__(self):
        data = self.obj.generateSession(self.key_secret[1], self.key_secret[2], TOTP(self.key_secret[3]).now())
        response = urllib.request.urlopen(self.url)
        self.instrument_list = json.loads(response.read())
        self.auth_token = data["data"]["jwtToken"]
        self.feed_token = self.obj.getfeedToken()
        self.websocket_thread = None
        self.ticks=None
        self.sws = None 
        self.last_traded_price=0
    def token_lookup(self,ticker,instrument_list, exchange="NSE"):
        for instrument in instrument_list:
            if instrument["name"] == ticker and instrument["exch_seg"] == exchange :
                return instrument["token"]
            
    def symbol_lookup(self,token,instrument_list,exchange="NSE"):
        for instrument in instrument_list:
            if instrument["token"] == token and instrument["exch_seg"] == exchange :
                return instrument["name"]
    

    def hist_data_extended(self,ticker,duration,interval,instrument_list,exchange="NSE"):
        st_date = dt.date.today() - dt.timedelta(duration)
        end_date = dt.datetime.now() 
        st_date = dt.datetime(st_date.year, st_date.month, st_date.day, 9, 15)
        end_date = dt.datetime(end_date.year, end_date.month, end_date.day)
        df_data = pd.DataFrame(columns=["date","open","high","low","close","volume"])
        
        params = {
                "exchange": exchange,
                "symboltoken": AngelOneAPi.token_lookup(self,ticker,instrument_list),
                "interval": interval,
                "fromdate": (st_date).strftime('%Y-%m-%d %H:%M'),
                "todate": dt.datetime.now().strftime('%Y-%m-%d %H:%M') 
                }
        hist_data = AngelOneAPi.obj.getCandleData(params)
        temp = pd.DataFrame(hist_data["data"],
                            columns = ["date","open","high","low","close","volume"])
        df_data = pd.concat([temp, df_data], ignore_index=True)
        df_data.set_index("date",inplace=True)
        df_data.index = pd.to_datetime(df_data.index)
        df_data.index = df_data.index.tz_localize(None)
        df_data.drop_duplicates(keep="first",inplace=True)    
        return df_data
    

    def option_contracts(self,ticker, option_type="CE", exchange="NFO"):
        option_contracts = []
        for instrument in self.instrument_list:
            if instrument["name"]==ticker and instrument["instrumenttype"] in ["OPTSTK","OPTIDX"]:  # and instrument["symbol"][-2:]==option_type:
                option_contracts.append(instrument)
        
        return pd.DataFrame(option_contracts)

    def option_contracts_atm(self,ticker, underlying_price):
        df_opt_contracts = AngelOneAPi.option_contracts(self,ticker)
        df_opt_contracts["time_to_expiry"] = (pd.to_datetime(df_opt_contracts["expiry"]) + dt.timedelta(0,16*3600) - dt.datetime.now()).dt.total_seconds() / dt.timedelta(days=1).total_seconds() # add 1 to get around the issue of time to expiry becoming 0 for options maturing on trading day   
        df_opt_contracts.sort_values(by=["time_to_expiry"],inplace=True, ignore_index=True)
        atm_strike = df_opt_contracts.loc[abs(pd.to_numeric(df_opt_contracts["strike"])/100 - underlying_price).argmin(),'strike']    
        return (df_opt_contracts[df_opt_contracts["strike"] == atm_strike]).reset_index(drop=True).iloc[:4,:]

    def underlying_price(self,exchange,ticker,token):
        try:
            underlying_price_ = AngelOneAPi.obj.ltpData(exchange, ticker, token)["data"]["ltp"]
            return underlying_price_
        except Exception as e:
               return 0

    
    def GetLiveData(self,tokens):
        
        sws = SmartWebSocketV2(self.auth_token, self.key_secret[0], self.key_secret[2], self.feed_token)
        correlation_id = "stream_1" #any string value which will help identify the specific streaming in case of concurrent streaming
        action = 1 #1 subscribe, 0 unsubscribe
        mode = 3 #1 for LTP, 2 for Quote and 2 for SnapQuote
        #token_list = [{"exchangeType": 2, "tokens": ["56086"]}]
        
        def on_data(wsapp, message):
            self.last_traded_price = round(float(message["last_traded_price"]) / 100, 2)
        
        def on_open(wsapp):
            print("on open")
            sws.subscribe(correlation_id, mode,  [tokens])
        def on_error(wsapp, error):
            print(error)
        
        def close_connection():
            sws.close_connection()

        def on_close(wsapp):
            print("Close") 
        # Assign the callbacks.
        sws.on_open = on_open
        sws.on_data = on_data
        sws.on_error = on_error
        sws.on_close = on_close

        sws.connect()
        time.sleep(10)

    def closeLive(self):
        if self.sws:
            self.sws.close_connection()
        
    def Place_orders(self,tokens):
        thread = threading.Thread(target=self.GetLiveData, args=(tokens,), daemon=True)
        thread.start()
                
        while thread.is_alive():
            def maketData(tick):
                print(tick)    

    
    def place_limit_order(self,instrument_list,ticker,token,buy_sell,price,quantity,exchange="NFO"):
        #token=AngelOneAPi.token_lookup(self,ticker, instrument_list)
       
        params = {
                    "variety":"NORMAL",
                    "tradingsymbol":ticker,
                    "symboltoken":str(token),
                    "transactiontype":buy_sell,
                    "exchange":exchange,
                    "ordertype":"LIMIT",
                    "producttype":"INTRADAY",
                    "duration":"DAY",
                    "price":price,
                    "quantity":quantity
                    }
        response = AngelOneAPi.obj.placeOrder(params)
        return response

    def place_market_order(self,instrument_list,ticker,token,buy_sell,quantity,sl=0,sqof=0,exchange="NFO"):
        #token=AngelOneAPi.token_lookup(self,ticker, instrument_list)
        params = {
                    "variety":"NORMAL",
                    "tradingsymbol":ticker,
                    "symboltoken":token,
                    "transactiontype":buy_sell,
                    "exchange":exchange,
                    "ordertype":"MARKET",
                    "producttype":"INTRADAY",
                    "duration":"DAY",
                    "quantity":quantity
                    }
        response = AngelOneAPi.obj.placeOrder(params)
        return response


    def cancel_order(order_id):
        params = {
                "variety":"NORMAL",
                "orderid":order_id
                }
        response = AngelOneAPi.obj.cancelOrder(params["orderid"], params["variety"])
        return response

    def modify_order_type(instrument_list,ticker,token,order_id,order_type,quantity):
        params = {
                    "variety":"NORMAL",
                    "orderid":order_id,
                    "ordertype":order_type,
                    "producttype":"INTRADAY",
                    "duration":"DAY",
                    "tradingsymbol":ticker,
                    "quantity":quantity,
                    "symboltoken":token,
                    "exchange":"NSE"
                    }
        response = AngelOneAPi.obj.modifyOrder(params)
        return response

    
    def get_open_orders(self,order_Id):
        print("req orderid:",order_Id)
        response = AngelOneAPi.obj.orderBook()

        for order in response["data"]:
            if order.get("orderid") == order_Id:
                orderid=order.get("orderid")
                Price=order.get("price")
                Status=order.get("status")
                avg_price=order.get("averageprice")
                if Price==0:
                    Price=avg_price
                return orderid,Status,Price

    def get_open_orders_back(self):
        

        order_Id='240628001058438'
        Price=0
        response = AngelOneAPi.obj.orderBook()
        for order in response["data"]:
            if order.get("orderid") == order_Id:
                orderid=order.get("orderid")
                Price=order.get("price")
                avg_price=order.get("averageprice")
                Status=order.get("status")
                if Price==0:
                    Price=avg_price
                return orderid,Status,Price
                

        

       

        
    