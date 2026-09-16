from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

import requests

logger = logging.getLogger("alpha.holidays")

NSE_HOME_URL = "https://www.nseindia.com/"
NSE_HOLIDAY_API_URL = "https://www.nseindia.com/api/holiday-master?type=trading"
CACHE_PATH = Path(__file__).resolve().parent.parent / "data" / "nse_holidays_cache.json"

_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

# NSE occasionally changes the key name for the trade date field; try each in order.
_DATE_KEYS = ("tradingDate", "trading_date", "date", "Date")
# Prefer the F&O calendar (what actually matters for index options); fall back to
# equity (CM) if NSE ever renames or drops the FO segment from the response.
_SEGMENT_PREFERENCE = ("FO", "CM")


class HolidayFetchError(Exception):
    pass


def _normalize_date(raw: str) -> str:
    """Return the date as DD-Mon-YYYY, matching the format used everywhere else here."""
    raw = raw.strip()
    for fmt in ("%d-%b-%Y", "%d-%B-%Y", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(raw, fmt).strftime("%d-%b-%Y")
        except ValueError:
            continue
    raise ValueError(f"Unrecognized date format from NSE: {raw!r}")


def fetch_nse_holidays(timeout: float = 15.0) -> set[str]:
    """Fetch this year's trading holiday calendar directly from NSE.

    NSE fronts its API with bot-detection that rejects requests without a real
    browser-like session, so we first hit the homepage to pick up session cookies,
    then call the holiday API using that same session. This is known to fail from
    datacenter/cloud IPs (NSE blocks those outright with a 403) even though it works
    from ordinary residential/office connections -- callers must treat failure as
    routine and fall back to a cache or static list, never crash on it.
    """
    session = requests.Session()
    session.headers.update(_BROWSER_HEADERS)

    try:
        home_resp = session.get(NSE_HOME_URL, timeout=timeout)
        home_resp.raise_for_status()

        api_resp = session.get(
            NSE_HOLIDAY_API_URL,
            headers={"Accept": "application/json", "Referer": NSE_HOME_URL},
            timeout=timeout,
        )
        api_resp.raise_for_status()
        payload = api_resp.json()
    except Exception as exc:
        raise HolidayFetchError(f"Could not reach NSE holiday API: {exc}") from exc

    segment_rows = None
    for segment in _SEGMENT_PREFERENCE:
        if segment in payload and payload[segment]:
            segment_rows = payload[segment]
            break
    if segment_rows is None:
        raise HolidayFetchError(f"NSE response had none of the expected segments {_SEGMENT_PREFERENCE}")

    holidays: set[str] = set()
    for row in segment_rows:
        raw_date = next((row[k] for k in _DATE_KEYS if k in row), None)
        if raw_date is None:
            logger.warning("Skipping NSE holiday row with no recognizable date field: %s", row)
            continue
        try:
            holidays.add(_normalize_date(raw_date))
        except ValueError as exc:
            logger.warning("Skipping unparseable NSE holiday date: %s", exc)

    if not holidays:
        raise HolidayFetchError("NSE response parsed but yielded zero holiday dates")

    return holidays


def _load_cache() -> tuple[set[str], str] | None:
    if not CACHE_PATH.exists():
        return None
    try:
        data = json.loads(CACHE_PATH.read_text())
        return set(data["holidays"]), data["fetched_at"]
    except Exception as exc:
        logger.warning("Could not read holiday cache at %s: %s", CACHE_PATH, exc)
        return None


def _save_cache(holidays: set[str]) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(
        json.dumps({"fetched_at": datetime.now().isoformat(timespec="seconds"),
                    "holidays": sorted(holidays)}, indent=2)
    )


def get_holidays(static_fallback: set[str]) -> set[str]:
    """Live NSE fetch, with a cached-then-static fallback chain.

    Never raises: worst case, this returns the hardcoded list from config.yaml and
    logs loudly that both the live fetch and the cache were unavailable.
    """
    try:
        holidays = fetch_nse_holidays()
        _save_cache(holidays)
        logger.info("Fetched %d holidays live from NSE.", len(holidays))
        return holidays
    except HolidayFetchError as exc:
        logger.warning("Live NSE holiday fetch failed (%s); trying cache.", exc)

    cached = _load_cache()
    if cached:
        holidays, fetched_at = cached
        logger.warning("Using cached NSE holiday list from %s (%d dates).", fetched_at, len(holidays))
        return holidays

    logger.error(
        "No live NSE holiday data and no cache available -- falling back to the "
        "static list in config.yaml. That list may be out of date; verify it manually."
    )
    return static_fallback
