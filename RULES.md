# Alpha Trading Bot — Rules Book

Living document of every finalized rule/decision, so nothing has to be re-derived
from chat history. Update this file whenever a new rule is validated and locked in.

Last updated: 2026-09-19 (phase-5 deployed: 6 indices incl. SENSEX and
NIFTYNXT50; prior day: day-1 live review, cost-of-trading analysis as a
standing rule, HDFCBANK/ICICIBANK/TCS removed, validate_all.py added, 3
entry-timing ideas tested and rejected).

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

### MIDCPNIFTY (Nifty Midcap Select index options) — added 2026-09-18
- A genuine 4th tradeable NSE index (real OPTIDX options, not individual
  midcap stocks) — `index_token: 26074`, `candle_token: 99926074`, same
  dual-token pattern as NIFTY/BANKNIFTY/FINNIFTY. Volume=0 like every other
  index (computed, never directly traded).
- **Signal**: Donchian Channel Breakout (20) — same winning strategy as
  CRUDEOIL and PNB, reused `donchian_channel_signal.py` directly, no new
  code needed. Beat EMA(5/13) (2nd), Supertrend Standalone (3rd) in the
  27+ strategy comparison.
- **Take-profit**: 120 index points; **Stop-loss**: 58 index points (current
  price ~14,500.75).
- **Backtest**: 1000 days (50,636 candles, 2023-12-26 to 2026-09-18), gross
  52.33% win rate at the baseline (290/139.2) comparison scale -- one of the
  best win rates of any instrument tested this session. TP/SL then tuned
  specifically for NET-of-cost edge (not just gross points, per the standing
  rule below) across 60/29 up to 700/336 -- **net/trade peaks at 120/58
  (Rs192.61/trade after realistic F&O costs), the best net/trade of any
  instrument tested so far**, beating IDFCFIRSTB's previous best
  (Rs130.24/trade). Genuine peak, not a runaway: net/trade rises from
  Rs111.53 (60/29) to Rs192.61 (120/58) then falls back down (Rs139.56 at
  150/72), and goes NEGATIVE beyond ~450/216 as the assumed premium scale
  (and thus turnover-based costs) grows faster than gross profit.
- **Lot size**: 120, confirmed live from the instrument master.
- Same delta=0.5 approximation caveat as every other index/stock capital
  estimate in this doc (no historical option-premium series available).

### SENSEX (BSE index options) — BUILT IN CODE 2026-09-19 (phase-5)
- A genuine BSE index, real options — but trades on a DIFFERENT exchange
  segment than every other instrument so far: options are on **BFO** (BSE
  F&O), not NFO. Index quote AND candle data both use the SAME token
  (`99919000`, `exch_seg: BSE`) -- simpler than NIFTY's dual-token pattern,
  no separate index_token/candle_token needed. Volume=0 (computed index,
  same as every NSE index).
- **Signal**: EMA Crossover (13/34) — a slower EMA pair than any other
  instrument so far. Beat Keltner Channel Breakout (2nd) and Donchian (3rd)
  in the 27+ strategy comparison, with an unusually strong 53-54% gross win
  rate at the baseline comparison scale.
