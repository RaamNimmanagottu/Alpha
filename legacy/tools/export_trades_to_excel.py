"""Export data/trades.db to an Excel file for easy manual review -- e.g. reviewing
a 30-day paper-trading run before deciding whether to flip config.yaml's
paper_trading to false.

SQLite stays the single source of truth (same store for paper and live trades, so
switching modes never changes any storage code); this is a read-only view for
humans, not a second place trades are written to.

Run with (from the project root E:\\Alpha):
    .venv\\Scripts\\python.exe tools\\export_trades_to_excel.py
    .venv\\Scripts\\python.exe tools\\export_trades_to_excel.py --mode PAPER

Writes data/trades_export.xlsx.
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

from alpha.state import DB_PATH

OUTPUT_FILE = DB_PATH.parent / "trades_export.xlsx"


def main() -> int:
    parser = argparse.ArgumentParser(description="Export trades.db to Excel for review")
    parser.add_argument("--mode", choices=["PAPER", "LIVE"], help="only export trades of this mode")
    args = parser.parse_args()

    if not DB_PATH.exists():
        print(f"No database found at {DB_PATH}")
        return 1

    query = "SELECT * FROM trades"
    params: tuple = ()
    if args.mode:
        query += " WHERE mode=?"
        params = (args.mode,)
    query += " ORDER BY id"

    conn = sqlite3.connect(DB_PATH)
    try:
        df = pd.read_sql_query(query, conn, params=params)
    finally:
        conn.close()

    if df.empty:
        print("No trades found to export.")
        return 0

    closed = df[df["status"] == "CLOSED"]
    print(f"{len(df)} trades ({len(closed)} closed, {len(df) - len(closed)} open)")
    if not closed.empty:
        wins = (closed["pnl"] > 0).sum()
        print(f"Closed: {wins} wins ({100 * wins / len(closed):.1f}%), "
              f"total pnl={closed['pnl'].sum():.2f}, avg pnl={closed['pnl'].mean():.2f}")
        if "mode" in closed.columns:
            print(closed.groupby("mode")["pnl"].agg(["count", "sum", "mean"]).to_string())

    df.to_excel(OUTPUT_FILE, index=False)
    print(f"Written to {OUTPUT_FILE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
