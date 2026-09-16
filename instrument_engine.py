from __future__ import annotations

import logging
import uuid
from datetime import date, datetime, time

from broker import AngelOneBroker, OrderRejected, OrderResult
from config import ROOT_DIR, AppConfig, InstrumentConfig
from ema_crossover_signal import get_signal
from historical_data import update_historical_data
from notifier import TelegramNotifier
from risk import RiskManager
from state import TradeStore

logger = logging.getLogger("alpha.engine")


class InstrumentEngine:
    """One self-contained trading engine per index (NIFTY, BANKNIFTY, ...).

    The original bot duplicated this entire block of logic once per instrument inside
    main.py. That copy-paste is exactly where several bugs crept in (BankNifty reading
    Nifty's LTP for a threshold check, BankNifty's order id being written into the
    Nifty variable, etc.) A single parameterized engine removes that entire class of
    bug by construction: there is only one code path to fix or audit.
    """

    def __init__(
        self,
        cfg: InstrumentConfig,
        app_cfg: AppConfig,
        broker: AngelOneBroker,
        store: TradeStore,
        risk: RiskManager,
        notifier: TelegramNotifier,
    ):
        self.cfg = cfg
        self.app_cfg = app_cfg
        self.broker = broker
        self.store = store
        self.risk = risk
        self.notifier = notifier
        self.index_token = cfg.index_token or broker.token_lookup(cfg.exchange_index_symbol)
        if not self.index_token:
            raise RuntimeError(f"Could not resolve index token for {cfg.exchange_index_symbol}")

        interval_suffix = app_cfg.historical_data.interval.lower()
        self._historical_excel_path = (
            ROOT_DIR / app_cfg.historical_data.storage_dir / f"{cfg.name}_{interval_suffix}.xlsx"
        )
        self._last_acted_signal_time = None
        """Timestamp of the last signal candle we already attempted to act on
        (entered or not) -- without this, the same crossover event would be
        re-evaluated on every poll cycle until a new candle forms."""

    def _is_expiry_today(self, atm_df) -> bool:
        expiry_str = atm_df["expiry"].iloc[0]
        expiry_date = datetime.strptime(expiry_str, "%d%b%Y").date()
        return expiry_date == date.today()

    def run_once(self) -> None:
        now = datetime.now()

        ltp = self.broker.underlying_price("NSE", self.cfg.exchange_index_symbol, self.index_token)
        if not ltp:
            logger.warning("%s: could not fetch LTP this cycle, skipping", self.cfg.name)
            return

        atm_df = self.broker.option_contracts_atm(self.cfg.exchange_index_symbol, ltp)
        if atm_df.empty:
            logger.warning("%s: no ATM contracts found, skipping", self.cfg.name)
            return

        expiry_today = self._is_expiry_today(atm_df)

        open_trade = self.store.get_open_trade(self.cfg.name)
        if open_trade is not None:
            # Always manage an existing position regardless of expiry day -- never
            # abandon a live trade, only refuse to open new ones on expiry day.
            force_exit = self.cfg.force_exit_time_expiry_day if expiry_today else self.cfg.force_exit_time
            self._manage_open_trade(open_trade, ltp, now, force_exit)
            return

        if expiry_today:
            logger.info(
                "%s: today is this contract's expiry day -- no new entries "
                "(0DTE gamma/spread risk the backtest can't see; not a backtested behavior)",
                self.cfg.name,
            )
            return

        self._consider_entry(ltp, now, self.cfg.entry_cutoff_time)

    def _consider_entry(self, ltp: float, now: datetime, entry_cutoff: time) -> None:
        if now.time() < self.cfg.entry_start_time or now.time() >= entry_cutoff:
            return

        allowed, reason = self.risk.can_open_new_trade(self.cfg.name)
        if not allowed:
            logger.info("%s: entry blocked by risk manager: %s", self.cfg.name, reason)
            return

        hist_cfg = self.app_cfg.historical_data
        candles = update_historical_data(
            self.broker,
            self.cfg.candle_token,
            self._historical_excel_path,
            interval=hist_cfg.interval,
            interval_minutes=hist_cfg.interval_minutes,
            lookback_days=hist_cfg.lookback_days,
        )
        signal = get_signal(self.cfg.exchange_index_symbol, candles)
        logger.info("%s signal: %s (ltp=%.1f)", self.cfg.name, signal.direction, ltp)

        if signal.direction == "WAIT":
            return

        # A crossover is a discrete event tied to one specific candle -- without
        # this check, the same signal would be re-evaluated (and re-attempted if
        # entry failed) on every poll cycle until the next candle forms.
        if signal.signal_candle_time == self._last_acted_signal_time:
            return
        self._last_acted_signal_time = signal.signal_candle_time

        self.notifier.send(
            f"SIGNAL: {self.cfg.name} {signal.direction} at ltp={ltp:.1f}"
        )

        if signal.direction == "BUY":
            self._enter(ltp + self.cfg.buy_strike_offset, "CE", underlying_ltp=ltp)
        elif signal.direction == "SELL":
            self._enter(ltp + self.cfg.sell_strike_offset, "PE", underlying_ltp=ltp)

    def _execute_order(
        self, symbol: str, token: str, transaction_type: str, quantity: int
    ) -> OrderResult | None:
        """Places a real order, or simulates one when app_cfg.paper_trading is set.
        Returns None on failure (rejected, didn't fill, or -- paper mode only --
        the option's LTP couldn't be fetched to simulate a fill).

        Paper trading exercises every other part of the system exactly as real
        trading would (same signal, same risk manager, same TradeStore) -- only
        this one call is swapped out, so a 30-day paper run is a faithful test of
        the whole pipeline, not just the signal.
        """
        if self.app_cfg.paper_trading:
            fill_price = self.broker.underlying_price("NFO", symbol, token)
            if not fill_price:
                logger.error("%s: [PAPER] could not fetch LTP for %s to simulate a fill",
                             self.cfg.name, symbol)
                return None
            order_id = f"PAPER-{uuid.uuid4().hex[:10]}"
            logger.info("%s: [PAPER] simulated %s %s @ %.2f x%d",
                        self.cfg.name, transaction_type, symbol, fill_price, quantity)
            return OrderResult(order_id=order_id, status="complete", price=fill_price)

        try:
            order_id = self.broker.place_market_order(symbol, token, transaction_type, quantity)
        except OrderRejected as exc:
            logger.error("%s: %s order rejected: %s", self.cfg.name, transaction_type, exc)
            return None

        result = self.broker.wait_for_order_result(
            order_id, self.app_cfg.order_fill_timeout_seconds, self.app_cfg.order_fill_poll_seconds,
        )
        if result.status != "complete":
            logger.error("%s: %s order %s did not complete (status=%s)",
                         self.cfg.name, transaction_type, order_id, result.status)
            return None
        return result

    def _enter(self, strike_reference_price: float, option_type: str, underlying_ltp: float) -> None:
        atm_df = self.broker.option_contracts_atm(self.cfg.exchange_index_symbol, strike_reference_price)
        candidates = atm_df[atm_df["symbol"].str.contains(option_type)]
        if candidates.empty:
            logger.error("%s: no %s contract found near %.1f", self.cfg.name, option_type, strike_reference_price)
            return
        contract = candidates.iloc[0]
        strike = float(contract["strike"]) / 100  # instrument master quotes strikes in paise

        result = self._execute_order(contract["symbol"], contract["token"], "BUY", self.cfg.quantity)
        if result is None:
            return

        mode = "PAPER" if self.app_cfg.paper_trading else "LIVE"
        self.store.open_trade(
            instrument=self.cfg.name,
            order_id=result.order_id,
            symbol=contract["symbol"],
            trade_type=option_type,
            token=contract["token"],
            entry_price=result.price,
            quantity=self.cfg.quantity,
            entry_underlying_price=underlying_ltp,
            strike=strike,
            mode=mode,
        )
        logger.info("%s: [%s] entered %s %s @ %.2f x%d (underlying=%.1f)", self.cfg.name, mode, option_type,
                    contract["symbol"], result.price, self.cfg.quantity, underlying_ltp)
        self.notifier.send(
            f"ENTRY [{mode}]: {self.cfg.name} {option_type} {contract['symbol']} "
            f"@ {result.price:.2f} x{self.cfg.quantity} (underlying={underlying_ltp:.1f})"
        )

    def _manage_open_trade(self, open_trade, underlying_ltp: float, now: datetime, force_exit: time) -> None:
        entry_underlying = open_trade.entry_underlying_price
        take_profit_points = self.cfg.take_profit_points
        stop_loss_points = self.cfg.stop_loss_points

        if open_trade.trade_type == "CE":
            take_profit_price = entry_underlying + take_profit_points
            stop_loss_price = entry_underlying - stop_loss_points
            hit_take_profit = underlying_ltp >= take_profit_price
            hit_stop_loss = underlying_ltp <= stop_loss_price
        else:  # PE
            take_profit_price = entry_underlying - take_profit_points
            stop_loss_price = entry_underlying + stop_loss_points
            hit_take_profit = underlying_ltp <= take_profit_price
            hit_stop_loss = underlying_ltp >= stop_loss_price

        hit_time_exit = now.time() >= force_exit

        if not (hit_take_profit or hit_stop_loss or hit_time_exit):
            logger.info("%s: holding %s, underlying=%.2f entry_underlying=%.2f tp=%.2f sl=%.2f",
                        self.cfg.name, open_trade.symbol, underlying_ltp, entry_underlying,
                        take_profit_price, stop_loss_price)
            return

        reason = "take_profit" if hit_take_profit else "stop_loss" if hit_stop_loss else "time_exit"
        logger.info("%s: exiting %s due to %s (underlying=%.2f)",
                     self.cfg.name, open_trade.symbol, reason, underlying_ltp)

        entry_price = open_trade.entry_price

        result = self._execute_order(open_trade.symbol, open_trade.token, "SELL", open_trade.quantity)
        if result is None:
            if open_trade.mode != "PAPER":
                logger.error("%s: exit order failed -- position may still be open at "
                             "the broker, investigate manually", self.cfg.name)
            return

        self.store.close_trade(open_trade.id, result.price)
        pnl = (result.price - entry_price) * open_trade.quantity
        logger.info("%s: closed %s entry=%.2f exit=%.2f pnl=%.2f",
                    self.cfg.name, open_trade.symbol, entry_price, result.price, pnl)
        self.notifier.send(
            f"EXIT [{reason}]: {self.cfg.name} {open_trade.symbol} "
            f"entry={entry_price:.2f} exit={result.price:.2f} pnl={pnl:.2f}"
        )