- **Take-profit**: 1200 index points; **Stop-loss**: 576 index points
  (current price ~74,295 -- SENSEX trades at ~3x NIFTY's level).
- **Backtest**: 1000 days (50,642 candles, 2023-12-26 to 2026-09-18). TP/SL
  tuned for NET-of-cost edge (same F&O cost model as every instrument this
  session) across 600/288 up to 2800/1344 -- **genuine peak at 1200/576:
  659 trades, 53.0% win rate, Rs159.07/trade net of realistic costs** --
  third-best net/trade of any instrument tested this session (after
  MIDCPNIFTY's Rs192.61 and IDFCFIRSTB's Rs130.24... actually above
  IDFCFIRSTB, so second-best). Rises from Rs81.96 (600/288) to the 1200/576
  peak then falls on both sides (Rs132.55 at 1485.9/713.2, down to Rs3.02
  at 2800/1344) -- not a runaway.
- **Lot size**: 20, confirmed live from the instrument master.
- **5-instrument combined capital estimate** (NIFTY+BANKNIFTY+FINNIFTY+
  MIDCPNIFTY+SENSEX, Rs 2,00,000 start, 1000 days, net of costs,
  risk-capped): ~Rs 10,43,423 final (+421.7%, ~82.5% approx CAGR, -15.50%
  max drawdown). SENSEX contributed Rs1,04,826 net -- more than BANKNIFTY.
- **Built 2026-09-19** (user asked to add SENSEX + NIFTYNXT50 and deploy):
  `ema_crossover_13_34_signal.py` (dedicated module, same pattern as
  `ema_crossover_21_50_signal.py`), config entry with
  `underlying_exchange: BSE` / `options_exchange: BFO`. Live read-only check
  before deploy: underlying LTP, BFO option quotes and BSE candle data all
  resolve correctly (unlike the stock options, whose option quotes failed
  with "token not found").
- **Bug found and fixed while adding it**: `InstrumentEngine._get_candles()`
  never passed an exchange to `update_historical_data()`, which defaults to
  `"NSE"` -- SENSEX would have silently fetched zero candles from NSE
  forever, so its signal would never have fired (and nothing would have
  errored). Fixed to pass `exchange=self.cfg.underlying_exchange`;
  regression-tested in `test_exchange_plumbing.py`. `validate_all.py` now
  also accepts BSE/BFO and checks the underlying/options exchange pair is
  consistent (NSE->NFO, BSE->BFO, MCX->MCX).
- **`min_premium_threshold` set to 0 (feature disabled, plain ATM as
  backtested)**: the 1.2 x take_profit_points heuristic used for the other
  indices gave 1440 here, but SENSEX's real ATM premium was only ~Rs270-600
  when checked, so the min-premium walk would have forced a very deep-ITM
  strike -- a large unbacktested deviation. A live check across all
  instruments (2026-09-19) showed the heuristic is only sensible where it
  lands near real ATM premium: NIFTY 120 vs ATM ~86-92 (walks ITM slightly,
  as intended), MIDCPNIFTY 144 vs ~119-148 (slight), BANKNIFTY 360 vs
  ~415-536 and FINNIFTY 180 vs ~187-258 (below ATM, so effectively inert).
  Needs a deliberate value near SENSEX's real ATM premium if the ITM
  behaviour is wanted there.
- Same delta=0.5 approximation caveat as every other capital estimate here.

### NIFTYNXT50 (Nifty Next 50 index options) — BUILT IN CODE 2026-09-19 (phase-5), **REMOVED 2026-09-21 (illiquid)**
- **REMOVED 2026-09-21** (user decision, confirmed by live paper data): the options have no real
  two-sided market. Day-3 paper trades opened and closed at the *same* price with Rs0 P&L
  (CE 3488.05 -> 3488.05 twice, PE 2902.55 -> 2902.55), i.e. quotes did not move / no real fills.
  The backtest edge below used INDEX points with a 0.5-delta approximation, so it was never tradable
  in these options. Its Rs3,60,604 share of the 6-index estimate below is therefore NOT achievable
  -- treat the combined 6-index numbers as overstated. Config block removed, `max_trades_per_day`
  18 -> 15 (5 x 3). `donchian_channel_signal.py` stays (MIDCPNIFTY uses it) and the NXT50 short name
  stays in `telegram_format.py` so past NXT50 rows still render. Lesson: check option liquidity
  (two-sided quotes, spread, volume/OI) BEFORE trusting an index-points backtest for an instrument.
- (Original build notes follow.) A genuine NSE index with real OPTIDX options: `index_token: 26013`,
  `candle_token: 99926013` (same dual-token pattern as NIFTY), lot size 25,
  volume=0 (computed index).
- **Signal**: Donchian Channel Breakout (20) -- reuses
  `donchian_channel_signal.py` (same as MIDCPNIFTY/PNB/CRUDEOIL), no new code.
  Won the 27+ strategy comparison at +35,789 gross points, 52.66% win rate
  (MACD+RSI Combo was 2nd with the highest win rate, 54.93%).
- **TP/SL**: 800/384. Tuned for net-of-cost edge across 200/96 up to 2800/1344
  -- **the surface is bimodal (two local peaks), like TCS's was**: net/trade
  is Rs169.13 at 400/192 and Rs190.80 at 800/384, with dips between and after
  (Rs149-154 around 450-600, Rs154.51 at 1000/480). Chose 800/384 (1890
  trades, 52.1% win rate, Rs190.80/trade) -- second-best net/trade of any
  instrument tested this session after MIDCPNIFTY's Rs192.61 -- but a bimodal
  surface is lower-confidence than a clean single peak; watch it in the
  paper-trading month.
- **Single-instrument capital estimate** (Rs 2,00,000, 1000 days, net of
  costs, risk-capped at 3 trades/day): ~Rs 5,29,473 (+164.7%, ~42.9% CAGR,
  -22.88% max drawdown).
- `min_premium_threshold: 0` (disabled) for the same reason as SENSEX: the
  heuristic gave 960 vs a real ATM premium of ~Rs560-644.

### Combined 6-index estimate and phase-5 roster (2026-09-19) -- NIFTYNXT50 removed 2026-09-21, live roster is now 5 indices
- NIFTY + BANKNIFTY + FINNIFTY + MIDCPNIFTY + SENSEX + NIFTYNXT50, Rs
  2,00,000 start, 1000 days, net of realistic F&O costs, per-instrument
  3-trades/day cap: **~Rs 13,72,897 final (+586.4%, ~101.7% approx CAGR,
  -21.31% max drawdown)**. Per-instrument net: MIDCPNIFTY 3,81,375 /
  NIFTYNXT50 3,60,604 / FINNIFTY 1,81,167 / NIFTY 1,30,899 / SENSEX
  1,04,826 / BANKNIFTY 55,681. Same delta=0.5 (no theta) approximation
  caveat as every capital estimate in this doc -- the live paper-trading
  month is what gives the real answer.
- `max_trades_per_day: 18` (= 6 x `max_trades_per_instrument: 3`).
- Other index-option pairs found in the instrument master but NOT tested:
  BANKEX (BFO, lot 30), SENSEX50 (BFO, lot 75), MCXBULLDEX (MCX, lot 15/30),
  FOCIT (BFO, lot 45), NIFTYFPI (NFO, lot 1100).

### Equity-vs-options check (2026-09-18, informational only)
- Re-ran the 3 stocks that failed as options (HDFCBANK, ICICIBANK, TCS) as
  plain equity intraday trades (1:1 price capture, no delta dampening;
  equity STT 0.025% sell-side vs options' 0.15%). Mixed: HDFCBANK flips to
  +Rs38.13/trade net (from -Rs12.03), but ICICIBANK (-Rs108.25) and TCS
  (-Rs127.64) get much worse -- equity turnover per trade (full share price
  x quantity) is 10-50x an option's premium, so the absolute costs balloon
  for high-priced, high-frequency signals. And the capital needed is
  Rs4.7-9.4 lakh per position at these quantities, far beyond Rs 2,00,000.
  Not pursued; options remain the vehicle.

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

### Stock options (NSE OPTSTK) — 6 stocks, BUILT IN CODE 2026-09-18
- **Why this category**: unlike NIFTY/BANKNIFTY/FINNIFTY (computed indices,
  never directly traded, always volume=0), a stock's OWN underlying equity
  trades on the NSE cash market with real volume — e.g. RELIANCE's 1000-day
  cumulative volume was 8.65 billion shares, vs. zero for any index.
- **Status**: all 6 below are live in `config.yaml` with `paper_trading: true`
  — a deliberate one-month live-paper experiment (real market data, real
  option premiums fetched live, zero real capital risk) rather than trusting
  the backtest numbers alone. Review after ~1 month and prune whichever
  underperform their own backtest expectations. New signal modules:
  `ema_crossover_21_50_signal.py`, `cci_signal.py`,
  `momentum_zero_cross_signal.py`, `ema_crossover_confirmed_signal.py`
  (Keltner reuses the existing `keltner_channel_signal.py`).
- **`max_trades_per_day` raised again, 9 -> 27** the same day these were
  added: 9 instruments x `max_trades_per_instrument: 3` = 27, so the combined
  cap still can't bind before an individual instrument's own limit (same
  reasoning as the 6->9 raise earlier that day). `daily_loss_limit: 5000`
  remains the real account-wide brake, not this trade-count cap.
- **Backtest summary (1000 days each, 2023-12-26 to 2026-09-18)**:

  | Stock | Signal | TP/SL | Lot size | Trades | Win% | Total pts |
  |---|---|---|---|---|---|---|
  | RELIANCE | Keltner Channel Breakout | 25/12 | 500 | 866 | 51.62% | +612.80 |
  | HDFCBANK | EMA(21/50) Crossover | 60/29 | 650 | 488 | 53.28% | +212.09 |
  | ICICIBANK | CCI(20) Overbought/Oversold | 45/22 | 700 | 1192 | 52.94% | +437.10 |
  | TCS | Momentum(10) Zero-Cross | 90/45 | 225 | 1457 | 48.87% | +1244.60 |
  | INFY | EMA(9/21) Confirmed (2-candle) | 35/17 | 400 | 826 | 51.57% | +613.60 |
  | SBIN | Keltner Channel Breakout | 75/37 | 750 | 724 | 49.31% | +411.95 |

  **5 different winning strategies across 6 stocks** (Keltner repeats for
  RELIANCE and SBIN only) — reconfirms yet again that signals don't transfer,
  now across 11 instruments total (3 indices + 2 commodities-documented-only
  + 6 stocks).
- **VWAP Cross was NOT the winner on any stock tested**, including RELIANCE
  where it was actually negative (-87.85) despite real volume being
  available — confirms again (as with GOLD/CRUDEOIL) that volume alone
  doesn't make VWAP the best strategy; it just makes it computable at all.
- **Confidence varies noticeably by stock** — most showed a clean single
  TP/SL peak (RELIANCE, INFY, ICICIBANK), but HDFCBANK and TCS had noisier,
  less monotonic TP/SL surfaces (HDFCBANK plateaued rather than peaking; TCS
  bounced between two local peaks at 32/15 and 90/45 without a clean single
  optimum — chose 90/45 for the better win-rate/avg-points trade-off, but
  flag this as lower-confidence than the others). Treat HDFCBANK/TCS results
  with a bit more skepticism than the rest until the paper-trading month
  confirms them.
- **Force-exit risk is much milder here than on commodities** (checked on
  RELIANCE specifically): worst single trade lost 12.88 points at 25/12 —
  close to the nominal SL, NOT the 4-13x overshoot seen on CRUDEOIL/GOLD.
  Equity options behave more like the indices in this respect.
- **RELIANCE capital estimate (Rs 2,00,000 start, 1000 days)**: ~Rs
  3,53,487.50 final (+76.7%, ~23.2% approx CAGR, -10.73% max drawdown) --
  but this used a 0.5-delta APPROXIMATION for option premium P&L (Angel
  One's optionGreek API doesn't support individual stocks, and no historical
  stock-option premium series was available to replay exactly). Treat as a
  rough estimate, not the same precision as NIFTY/BANKNIFTY/FINNIFTY's real
  option-premium-based numbers -- the live paper-trading month will give a
  real answer.
- **Stock F&O has MONTHLY expiry only** (no weekly), unlike
  NIFTY/BANKNIFTY/FINNIFTY — different theta/rollover profile, not yet
  separately analyzed.
- **Lot sizes confirmed live from the instrument master** (2026-09-18):
  RELIANCE 500, HDFCBANK 650, ICICIBANK 700, TCS 225, INFY 400, SBIN 750.

### NEW RULE: every instrument's backtest must be re-checked net of realistic
### F&O trading costs before it's trusted, not just gross points/PnL
Added 2026-09-18, after this exact gap nearly kept 3 losing instruments live.
Gross points/PnL from `trade_simulator.simulate()` ignores brokerage, STT,
exchange transaction charges, stamp duty, SEBI fees and GST entirely. These
are NOT a rounding error -- on the first full check (day 1 of live
NIFTY+BANKNIFTY+FINNIFTY+6-stocks paper trading), costs consumed **58-65% of
gross profit** across the 9-instrument set, and completely flipped 3 stocks
(HDFCBANK, ICICIBANK, TCS) from apparently-profitable to net-loss-making.

**Cost model used** (typical Angel One / discount-broker F&O rates, current
as of 2026-09-18 -- verify against an actual contract note before fully
trusting the exact numbers, but the model and its qualitative conclusions
are sound):
- Brokerage: Rs 20 flat per executed order (Rs 40/round trip) -- confirmed
  from Angel One's own brokerage calculator.
- STT (Securities Transaction Tax): **0.15%** of SELL-side premium turnover
  -- this is the rate effective 1-Apr-2026 (raised from 0.10%); using the
  old rate understates costs meaningfully, caught and corrected this session.
- Exchange transaction charges: ~0.05% of total (buy+sell) premium turnover.
- SEBI turnover fees: Rs 10/crore (~0.0001%) -- confirmed from Angel One,
  negligible in absolute terms.
- Stamp duty: 0.003% of BUY-side turnover only.
- GST: 18% on (brokerage + exchange charges + SEBI fees).
- For NIFTY/BANKNIFTY/FINNIFTY and the 6 stocks, option premium turnover was
  itself approximated (0.5-delta, same caveat as the capital-estimate
  numbers elsewhere in this doc) since exact historical premiums aren't
  available -- so absolute cost figures carry that same uncertainty, but the
  **relative** pattern below (why some instruments survive costs and others
  don't) is driven by lot-size x stock-price (turnover), which is real data,
  not an approximation.

**Why some instruments survive and others don't**: percentage-based costs
(STT, exchange charges) scale with premium turnover = premium price x lot
size. High-priced stocks with large lot sizes (ICICIBANK ~Rs1339 x 700,
TCS ~Rs2113 x 225, HDFCBANK ~Rs720 x 650) generate huge turnover per trade
relative to their points-based edge, so costs eat almost all of it. Indices
and lower-priced/smaller-lot names keep a much larger fraction of their
gross edge.

**Full 1000-day net-of-cost results (original 9-instrument set, before the
swap below)**:

| Instrument | Trades | Gross PnL | Total Cost | Net PnL | Net/trade |
|---|---|---|---|---|---|
| FINNIFTY | 1075 | Rs2,58,690 | Rs77,523 | Rs1,81,167 | Rs168.53 |
| NIFTY | 1158 | Rs2,06,404 | Rs75,505 | Rs1,30,899 | Rs113.04 |
| RELIANCE | 866 | Rs1,53,200 | Rs70,557 | Rs82,643 | Rs95.43 |
| INFY | 826 | Rs1,22,720 | Rs70,610 | Rs52,110 | Rs63.09 |
| BANKNIFTY | 1136 | Rs1,37,319 | Rs81,638 | Rs55,681 | Rs49.02 |
| SBIN | 724 | Rs1,54,481 | Rs1,44,957 | Rs9,525 | Rs13.16 |
| ICICIBANK | 1192 | Rs1,52,985 | Rs1,58,426 | **-Rs5,441** | **-Rs4.56** |
| TCS | 1457 | Rs1,40,018 | Rs1,49,089 | **-Rs9,072** | **-Rs6.23** |
| HDFCBANK | 488 | Rs68,929 | Rs74,799 | **-Rs5,870** | **-Rs12.03** |

**Action taken**: removed HDFCBANK, ICICIBANK, TCS from `config.yaml` and
the live paper-trading roster entirely -- genuinely net-loss-making, not
just thin-margin. Their signal modules (`ema_crossover_21_50_signal.py`,
`cci_signal.py`, `momentum_zero_cross_signal.py`) stay registered in
`instrument_engine.py`'s `SIGNAL_STRATEGIES` but are unused by any
instrument now.

### Midcap stocks — 4 added, 1 rejected, same day (2026-09-18)
Hypothesis after the cost finding above: **lower-priced stocks should keep
more of their edge**, since turnover-based costs scale with price x lot
size while the points-based edge doesn't necessarily scale the same way.
Tested 5 liquid midcap-ish F&O names (PNB, FEDERALBNK, IDFCFIRSTB,
BANKBARODA, TATAPOWER) with the full 27+ strategy comparison, then
TP/SL-tuned each winner AND checked net-of-cost edge (same cost model
above) before adding anything to config.yaml -- confirmed for 4/5:

| Stock | Signal | TP/SL | Lot | Trades | Win% | Net/trade (after costs) |
|---|---|---|---|---|---|---|
| IDFCFIRSTB | Opening Range Breakout (15min) | 1.72/0.82 | 9275 | 884 | 50.2% | **Rs130.24** (best of any instrument tested) |
| FEDERALBNK | Stochastic(14,3) Overbought/Oversold | 10/4.8 | 2500 | 1049 | 51.1% | Rs93.34 |
| PNB | Donchian Channel Breakout (20) | 2.35/1.13 | 8000 | 1476 | 46.0% | Rs86.95 |
| BANKBARODA | 3-EMA Ribbon Alignment (9/21/50) | 10/4.8 | 2925 | 767 | 49.5% | Rs54.63 |
| TATAPOWER | Stochastic(14,3) Overbought/Oversold | (all tested) | 1450 | -- | -- | **NEGATIVE at every TP/SL tried** (-Rs18.71 to -Rs116.90) -- NOT added |

All 4 winners beat every one of the 3 removed large-caps on net/trade,
several by a wide margin -- the hypothesis held. Built in code
(`stochastic_signal.py`, `opening_range_breakout_signal.py`,
`ema_ribbon_signal.py`; `donchian_channel_signal.py` was already written
for CRUDEOIL, reused here for PNB) and added to `config.yaml` with
`paper_trading: true`, same as the rest. TATAPOWER's own strategy just
doesn't have enough raw points-based edge to survive real costs at any
tested TP/SL -- not added, and per Lesson #1, no other midcap should be
assumed to work without its own backtest either.

**Current live instrument roster after this session (11 total)**: NIFTY,
BANKNIFTY, FINNIFTY, MIDCPNIFTY, RELIANCE, INFY, SBIN, PNB, FEDERALBNK,
IDFCFIRSTB, BANKBARODA. `max_trades_per_day` raised to 33 (= 11 x
`max_trades_per_instrument: 3`) to match.

### Commodities — BLOCKED from going live, real architecture gap found 2026-09-18
- Attempted to add GOLD/CRUDEOIL to `config.yaml` alongside the 6 stocks
  (same paper-trading-month plan). Found a real, serious blocker before
  writing any config for them -- NOT just a documentation gap this time:
  - Commodity futures **roll to a new contract every few weeks**, unlike
    NIFTY/BANKNIFTY/FINNIFTY's permanent index token. GOLD currently has 6
    live FUTCOM contracts, CRUDEOIL has 10, at different expiries. The
    specific contract this project's earlier backtest data was fetched
    from (`CRUDEOIL21SEP26FUT`, token 565899) expires **2026-09-21 -- 3
    days after this was checked.** Hardcoding a token in config.yaml the
    way every other instrument does would go stale almost immediately.
  - `broker.token_lookup(name, "MCX")`, the fallback used when
    `index_token` is omitted, silently resolves to **the wrong thing
    entirely** for commodities -- checked live and it returned a random
    OPTION contract's token (e.g. `GOLD30JUN27132500CE`) instead of the
    underlying future, because `_instrument_by_key` is a plain
    `(name, exch_seg)` dict that just keeps whichever instrument-master row
    happened to be last for that key, with no filtering for instrument
    type or expiry. Using this blindly would have fed a garbage "LTP" into
    every part of the engine that assumes it's the underlying's price --
    broken signals, broken strike selection, possibly a crash. This is NOT
    paper-trading-safe either, since paper mode still fetches real LTP.
  - **What's needed before commodities can go live (even in paper mode)**:
    a broker method that finds the nearest NON-expired FUTCOM contract for
    a given commodity name at runtime (not a fixed config token), used
    consistently for both the underlying LTP fetch and as the reference
    price for strike selection (commodity options are options on the
    future, not on spot). Not yet built.
- **What WAS done and kept** (safe, additive, doesn't change any existing
  instrument's behavior -- verified all 9 current instruments still default
  correctly): extended `broker.py`'s `option_contracts()` to also match
  `OPTFUT` (MCX commodity options use this instrumenttype, vs. NSE's
  `OPTSTK`/`OPTIDX`); added `underlying_exchange`/`options_exchange` fields
  to `InstrumentConfig` (default `"NSE"`/`"NFO"`, would be `"MCX"`/`"MCX"`
  for commodities) so `instrument_engine.py` no longer hardcodes `"NSE"`/
  `"NFO"` at its three LTP/order call sites; added `donchian_channel_signal.py`
  (CRUDEOIL's backtested winner) as a ready-but-unused module, same
  pattern-consistent style as the other signal modules. GOLD's winner
  (Keltner Channel Breakout) can reuse the existing `keltner_channel_signal.py`
  once the rollover problem above is solved.

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
- `max_trades_per_day: 27` — combined across all instruments (raised 6 -> 9 ->
  27 on 2026-09-18; see the note in section 1 — was observed live to block
  healthy instruments once a different one whipsawed through its own share
  of the cap, then raised again to keep pace with 6 new stock instruments).
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

- **Strike selection**: as of 2026-09-18, `strike_selection_mode: min_premium`
  (previously `delta`). Start at ATM; if its own live premium is below that
  instrument's `min_premium_threshold`, walk into ITM strikes (closest to
  ATM first, correct ITM direction per option type: lower strikes for CE,
  higher for PE) until one clears the threshold, or fall back to plain ATM
  (with a Telegram warning) if none do within 15 strikes. Never blocks an
  entry on this. **Rationale**: an ATM option's delta is ~0.5, so its
  premium only tracks about half of the underlying's points-based move —
  since every TP/SL in this project is calibrated in underlying points, an
  ATM-only strategy's real option P&L structurally under-captures the
  backtested edge. An ITM strike has higher delta and tracks the
  underlying's move more faithfully, and — unlike the old `delta` mode —
  doesn't depend on Angel One's `optionGreek` API at all, which doesn't
  support every instrument type (see the RELIANCE/stock-options section).
  Thresholds (2026-09-18, NOT separately backtested — a live-only change,
  same as `delta` mode was): NIFTY 120 (user-specified), BANKNIFTY 360,
  FINNIFTY 180, MIDCPNIFTY 144 (all three others = 1.2 x that instrument's
  own `take_profit_points`, matching NIFTY's own 120/100 ratio — a starting
  heuristic to refine, not independently validated per instrument).
  Implementation: `InstrumentEngine._select_min_premium_contract()` in
  `instrument_engine.py`; unit-tested with a mock broker in
  `test_min_premium_selection.py` (ATM-already-clears-threshold, CE walks
  to lower strikes, PE walks to higher strikes, falls back to ATM when
  nothing clears the threshold, threshold=0 disables the feature entirely).
- ATM (`buy_strike_offset`/`sell_strike_offset`: 0) is still the backtested
  baseline underneath all three modes — `min_premium` and `delta` are both
  live-only deviations from what was actually backtested.

### RBI MPC announcement-day performance check (2026-09-18)
- No API exists for RBI's Monetary Policy Committee calendar — RBI publishes
  it as a press release in advance (per Section 45ZI of the RBI Act), the
  same way NSE publishes its holiday list. If this ever needs automating,
  it'd have to be hardcoded/updated periodically like `holiday_list_2026`,
  not fetched live.
- Checked how all 4 index instruments' validated strategies performed
  specifically on the last ~15 RBI policy-announcement dates (2024-2026,
  within the 1000-day backtest window) vs all other days. **Mixed, and
  partly counter-intuitive**:

  | Instrument | RBI days (avg pts/trade) | Normal days | |
  |---|---|---|---|
  | NIFTY | +10.67 | +5.34 | better on RBI days (~2x) |
  | BANKNIFTY | +15.65 | +7.83 | better on RBI days (~2x) |
  | FINNIFTY | **-9.12** | +8.40 | **worse -- flips negative** |
  | MIDCPNIFTY | +0.48 | +4.75 | worse, but still positive |
  | Combined | +5.11 | +6.26 | modestly worse, not dramatic |

  NIFTY/BANKNIFTY's EMA-crossover trend-following signal seems to actually
  benefit from RBI days' strong directional post-announcement moves;
  FINNIFTY's Keltner Channel breakout signal appears to get whipsawed by
  the initial volatility instead. SL-exit rate was modestly higher on RBI
  days (31.3% vs 26.6%), worst single trade was NOT worse (-150 vs -229.3
  normal, likely just small-sample noise).
- **Sample size caveat (per Lesson #1)**: only ~15 RBI dates / 20-43 trades
  per instrument over 3 years — too small to be strong evidence, treat as
  an early signal worth monitoring, not a reason to change code yet. The
  Oct/Dec 2025 dates used were best-effort estimates (bi-monthly pattern),
  not directly confirmed against an RBI press release.
- **No action taken yet** — flagging FINNIFTY specifically for extra
  attention around future RBI announcement days, not disabling or adjusting
  anything.

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
   alone), because the "confirmation" timeframe is itself lagging. Reconfirmed
   2026-09-18 on NIFTY's live EMA crossover three different ways, all on the
   full 1000-day dataset: (a) waiting for a pullback to the signal candle's
   own MIDPOINT for every signal (not just extended ones): 806 trades, 42.06%
   win, only +1183.60pts vs baseline's +6350.90; (b) requiring the crossover
   to hold for 2/3/4 consecutive candles before acting: total points fell
   monotonically as confirmation length grew (+5748, +4212, +3514 vs
   baseline's +6350.90); (c) requiring the entry candle to open in the
   signal's favor ("gap confirmation"): dropped ~50% of all signals and the
   survivors still did far worse (+1622.30 vs +6350.90). All three ideas
   sounded reasonable from a single live whipsaw trade that day, but the full
   1000-day evidence says no every time -- the existing extended-candle-only
   pullback logic (RULES.md section 4) remains the one confirmation-style
   filter that actually helps, precisely because it's the only one validated
   against the full history rather than a single day's anecdote.
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

- **Run `validate_all.py` before every deploy, and after any change to
  config.yaml, an instrument's settings, or a signal module** (added
  2026-09-18). `.venv\Scripts\python.exe validate_all.py` -- exits 0/pass,
  1/fail, safe to gate a deploy on. Checks: every .py file parses,
  `instrument_engine.py` imports cleanly, `config.yaml` loads, every
  instrument's `signal_strategy` is actually registered (not just a
  correctly-spelled string), per-instrument sanity (positive lot
  size/TP/SL, sane time ordering, valid exchange codes), **risk config
  sanity — specifically `max_trades_per_day >= num_instruments x
  max_trades_per_instrument`**, every active instrument's signal module
  smoke-tested against synthetic data, and `.env` has every required
  credential key. The risk-config check exists specifically because the
  combined-cap-starves-an-instrument bug (section 1's "Note on
  `max_trades_per_day`") happened twice for real on 2026-09-18 before this
  script existed -- it's now caught automatically instead of only after
  something breaks live.
- Local build → validate (`validate_all.py`, unit tests, backtests) → commit
  → merge → push to GitHub can proceed without asking each time.
- **Deploying to the live EC2 instance (`i-0f3149bf3fc2e4779`) always requires
  explicit user approval first** — even after full local validation passes.
  (See memory: feedback-ask-before-ec2-deploy)
- **EC2 deploy history**: `phase-2` (2026-09-17, 3 indices) -> `phase-4`
  (2026-09-18 night, 4 indices + `min_premium` strike selection, verified by
  the boot log showing all 4 engines) -> **`phase-5` (2026-09-19, current)**:
  NIFTY, BANKNIFTY, FINNIFTY, MIDCPNIFTY, SENSEX, NIFTYNXT50, paper trading,
  `max_trades_per_day: 18`. Deployed as one tar.gz (29 files: every
  top-level .py + config.yaml) -- a single scp + extract fits inside the
  120s systemd grace window, unlike per-file scp which lost the race twice.
  Verified on the server: `validate_all.py` 116/116, and a one-off script
  that builds all 6 engines with the real broker, prefetches SENSEX candles
  from BSE (5,129) and NIFTYNXT50 candles (5,145) and evaluates both signals.
  (On a weekend the service itself can't show this -- main.py exits at the
  weekend check before engines are built -- so verify with a one-off script.)
- The 7 stock/midcap instruments (RELIANCE, INFY, SBIN, PNB, FEDERALBNK,
  IDFCFIRSTB, BANKBARODA) remain built in code, backtested and documented but
  are NOT in config.yaml / NOT deployed (deliberately excluded since phase-4).
- Every deploy needs the dev machine's current outbound IP in the security
  group first (it changes almost daily -- check `https://api.ipify.org`); an
  SSH timeout with no other symptom is almost always that.
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
