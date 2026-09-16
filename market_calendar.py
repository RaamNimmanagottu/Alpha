from __future__ import annotations

from datetime import date, datetime

from config import MarketConfig


def is_weekend(today: date | None = None) -> bool:
    today = today or date.today()
    return today.weekday() >= 5  # Saturday=5, Sunday=6


def is_holiday(holidays: dict[str, str], today: date | None = None) -> bool:
    today = today or date.today()
    return today.strftime("%d-%b-%Y") in holidays


def holiday_name(holidays: dict[str, str], today: date | None = None) -> str | None:
    today = today or date.today()
    return holidays.get(today.strftime("%d-%b-%Y"))


def non_trading_reason(holidays: dict[str, str], today: date | None = None) -> str | None:
    """Return why `today` isn't a trading day, or None if it is one."""
    today = today or date.today()
    if is_weekend(today):
        return f"weekend ({today.strftime('%A')})"
    name = holiday_name(holidays, today)
    if name is not None:
        return f"holiday: {name}" if name else "holiday"
    return None


def is_trading_day(holidays: dict[str, str], today: date | None = None) -> bool:
    return non_trading_reason(holidays, today) is None


def is_market_open(market: MarketConfig, now: datetime | None = None) -> bool:
    """Always re-evaluated against the *current* time.

    The previous implementation captured `is_market_open()` and `datetime.now()`
    exactly once before entering the trading loop, so the bot never actually noticed
    market close and its time-based exit rules never fired for the rest of the day.
    This function must be called fresh on every loop iteration.
    """
    now = now or datetime.now()
    if now.weekday() >= 5:
        return False
    open_dt = now.replace(
        hour=market.open_time.hour, minute=market.open_time.minute, second=0, microsecond=0
    )
    close_dt = now.replace(
        hour=market.close_time.hour, minute=market.close_time.minute, second=0, microsecond=0
    )
    return open_dt <= now <= close_dt


def market_phase(market: MarketConfig, now: datetime | None = None) -> str:
    """One of 'before_open', 'open', 'closed'.

    Distinct from is_market_open() on purpose: if the VM is started early (e.g. the
    external scheduler boots it at 9:00 for a 9:22 open), the main loop must WAIT for
    'before_open' rather than treat it the same as 'closed' -- otherwise the bot exits
    (and, with shutdown_vm_on_exit, powers the machine off) before the market ever
    opens, and never trades that day.
    """
    now = now or datetime.now()
    if now.time() < market.open_time:
        return "before_open"
    if now.time() >= market.close_time:
        return "closed"
    return "open"
