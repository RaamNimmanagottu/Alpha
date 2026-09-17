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

# Single-row table: current account capital, starting from config.starting_capital
# the first time it's ever read, then updated in place after every closed trade.
# Persists across restarts/days by design -- capital compounds day over day, it
# does not reset each morning.
ACCOUNT_SCHEMA = """
CREATE TABLE IF NOT EXISTS account (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    capital REAL NOT NULL
);
"""

# Columns added after the original schema -- migrated onto an existing database
# automatically in __init__ rather than requiring anyone to delete/recreate it.
_MIGRATION_COLUMNS = {
    "entry_underlying_price": "REAL",
    "strike": "REAL",
    "pnl": "REAL",
    "mode": "TEXT NOT NULL DEFAULT 'LIVE'",
    "entry_iv": "REAL",
    "peak_favorable_underlying": "REAL",
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
    entry_iv: Optional[float]
    """The option's implied volatility at entry, if greeks were available -- used to
    detect IV crush (a meaningful IV drop from this baseline) as an exit trigger."""
    peak_favorable_underlying: Optional[float]
    """Best underlying price seen since entry, in the trade's favorable direction --
    the trailing stop-loss trails behind this, never behind the original static SL."""


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
            conn.execute(ACCOUNT_SCHEMA)
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

    def get_capital(self, starting_capital: float) -> float:
        """Current account capital. On first-ever call (no row yet), seeds it with
        `starting_capital` and returns that -- every later call ignores the
        argument and just returns whatever's persisted, since capital compounds
        across days rather than resetting to `starting_capital` each morning."""
        with self._connect() as conn:
            row = conn.execute("SELECT capital FROM account WHERE id=1").fetchone()
            if row is not None:
                return float(row["capital"])
            conn.execute("INSERT INTO account (id, capital) VALUES (1, ?)", (starting_capital,))
            return starting_capital

    def update_capital(self, delta: float) -> float:
        """Adds `delta` (a trade's pnl) to the current capital and returns the new
        total. Assumes get_capital() (or a prior update_capital()) has already
        seeded the row -- called only after a trade closes, by which point the
        bot has always already read the starting capital at least once."""
        with self._connect() as conn:
            row = conn.execute("SELECT capital FROM account WHERE id=1").fetchone()
            new_capital = float(row["capital"]) + delta if row is not None else delta
            conn.execute(
                "INSERT INTO account (id, capital) VALUES (1, ?) "
                "ON CONFLICT(id) DO UPDATE SET capital=excluded.capital",
                (new_capital,),
            )
            return new_capital

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
        entry_iv: float | None = None,
    ) -> int:
        now = datetime.now()
        with self._connect() as conn:
            cur = conn.execute(
                """INSERT INTO trades
                   (trade_date, instrument, order_id, symbol, trade_type, token, strike,
                    entry_price, entry_underlying_price, quantity, mode, status, opened_at,
                    entry_iv, peak_favorable_underlying)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'OPEN', ?, ?, ?)""",
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
                    entry_iv,
                    entry_underlying_price,  # peak starts at entry -- nothing favorable has happened yet
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

    def update_peak_favorable(self, trade_id: int, peak_favorable_underlying: float) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE trades SET peak_favorable_underlying=? WHERE id=?",
                (peak_favorable_underlying, trade_id),
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
