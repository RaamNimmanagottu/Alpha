from __future__ import annotations

import logging

from config import RiskConfig
from state import TradeStore

logger = logging.getLogger("alpha.risk")


class RiskManager:
    """Central place for every "should we be allowed to trade right now" decision.

    None of this existed in the original bot: there was no daily loss cap, no cap on
    trade count, and no margin check before firing an order.
    """

    def __init__(self, config: RiskConfig, store: TradeStore):
        self.config = config
        self.store = store
        self._halted = False
        self._halt_reason = ""

    def refresh(self) -> None:
        """Re-evaluate the daily loss limit. Call once per loop iteration."""
        if self._halted:
            return
        pnl = self.store.realized_pnl_today()
        if pnl <= -abs(self.config.daily_loss_limit):
            self._halted = True
            self._halt_reason = f"Daily loss limit breached: realized P&L {pnl:.2f}"
            logger.error(self._halt_reason)

    @property
    def is_halted(self) -> bool:
        return self._halted

    @property
    def halt_reason(self) -> str:
        return self._halt_reason

    def can_open_new_trade(self, instrument: str) -> tuple[bool, str]:
        if self._halted:
            return False, self._halt_reason

        all_trades_today = self.store.trades_today()
        if len(all_trades_today) >= self.config.max_trades_per_day:
            return False, f"Max trades per day reached ({self.config.max_trades_per_day})"

        instrument_trades_today = [t for t in all_trades_today if t.instrument == instrument]
        if len(instrument_trades_today) >= self.config.max_trades_per_instrument:
            return (
                False,
                f"Max trades for {instrument} reached ({self.config.max_trades_per_instrument})",
            )

        return True, ""

    def halt(self, reason: str) -> None:
        self._halted = True
        self._halt_reason = reason
        logger.error("Trading halted: %s", reason)
