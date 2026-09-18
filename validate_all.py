"""Full validation suite for config.yaml + the codebase, meant to be run
before every deploy (and after any change to config.yaml, an instrument's
settings, or a signal module).

Checks, in order:
  1. Every top-level .py file and every *_signal.py module parses (syntax).
  2. instrument_engine.py imports cleanly (catches a missing/broken import
     in any registered signal module).
  3. config.yaml loads via AppConfig.load() without error.
  4. Every instrument's signal_strategy is registered in
     instrument_engine.SIGNAL_STRATEGIES (config.py's static string check
     only verifies the name is spelled right, not that the module actually
     resolves).
  5. Per-instrument sanity: no duplicate names, positive lot_size/TP/SL,
     entry_start_time < entry_cutoff_time <= force_exit_time, non-empty
     tokens, valid underlying/options exchange.
  6. Risk config sanity: **max_trades_per_day >= num_instruments x
     max_trades_per_instrument** -- this exact gap caused two real
     incidents on 2026-09-18 (a live trading day was cut short for
     profitable instruments because the combined cap bound before every
     instrument reached its own limit). This check exists specifically so
     that mistake can't happen silently again.
  7. Every signal module used by an ACTIVE instrument in config.yaml is
     smoke-tested with synthetic candle data (catches a runtime crash that
     static analysis can't).
  8. .env has every credential key the bot needs (existence only, values
     are never printed).

Run with: .venv\\Scripts\\python.exe validate_all.py
Exits 0 if everything passes, 1 if anything fails (safe to use as a deploy
gate).
"""
from __future__ import annotations

import ast
import glob
import os
import sys
from datetime import time as dtime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

FAILURES: list[str] = []
PASSES = 0


def check(label: str, condition: bool, detail: str = "") -> None:
    global PASSES
    if condition:
        PASSES += 1
        print(f"  PASS: {label}")
    else:
        FAILURES.append(f"{label}" + (f" -- {detail}" if detail else ""))
        print(f"  FAIL: {label}" + (f" -- {detail}" if detail else ""))


# --- 1. Syntax check every top-level .py file ---
print("\n=== 1. Syntax check (all top-level .py files) ===")
py_files = sorted(
    p for p in glob.glob(str(ROOT / "*.py"))
    if Path(p).name != "validate_all.py"
)
for path in py_files:
    name = Path(path).name
    try:
        ast.parse(Path(path).read_text(encoding="utf-8"), path)
        check(f"syntax: {name}", True)
    except SyntaxError as exc:
        check(f"syntax: {name}", False, str(exc))

# --- 2. instrument_engine.py imports cleanly ---
print("\n=== 2. instrument_engine.py imports cleanly ===")
try:
    import instrument_engine  # noqa: E402
    check("instrument_engine imports", True)
except Exception as exc:
    check("instrument_engine imports", False, repr(exc))
    print("\nCannot continue -- fix the import error above first.")
    sys.exit(1)

# --- 3. config.yaml loads ---
print("\n=== 3. config.yaml loads via AppConfig.load() ===")
try:
    from config import AppConfig
    app_cfg = AppConfig.load()
    check("AppConfig.load()", True)
except Exception as exc:
    check("AppConfig.load()", False, repr(exc))
    print("\nCannot continue -- fix the config error above first.")
    sys.exit(1)

instruments = app_cfg.instruments
print(f"  ({len(instruments)} instrument(s) loaded: {', '.join(i.name for i in instruments)})")

# --- 4. Every signal_strategy resolves to a registered function ---
print("\n=== 4. Every instrument's signal_strategy is registered ===")
for inst in instruments:
    check(
        f"{inst.name}: signal_strategy '{inst.signal_strategy}' registered",
        inst.signal_strategy in instrument_engine.SIGNAL_STRATEGIES,
        f"not in SIGNAL_STRATEGIES: {list(instrument_engine.SIGNAL_STRATEGIES.keys())}",
    )

