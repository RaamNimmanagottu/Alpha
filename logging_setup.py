from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler

from paths import ROOT_DIR


def setup_logging(log_name: str = "trading_bot") -> logging.Logger:
    logger = logging.getLogger("alpha")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    fmt = logging.Formatter("%(asctime)s %(levelname)-8s %(name)s: %(message)s")

    file_handler = RotatingFileHandler(
        ROOT_DIR / f"{log_name}.log", maxBytes=5_000_000, backupCount=5, encoding="utf-8"
    )
    file_handler.setFormatter(fmt)
    file_handler.setLevel(logging.INFO)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(fmt)
    console_handler.setLevel(logging.INFO)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    return logger
