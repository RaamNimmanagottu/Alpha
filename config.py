from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import time
from pathlib import Path

import yaml
from dotenv import load_dotenv

from paths import ROOT_DIR


def _parse_time(value: str) -> time:
    hh, mm = value.split(":")
    return time(int(hh), int(mm))


_VALID_STRIKE_SELECTION_MODES = ("atm", "delta")


def _parse_strike_selection_mode(raw: dict) -> str:
    mode = raw.get("strike_selection_mode", "atm")
    if mode not in _VALID_STRIKE_SELECTION_MODES:
        raise ValueError(
            f"config.yaml: strike_selection_mode must be one of {_VALID_STRIKE_SELECTION_MODES}, got {mode!r}"
        )
    return mode


def _parse_target_delta(raw: dict) -> float:
    value = float(raw.get("target_delta", 0.5))
    if not (0.0 < value < 1.0):
        raise ValueError(f"config.yaml: target_delta must be between 0 and 1 (exclusive), got {value}")
    return value


def _parse_positive_float(raw: dict, key: str, default: float) -> float:
    value = float(raw.get(key, default))
    if value <= 0:
        raise ValueError(f"config.yaml: {key} must be > 0, got {value}")
    return value


def _parse_pct(raw: dict, key: str, default: float) -> float:
    value = float(raw.get(key, default))
    if not (0.0 < value < 100.0):
        raise ValueError(f"config.yaml: {key} must be between 0 and 100 (exclusive), got {value}")
    return value


_VALID_SIGNAL_STRATEGIES = ("ema_crossover", "rsi_oversold")


def _parse_signal_strategy(instrument_raw: dict) -> str:
    strategy = instrument_raw.get("signal_strategy", "ema_crossover")
    if strategy not in _VALID_SIGNAL_STRATEGIES:
        raise ValueError(
            f"config.yaml: instrument {instrument_raw.get('name')!r} has signal_strategy="
            f"{strategy!r}, must be one of {_VALID_SIGNAL_STRATEGIES}"
        )
    return strategy


@dataclass(frozen=True)
class Credentials:
    api_key: str
    client_id: str
    mpin: str
    totp_secret: str

    @staticmethod
    def from_env() -> "Credentials":
        load_dotenv(ROOT_DIR / ".env")
        missing = [
            name
            for name in ("ANGEL_API_KEY", "ANGEL_CLIENT_ID", "ANGEL_MPIN", "ANGEL_TOTP_SECRET")
            if not os.getenv(name)
        ]
        if missing:
            raise RuntimeError(
                f"Missing required credentials in .env: {', '.join(missing)}. "
                f"Copy .env.example to .env and fill it in."
            )
        return Credentials(
            api_key=os.environ["ANGEL_API_KEY"],
            client_id=os.environ["ANGEL_CLIENT_ID"],
            mpin=os.environ["ANGEL_MPIN"],
            totp_secret=os.environ["ANGEL_TOTP_SECRET"],
        )


@dataclass(frozen=True)
class InstrumentConfig:
    name: str
    exchange_index_symbol: str
    index_token: str | None
    candle_token: str
    """Separate from index_token: NSE indices use a distinct token for historical
    candle data (e.g. 99926000 for NIFTY) from the one used for LTP quotes (e.g.
    26000) -- the LTP token silently returns zero candles from getCandleData."""
    signal_strategy: str
    """Which signal generator this instrument uses (see instrument_engine.py's
    SIGNAL_STRATEGIES registry) -- different instruments genuinely need
    different signals. NIFTY's backtested winner (EMA9/21 crossover) actually
    LOSES money on BANKNIFTY; RSI overbought/oversold wins there instead. Not a
    one-size-fits-all setting -- validate per instrument before choosing."""
    lot_size: int
    quantity_lots: int
    buy_strike_offset: float
    sell_strike_offset: float
    take_profit_points: float
    """Points of INDEX movement that triggers a take-profit exit -- matches
    backtest/trade_simulator.py exactly, since that's what was actually validated in
    backtesting."""
    take_profit_premium_pct: float
    """Take-profit also fires if the option's own premium rises this % from the
    entry fill (e.g. entry 150, pct=10 -> exit at 165), independent of the index-based
    check above -- whichever condition hits first wins. Not backtested; a live-only
    addition to lock in gains faster when the premium outpaces the index (e.g. IV
    expansion)."""
    stop_loss_points: float
    entry_start_time: time
    """No entries before this time -- matches the backtest's ENTRY_START_TIME."""
    entry_cutoff_time: time
    """No new entries after this time. On the contract's own expiry day, no new
    entries are taken at all regardless of this cutoff (see instrument_engine.py)."""
    force_exit_time: time
    force_exit_time_expiry_day: time
    """Used only to force-close a position that is somehow still open on expiry
    day (safety fallback -- normal same-day exits mean this shouldn't happen)."""

    @property
    def quantity(self) -> int:
        return self.lot_size * self.quantity_lots


