# Alpha Trading Bot — Rules Book

Living document of every finalized rule/decision, so nothing has to be re-derived
from chat history. Update this file whenever a new rule is validated and locked in.

Last updated: 2026-09-17 (phase-2 deployed to EC2; systemd startup grace period added).

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
**RESOLVED 2026-09-18, changed from 6 to 9.** This risk was flagged in advance
(see below) and then actually observed live on day 1 of BANKNIFTY/FINNIFTY:
NIFTY whipsawed through 3 trades (2 losses, 1 small loss) by 13:55, which
combined with BANKNIFTY's 2 and FINNIFTY's 1 to hit the old combined cap of 6
-- `entry blocked by risk manager: Max trades per day reached (6)` then
repeated in the logs for both BANKNIFTY and FINNIFTY for the rest of the
session, even though both were profitable that day (+2253, +1620) and had
room left under their own `max_trades_per_instrument: 3`. Raised
`max_trades_per_day` to 9 (= 3 instruments x 3 each) so the combined cap can
no longer bind before every instrument reaches its own individual limit --
matches the original intent of `max_trades_per_instrument` (a bad day for one
instrument should not starve the other two). `daily_loss_limit: 5000` remains
the real account-wide brake regardless of this change.

Original note (kept for context): `max_trades_per_day: 6` is a combined cap
across NIFTY+BANKNIFTY+FINNIFTY. With 3 instruments each capped individually
at `max_trades_per_instrument: 3`, the combined cap (6) can now bind before
every instrument reaches its own limit -- e.g. NIFTY+BANKNIFTY alone hitting 6
trades leaves FINNIFTY with zero for the rest of that day. Flagged, not yet
changed -- a deliberate risk-parameter decision to make consciously, not
accidentally.

### CRUDEOIL (MCX futures) — documented only, NOT built in code
- **Signal**: Donchian Channel Breakout (20) — close breaks above/below the prior
  20-candle high/low. Beat VWAP Cross (2nd place) and Keltner Channel Breakout
  (3rd) in a 27-strategy comparison that, for the first time, included volume-based
  strategies (VWAP Cross) since MCX commodities have real volume unlike NSE
  indices — confirms the user's hypothesis that volume-based signals are viable
  here, though VWAP wasn't the single best.
- **Take-profit**: 150 points; **Stop-loss**: 75 points (current price ~9731;
  ATR(14) avg 13.32, median 9.69 — SL is ~7-8x median ATR, i.e. wide relative to
  typical 5-min movement).
- **Backtest**: 1000 days (119,981 candles, 2023-12-22 to 2026-09-17, real volume
  sum 2.27 crore), 9145 trades, 45.96% win rate, +6092.00 points. TP/SL tuned
  across 50/25 up to 500/250 — total points peak clearly at 150/75, then decline
  as TP/SL widen further (200/100: +5522, 500/250: +3727) — a genuine plateau,
  not a runaway/overfit edge.
- **Risk-profile warning (worse here than on index instruments)**: at every TP/SL
  tested from 50/25 up to 200/100, the single worst real trade lost **128 points**
  — i.e. WORSE than the nominal stop-loss at every one of those settings (up to
  4x worse than the 25-pt SL, still 1.7x worse than the 100-pt SL). This is the
  same day-end force-exit gap already known for NIFTY/BANKNIFTY (see Exit Rules
  section) but far more pronounced on CRUDEOIL. Also, 88-98% of trades exit on
  time, not on TP/SL — the strategy is closer to "ride the breakout until forced
  exit" than a tightly TP/SL-managed strategy. Position sizing and daily-loss-limit
  assumptions would need re-checking against this before ever going live.
- **Lot size**: not yet confirmed from live instrument master (needed before any
  code is built).

### GOLD (MCX futures) — documented only, NOT built in code
- **Signal**: Keltner Channel Breakout — beat Donchian Channel Breakout (2nd) and
  Williams %R (3rd). VWAP Cross placed 5th (+3164 at baseline TP/SL) — present
  but not dominant on GOLD.
- **Take-profit**: 500 points; **Stop-loss**: 250 points (current price ~154,305).
- **Backtest**: only **130 days available** (6415 candles, 2026-05-14 to
  2026-09-17, real volume sum 59,588) — this specific MCX contract
  (GOLD04DEC26FUT) simply doesn't have more history yet; NOT a 1000-day test.
  423 trades, 40.19% win rate, +11611.00 points, avg +27.45 pts/trade. TP/SL
  tuned 150/75 up to 1500/750 — peaks clearly at 500/250, declines on both sides
  (300/150: +10410, 1000/500: +6885).
