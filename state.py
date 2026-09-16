from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from paths import ROOT_DIR

DB_PATH = ROOT_DIR / "data" / "trades.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_date TEXT NOT NULL,
    instrument TEXT NOT NULL,
    order_id TEXT,
    symbol TEXT,
    trade_type TEXT,
    token TEXT,
    strike REAL,
    entry_price REAL,
    entry_underlying_price REAL,
    exit_price REAL,
    quantity INTEGER,
    pnl REAL,
    mode TEXT NOT NULL DEFAULT 'LIVE',
    status TEXT NOT NULL DEFAULT 'OPEN',
    opened_at TEXT,
    closed_at TEXT
);
"""

# Columns added after the original schema -- migrated onto an existing database
# automatically in __init__ rather than requiring anyone to delete/recreate it.
_MIGRATION_COLUMNS = {
    "entry_underlying_price": "REAL",
    "strike": "REAL",
    "pnl": "REAL",
    "mode": "TEXT NOT NULL DEFAULT 'LIVE'",
}


@dataclass
class Trade:
    id: int
    trade_date: str
    instrument: str
    order_id: str
    symbol: str
    trade_type: str
    token: str
    strike: Optional[float]
    entry_price: float
    entry_underlying_price: Optional[float]
    """The index's own LTP at entry -- take-profit/stop-loss are evaluated against
    the underlying's index-point movement (matching the backtested strategy exactly),
    not the option premium's own percentage move."""
    exit_price: Optional[float]
    quantity: int
    pnl: Optional[float]
    mode: str
    """'PAPER' for a simulated trade (no real order ever placed) or 'LIVE'."""
    status: str
    opened_at: str
    closed_at: Optional[str]


class TradeStore:
    """SQLite-backed trade/position store.

    Replaces reading and rewriting a shared .xlsx file on every loop iteration, which
    was slow, not atomic, and would crash the bot outright if the file happened to be
    open in Excel at the wrong moment.
    """

    def __init__(self, db_path: Path | None = None):
        self.db_path = db_path or DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute(SCHEMA)
            existing_cols = {row["name"] for row in conn.execute("PRAGMA table_info(trades)")}
            for col, col_type in _MIGRATION_COLUMNS.items():
                if col not in existing_cols:
                    conn.execute(f"ALTER TABLE trades ADD COLUMN {col} {col_type}")

    @contextmanager
    def _connect(self):
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def open_trade(
        self,
        instrument: str,
        order_id: str,
        symbol: str,
        trade_type: str,
        token: str,
        entry_price: float,
        quantity: int,
        entry_underlying_price: float,
        strike: float,
        mode: str = "LIVE",
    ) -> int:
        now = datetime.now()
        with self._connect() as conn:
            cur = conn.execute(
                """INSERT INTO trades
                   (trade_date, instrument, order_id, symbol, trade_type, token, strike,
                    entry_price, entry_underlying_price, quantity, mode, status, opened_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'OPEN', ?)""",
                (
                    date.today().isoformat(),
                    instrument,
                    order_id,
                    symbol,
                    trade_type,
                    str(token),
                    strike,
                    entry_price,
                    entry_underlying_price,
                    quantity,
                    mode,
                    now.isoformat(timespec="seconds"),
                ),
            )
            return cur.lastrowid

    def close_trade(self, trade_id: int, exit_price: float) -> None:
        with self._connect() as conn:
            conn.execute(
                """UPDATE trades
                   SET status='CLOSED', exit_price=?, closed_at=?,
                       pnl=(? - entry_price) * quantity
                   WHERE id=?""",
                (exit_price, datetime.now().isoformat(timespec="seconds"), exit_price, trade_id),
            )

    def get_open_trade(self, instrument: str) -> Optional[Trade]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM trades WHERE instrument=? AND status='OPEN' ORDER BY id DESC LIMIT 1",
                (instrument,),
            ).fetchone()
        return Trade(**dict(row)) if row else None

    def trades_today(self, instrument: str | None = None) -> list[Trade]:
        query = "SELECT * FROM trades WHERE trade_date=?"
        params: tuple = (date.today().isoformat(),)
        if instrument:
            query += " AND instrument=?"
            params += (instrument,)
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [Trade(**dict(r)) for r in rows]

    def realized_pnl_today(self) -> float:
        """Sum of (exit - entry) * quantity for all closed trades opened today.

        Assumes long option positions (the bot only buys CE/PE, never writes options),
        so profit is simply (exit_price - entry_price) * quantity.
        """
        with self._connect() as conn:
            row = conn.execute(
                """SELECT COALESCE(SUM((exit_price - entry_price) * quantity), 0) AS pnl
                   FROM trades WHERE trade_date=? AND status='CLOSED'""",
                (date.today().isoformat(),),
            ).fetchone()
        return float(row["pnl"])