@dataclass(frozen=True)
class RiskConfig:
    daily_loss_limit: float
    max_trades_per_day: int
    max_trades_per_instrument: int


@dataclass(frozen=True)
class MarketConfig:
    open_time: time
    close_time: time


@dataclass(frozen=True)
class HistoricalDataConfig:
    interval: str
    interval_minutes: int
    lookback_days: int
    storage_dir: str


@dataclass(frozen=True)
class AppConfig:
    poll_interval_seconds: float
    order_fill_timeout_seconds: float
    order_fill_poll_seconds: float
    paper_trading: bool
    """When true, no real orders are ever placed -- entries/exits are simulated
    using live LTP and recorded exactly like real trades (same TradeStore, same risk
    manager, same signal logic). Flip to false manually after reviewing a paper
    trading run; nothing in this codebase auto-graduates itself to real money."""
    strike_selection_mode: str
    """"atm" (default/backtested behavior: always buy the strike closest to spot) or
    "delta" (buy the strike whose |delta| is closest to target_delta, from Angel
    One's live optionGreek data). Falls back to "atm" automatically, per-entry, if
    greeks data is unavailable or fails validation -- entries must never block on
    this. Not backtested; "delta" is a live-only strategy change."""
    target_delta: float
    """Only used when strike_selection_mode="delta". Compared against |delta| so the
    same value works for both CE (positive delta) and PE (negative delta)."""

    trailing_stop_enabled: bool
    """Once the trade has moved trailing_stop_activation_points in its favor, the
    stop-loss trails trailing_stop_distance_points behind the best underlying price
    seen since entry. Can only tighten the stop -- never looser than the original
    static stop_loss_points level. Not backtested; a live-only addition."""
    trailing_stop_activation_points: float
    trailing_stop_distance_points: float

    signal_reversal_exit_enabled: bool
    """Exit immediately if the EMA9/EMA21 signal reverses direction while a trade is
    open (e.g. a SELL signal fires while holding a CE) -- the strategy itself is
    saying the setup that justified the entry no longer holds. Not backtested."""

    iv_exit_enabled: bool
    """Exit if the option's IV has dropped iv_exit_drop_pct from its value at entry,
    even if index points haven't hit stop-loss -- IV crush eroding the premium's
    value out from under an otherwise-fine index move. Requires entry_iv to have been
    recorded (i.e. greeks were available at entry) and a fresh IV read to compare
    against; silently skipped for a cycle if either is unavailable. Not backtested."""
    iv_exit_drop_pct: float
    iv_check_interval_seconds: float
    """Throttles how often IV is re-fetched while a trade is open -- this is a
    separate, whole-chain API call from the per-cycle option LTP fetch, and doing it
    every poll cycle risks hitting the broker's rate limit (observed in testing)."""

    momentum_exit_enabled: bool
    """Exit early if the index moves momentum_exit_points in the trade's favorable
    direction within momentum_window_minutes -- treated as a fast move likely to
    fade/reverse, so lock in the gain rather than wait for the normal target. Not
    backtested; deliberately the take-profit-sooner-on-a-spike interpretation, not
    let-it-run."""
    momentum_window_minutes: float
    momentum_exit_points: float

    pullback_entry_enabled: bool
    """Backtested on 1000 days of NIFTY 5-min data: when the EMA9/21 crossover
    candle is unusually large (see pullback_extended_threshold_points), entering
    immediately means chasing a move that's already mostly happened. Waiting for
    price to pull back to that candle's own low (BUY) / high (SELL) before
    entering beat immediate entry on every metric (total points, win rate, avg
    points/trade) at a threshold around 100pts -- not just one lucky number, the
    improvement held across a wide range (80-150pts). Below the threshold,
    immediate entry (the original backtested baseline) still wins, so only
    extended candles get this treatment. If the pullback never comes before
    entry_cutoff_time, or a fresh opposite signal appears first, the trade is
    skipped entirely rather than chased late."""
    pullback_extended_threshold_points: float

    starting_capital: float
    """Seed value for the account capital ledger (state.py's TradeStore.get_capital),
    used only the very first time it's ever read -- capital compounds across days
    from then on, it does not reset to this value each morning."""

    shutdown_vm_on_exit: bool
    """When true, main.py powers off the machine it's running on after any clean
    exit (holiday, weekend, or market closed for the day) -- for a VM that's meant
    to auto-start each morning and shut down for cost savings otherwise. Defaults to
    false so this never surprises anyone running the bot on their own machine.
    Never fires on an error exit (e.g. broker connect failure), so there's still a
    window to look at what went wrong before the machine disappears."""
    risk: RiskConfig
    market: MarketConfig
    historical_data: HistoricalDataConfig
    instruments: list[InstrumentConfig]
    holiday_lists: dict[int, dict[str, str]]
    """Year -> {"DD-Mon-YYYY": holiday name}, parsed from each holiday_list_<year>
    block in config.yaml. Add a new block every December for the coming year."""

    def holidays_for_year(self, year: int) -> dict[str, str]:
        return self.holiday_lists.get(year, {})

    @staticmethod
    def load(path: Path | None = None) -> "AppConfig":
        path = path or (ROOT_DIR / "config.yaml")
        raw = yaml.safe_load(path.read_text())

        instruments = [
            InstrumentConfig(
                name=i["name"],
                exchange_index_symbol=i["exchange_index_symbol"],
                index_token=i.get("index_token"),
                candle_token=str(i["candle_token"]),
                signal_strategy=_parse_signal_strategy(i),
                lot_size=int(i["lot_size"]),
                quantity_lots=int(i["quantity_lots"]),
                buy_strike_offset=float(i["buy_strike_offset"]),
                sell_strike_offset=float(i["sell_strike_offset"]),
                take_profit_points=float(i["take_profit_points"]),
                take_profit_premium_pct=float(i["take_profit_premium_pct"]),
                stop_loss_points=float(i["stop_loss_points"]),
                entry_start_time=_parse_time(i["entry_start_time"]),
                entry_cutoff_time=_parse_time(i["entry_cutoff_time"]),
                force_exit_time=_parse_time(i["force_exit_time"]),
                force_exit_time_expiry_day=_parse_time(i["force_exit_time_expiry_day"]),
            )
            for i in raw["instruments"]
        ]

        holiday_lists: dict[int, dict[str, str]] = {}
        prefix = "holiday_list_"
        for key, value in raw.items():
            if key.startswith(prefix) and key[len(prefix):].isdigit():
                entries: dict[str, str] = {}
                for item in value:
                    if isinstance(item, dict):
                        entries[item["date"]] = item.get("name", "")
                    else:
                        entries[item] = ""  # plain date string, no name available
                holiday_lists[int(key[len(prefix):])] = entries

        return AppConfig(
            poll_interval_seconds=float(raw["poll_interval_seconds"]),
            order_fill_timeout_seconds=float(raw["order_fill_timeout_seconds"]),
            order_fill_poll_seconds=float(raw["order_fill_poll_seconds"]),
            paper_trading=bool(raw.get("paper_trading", True)),
            strike_selection_mode=_parse_strike_selection_mode(raw),
            target_delta=_parse_target_delta(raw),
            trailing_stop_enabled=bool(raw.get("trailing_stop_enabled", False)),
            trailing_stop_activation_points=_parse_positive_float(raw, "trailing_stop_activation_points", 50.0),
            trailing_stop_distance_points=_parse_positive_float(raw, "trailing_stop_distance_points", 30.0),
            signal_reversal_exit_enabled=bool(raw.get("signal_reversal_exit_enabled", False)),
            iv_exit_enabled=bool(raw.get("iv_exit_enabled", False)),
            iv_exit_drop_pct=_parse_pct(raw, "iv_exit_drop_pct", 20.0),
            iv_check_interval_seconds=_parse_positive_float(raw, "iv_check_interval_seconds", 30.0),
            momentum_exit_enabled=bool(raw.get("momentum_exit_enabled", False)),
            momentum_window_minutes=_parse_positive_float(raw, "momentum_window_minutes", 10.0),
            momentum_exit_points=_parse_positive_float(raw, "momentum_exit_points", 60.0),
            pullback_entry_enabled=bool(raw.get("pullback_entry_enabled", False)),
            pullback_extended_threshold_points=_parse_positive_float(raw, "pullback_extended_threshold_points", 100.0),
            starting_capital=_parse_positive_float(raw, "starting_capital", 200000.0),
            shutdown_vm_on_exit=bool(raw.get("shutdown_vm_on_exit", False)),
            risk=RiskConfig(
                daily_loss_limit=float(raw["risk"]["daily_loss_limit"]),
                max_trades_per_day=int(raw["risk"]["max_trades_per_day"]),
                max_trades_per_instrument=int(raw["risk"]["max_trades_per_instrument"]),
            ),
            market=MarketConfig(
                open_time=_parse_time(raw["market"]["open_time"]),
                close_time=_parse_time(raw["market"]["close_time"]),
            ),
            historical_data=HistoricalDataConfig(
                interval=raw["historical_data"]["interval"],
                interval_minutes=int(raw["historical_data"]["interval_minutes"]),
                lookback_days=int(raw["historical_data"]["lookback_days"]),
                storage_dir=raw["historical_data"]["storage_dir"],
            ),
            instruments=instruments,
            holiday_lists=holiday_lists,
        )