- **Confidence caveat (per Lesson #1)**: 130 days / 423 trades is a SMALL sample
  by this project's own standard (the BANKNIFTY 100-day-sample mistake). Treat
  this as preliminary until more history accumulates or a longer-history GOLD
  contract/series can be sourced.
- **Risk-profile warning**: worst single trade lost **988 points** at every TP/SL
  from 150/75 up to 1000/500 — again far worse than the nominal SL (up to 13x
  worse than the 75-pt SL, still ~4x worse than the 250-pt SL at the chosen
  setting). Same day-end force-exit gap as CRUDEOIL, even more extreme.
- **Lot size**: not yet confirmed from live instrument master (needed before any
  code is built).

### Commodities — general findings
- Confirms the project's core lesson yet again: a 4th and 5th different winning
  strategy (Donchian for CRUDEOIL, Keltner for GOLD) across 5 instruments now —
  NIFTY (EMA), BANKNIFTY (EMA-different-TP/SL), FINNIFTY (Keltner), CRUDEOIL
  (Donchian), GOLD (Keltner) — no single indicator transfers across instruments.
- Volume-based signals (VWAP Cross) ARE viable on commodities (unlike NSE
  indices where they produce zero trades) but did not turn out to be the single
  best strategy on either commodity tested so far.
- New lesson: day-end force-exit risk (already known for indices) is
  significantly worse on these two commodities — real worst-case losses were
  4-13x the nominal stop-loss depending on instrument/TP-SL setting. This should
  be weighed carefully before building live code for either.

---

## 2. Risk Management Rules (account-wide, `config.yaml`)

- `daily_loss_limit: 5000` — rupees, across ALL instruments combined; bot halts new
  entries for the rest of the day once breached.
- `max_trades_per_day: 9` — combined across all instruments (raised from 6 on
  2026-09-18; see the note in section 1 — was observed live to block healthy
  instruments once a different one whipsawed through its own share of the cap).
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
6. **Day-end force-exit can blow past the stop-loss far worse on commodities
   than on indices.** Already known for NIFTY/BANKNIFTY (worst case ~2x the SL);
   on CRUDEOIL and GOLD, worst observed real losses were 4-13x the nominal SL
   across every TP/SL setting tested. Any commodity strategy must account for
   this before going live, not just copy the index risk assumptions.

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
  explicit user approval first** — even after full local validation passes.
  (See memory: feedback-ask-before-ec2-deploy)
- **EC2 is now on `phase-2`** (deployed 2026-09-17): NIFTY (EMA crossover),
  BANKNIFTY (EMA crossover, TP300/SL150), FINNIFTY (Keltner Channel Breakout,
  TP150/SL75) all verified loading correctly on the server. GOLD/CRUDEOIL
  (documented-only) are NOT part of this deploy.
- After every `config.yaml` deploy to EC2, must `sed` `shutdown_vm_on_exit` back
  to `true` on the server — the local file's committed default is `false` (safe
  for a dev machine) and silently overwrites the production value otherwise. (See
  memory: project-shutdown-vm-config-gotcha)

### Deployment mechanics (so this never has to be re-derived)
- Instance: `i-0f3149bf3fc2e4779` ("alpha-trading-bot"), region
  **ap-southeast-2** (Sydney), user `admin`, SSH key
  `C:\Users\DELL\.ssh\alpha-key.pem`.
- **There IS an automated daily start scheduler** — EventBridge Scheduler
  `alpha-vm-daily-start` (schedule group `default`, region ap-southeast-2),
  cron `0 9 ? * MON-FRI *`, timezone Asia/Calcutta, target `EC2_StartInstances`,
  enabled. Starts the instance at 9:00 AM IST every weekday — lands well before
  the 9:15 market open, with room for the systemd 120s grace period plus the
  bot's own `before_open` wait logic. **I incorrectly claimed on 2026-09-17
  that no such scheduler existed** — I had only checked this git repo (where
  the old Terraform/CloudTrail setup was removed) and never checked the AWS
  Console directly, since my `aws events list-rules` / `aws lambda
  list-functions` calls are also denied by the same org-level SCP. There is
  NO scheduler for stopping the instance — that side is handled entirely by
  the bot's own `shutdown_vm_on_exit` logic when it exits. **Whenever a
  question is about what automation exists in AWS, check the Console (or ask
  the user to) — do not assume from the repo alone, since Console-managed
  infra like this leaves no trace in git.**
- **Public IP is NOT static** — the instance uses auto-assign public IP (free
  while stopped; an Elastic IP would cost ~$3.60/month, deliberately not used).
  The IP changes every stop/start cycle, so old `known_hosts` entries go stale
  and cannot be relied on. My AWS CLI identity (`terraform-deploy`) has an
  **explicit organization-level SCP deny on `ec2:DescribeInstances`** (and
  likely other EC2 read calls) — I cannot look up the current IP myself. The
  user must supply it (or run
  `aws ec2 describe-instances --instance-ids i-0f3149bf3fc2e4779 --query "Reservations[0].Instances[0].[State.Name,PublicIpAddress]" --output text`
  themselves) at the start of every deploy session.
