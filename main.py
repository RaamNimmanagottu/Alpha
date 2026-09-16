from __future__ import annotations

import argparse
import signal
import subprocess
import sys
import time
from datetime import date

from broker import AngelOneBroker, BrokerError
from config import AppConfig, Credentials
from instrument_engine import InstrumentEngine
from logging_setup import setup_logging
from market_calendar import market_phase, non_trading_reason
from notifier import TelegramNotifier
from risk import RiskManager
from state import TradeStore

logger = setup_logging()

_shutdown_requested = False

BEFORE_OPEN_POLL_SECONDS = 30
"""How often to re-check while waiting for market open, if the VM was started early
(e.g. by an external scheduler ahead of the actual open time) -- deliberately coarser
than config.poll_interval_seconds, which is tuned for the live trading loop, not idle
waiting."""

HOLIDAY_EXIT_DELAY_SECONDS = 30
"""On a holiday the bot exits within milliseconds of starting -- before a
VM/scheduler shuts the machine back down for cost savings, this gives a window to
console/SSH in if needed (e.g. to check logs or confirm the holiday was detected
correctly). Not applied on weekends, since those are already predictable to
whatever external scheduler starts the VM in the first place -- only the holiday
case is the one an outside scheduler can't know about on its own."""


def _handle_shutdown(signum, frame):
    global _shutdown_requested
    logger.warning("Shutdown signal received (%s). Finishing current cycle then exiting.", signum)
    _shutdown_requested = True


def _shutdown_vm_if_configured(config: AppConfig, notifier: TelegramNotifier) -> None:
    """Powers off the machine on a clean exit, if config.yaml opted in. Only ever
    called from a return-0 path -- never on a broker-connect failure -- so a real
    problem leaves the machine up long enough to look at."""
    if not config.shutdown_vm_on_exit:
        return
    logger.info("shutdown_vm_on_exit is enabled -- shutting this machine down now.")
    notifier.send("EC2 STOPPED: shutting down now.")
    try:
        subprocess.run(["sudo", "shutdown", "-h", "now"], check=True)
    except Exception:
        logger.exception(
            "Failed to shut down -- is passwordless sudo for the 'shutdown' command "
            "configured for this user? See deploy/README.md."
        )


def main(check_holiday: bool = True) -> int:
    signal.signal(signal.SIGINT, _handle_shutdown)
    signal.signal(signal.SIGTERM, _handle_shutdown)

    notifier = TelegramNotifier.from_env()
    notifier.send("EC2 STARTED: bot process starting up.")

    config = AppConfig.load()

    if check_holiday:
        current_year = date.today().year
        holidays = config.holidays_for_year(current_year)
        if not holidays:
            logger.warning(
                "No holiday_list_%d block found in config.yaml -- add one, or the bot "
                "will not know about this year's exchange holidays.", current_year,
            )

        reason = non_trading_reason(holidays)
        if reason:
            logger.info("Not a trading day (%s). Exiting.", reason)
            notifier.send(f"Not a trading day ({reason}). Exiting without trading.")
            if reason.startswith("holiday:"):
                logger.info("Waiting %ds before exiting so there's time to console in if needed.",
                            HOLIDAY_EXIT_DELAY_SECONDS)
                time.sleep(HOLIDAY_EXIT_DELAY_SECONDS)
            _shutdown_vm_if_configured(config, notifier)
            return 0
    else:
        logger.warning(
            "check_holiday=False -- skipping the weekend/holiday check (testing only). "
            "The market-hours check below still applies as normal."
        )

    credentials = Credentials.from_env()
    broker = AngelOneBroker(credentials)
    try:
        broker.connect()
    except BrokerError:
        logger.exception("Failed to connect to broker. Exiting.")
        notifier.send("ERROR: failed to connect to broker. Bot exiting.")
        return 1

    store = TradeStore()
    risk = RiskManager(config.risk, store)

    engines = [
        InstrumentEngine(inst_cfg, config, broker, store, risk, notifier)
        for inst_cfg in config.instruments
    ]

    logger.info("Trading engine started for: %s", ", ".join(e.cfg.name for e in engines))

    notified_waiting_for_open = False
    while not _shutdown_requested:
        phase = market_phase(config.market)
        if phase == "closed":
            logger.info("Market closed. Exiting main loop.")
            break
        if phase == "before_open":
            if not notified_waiting_for_open:
                logger.info("Started before market open (opens %s) -- waiting.", config.market.open_time)
                notifier.send(f"Bot started before market open (opens {config.market.open_time}). Waiting.")
                notified_waiting_for_open = True
            time.sleep(BEFORE_OPEN_POLL_SECONDS)
            continue

        risk.refresh()
        if risk.is_halted:
            logger.error("Risk manager has halted trading: %s. Idling until market close.",
                         risk.halt_reason)
            time.sleep(config.poll_interval_seconds)
            continue

        for engine in engines:
            try:
                engine.run_once()
            except Exception:
                # A single bad cycle for one instrument must never take down the whole
                # bot -- the old version had no top-level exception handling at all, so
                # any transient error (a missing dataframe row, a locked file, a flaky
                # API call) crashed the process outright, sometimes with a live position
                # left unmanaged.
                logger.exception("%s: unhandled error during run_once(), continuing", engine.cfg.name)

        time.sleep(config.poll_interval_seconds)

    open_positions = [store.get_open_trade(e.cfg.name) for e in engines]
    open_positions = [p for p in open_positions if p is not None]
    if open_positions:
        logger.warning(
            "Exiting with %d open position(s) still tracked: %s. "
            "These rely on the broker's own intraday square-off, or must be closed manually.",
            len(open_positions),
            ", ".join(f"{p.instrument}:{p.symbol}" for p in open_positions),
        )
        notifier.send(
            f"WARNING: exiting with {len(open_positions)} open position(s) still tracked: "
            + ", ".join(f"{p.instrument}:{p.symbol}" for p in open_positions)
        )

    logger.info("Shutdown complete.")
    notifier.send("Bot shutting down (market closed / loop ended).")
    _shutdown_vm_if_configured(config, notifier)
    return 0


def _str_to_bool(value: str) -> bool:
    if value.lower() in ("true", "1", "yes"):
        return True
    if value.lower() in ("false", "0", "no"):
        return False
    raise argparse.ArgumentTypeError(f"expected True or False, got {value!r}")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Alpha intraday options trading bot")
    parser.add_argument(
        "check_holiday",
        nargs="?",
        type=_str_to_bool,
        default=True,
        help="Weekend/holiday check before starting: True (default) or False. "
             "Example: python main.py False -- for testing only.",
    )
    parser.add_argument(
        "--check-holiday",
        dest="check_holiday_flag",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Same setting via a named flag instead of a positional argument: "
             "--check-holiday / --no-check-holiday.",
    )
    args = parser.parse_args()
    if args.check_holiday_flag is not None:
        args.check_holiday = args.check_holiday_flag
    return args


if __name__ == "__main__":
    args = _parse_args()
    sys.exit(main(check_holiday=args.check_holiday))
