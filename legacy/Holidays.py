import pandas as pd
from datetime import datetime, date
import datetime as dt

class Holidays:
    def isHolidayToday():
        data = [
            {"SR. NO": 1, "DATE": "22-Jan-2024", "DAY": "Monday", "DESCRIPTION": "Special Holiday"},
            {"SR. NO": 2, "DATE": "26-Jan-2024", "DAY": "Friday", "DESCRIPTION": "Republic Day"},
            {"SR. NO": 3, "DATE": "08-Mar-2024", "DAY": "Friday", "DESCRIPTION": "Mahashivratri"},
            {"SR. NO": 4, "DATE": "25-Mar-2024", "DAY": "Monday", "DESCRIPTION": "Holi"},
            {"SR. NO": 5, "DATE": "29-Mar-2024", "DAY": "Friday", "DESCRIPTION": "Good Friday"},
            {"SR. NO": 6, "DATE": "11-Apr-2024", "DAY": "Thursday", "DESCRIPTION": "Id-Ul-Fitr (Ramadan Eid)"},
            {"SR. NO": 7, "DATE": "17-Apr-2024", "DAY": "Wednesday", "DESCRIPTION": "Shri Ram Navmi"},
            {"SR. NO": 8, "DATE": "01-May-2024", "DAY": "Wednesday", "DESCRIPTION": "Maharashtra Day"},
            {"SR. NO": 9, "DATE": "20-May-2024", "DAY": "Monday", "DESCRIPTION": "General Parliamentary Elections"},
            {"SR. NO": 10, "DATE": "17-Jun-2024", "DAY": "Monday", "DESCRIPTION": "Bakri Id"},
            {"SR. NO": 11, "DATE": "17-Jul-2024", "DAY": "Wednesday", "DESCRIPTION": "Moharram"},
            {"SR. NO": 12, "DATE": "15-Aug-2024", "DAY": "Thursday", "DESCRIPTION": "Independence Day"},
            {"SR. NO": 13, "DATE": "02-Oct-2024", "DAY": "Wednesday", "DESCRIPTION": "Mahatma Gandhi Jayanti"},
            {"SR. NO": 14, "DATE": "01-Nov-2024", "DAY": "Friday", "DESCRIPTION": "Diwali Laxmi Pujan*"},
            {"SR. NO": 15, "DATE": "15-Nov-2024", "DAY": "Friday", "DESCRIPTION": "Gurunanak Jayanti"},
            {"SR. NO": 16, "DATE": "25-Dec-2024", "DAY": "Wednesday", "DESCRIPTION": "Christmas"}
        ]
        df = pd.DataFrame(data)
        today = date.today()
        today_str = today.strftime('%d-%b-%Y')

        # Check if today's date is in the holiday dates
        if today_str in df['DATE'].values:
            return True
        else:
            return False


    def todayName():
        return ((date.today()).strftime('%A')).lower()

    def is_market_open():
        now = dt.datetime.now()
        market_open_time = now.replace(hour=9, minute=22, second=0, microsecond=0)
        market_close_time = now.replace(hour=15, minute=20, second=0, microsecond=0)
        
        if now.weekday() < 5 and market_open_time <= now <= market_close_time:
            return True
        else:
            return False