# --- 5. Per-instrument sanity checks ---
print("\n=== 5. Per-instrument sanity checks ===")
names_seen = set()
for inst in instruments:
    check(f"{inst.name}: unique name", inst.name not in names_seen, "duplicate instrument name")
    names_seen.add(inst.name)
    check(f"{inst.name}: lot_size > 0", inst.lot_size > 0, f"lot_size={inst.lot_size}")
    check(f"{inst.name}: quantity_lots > 0", inst.quantity_lots > 0, f"quantity_lots={inst.quantity_lots}")
    check(f"{inst.name}: take_profit_points > 0", inst.take_profit_points > 0,
          f"take_profit_points={inst.take_profit_points}")
    check(f"{inst.name}: stop_loss_points > 0", inst.stop_loss_points > 0,
          f"stop_loss_points={inst.stop_loss_points}")
    check(f"{inst.name}: entry_start_time < entry_cutoff_time",
          inst.entry_start_time < inst.entry_cutoff_time,
          f"{inst.entry_start_time} >= {inst.entry_cutoff_time}")
    check(f"{inst.name}: entry_cutoff_time <= force_exit_time",
          inst.entry_cutoff_time <= inst.force_exit_time,
          f"{inst.entry_cutoff_time} > {inst.force_exit_time}")
    check(f"{inst.name}: candle_token non-empty", bool(inst.candle_token), "empty candle_token")
    check(f"{inst.name}: underlying_exchange valid", inst.underlying_exchange in ("NSE", "MCX"),
          f"underlying_exchange={inst.underlying_exchange!r}")
    check(f"{inst.name}: options_exchange valid", inst.options_exchange in ("NFO", "MCX"),
          f"options_exchange={inst.options_exchange!r}")

# --- 6. Risk config: the exact bug caught twice on 2026-09-18 ---
print("\n=== 6. Risk config: combined cap can't starve an individual instrument ===")
required_min = len(instruments) * app_cfg.risk.max_trades_per_instrument
check(
    "max_trades_per_day >= num_instruments x max_trades_per_instrument",
    app_cfg.risk.max_trades_per_day >= required_min,
    f"max_trades_per_day={app_cfg.risk.max_trades_per_day}, "
    f"need >= {len(instruments)} instruments x {app_cfg.risk.max_trades_per_instrument} = {required_min} "
    f"-- a profitable instrument WILL get starved by a bad day in a different one otherwise",
)
check("daily_loss_limit > 0", app_cfg.risk.daily_loss_limit > 0, f"daily_loss_limit={app_cfg.risk.daily_loss_limit}")
check("max_trades_per_instrument > 0", app_cfg.risk.max_trades_per_instrument > 0,
      f"max_trades_per_instrument={app_cfg.risk.max_trades_per_instrument}")
check("starting_capital > 0", app_cfg.starting_capital > 0, f"starting_capital={app_cfg.starting_capital}")
check("paper_trading is a bool", isinstance(app_cfg.paper_trading, bool))
if app_cfg.paper_trading:
    print("  (paper_trading=True -- no real orders will be placed)")
else:
    print("  *** paper_trading=False -- REAL ORDERS WILL BE PLACED ***")

# --- 7. Smoke-test every ACTIVE signal module with synthetic data ---
print("\n=== 7. Smoke-test every active instrument's signal module ===")
import numpy as np
import pandas as pd

np.random.seed(42)
n = 300
dates = pd.date_range("2026-01-05 09:15", periods=n, freq="5min")
walk = np.cumsum(np.random.randn(n) * 2) + 1000
synthetic = pd.DataFrame({
    "date": dates,
    "open": walk,
    "high": walk + np.abs(np.random.randn(n)),
    "low": walk - np.abs(np.random.randn(n)),
    "close": walk + np.random.randn(n) * 0.5,
    "volume": np.random.randint(1000, 5000, n),
})

tested_strategies = set()
for inst in instruments:
    strat = inst.signal_strategy
    if strat in tested_strategies or strat not in instrument_engine.SIGNAL_STRATEGIES:
        continue
    tested_strategies.add(strat)
    fn = instrument_engine.SIGNAL_STRATEGIES[strat]
    try:
        result = fn(inst.exchange_index_symbol, synthetic)
        check(f"signal module '{strat}' runs without crashing", hasattr(result, "direction"),
              f"unexpected return type: {type(result)}")
    except Exception as exc:
        check(f"signal module '{strat}' runs without crashing", False, repr(exc))

# --- 8. .env has required credential keys ---
print("\n=== 8. .env has required credential keys (existence only) ===")
env_path = ROOT / ".env"
env_keys = set()
if env_path.exists():
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            env_keys.add(line.split("=", 1)[0].strip())

required_env_keys = [
    "ANGEL_API_KEY", "ANGEL_CLIENT_ID", "ANGEL_MPIN", "ANGEL_TOTP_SECRET",
    "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID",
]
for key in required_env_keys:
    check(f".env has {key}", key in env_keys)

# --- Summary ---
print(f"\n{'=' * 60}")
print(f"TOTAL: {PASSES} passed, {len(FAILURES)} failed")
if FAILURES:
    print("\nFAILURES:")
    for f in FAILURES:
        print(f"  - {f}")
    sys.exit(1)
else:
    print("ALL CHECKS PASSED -- safe to deploy.")
    sys.exit(0)
