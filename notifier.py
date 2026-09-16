from __future__ import annotations

import logging
import os

import requests
from dotenv import load_dotenv

from paths import ROOT_DIR

logger = logging.getLogger("alpha.notifier")

_API_URL = "https://api.telegram.org/bot{token}/sendMessage"


class TelegramNotifier:
    """Best-effort Telegram notifications for bot lifecycle and trade events.

    Never raises: a missing token, a network blip, or Telegram being down must
    never interrupt trading. If unconfigured, sends are silently skipped (after
    one warning at startup).
    """

    def __init__(self, bot_token: str | None, chat_id: str | None):
        self._bot_token = bot_token
        self._chat_id = chat_id
        if not self.enabled:
            logger.warning(
                "TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not set in .env -- "
                "Telegram notifications disabled."
            )

    @staticmethod
    def from_env() -> "TelegramNotifier":
        load_dotenv(ROOT_DIR / ".env")
        return TelegramNotifier(os.getenv("TELEGRAM_BOT_TOKEN"), os.getenv("TELEGRAM_CHAT_ID"))

    @property
    def enabled(self) -> bool:
        return bool(self._bot_token and self._chat_id)

    def send(self, text: str) -> None:
        if not self.enabled:
            return
        try:
            response = requests.post(
                _API_URL.format(token=self._bot_token),
                json={"chat_id": self._chat_id, "text": text},
                timeout=10,
            )
            if not response.ok:
                logger.warning("Telegram send failed: %s %s", response.status_code, response.text)
        except Exception:
            logger.exception("Telegram send raised an exception")
