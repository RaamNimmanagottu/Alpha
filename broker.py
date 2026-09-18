from __future__ import annotations

import json
import logging
import time as time_module
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

import pandas as pd
from pyotp import TOTP
from SmartApi import SmartConnect

from config import Credentials

logger = logging.getLogger("alpha.broker")

INSTRUMENT_MASTER_URL = (
    "https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json"
)


class BrokerError(Exception):
    """Raised when a broker operation fails after retries."""


class OrderRejected(Exception):
    """Raised when the broker accepted the request but rejected/cancelled the order itself."""


@dataclass
class OrderResult:
    order_id: str
    status: str
    price: float


def _retry(fn, *, attempts: int = 3, delay_seconds: float = 1.0, what: str = "operation"):
    last_exc: Optional[Exception] = None
    for attempt in range(1, attempts + 1):
        try:
            return fn()
        except Exception as exc:  # broad: broker/network calls can fail in many ways
            last_exc = exc
            logger.warning("%s failed (attempt %d/%d): %s", what, attempt, attempts, exc)
            if attempt < attempts:
                time_module.sleep(delay_seconds * attempt)
    raise BrokerError(f"{what} failed after {attempts} attempts") from last_exc


class AngelOneBroker:
    """Thin, defensive wrapper around SmartConnect.

    Unlike the previous implementation, nothing here runs at import/class-definition
    time -- the session, instrument master, and tokens are all fetched lazily in
    __init__ / connect(), so importing this module never touches the network or reads
    credentials.
    """

    def __init__(self, credentials: Credentials):
        self._credentials = credentials
        self.client = SmartConnect(api_key=credentials.api_key)
        self.instrument_list: list[dict] = []
        self.auth_token: str | None = None
        self.feed_token: str | None = None
        self._instrument_by_key: dict[tuple[str, str], dict] = {}

    def connect(self) -> None:
        creds = self._credentials

        def _login():
            return self.client.generateSession(creds.client_id, creds.mpin, TOTP(creds.totp_secret).now())

        session = _retry(_login, what="broker login")
        if not session or not session.get("status"):
            raise BrokerError(f"Login failed: {session}")

        self.auth_token = session["data"]["jwtToken"]
        self.feed_token = self.client.getfeedToken()

        def _fetch_instruments():
            with urllib.request.urlopen(INSTRUMENT_MASTER_URL, timeout=30) as response:
                return json.loads(response.read())

        self.instrument_list = _retry(_fetch_instruments, what="instrument master download")
        self._instrument_by_key = {
            (i["name"], i["exch_seg"]): i for i in self.instrument_list if "name" in i
        }
        logger.info("Connected. %d instruments loaded.", len(self.instrument_list))

    def token_lookup(self, ticker: str, exchange: str = "NSE") -> str | None:
        instrument = self._instrument_by_key.get((ticker, exchange))
        return instrument["token"] if instrument else None

    def option_contracts(self, ticker: str) -> pd.DataFrame:
        contracts = [
            i
            for i in self.instrument_list
            # OPTFUT covers MCX commodity options (options on the futures
            # contract, e.g. GOLD/CRUDEOIL) -- OPTSTK/OPTIDX cover NSE stock
            # and index options. Safe to check all three unconditionally:
            # the `name` match already scopes this to one ticker.
            if i["name"] == ticker and i["instrumenttype"] in ("OPTSTK", "OPTIDX", "OPTFUT")
        ]
        return pd.DataFrame(contracts)

    def option_contracts_nearest_expiry(self, ticker: str) -> pd.DataFrame:
        """All strikes/CE+PE for the *nearest* expiry only.

        The previous implementation picked the closest strike across *all* expiries at
        once -- since weekly and monthly contracts share the same strike ladder, that
        could silently mix rows from two different expiries into the result. Filtering
        to the nearest expiry first avoids that, and is shared by option_contracts_atm
        (narrows further to one strike) and delta-based strike selection (searches
        across all strikes at this expiry).
        """
        df = self.option_contracts(ticker)
        if df.empty:
            return df

        df = df.copy()
        df["expiry_date"] = pd.to_datetime(df["expiry"], format="%d%b%Y")
        nearest_expiry = df["expiry_date"].min()
        return df[df["expiry_date"] == nearest_expiry].reset_index(drop=True)

    def option_contracts_atm(self, ticker: str, underlying_price: float) -> pd.DataFrame:
        """Return the CE/PE pair closest to the money, restricted to the nearest expiry."""
        df = self.option_contracts_nearest_expiry(ticker)
        if df.empty:
            return df

        strikes = pd.to_numeric(df["strike"]) / 100
        atm_idx = (strikes - underlying_price).abs().idxmin()
        atm_strike = df.loc[atm_idx, "strike"]
        return df[df["strike"] == atm_strike].reset_index(drop=True)

    def option_greeks(self, name: str, expiry: str) -> pd.DataFrame:
        """Delta/gamma/theta/vega/IV for every strike of `name` at `expiry` (e.g.
        expiry="22SEP2026", matching the instrument master's own expiry format).

        Returns an empty DataFrame on any failure (API error, malformed response, or
        every row failing numeric validation) -- callers must treat that as "greeks
        unavailable" and fall back to ATM selection rather than blocking entries.
        """
        def _fetch():
            return self.client.optionGreek({"name": name, "expirydate": expiry})

        try:
            response = _retry(_fetch, attempts=2, delay_seconds=0.5, what=f"optionGreek {name} {expiry}")
        except BrokerError:
            logger.error("Could not fetch option greeks for %s %s after retries", name, expiry)
            return pd.DataFrame()

        if not response or not response.get("status"):
            logger.error("optionGreek failed for %s %s: %s", name, expiry, response)
            return pd.DataFrame()

        rows = response.get("data") or []
        df = pd.DataFrame(rows)
        if df.empty:
            return df

        numeric_cols = ["strikePrice", "delta", "gamma", "theta", "vega", "impliedVolatility"]
        for col in numeric_cols:
            df[col] = pd.to_numeric(df[col], errors="coerce")

        before = len(df)
        df = df.dropna(subset=numeric_cols).reset_index(drop=True)
        if len(df) < before:
            logger.warning("optionGreek %s %s: dropped %d row(s) with unparseable numeric fields",
                            name, expiry, before - len(df))

        return df

    def underlying_price(self, exchange: str, ticker: str, token: str) -> float:
        def _fetch():
            return self.client.ltpData(exchange, ticker, token)

        try:
            response = _retry(_fetch, attempts=2, delay_seconds=0.5, what=f"ltp for {ticker}")
        except BrokerError:
            logger.error("Could not fetch LTP for %s after retries", ticker)
            return 0.0
        return float(response["data"]["ltp"])

    def get_candle_data(
        self,
        token: str,
        interval: str,
        from_dt: datetime,
        to_dt: datetime,
        exchange: str = "NSE",
    ) -> pd.DataFrame:
        """Historical OHLC candles for `token` between from_dt and to_dt (inclusive-ish;
        Angel's API is minute-grained). For NSE indices (NIFTY/BANKNIFTY) this requires
        the special index token used for historical data (e.g. 99926000), NOT the token
        used for LTP quotes (e.g. 26000) -- the LTP token silently returns zero rows here.
        """
        params = {
            "exchange": exchange,
            "symboltoken": str(token),
            "interval": interval,
            "fromdate": from_dt.strftime("%Y-%m-%d %H:%M"),
            "todate": to_dt.strftime("%Y-%m-%d %H:%M"),
        }

        def _fetch():
            return self.client.getCandleData(params)

        response = _retry(_fetch, attempts=3, delay_seconds=1.0, what=f"getCandleData token={token}")
        if not response or not response.get("status"):
            raise BrokerError(f"getCandleData failed: {response}")

        rows = response.get("data") or []
        df = pd.DataFrame(rows, columns=["date", "open", "high", "low", "close", "volume"])
        if not df.empty:
            # Angel returns ISO timestamps with a +05:30 offset already in IST; strip the
            # tz label without converting the instant (utc=True would shift wall-clock
            # time back by 5:30, which is wrong here -- verified empirically).
            df["date"] = pd.to_datetime(df["date"]).dt.tz_localize(None)
        return df

    def place_market_order(
        self,
        symbol: str,
        token: str,
        transaction_type: str,
        quantity: int,
        exchange: str = "NFO",
    ) -> str:
        params = {
            "variety": "NORMAL",
            "tradingsymbol": symbol,
            "symboltoken": str(token),
            "transactiontype": transaction_type,
            "exchange": exchange,
            "ordertype": "MARKET",
            "producttype": "INTRADAY",
            "duration": "DAY",
            "quantity": quantity,
        }

        def _place():
            return self.client.placeOrder(params)

        order_id = _retry(_place, attempts=2, delay_seconds=0.5, what=f"place order {symbol}")
        if not order_id:
            raise OrderRejected(f"Broker rejected order placement for {symbol}: {params}")
        logger.info("Placed %s %s x%d -> order_id=%s", transaction_type, symbol, quantity, order_id)
        return order_id

    def cancel_order(self, order_id: str, variety: str = "NORMAL") -> Any:
        return self.client.cancelOrder(order_id, variety)

    def modify_order(
        self, order_id: str, symbol: str, token: str, order_type: str, quantity: int
    ) -> Any:
        params = {
            "variety": "NORMAL",
            "orderid": order_id,
            "ordertype": order_type,
            "producttype": "INTRADAY",
            "duration": "DAY",
            "tradingsymbol": symbol,
            "quantity": quantity,
            "symboltoken": token,
            "exchange": "NFO",
        }
        return self.client.modifyOrder(params)

    def wait_for_order_result(
        self, order_id: str, timeout_seconds: float, poll_seconds: float
    ) -> OrderResult:
        """Poll the order book until the order reaches a terminal state or times out.

        The old code checked the order book exactly once, immediately after placing the
        order, and crashed with an unhandled TypeError if the order hadn't shown up yet.
        """
        deadline = time_module.monotonic() + timeout_seconds
        terminal_statuses = {"complete", "rejected", "cancelled"}

        while True:
            try:
                response = self.client.orderBook()
            except Exception as exc:
                logger.warning("orderBook() call failed while polling %s: %s", order_id, exc)
                response = None

            if response and response.get("data"):
                for order in response["data"]:
                    if order.get("orderid") == order_id:
                        status = (order.get("status") or "").lower()
                        price = order.get("price") or 0
                        avg_price = order.get("averageprice") or 0
                        effective_price = float(price) if float(price) != 0 else float(avg_price)
                        if status in terminal_statuses:
                            return OrderResult(order_id=order_id, status=status, price=effective_price)

            if time_module.monotonic() >= deadline:
                logger.error("Timed out waiting for order %s to settle", order_id)
                return OrderResult(order_id=order_id, status="unknown", price=0.0)

            time_module.sleep(poll_seconds)

    def rms_limits(self) -> dict:
        return self.client.rmsLimit()
