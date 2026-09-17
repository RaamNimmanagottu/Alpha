# Alpha Trading Bot — Rules Book

Living document of every finalized rule/decision, so nothing has to be re-derived
from chat history. Update this file whenever a new rule is validated and locked in.

Last updated: 2026-09-17 (after `phase-1` tag; added FINNIFTY backtest findings).

---

## 1. Per-Instrument Strategy Rules

Each instrument uses whatever signal was actually validated for IT on 1000 days of
real historical data — never assume one strategy transfers to another instrument.

### NIFTY
- **Signal**: EMA(9)/EMA(21) crossover (`ema_crossover_signal.py`)
- **Take-profit**: 100 index points, OR premium +10% from entry (whichever hits first)
- **Stop-loss**: 50 index points
- **Lot size**: 65 (verify every expiry cycle — NSE revises periodically)
- **Backtest**: 1000 days, 1158 trades, 46.8% win rate, +6350.90 points, best of 27
  strategies tested (VWAP, MACD+RSI, Donchian, Heikin-Ashi, 3-EMA ribbon, RSI,
  Bollinger, Supertrend, etc. all tested and lost to this)

### BANKNIFTY
- **Signal**: EMA(9)/EMA(21) crossover — SAME as NIFTY (confirmed after correcting
  an earlier mistake, see Lesson #1 below)
- **Take-profit**: 300 index points
- **Stop-loss**: 150 index points
- **Lot size**: 30 (confirmed live from instrument master)
- **Backtest**: 1000 days (50,563 candles, 2023-12-26 to 2026-09-17), 1136 trades,
  45.69% win rate, +9154.60 points
- **Status**: built and correct in code as of commit `7f34715` (the earlier
  `8a12455` had it wrong, on RSI — fixed). On GitHub `main`. **NOT deployed to
  EC2** — awaiting explicit go-ahead (see Rule #10).

### FINNIFTY
- **Signal**: Keltner Channel Breakout — NOT EMA crossover (EMA is only #4 here,
  +2460pts; Keltner wins by a wide margin). A THIRD different strategy across our
  3 index instruments so far (NIFTY: EMA, BANKNIFTY: EMA-different-TP/SL, FINNIFTY:
  Keltner) — confirms again that signals don't transfer across instruments.
- **Take-profit**: 150 index points
- **Stop-loss**: 75 index points
- **Lot size**: 60 (confirmed live from instrument master)
- **Backtest**: 1000 days (50,563 candles, 2023-12-26 to 2026-09-17, price range
  19829-28555, current ~25318), 1075 trades, 49.40% win rate, +8623.00 points —
  robust across nearby TP/SL values too (120/60: +7643, 150/100: +7472 with even
  higher 51.46% win rate), not a single lucky number.
- **Status**: built in code as of commit `7f34715` (`keltner_channel_signal.py` +
  config.yaml entry). On GitHub `main`. **NOT deployed to EC2** — awaiting
  explicit go-ahead (see Rule #10).

### Note on `max_trades_per_day` with 3 instruments
`max_trades_per_day: 6` is a combined cap across NIFTY+BANKNIFTY+FINNIFTY. With
3 instruments each capped individually at `max_trades_per_instrument: 3`, the
combined cap (6) can now bind before every instrument reaches its own limit --
e.g. NIFTY+BANKNIFTY alone hitting 6 trades leaves FINNIFTY with zero for the
rest of that day. Flagged, not yet changed -- a deliberate risk-parameter
decision to make consciously, not accidentally.

### Not yet built
- GOLD, CRUDEOIL — feasibility-checked (real volume available on both, unlike
  NSE indices; MCX session runs ~9:00 AM to ~9:25 PM, not literally "night only").
  Not yet backtested.

---

## 2. Risk Management Rules (account-wide, `config.yaml`)

- `daily_loss_limit: 5000` — rupees, across ALL instruments combined; bot halts new
  entries for the rest of the day once breached.
- `max_trades_per_day: 6` — combined across all instruments.
- `max_trades_per_instrument: 3` — per instrument, per day.
- These are NOT modeled in `legacy/backtest/trade_simulator.py` — raw backtest
  numbers assume unlimited trades/day. Confirmed empirically (2024-02-29 case:
  5 same-day whipsaw SL trades in the raw backtest, only 3 would actually happen
  live) that these caps meaningfully protect against bad whipsaw days, at a modest
  cost to total backtested return (~-5.7% over 1000 days when applied to NIFTY).

## 3. Position Sizing Rules

- **Fixed 1 lot per instrument, no compounding** — this is the validated, sane
  approach. `quantity_lots: 1` in config.yaml for every instrument.
- **Full compounding (betting all affordable lots each trade) is DANGEROUS** —
  tested and confirmed: turns a profitable strategy into a 66-96% account loss
  depending on capital level, due to sequence-of-returns risk / gambler's ruin.
  Never do this.
- **Fixed-fractional sizing (risk a fixed % of capital per trade) only works with
  enough starting capital** — below ~₹2,00,000 (given ~₹7,800/lot at ₹120 premium),
  conservative fractions (10-30%) can't even afford 1 lot. At ₹2,00,000+, 4-7% risk
  fraction gives realistic, safe growth (9.6-23.3% max drawdown, 128-337% return
  over the backtest period). 10%+ starts producing unrealistic (liquidity-ignoring)
  numbers.
- **Starting capital**: ₹2,00,000 (`starting_capital` in config.yaml), persisted in
  `data/trades.db`'s `account` table, compounds day-to-day (never resets each
  morning).
- **Combined NIFTY+BANKNIFTY simulation** (fixed 1 lot each, risk-manager caps
  applied, ₹2,00,000 start): final capital ₹4,75,608 over ~2.75 years (+137.8%,
  ~37% CAGR), max drawdown 23.3% of peak. This does NOT include brokerage/taxes.

## 4. Exit Rules (live-only additions, not backtested — each independently toggleable)

- **Trailing stop-loss**: once a trade moves `trailing_stop_activation_points` (50)
  in favor, SL trails `trailing_stop_distance_points` (30) behind the best price
  seen. Can only tighten, never loosen past the static SL.
- **Signal-reversal exit**: exits immediately if the EMA signal flips opposite
  direction while a trade is open.
- **IV-crush exit**: exits if IV drops `iv_exit_drop_pct` (20%) from entry.
  Throttled fetch (`iv_check_interval_seconds`, 30s) to avoid rate limits. Never
  falsely triggers on missing data — skips the check instead.
- **Momentum exit**: exits early if the index moves `momentum_exit_points` (60) in
  the favorable direction within `momentum_window_minutes` (10) — "lock in a fast
  spike before it fades" interpretation (explicitly chosen over "let it run").
- **Pullback entry**: on an extended crossover candle (≥`pullback_extended_threshold_points`,
  100), waits for a pullback to that candle's own low/high instead of chasing.
  Backtested: +10.8% total points vs immediate entry, held across 80-150pt
  thresholds (not a single lucky number).
- **Important known gap**: max loss per trade is NOT strictly bounded by
  `stop_loss_points`. Day-end force-exit (`force_exit_time`) can lose MORE than the
  SL if price moves sharply in the final minutes without touching the SL trigger
  first (observed worst case: BANKNIFTY -229.35pts vs 150pt SL; NIFTY -96.85pts vs
  50pt SL). Not yet mitigated.

## 5. Entry Rules

- **Strike selection**: `strike_selection_mode: delta` with `target_delta: 0.5`
  (NIFTY) — picks the strike closest to a target delta using live Angel One
  `optionGreek` data, falls back to plain ATM (with a Telegram warning) if greeks
  data is unavailable or fails validation. Never blocks an entry on this.
- ATM (`buy_strike_offset`/`sell_strike_offset`: 0) is the backtested baseline for
  both NIFTY and BANKNIFTY currently.

## 6. Data Constraints (Angel One / broker limits)

- 1-min candles: ~30 days max in a single wide-range request.
- 3-min candles: ~60 days max.
- 5-min candles: ~100 days max **in a single wide-range request** — BUT chunking
  into small (~20-day) windows and stitching gets much further back (confirmed:
  1000+ days of real BANKNIFTY data obtained this way). Use this method for any
  future instrument's historical backtest data.
- NSE index candles (NIFTY, BANKNIFTY, FINNIFTY) always have volume=0 — VWAP and
  volume-based signals cannot work on them.
- MCX commodities (GOLD, CRUDEOIL futures) DO have real, substantial volume —
  volume-based signals are viable there, once built.
- Live OI (`opnInterest`) is available via `getMarketData` for futures, but NOT
  via `getCandleData` (historical) — so OI-based strategies can only be built
  live-only, not backtested on history, for now.

## 7. Financial Target Reality Check

- ₹20,00,000 in 1 year from ₹2,00,000 (10x) is **not realistic** with this
  systematic approach — best validated number is ~37% CAGR (combined
  NIFTY+BANKNIFTY, fixed lot sizing). Treat growth targets as "as much as the
  validated edge allows", not a fixed commitment.

## 8. Lessons Learned (things that turned out wrong — kept so we don't repeat them)

1. **Small sample sizes lie.** BANKNIFTY's first backtest (100 days) said RSI
   Overbought/Oversold was the clear winner (+2601pts) and EMA crossover LOST
   money (-1268pts). The full 1000-day backtest showed the exact opposite: RSI
   LOSES (-3600pts), EMA crossover wins (+7920 to +9154pts depending on TP/SL).
   Never trust a <500-day backtest as strong evidence — it's a starting point only.
2. **"Best of N strategies" tested on the same data has real overfitting risk** —
   NIFTY's original 46.8% number is "best of 23", a known red flag, though it has
   held up reasonably in subsequent re-tests.
3. **Fighting signal lag with more lagging confirmation makes it worse, not
   better** — multi-timeframe (1min+3min+5min "same trend") confirmation was
   tested and made results significantly worse (-489pts vs +86pts for 1-min
   alone), because the "confirmation" timeframe is itself lagging.
4. **Pivot-point "room to target" filtering doesn't have real predictive power**
   on this data — tested across multiple thresholds, all flat-to-worse than no
   filter.
5. **Extending force_exit_time later (closer to real market close) makes results
   WORSE, not better** — the last 30 minutes before 14:50 tend to move against
   open positions on this data; the existing 14:50 cutoff is protective, not
   arbitrary.

## 9. Git Workflow Rules

- **Always create a feature branch before committing code changes** — never
  commit directly to `main`. Flow: `git checkout -b <name>` → commit → merge to
  `main` (`--no-edit`) → push. (See memory: feedback-git-feature-branch-workflow)
- `git tag -a phase-1` marks the last known-good, fully-approved state. Use
  `git show phase-1:<path>` to extract a specific file's content at that point
  without disturbing the current working tree.

## 10. Deployment Rules

- Local build → validate (unit tests, backtests) → commit → merge → push to
  GitHub can proceed without asking each time.
- **Deploying to the live EC2 instance (`i-0f3149bf3fc2e4779`) always requires
  explicit user approval first** — even after full local validation passes. The
  EC2 instance stays pinned to the last explicitly-approved state (currently
  `phase-1`) until told otherwise. (See memory: feedback-ask-before-ec2-deploy)
- After every `config.yaml` deploy to EC2, must `sed` `shutdown_vm_on_exit` back
  to `true` on the server — the local file's committed default is `false` (safe
  for a dev machine) and silently overwrites the production value otherwise. (See
  memory: project-shutdown-vm-config-gotcha)
