import pandas as pd
from datetime import datetime, date


class Orders:
    
    def append_order_to_excel(order_id, Indices,symbol,tradeType, Token, price, quantity):
        excel_file = 'order_details.xlsx'        
        new_order = pd.DataFrame({
            'Order_ID': [order_id],
            'Indices':[Indices],
            'Symbol': [symbol],
            'TradeType': [tradeType],
            'Token': [Token],
            'Entry_Price': [price],
            'Quantity': [quantity],
            'Status': ['OPEN'],
            'Timestamp': [datetime.now().strftime('%Y-%m-%d %H:%M:%S')]
        })
        with pd.ExcelWriter(excel_file, mode='a', if_sheet_exists='overlay') as writer:
            new_order.to_excel(writer, header=False, index=False, startrow=writer.sheets['Sheet1'].max_row)    

    def update_order_status_in_excel(order_id, status,price):
        excel_file = 'order_details.xlsx'
        try:
            df = pd.read_excel(excel_file)
            
            order_id = (order_id)
            df.loc[df['Order_ID'] == order_id, 'Status'] = status
            df.loc[df['Order_ID'] == order_id, 'Exit_Price'] = price
            #df.loc[df['Order_ID'] == order_id, 'Exit_Time'] = str(datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
            df.to_excel(excel_file, index=False)
            print("Updated Successfully..")
        except PermissionError as e:
            print(f"PermissionError: {e}. File Not Updated Please check.....")
            

        
    def get_open_orders(symbol):
        excel_file = 'order_details.xlsx'
        try:
            df = pd.read_excel(excel_file)
            open_orders = df[df['Status'] == 'OPEN']
            if symbol:
                open_orders = open_orders[open_orders['Indices'].str.contains(symbol, case=False)]
            open_orders = open_orders.astype(str)
            return open_orders
        except PermissionError as e:
            print(f"PermissionError: {e}. Ensure the file is not open or locked by another process.")
            return pd.DataFrame() 