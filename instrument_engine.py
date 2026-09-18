from __future__ import annotations

import logging
import uuid
from datetime import date, datetime, time

import pandas as pd

from broker import AngelOneBroker, OrderRejected, OrderResult
from cci_signal import get_signal as _cci_get_signal
from config import ROOT_DIR, AppConfig, InstrumentConfig
from ema_crossover_signal import get_signal as _ema_crossover_get_signal
from ema_crossover_21_50_signal import get_signal as _ema_crossover_21_50_get_signal
from ema_crossover_confirmed_signal import get_signal as _ema_crossover_confirmed_get_signal
from historical_data import update_historical_data
from keltner_channel_signal import get_signal as _keltner_channel_get_signal
from momentum_zero_cross_signal import get_signal as _momentum_zero_cross_get_signal
from notifier import TelegramNotifier
from risk import RiskManager
from rsi_oversold_signal import get_signal as _rsi_oversold_get_signal
from state import TradeStore

logger = logging.getLogger("alpha.engine")

SIGNAL_STRATEGIES = {
    "ema_crossover": _ema_crossover_get_signal,
    "rsi_oversold": _rsi_oversold_get_signal,
    "keltner_channel": _keltner_channel_get_signal,
    "ema_crossover_21_50": _ema_crossover_21_50_get_signal,
    "cci_overbought_oversold": _cci_get_signal,
    "momentum_zero_cross": _momentum_zero_cross_get_signal,
    "ema_crossover_confirmed": _ema_crossover_confirmed_get_signal,
}
"""Per-instrument signal generator dispatch (config.yaml's signal_strategy
field, validated in config.py). Different instruments genuinely need different
signals, each independently backtested on 1000 days of real data (see
RULES.md): NIFTY/BANKNIFTY use EMA9/21 crossover, FINNIFTY/RELIANCE/SBIN use
Keltner Channel Breakout, HDFCBANK uses EMA21/50, ICICIBANK uses CCI
overbought/oversold, TCS uses Momentum zero-cross, INFY uses 2-candle
confirmed EMA9/21. Never assume one strategy transfers to another instrument
without backtesting it there."""


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
        self._get_signal = SIGNAL_STRATEGIES[cfg.signal_strategy]

        interval_suffix = app_cfg.historical_data.interval.lower()
        self._historical_excel_path = (
            ROOT_DIR / app_cfg.historical_data.storage_dir / f"{cfg.name}_{interval_suffix}.xlsx"
        )
        self._last_acted_signal_time = None
        """Timestamp of the last signal candle we already attempted to act on
        (entered or not) -- without this, the same crossover event would be
        re-evaluated on every poll cycle until a new candle forms."""

        self._last_iv_check_time: datetime | None = None
        self._last_known_iv: float | None = None
        """Throttled IV cache for the currently open position (see _maybe_fetch_iv).
        Explicitly reset to None in _enter() on every new trade -- otherwise a stale
        value left over from a just-closed trade could look like an IV crash on the
        very first cycle of a brand new one."""

        self._pending_entry: dict | None = None
        """A crossover signal that was too "extended" (see pullback_entry_enabled)
        to chase immediately -- waiting for price to pull back to the crossover
        candle's own low (BUY) / high (SELL) instead. In-memory only, same as
        _last_acted_signal_time: a same-day bot restart loses it, which is fine --
        the underlying signal will simply re-evaluate fresh next cycle."""

    def _is_expiry_today(self, atm_df) -> bool:
        expiry_str = atm_df["expiry"].iloc[0]
        expiry_date = datetime.strptime(expiry_str, "%d%b%Y").date()
        return expiry_date == date.today()

    def _get_candles(self) -> pd.DataFrame:
        hist_cfg = self.app_cfg.historical_data
        return update_historical_data(
            self.broker,
            self.cfg.candle_token,
            self._historical_excel_path,
            interval=hist_cfg.interval,
            interval_minutes=hist_cfg.interval_minutes,
            lookback_days=hist_cfg.lookback_days,
        )

    def prefetch_candles(self) -> None:
        """Warm the historical-candle cache while waiting for market open, so the
        first run_once() after open doesn't pay for a fresh fetch (up to 100 days,
        on a never-before-run instrument) on the clock. Safe to call on every
        before-open poll cycle -- update_historical_data() already throttles
        itself to one real fetch per candle interval."""
        self._get_candles()

    def run_once(self) -> None:
        now = datetime.now()

        ltp = self.broker.underlying_price(self.cfg.underlying_exchange, self.cfg.exchange_index_symbol, self.index_token)
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
            option_ltp = self.broker.underlying_price(self.cfg.options_exchange, open_trade.symbol, open_trade.token)
            candles = self._get_candles()
            latest_signal = self._get_signal(self.cfg.exchange_index_symbol, candles)
            expiry_str = atm_df["expiry"].iloc[0]
            current_iv = self._maybe_fetch_iv(open_trade, expiry_str)
            self._manage_open_trade(
                open_trade, ltp, option_ltp, now, force_exit, candles, latest_signal, current_iv
            )
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
        if self._pending_entry is not None:
            self._check_pending_entry(ltp, now, entry_cutoff)
            return

        if now.time() < self.cfg.entry_start_time or now.time() >= entry_cutoff:
            return

        allowed, reason = self.risk.can_open_new_trade(self.cfg.name)
        if not allowed:
            logger.info("%s: entry blocked by risk manager: %s", self.cfg.name, reason)
            return

        candles = self._get_candles()
        signal = self._get_signal(self.cfg.exchange_index_symbol, candles)
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

        # Backtested on 1000 days of NIFTY 5-min data: chasing an already-extended
        # crossover candle (>= pullback_extended_threshold_points high-low range)
        # underperforms waiting for a pullback to that candle's own low/high instead
        # -- +10.8% total points, better win rate AND avg points/trade, vs entering
        # immediately, at a threshold around 100pts. Below the threshold, immediate
        # entry (the original backtested baseline) still wins, so only extended
        # candles get the pullback treatment.
        crossover_candle = candles.iloc[-1]
        candle_range = crossover_candle["high"] - crossover_candle["low"]
        extended = (
            self.app_cfg.pullback_entry_enabled
            and candle_range >= self.app_cfg.pullback_extended_threshold_points
        )

        if signal.direction == "BUY":
            if extended:
                self._set_pending_entry("CE", crossover_candle["low"], ltp, candle_range, signal.signal_candle_time)
            else:
                self._enter(ltp + self.cfg.buy_strike_offset, "CE", underlying_ltp=ltp)
        elif signal.direction == "SELL":
            if extended:
                self._set_pending_entry("PE", crossover_candle["high"], ltp, candle_range, signal.signal_candle_time)
            else:
                self._enter(ltp + self.cfg.sell_strike_offset, "PE", underlying_ltp=ltp)

    def _set_pending_entry(
        self, direction: str, limit_price: float, signal_ltp: float, candle_range: float, signal_candle_time
    ) -> None:
        self._pending_entry = {
            "direction": direction, "limit_price": limit_price, "signal_candle_time": signal_candle_time,
        }
        logger.info(
            "%s: crossover candle extended (range=%.1f >= %.1f) -- waiting for pullback to %.1f "
            "instead of chasing at %.1f", self.cfg.name, candle_range,
            self.app_cfg.pullback_extended_threshold_points, limit_price, signal_ltp,
        )
        self.notifier.send(
            f"PULLBACK WAIT: {self.cfg.name} {direction} signal at ltp={signal_ltp:.1f} was extended "
            f"({candle_range:.1f}pt candle) -- waiting for pullback to {limit_price:.1f} before entering"
        )

    def _check_pending_entry(self, ltp: float, now: datetime, entry_cutoff: time) -> None:
        direction = self._pending_entry["direction"]
        limit_price = self._pending_entry["limit_price"]

        if now.time() >= entry_cutoff:
            logger.info("%s: pending %s pullback entry at %.1f expired unfilled (past entry cutoff)",
                         self.cfg.name, direction, limit_price)
            self.notifier.send(
                f"PULLBACK EXPIRED: {self.cfg.name} {direction} pending entry at {limit_price:.1f} never filled."
            )
            self._pending_entry = None
            return

        # A fresh signal in the opposite direction invalidates the setup that
        # justified waiting for this pullback in the first place.
        candles = self._get_candles()
        latest_signal = self._get_signal(self.cfg.exchange_index_symbol, candles)
        opposite = (
            (direction == "CE" and latest_signal.direction == "SELL")
            or (direction == "PE" and latest_signal.direction == "BUY")
        )
        if opposite and latest_signal.signal_candle_time != self._pending_entry["signal_candle_time"]:
            logger.info("%s: pending %s pullback cancelled -- fresh opposite signal (%s)",
                         self.cfg.name, direction, latest_signal.direction)
            self.notifier.send(
                f"PULLBACK CANCELLED: {self.cfg.name} {direction} pending entry invalidated by opposite signal."
            )
            self._pending_entry = None
            self._last_acted_signal_time = latest_signal.signal_candle_time
            return

        filled = (direction == "CE" and ltp <= limit_price) or (direction == "PE" and ltp >= limit_price)
        if not filled:
            return

        self._pending_entry = None
        offset = self.cfg.buy_strike_offset if direction == "CE" else self.cfg.sell_strike_offset
        logger.info("%s: pullback filled -- %s at %.1f (target was %.1f)", self.cfg.name, direction, ltp, limit_price)
        self._enter(ltp + offset, direction, underlying_ltp=ltp)

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
            fill_price = self.broker.underlying_price(self.cfg.options_exchange, symbol, token)
            if not fill_price:
                logger.error("%s: [PAPER] could not fetch LTP for %s to simulate a fill",
                             self.cfg.name, symbol)
                return None
            order_id = f"PAPER-{uuid.uuid4().hex[:10]}"
            logger.info("%s: [PAPER] simulated %s %s @ %.2f x%d",
                        self.cfg.name, transaction_type, symbol, fill_price, quantity)
            return OrderResult(order_id=order_id, status="complete", price=fill_price)

        try:
            order_id = self.broker.place_market_order(
                symbol, token, transaction_type, quantity, exchange=self.cfg.options_exchange
            )
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

    def _select_atm_contract(self, candidates: pd.DataFrame, strike_reference_price: float):
        atm_strike = candidates.loc[
            (pd.to_numeric(candidates["strike"]) / 100 - strike_reference_price).abs().idxmin(), "strike"
        ]
        return candidates[candidates["strike"] == atm_strike].iloc[0]

    def _select_contract(self, strike_reference_price: float, option_type: str):
        """Returns (contract_row, greeks_row_or_None).

        In "atm" mode (or as a fallback from "delta" mode), greeks_row is None and no
        Telegram/log noise beyond the normal entry message is produced. In "delta"
        mode, every fallback path is logged AND sent to Telegram, since silently
        trading a different strike than configured is exactly the kind of thing that
        must be visible, not just logged.
        """
        nearest_df = self.broker.option_contracts_nearest_expiry(self.cfg.exchange_index_symbol)
        if nearest_df.empty:
            return None, None
        candidates = nearest_df[nearest_df["symbol"].str.contains(option_type)]
        if candidates.empty:
            return None, None

        if self.app_cfg.strike_selection_mode != "delta":
            return self._select_atm_contract(candidates, strike_reference_price), None

        expiry_str = candidates["expiry"].iloc[0]
        greeks_df = self.broker.option_greeks(self.cfg.exchange_index_symbol, expiry_str)
        if greeks_df.empty:
            logger.warning("%s: option greeks unavailable, falling back to ATM strike selection", self.cfg.name)
            self.notifier.send(
                f"WARNING: {self.cfg.name} greeks fetch failed -- entry falling back to ATM strike selection."
            )
            return self._select_atm_contract(candidates, strike_reference_price), None

        type_greeks = greeks_df[greeks_df["optionType"] == option_type]
        # Sanity bounds: reject degenerate/corrupted rows outright rather than trust
        # them -- |delta| must be a real probability-like value, IV must be positive.
        valid_greeks = type_greeks[
            (type_greeks["delta"].abs() > 0) & (type_greeks["delta"].abs() < 1)
            & (type_greeks["impliedVolatility"] > 0)
        ]
        if valid_greeks.empty:
            logger.warning("%s: no valid %s greeks rows, falling back to ATM strike selection",
                            self.cfg.name, option_type)
            self.notifier.send(
                f"WARNING: {self.cfg.name} greeks data failed validation -- "
                f"entry falling back to ATM strike selection."
            )
            return self._select_atm_contract(candidates, strike_reference_price), None

        target = self.app_cfg.target_delta
        best_greek = valid_greeks.loc[(valid_greeks["delta"].abs() - target).abs().idxmin()]

        selected_strike_paise = round(best_greek["strikePrice"] * 100)
        matching = candidates[pd.to_numeric(candidates["strike"]) == selected_strike_paise]
        if matching.empty:
            logger.warning(
                "%s: delta-selected strike %.0f (delta=%.3f) has no tradeable contract, falling back to ATM",
                self.cfg.name, best_greek["strikePrice"], best_greek["delta"],
            )
            self.notifier.send(
                f"WARNING: {self.cfg.name} delta-selected strike {best_greek['strikePrice']:.0f} "
                f"not tradeable -- entry falling back to ATM strike selection."
            )
            return self._select_atm_contract(candidates, strike_reference_price), None

        return matching.iloc[0], best_greek

    def _enter(self, strike_reference_price: float, option_type: str, underlying_ltp: float) -> None:
        contract, greek = self._select_contract(strike_reference_price, option_type)
        if contract is None:
            logger.error("%s: no %s contract found near %.1f", self.cfg.name, option_type, strike_reference_price)
            return
        strike = float(contract["strike"]) / 100  # instrument master quotes strikes in paise

        result = self._execute_order(contract["symbol"], contract["token"], "BUY", self.cfg.quantity)
        if result is None:
            return

        mode = "PAPER" if self.app_cfg.paper_trading else "LIVE"
        entry_iv = float(greek["impliedVolatility"]) if greek is not None else None
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
            entry_iv=entry_iv,
        )
        # A stale IV cached from a just-closed trade must never leak into this new
        # one's IV-crush check -- force a fresh fetch on its first management cycle.
        self._last_iv_check_time = None
        self._last_known_iv = entry_iv

        greeks_note = ""
        if greek is not None:
            greeks_note = (
                f" | delta={greek['delta']:.3f} gamma={greek['gamma']:.4f} theta={greek['theta']:.2f} "
                f"vega={greek['vega']:.2f} iv={greek['impliedVolatility']:.2f}%"
            )
        logger.info("%s: [%s] entered %s %s @ %.2f x%d (underlying=%.1f)%s", self.cfg.name, mode, option_type,
                    contract["symbol"], result.price, self.cfg.quantity, underlying_ltp, greeks_note)
        self.notifier.send(
            f"ENTRY [{mode}]: {self.cfg.name} {option_type} {contract['symbol']} "
            f"@ {result.price:.2f} x{self.cfg.quantity} (underlying={underlying_ltp:.1f}){greeks_note}"
        )

    def _maybe_fetch_iv(self, open_trade, expiry_str: str) -> float | None:
        """Throttled IV fetch for the open position -- optionGreek is a separate
        whole-chain API call, and doing it every 3s poll cycle risks the broker's
        rate limit (observed directly in live testing). Returns the last known-good
        IV on a skipped or failed cycle rather than None, so one transient failure
        can't masquerade as "IV crashed to nothing" and falsely trigger an exit.
        """
        now = datetime.now()
        if (
            self._last_iv_check_time is not None
            and (now - self._last_iv_check_time).total_seconds() < self.app_cfg.iv_check_interval_seconds
        ):
            return self._last_known_iv

        self._last_iv_check_time = now
        greeks_df = self.broker.option_greeks(self.cfg.exchange_index_symbol, expiry_str)
        if greeks_df.empty:
            return self._last_known_iv

        matches = greeks_df[
            (greeks_df["optionType"] == open_trade.trade_type)
            & ((greeks_df["strikePrice"] - open_trade.strike).abs() < 0.01)
        ]
        if matches.empty:
            return self._last_known_iv

        iv = float(matches.iloc[0]["impliedVolatility"])
        if not (0 < iv < 200):  # sanity bound -- reject corrupted/degenerate values
            return self._last_known_iv

        self._last_known_iv = iv
        return iv

    def _momentum_move(self, candles: pd.DataFrame, trade_type: str) -> float | None:
        """Points moved in the trade's favorable direction over the last
        momentum_window_minutes, or None if there isn't enough candle history yet
        to measure it."""
        if candles.empty:
            return None
        cutoff = candles["date"].iloc[-1] - pd.Timedelta(minutes=self.app_cfg.momentum_window_minutes)
        window = candles[candles["date"] >= cutoff]
        if len(window) < 2:
            return None
        start_price = float(window["close"].iloc[0])
        end_price = float(window["close"].iloc[-1])
        return (end_price - start_price) if trade_type == "CE" else (start_price - end_price)

    def _manage_open_trade(
        self,
        open_trade,
        underlying_ltp: float,
        option_ltp: float,
        now: datetime,
        force_exit: time,
        candles: pd.DataFrame,
        latest_signal,
        current_iv: float | None,
    ) -> None:
        entry_underlying = open_trade.entry_underlying_price
        entry_price = open_trade.entry_price
        take_profit_points = self.cfg.take_profit_points
        stop_loss_points = self.cfg.stop_loss_points

        # -- Static index-based take-profit/stop-loss: the backtested baseline -----
        if open_trade.trade_type == "CE":
            index_take_profit_price = entry_underlying + take_profit_points
            static_stop_loss_price = entry_underlying - stop_loss_points
            hit_index_take_profit = underlying_ltp >= index_take_profit_price
        else:  # PE
            index_take_profit_price = entry_underlying - take_profit_points
            static_stop_loss_price = entry_underlying + stop_loss_points
            hit_index_take_profit = underlying_ltp <= index_take_profit_price

        # -- Trailing stop-loss (live-only): can only tighten the stop, never loosen
        # it past the static level above --------------------------------------------
        stop_loss_price = static_stop_loss_price
        peak = (
            open_trade.peak_favorable_underlying
            if open_trade.peak_favorable_underlying is not None
            else entry_underlying
        )
        if self.app_cfg.trailing_stop_enabled:
            if open_trade.trade_type == "CE":
                new_peak = max(peak, underlying_ltp)
                favorable_move = new_peak - entry_underlying
                if favorable_move >= self.app_cfg.trailing_stop_activation_points:
                    stop_loss_price = max(static_stop_loss_price, new_peak - self.app_cfg.trailing_stop_distance_points)
            else:  # PE
                new_peak = min(peak, underlying_ltp)
                favorable_move = entry_underlying - new_peak
                if favorable_move >= self.app_cfg.trailing_stop_activation_points:
                    stop_loss_price = min(static_stop_loss_price, new_peak + self.app_cfg.trailing_stop_distance_points)

            if new_peak != peak:
                self.store.update_peak_favorable(open_trade.id, new_peak)
            peak = new_peak

        if open_trade.trade_type == "CE":
            hit_stop_loss = underlying_ltp <= stop_loss_price
        else:
            hit_stop_loss = underlying_ltp >= stop_loss_price

        # -- Premium %-based take-profit ---------------------------------------------
        premium_take_profit_price = entry_price * (1 + self.cfg.take_profit_premium_pct / 100)
        hit_premium_take_profit = option_ltp > 0 and option_ltp >= premium_take_profit_price
        hit_take_profit = hit_index_take_profit or hit_premium_take_profit

        # -- Signal-reversal exit (live-only) -----------------------------------------
        hit_signal_reversal = False
        if self.app_cfg.signal_reversal_exit_enabled and latest_signal is not None:
            hit_signal_reversal = (
                (open_trade.trade_type == "CE" and latest_signal.direction == "SELL")
                or (open_trade.trade_type == "PE" and latest_signal.direction == "BUY")
            )

        # -- IV-crush exit (live-only) -------------------------------------------------
        hit_iv_exit = False
        if self.app_cfg.iv_exit_enabled and open_trade.entry_iv is not None and current_iv is not None:
            iv_drop_pct = (open_trade.entry_iv - current_iv) / open_trade.entry_iv * 100
            hit_iv_exit = iv_drop_pct >= self.app_cfg.iv_exit_drop_pct

        # -- Momentum exit (live-only): a fast favorable move -> lock in profit ------
        hit_momentum_exit = False
        if self.app_cfg.momentum_exit_enabled:
            move = self._momentum_move(candles, open_trade.trade_type)
            hit_momentum_exit = move is not None and move >= self.app_cfg.momentum_exit_points

        hit_time_exit = now.time() >= force_exit

        if not (
            hit_take_profit or hit_stop_loss or hit_time_exit
            or hit_signal_reversal or hit_iv_exit or hit_momentum_exit
        ):
            logger.info(
                "%s: holding %s, underlying=%.2f entry_underlying=%.2f index_tp=%.2f sl=%.2f "
                "option_ltp=%.2f entry_price=%.2f premium_tp=%.2f iv=%s entry_iv=%s",
                self.cfg.name, open_trade.symbol, underlying_ltp, entry_underlying,
                index_take_profit_price, stop_loss_price, option_ltp, entry_price, premium_take_profit_price,
                f"{current_iv:.2f}" if current_iv is not None else "n/a",
                f"{open_trade.entry_iv:.2f}" if open_trade.entry_iv is not None else "n/a",
            )
            return

        if hit_stop_loss:
            reason = "trailing_stop_loss" if stop_loss_price != static_stop_loss_price else "stop_loss"
        elif hit_signal_reversal:
            reason = "signal_reversal"
        elif hit_iv_exit:
            reason = "iv_crush"
        elif hit_momentum_exit:
            reason = "momentum"
        elif hit_index_take_profit:
            reason = "take_profit_index"
        elif hit_premium_take_profit:
            reason = "take_profit_premium"
        else:
            reason = "time_exit"
        logger.info("%s: exiting %s due to %s (underlying=%.2f, option_ltp=%.2f, sl=%.2f, iv=%s)",
                     self.cfg.name, open_trade.symbol, reason, underlying_ltp, option_ltp, stop_loss_price,
                     f"{current_iv:.2f}" if current_iv is not None else "n/a")

        result = self._execute_order(open_trade.symbol, open_trade.token, "SELL", open_trade.quantity)
        if result is None:
            if open_trade.mode != "PAPER":
                logger.error("%s: exit order failed -- position may still be open at "
                             "the broker, investigate manually", self.cfg.name)
            return

        self.store.close_trade(open_trade.id, result.price)
        pnl = (result.price - entry_price) * open_trade.quantity
        new_capital = self.store.update_capital(pnl)
        logger.info("%s: closed %s entry=%.2f exit=%.2f pnl=%.2f capital=%.2f",
                    self.cfg.name, open_trade.symbol, entry_price, result.price, pnl, new_capital)
        self.notifier.send(
            f"EXIT [{reason}]: {self.cfg.name} {open_trade.symbol} "
            f"entry={entry_price:.2f} exit={result.price:.2f} pnl={pnl:.2f} | capital={new_capital:.2f}"
        )
