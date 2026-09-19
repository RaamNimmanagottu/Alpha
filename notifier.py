from __future__ import annotations

import html
import logging
import os
import re

import requests
from dotenv import load_dotenv

from paths import ROOT_DIR

logger = logging.getLogger("alpha.notifier")

_API_URL = "https://api.telegram.org/bot{token}/sendMessage"
_TAG_RE = re.compile(r"<[^>]+>")


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

    def send_html(self, html_text: str, plain_fallback: str | None = None) -> None:
        """Send an HTML-formatted message (see telegram_format.py).

        If Telegram rejects the markup (e.g. a stray unescaped '<'), resend as plain
        text -- `plain_fallback` if given, else the HTML with tags stripped -- so an
        alert is never lost to a formatting problem. Never raises.
        """
        if not self.enabled:
            return
        try:
            response = requests.post(
                _API_URL.format(token=self._bot_token),
                json={"chat_id": self._chat_id, "text": html_text, "parse_mode": "HTML",
                      "disable_web_page_preview": True},
                timeout=10,
            )
            if response.ok:
                return
            logger.warning("Telegram HTML send failed (%s %s); falling back to plain text",
                           response.status_code, response.text)
        except Exception:
            logger.exception("Telegram HTML send raised an exception; falling back to plain text")
        self.send(plain_fallback if plain_fallback is not None else html.unescape(_TAG_RE.sub("", html_text)))