- Remote app path: `/home/admin/alpha`. Service: `alpha.service` (systemd) —
  `sudo systemctl restart alpha.service` / `sudo systemctl status alpha.service`
  / `sudo journalctl -u alpha.service -f` to tail logs.
- `/home/admin/alpha` is **NOT a git repo** on the server (confirmed 2026-09-17)
  — deploys are plain `scp` of individual changed files, not `git pull`. Deploy
  flow: back up the files about to be overwritten (e.g. to
  `~/alpha_phase1_backup/`), `scp` the new versions from a local
  `git show <tag>:<path>` extraction (PowerShell's `Out-File` adds a UTF-8 BOM
  by default — write with `[System.IO.File]::WriteAllText(path, content, (New-Object
  System.Text.UTF8Encoding($false)))` instead, or verify with a byte check,
  since a BOM can break Python source), re-apply the `shutdown_vm_on_exit: true`
  sed fix to `config.yaml`, verify with a syntax check (`ast.parse`) and a
  config load check (`AppConfig.load()`) before touching the service, then
  restart/start it and watch logs/Telegram for a clean boot.
- **The 2026-09-17 "instance won't SSH" incident — real root cause, corrected**:
  spent a long session assuming this was a self-shutdown timing race
  (`alpha.service` starting, seeing the market closed, and shutting the VM down
  before SSH could connect). The actual cause was much simpler: the security
  group (`sg-0d032cf598b3a6011`, region **ap-southeast-2** — not ap-south-1,
  correct that earlier assumption too) only allow-listed two stale `/32` IPs
  (`49.43.230.0/32`, `49.43.230.153/32`) for port 22, and the dev machine's
  actual dynamic ISP IP had since moved to `49.43.230.200` — outside both. Every
  SSH attempt timed out at the network level regardless of the bot's timing.
  **If SSH ever times out (not "connection refused") on this instance, check
  the security group's inbound rule for port 22 against the current public IP
  FIRST**, before assuming it's a shutdown race. (`https://api.ipify.org` or
  similar to check the current outbound IP.)
- **AWS CLI mutating calls are blocked account-wide, not just for me**:
  confirmed 2026-09-17 that `ec2:ModifyInstanceAttribute` (and `DescribeInstances`)
  are denied by an org-level SCP for the `terraform-deploy` IAM identity **even
  when the user runs the exact same command themselves** from their own
  terminal — this is a hard account/identity-level restriction, not a
  Claude-Code-classifier or "who's calling" issue. Don't try to route around it
  by having the user re-run a blocked `aws ec2 ...` command; it will fail for
  them too. The boothook-via-user-data approach (previously documented here)
  is DEAD for this account unless the org SCP changes or a different AWS
  Console login (not this IAM user) is used for that one action.
- **Permanent fix actually adopted (2026-09-17), replacing the boothook trick**:
  added a startup grace period to `/etc/systemd/system/alpha.service`.
  `alpha.service` stays enabled (auto-starts on boot, as before — no manual
  daily start step needed), but now waits 2 minutes after boot before `main.py`
  even runs. This gives a reliable window to SSH in (once the security group
  allows the current IP — see above) and stop/inspect the service before it
  can reach the market-closed self-shutdown path, on ANY boot, without needing
  the user-data/boothook dance at all. Negligible cost on a real trading day
  (started well before market open anyway). Verified end-to-end 2026-09-17:
  reboot → 120s wait → bot starts → detects market closed → sends Telegram →
  full `shutdown -h now` → instance goes to `stopped` in the AWS console, all
  confirmed.
  ```
  [Service]
  ...
  TimeoutStartSec=180
  ExecStartPre=/bin/sleep 120
  ExecStart=/home/admin/alpha/.venv/bin/python /home/admin/alpha/main.py
  ...
  ```
  **Gotcha that broke the first attempt**: `ExecStartPre=/bin/sleep 120` alone
  is not enough — systemd's default `TimeoutStartSec` (90s) is shorter than the
  120s sleep, so the start-pre step gets killed for "timing out" before the
  sleep ever finishes, and the unit falls into an infinite
  fail-after-90s/retry-after-30s loop that never reaches `main.py` at all (no
  Telegram message, ever — this is what a broken version of this fix looks
  like). Must explicitly set `TimeoutStartSec` longer than the sleep duration
  (used 180s for a 120s sleep) whenever `ExecStartPre` includes a deliberate
  delay.
- **The user-data boothook set earlier during this incident must be cleared**
  once this permanent fix is in place — a `#cloud-boothook` script that stops
  and disables `alpha.service` runs on EVERY boot (that's its whole point,
  unlike a normal user-data script which only runs once), so it will silently
  re-disable the service on every future boot until the user-data is cleared
  via the AWS Console (Instance Settings → Edit user data → blank it out).
  Confirmed cleared 2026-09-17.
