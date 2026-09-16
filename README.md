# Alpha — Intraday Options Trading Bot (Angel One)

Buys ATM NIFTY options intraday off an EMA(9)/EMA(21) crossover signal computed
from the bot's own locally-stored historical candles (no external TA service),
manages exits by take-profit/stop-loss points on the underlying index and a hard
time cutoff, with a real risk manager and SQLite-backed trade state.

**Currently runs in paper-trading mode** (`config.yaml`'s `paper_trading: true`) —
no real orders are ever placed; entries/exits are simulated against live LTP and
recorded exactly like real trades would be, through the same store, risk manager,
and signal logic. The plan is to paper-trade for ~30 days, review the results
(`export_trades_to_excel.py`, see `legacy/tools/`), and only then flip
`paper_trading` to `false` by hand — there is no automatic graduation to real money
anywhere in this codebase.

The strategy isn't a guess: it was chosen by backtesting 23 strategies/variants
(MACD, RSI, EMA crossovers at 7 different period pairs, Bollinger, Keltner,
Supertrend, Opening Range Breakout, and combinations) over 1000 days of real NIFTY
5-minute data, plus a theta-decay-aware repricing pass using Black-Scholes and real
India VIX data. EMA(9)/EMA(21), unfiltered, won outright: 6,350 points / 46.8% win
rate, beating every mean-reversion-style strategy tested (RSI, Stochastic,
Williams %R, Bollinger bounce all lost money) and 6 other EMA period pairs (9/21's
popularity among retail traders doesn't appear to be an exploitable disadvantage in
this data). That whole backtesting framework is preserved at `legacy/backtest/` if
you want to extend or re-run it — it's not part of this live folder because the
live bot doesn't need scikit-learn/scipy or 1000 days of historical data sitting
around.

## Layout

This is intentionally a **flat, single-folder project** — everything main.py needs
sits right next to it, no subpackages:

- `main.py` — entry point; wires everything together and runs the polling loop.
- `config.py` — typed config loaded from `config.yaml` + `.env`.
- `broker.py` — Angel One (SmartAPI) wrapper: retries, lazy session init, safe
  order-fill polling, nearest-expiry-only ATM strike selection, historical candle fetch.
- `indicators.py` — RSI, Stochastic %K, CCI, ADX, Awesome Oscillator, Momentum,
  MACD, ATR, Bollinger Bands, EMA/SMA, Williams %R, Supertrend, Keltner Channels,
  classic pivot points — standard textbook formulas, no external TA dependency.
- `historical_data.py` — incrementally maintains a local Excel cache of OHLC
  candles per instrument (see "Historical data & signal" below).
- `ema_crossover_signal.py` — the actual signal: BUY/SELL/WAIT from EMA(9) crossing
  EMA(21), unfiltered — no support/resistance gate, no trend filter. Replaced an
  earlier RSI/Stochastic/CCI/ADX/AO/Momentum vote that was never backtested at all
  (retired, see `legacy/local_signals.py`).
- `risk.py` — daily loss limit, max trades/day, max trades/instrument.
- `state.py` — SQLite trade store (`data/trades.db`): open/close trades, realized
  P&L, per-trade `strike`/`mode` (`PAPER`/`LIVE`)/`pnl`.
- `instrument_engine.py` — the trading engine. No new entries on the contract's own
  expiry day (0DTE risk a points-based backtest can't see) — an existing open
  position is still managed and can still exit normally. Paper-trading mode
  (`_execute_order`) simulates a fill from live LTP instead of placing a real
  order, so a 30-day paper run exercises every other part of the system exactly as
  real trading would.
- `market_calendar.py` — holiday/weekend/market-hours checks, always against the
  live clock.
- `logging_setup.py` — rotating file (`trading_bot.log`, right here in this same
  folder) + console logging.
- `paths.py` — resolves the project root correctly whether running as a plain
  script or as a frozen `setup.py`-built executable (see "Building a standalone
  executable" below) — `__file__`-based paths break once frozen.
- `config.yaml` — lot size, strike offset, take-profit/stop-loss (index points),
  entry/exit cutoff times, risk limits, `paper_trading`, and the holiday calendar.
  Edit this to tune parameters; you shouldn't need to touch code for that.
- `.env` — secrets only (`ANGEL_API_KEY`, `ANGEL_CLIENT_ID`, `ANGEL_MPIN`,
  `ANGEL_TOTP_SECRET`), gitignored. `.env.example` is the template.
- `requirements.txt`, `setup.py` — dependencies and the standalone-executable build
  (see below). Neither is required just to run the bot from source — `main.py`
  imports the other modules directly since they're all in the same folder.

## Setup

```powershell
py -3.13 -m venv .venv
.venv\Scripts\pip install -r requirements.txt
copy .env.example .env   # then fill in your real Angel One credentials
```

Only `NIFTY` is configured in `config.yaml` — BANKNIFTY was never backtested with
this strategy and is deliberately left out until it is.

## Run

```powershell
.venv\Scripts\python main.py
```

Logs go to `trading_bot.log` (rotating, right in this folder) and stdout. Trade
state lives in `data/trades.db` (SQLite) — inspect it with any SQLite browser or
`sqlite3 data/trades.db`.

## Building a standalone executable

`setup.py` uses `cx_Freeze` to bundle `main.py` and every dependency into one
executable — useful for copying the bot to a VM without setting up a venv there.

```powershell
.venv\Scripts\pip install -r requirements.txt   # includes cx_Freeze
.venv\Scripts\python setup.py build
```

Output lands in `build\exe.win-amd64-<pyver>\` (or the Linux-equivalent folder name
when built there): `alpha_bot.exe` (or `alpha_bot` on Linux) plus every dependency,
`config.yaml`, and `.env.example`. **Verified working end-to-end on Windows**: built
it, copied a real `.env` next to the built `.exe`, ran it against the live broker —
connected, loaded the real config, exited correctly on market-closed.

Two things worth knowing:

1. **The build is platform-specific.** A Windows-built `.exe` will not run on
   Linux, and vice versa — `cx_Freeze` doesn't cross-compile. To get a Linux
   binary for the VM, copy the flat source files (not the pre-built Windows
   `.exe`) to the Linux machine and run the same two commands there; it'll
   produce a native Linux executable in its own `build/exe.linux-.../` folder.
   Not yet done — waiting on the actual VM existing.
2. **First run on a fresh Windows machine can take several minutes** the very
   first time, even though the app itself starts in seconds — Windows
   Defender/SmartScreen scans (and can briefly sandbox-execute) new, unsigned,
   unrecognized executables the first time they appear. Every run after that is
   normal speed. Don't mistake this for a hang.

`real .env` is deliberately **not** bundled into the build (only `.env.example`
is, via `setup.py`'s `include_files`) — copy your own `.env` next to the built
executable on whichever machine actually runs it.

## Historical data & signal

`historical_data.py` maintains one Excel file per instrument under
`data/historical/` (e.g. `NIFTY_five_minute.xlsx`), holding 5-minute OHLC candles
fetched from Angel One's `getCandleData`. First run backfills 100 days in one
request; every later run fetches only from the last stored candle onward, and
skips the fetch entirely if less than one candle interval has elapsed — it never
re-downloads data it already has or hammers the endpoint every poll cycle.

Each instrument in `config.yaml` has both an `index_token` (LTP quotes) and a
separate `candle_token` (historical data) — for NSE indices these are different
token namespaces. Confirmed empirically: NIFTY's LTP token (`26000`) returns
**zero** rows from `getCandleData`, while the special index token (`99926000`)
returns real data.

`ema_crossover_signal.get_signal()` computes EMA(9)/EMA(21) from that local candle
history. A crossover is a discrete event tied to one specific candle;
`instrument_engine.py` tracks the last signal candle it already acted on so the
same crossover isn't re-evaluated (or re-attempted, if entry failed) on every poll
cycle until a new candle actually forms.

## Holidays

`config.yaml` holds one block per year: `holiday_list_<YYYY>`. At startup,
`main.py` derives the current year and looks up `holiday_list_<that year>`
(`AppConfig.holidays_for_year`) to decide whether today is a trading day. **You
must add a new `holiday_list_<YYYY>` block every December** for the coming year —
if the block for the current year is missing, the bot logs a warning and treats
today as a trading day (fails open) rather than refusing to run. There's no live
NSE fetch (NSE 403s automated requests); that attempt is preserved, unused, at
`legacy/holiday_source.py`.

## Before running with real money

1. Run against Angel One's test/sandbox credentials first if available.
2. Watch the first few live sessions closely rather than leaving it fully unattended.
3. Review `config.yaml` risk limits (`daily_loss_limit`, `max_trades_per_day`) and
   set them to values you're actually comfortable losing.
4. Re-verify `lot_size` for NIFTY against the current NSE contract specification
   before each run — exchanges revise these periodically and a stale value
   silently changes your position size.
5. Remember the backtest measured index-point movement, not real option premium —
   theta decay and strike/IV effects mean real rupee results will differ from what
   the points-based backtest numbers suggested (see `legacy/backtest/apply_theta_decay.py`).

## `legacy/`

Nothing is ever permanently deleted from this project when it's superseded — it
moves here instead:

- The **original** bot before any of this rewrite (`main.py`, `main2.py`,
  `main_backup.py`, `main_test.py`, `ExcelUpdate.py`, `Holidays.py`, `api/`,
  `Constants/`, old `requirements_dev.txt`, `ApiKeys.txt`).
- `local_signals.py` and `signals_tradingview.py` — earlier signal attempts,
  superseded by the backtested `ema_crossover_signal.py`.
- `holiday_source.py` — a live NSE holiday fetch that didn't work reliably.
- `backtest/` — the full backtesting framework (23 strategies, theta-decay
  analysis, historical data fetchers) that produced the strategy this bot now
  runs. Has its own `requirements.txt` (scikit-learn/scipy) since the live bot
  doesn't need those.
- `tests/` — `test_engine_smoke.py`, a fake-broker test suite covering entry/TP/SL/
  time-exit/expiry-day/paper-trading behavior. Its imports are written against the
  old `alpha.xxx` package layout from before the flattening, so it needs its
  import lines updated to match this flat layout (drop the `alpha.` prefix) before
  it'll run again — the underlying test logic itself doesn't need to change.
- `tools/` — `health_check.py` (real, read-only check against your actual Angel
  One account) and `export_trades_to_excel.py`. Same import-path caveat as `tests/`.
- `deploy/` — a systemd service + setup script for running this continuously on a
  Linux VM. Same import-path caveat.

Nothing in `legacy/` is imported by the live bot.
