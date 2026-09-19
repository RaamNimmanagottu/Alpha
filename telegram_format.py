"""Telegram message builders: emoji headers + monospace (<pre>) tables, HTML mode.

Pure functions only -- no network, no DB access, no trading logic -- so they are
trivially unit-testable (test_telegram_format.py). Callers pass in plain data
(InstrumentConfig-like objects, Trade rows, floats) and get back an HTML string
for TelegramNotifier.send_html().

Why <pre> tables: Telegram bots can't colour text or render real tables, but a
monospace <pre> block with aligned columns reads like a table, and emoji in the
(non-monospace) header line supply the colour: 🟢 profit / 🔴 loss / 🔵 entry /
🔔 signal / 🚀 start / 📊 summary. Emoji are kept OUT of <pre> blocks because
their width isn't monospace and would break column alignment.

Phone width is ~35-40 monospace characters, so every table here stays <= ~34.
Every dynamic string goes through esc() -- an unescaped "<" or "&" makes Telegram
reject the whole message.
"""
from __future__ import annotations

import html
from datetime import datetime
from typing import Iterable, Optional

_SHORT_NAME = {
    "NIFTY": "NIFTY", "BANKNIFTY": "BANK", "FINNIFTY": "FIN", "MIDCPNIFTY": "MIDCP",
    "SENSEX": "SENSEX", "NIFTYNXT50": "NXT50",
}

_SHORT_STRATEGY = {
    "ema_crossover": "EMA9/21", "ema_crossover_13_34": "EMA13/34", "ema_crossover_21_50": "EMA21/50",
    "ema_crossover_confirmed": "EMA9/21c", "keltner_channel": "Keltner", "donchian_channel": "Donchian",
    "rsi_oversold": "RSI", "cci_overbought_oversold": "CCI", "momentum_zero_cross": "Momentum",
    "stochastic": "Stoch", "opening_range_breakout": "ORB", "ema_ribbon": "Ribbon",
}

MAX_CLOSED_ROWS_SHOWN = 20
"""Telegram caps a message at 4096 chars; 20 rows x ~34 chars is nowhere near it,
but an unbounded list on a very busy day shouldn't be able to get a message dropped."""


def esc(value) -> str:
    return html.escape(str(value), quote=False)


def short_name(name: str) -> str:
    return _SHORT_NAME.get(name, name[:6])


def short_strategy(name: str) -> str:
    return _SHORT_STRATEGY.get(name, name[:8])


def hhmm(iso_or_ts) -> str:
    """'2026-09-18T10:40:06' / Timestamp / datetime -> '10:40'. Never raises."""
    try:
        if isinstance(iso_or_ts, str):
            return datetime.fromisoformat(iso_or_ts).strftime("%H:%M")
        return iso_or_ts.strftime("%H:%M")
    except Exception:
        return "--:--"


def money(value: float, signed: bool = False) -> str:
    return f"{value:+,.0f}" if signed else f"{value:,.0f}"


def _side(trade_type: str) -> str:
    return trade_type  # "CE" / "PE"


def table(headers: list[str], rows: list[list], align: str) -> str:
    """Aligned monospace table body (NOT wrapped in <pre> yet, NOT escaped yet).

    `align` is one char per column: 'l' left-justify, 'r' right-justify.
    """
    str_rows = [[str(c) for c in r] for r in rows]
    widths = [max([len(h)] + [len(r[i]) for r in str_rows]) for i, h in enumerate(headers)]

    def fmt(cells):
        return " ".join(c.ljust(w) if a == "l" else c.rjust(w) for c, w, a in zip(cells, widths, align)).rstrip()

    head = fmt(headers)
    return "\n".join([head, "-" * len(head)] + [fmt(r) for r in str_rows])


def kv_table(pairs: list[tuple[str, str]]) -> str:
    """Two-column 'label   value' block, labels left-aligned."""
    width = max(len(k) for k, _ in pairs)
    return "\n".join(f"{k.ljust(width)}  {v}" for k, v in pairs)


def pre(body: str) -> str:
    return f"<pre>{esc(body)}</pre>"


def _closed_sorted(trades) -> list:
    closed = [t for t in trades if t.status == "CLOSED"]
    return sorted(closed, key=lambda t: t.closed_at or "")


def dashboard(trades: Iterable, capital: float) -> str:
    """Today's open positions, closed trades, day P&L and capital -- appended to
    the SIGNAL / ENTRY / EXIT messages so every alert carries the full picture."""
    trades = list(trades)
    open_ = [t for t in trades if t.status == "OPEN"]
    closed = _closed_sorted(trades)

    parts: list[str] = [f"<b>📋 TODAY</b>  ({len(open_)} open · {len(closed)} closed)"]

    parts.append(f"<b>Open ({len(open_)})</b>")
    if open_:
        rows = [[short_name(t.instrument), _side(t.trade_type), f"{t.entry_price:.2f}", t.quantity, hhmm(t.opened_at)]
                for t in open_]
        parts.append(pre(table(["Inst", "Sd", "Entry", "Qty", "Since"], rows, "llrrr")))
    else:
        parts.append("<i>none</i>")

    parts.append(f"<b>Closed ({len(closed)})</b>")
    if closed:
        shown = closed[-MAX_CLOSED_ROWS_SHOWN:]
        rows = [[short_name(t.instrument), _side(t.trade_type), f"{t.entry_price:.2f}",
                 f"{(t.exit_price or 0):.2f}", money(t.pnl or 0.0, signed=True)] for t in shown]
        body = table(["Inst", "Sd", "Entry", "Exit", "PnL"], rows, "llrrr")
        if len(closed) > len(shown):
            body += f"\n(+{len(closed) - len(shown)} earlier not shown)"
        parts.append(pre(body))
    else:
        parts.append("<i>none</i>")

    day_pnl = sum((t.pnl or 0.0) for t in closed)
    wins = sum(1 for t in closed if (t.pnl or 0.0) > 0)
    losses = sum(1 for t in closed if (t.pnl or 0.0) < 0)
    emoji = "🟢" if day_pnl > 0 else "🔴" if day_pnl < 0 else "⚪"
    parts.append(f"{emoji} Day PnL <b>₹{esc(money(day_pnl, signed=True))}</b> · W{wins} L{losses} · "
                 f"Capital <b>₹{esc(money(capital))}</b>")
    return "\n".join(parts)


def _levels(option_type: str, underlying: float, tp: float, sl: float) -> tuple[float, float]:
    """Underlying-price levels for take-profit / stop-loss: a call profits when the
    index rises, a put when it falls."""
    if option_type == "CE":
        return underlying + tp, underlying - sl
    return underlying - tp, underlying + sl


def startup_message(opening_capital: float, paper: bool, instruments, risk, now: Optional[datetime] = None) -> str:
    now = now or datetime.now()
    mode = "PAPER" if paper else "LIVE"
    info = kv_table([
        ("Capital", f"₹{money(opening_capital)}"),
        ("Mode", mode),
        ("Loss limit", f"₹{money(risk.daily_loss_limit)}/day"),
        ("Max trades", f"{risk.max_trades_per_day}/day ({risk.max_trades_per_instrument} per instr)"),
    ])
    rows = [[short_name(i.name), i.quantity, f"{i.take_profit_points:g}/{i.stop_loss_points:g}",
             short_strategy(i.signal_strategy)] for i in instruments]
    inst_table = table(["Inst", "Qty", "TP/SL", "Strategy"], rows, "lrll")
    return "\n".join([
        f"🚀 <b>EC2 STARTED</b>  {esc(now.strftime('%a %d-%b %H:%M'))}",
        pre(info),
        f"<b>Instruments ({len(rows)})</b>",
        pre(inst_table),
    ])


def signal_message(cfg, direction: str, ltp: float, signal_time, trades, capital: float,
                   now: Optional[datetime] = None) -> str:
    now = now or datetime.now()
    option_type = "CE" if direction == "BUY" else "PE"
    tp_level, sl_level = _levels(option_type, ltp, cfg.take_profit_points, cfg.stop_loss_points)
    pairs = [
        ("Signal", f"{direction} -> {option_type}"),
        ("Underlying", f"{ltp:.2f}"),
        ("Candle", hhmm(signal_time) if signal_time is not None else "--:--"),
        ("Strategy", short_strategy(cfg.signal_strategy)),
        ("Target lvl", f"{tp_level:.2f}  (+{cfg.take_profit_points:g})"),
        ("Stop lvl", f"{sl_level:.2f}  (-{cfg.stop_loss_points:g})"),
        ("Qty", str(cfg.quantity)),
    ]
    return "\n".join([
        f"🔔 <b>SIGNAL</b>  {esc(short_name(cfg.name))} · {esc(direction)}  {esc(now.strftime('%H:%M:%S'))}",
        pre(kv_table(pairs)),
        dashboard(trades, capital),
    ])


def entry_message(cfg, mode: str, option_type: str, symbol: str, premium: float, quantity: int,
                  underlying: float, strike: float, greek: Optional[dict], trades, capital: float,
                  now: Optional[datetime] = None) -> str:
    now = now or datetime.now()
    tp_level, sl_level = _levels(option_type, underlying, cfg.take_profit_points, cfg.stop_loss_points)
    pairs = [
        ("Contract", symbol),
        ("Strike", f"{strike:g}"),
        ("Premium", f"{premium:.2f}"),
        ("Qty", str(quantity)),
        ("Cost", f"₹{money(premium * quantity)}"),
        ("Underlying", f"{underlying:.2f}"),
        ("Target lvl", f"{tp_level:.2f}"),
        ("Stop lvl", f"{sl_level:.2f}"),
    ]
    if greek is not None:
        pairs.append(("Delta", f"{float(greek['delta']):.3f}"))
        pairs.append(("IV", f"{float(greek['impliedVolatility']):.2f}%"))
    return "\n".join([
        f"🔵 <b>ENTRY [{esc(mode)}]</b>  {esc(short_name(cfg.name))} · {esc(option_type)}  "
        f"{esc(now.strftime('%H:%M:%S'))}",
        pre(kv_table(pairs)),
        dashboard(trades, capital),
    ])


def exit_message(cfg, reason: str, symbol: str, entry_price: float, exit_price: float, quantity: int,
                 pnl: float, capital: float, opened_at, trades, now: Optional[datetime] = None) -> str:
    now = now or datetime.now()
    emoji = "🟢" if pnl > 0 else "🔴" if pnl < 0 else "⚪"
    cost = entry_price * quantity
    pct = (pnl / cost * 100) if cost else 0.0
    try:
        held_min = max(0, int((now - datetime.fromisoformat(opened_at)).total_seconds() // 60))
        held = f"{held_min}m"
    except Exception:
        held = "n/a"
    pairs = [
        ("Contract", symbol),
        ("Entry->Exit", f"{entry_price:.2f} -> {exit_price:.2f}"),
        ("Qty", str(quantity)),
        ("PnL", f"₹{money(pnl, signed=True)}  ({pct:+.1f}%)"),
        ("Held", held),
    ]
    return "\n".join([
        f"{emoji} <b>EXIT [{esc(reason)}]</b>  {esc(short_name(cfg.name))}  {esc(now.strftime('%H:%M:%S'))}",
        pre(kv_table(pairs)),
        dashboard(trades, capital),
    ])


def summary_message(opening_capital: float, closing_capital: float, trades, now: Optional[datetime] = None) -> str:
    now = now or datetime.now()
    trades = list(trades)
    closed = [t for t in trades if t.status == "CLOSED"]
    by_inst: dict[str, list] = {}
    for t in closed:
        by_inst.setdefault(t.instrument, []).append(t)

    rows = []
    for name, ts in by_inst.items():
        pnl = sum((t.pnl or 0.0) for t in ts)
        wins = sum(1 for t in ts if (t.pnl or 0.0) > 0)
        rows.append([short_name(name), len(ts), wins, len(ts) - wins, money(pnl, signed=True)])
    total_pnl = sum((t.pnl or 0.0) for t in closed)
    total_wins = sum(1 for t in closed if (t.pnl or 0.0) > 0)
    rows.append(["TOTAL", len(closed), total_wins, len(closed) - total_wins, money(total_pnl, signed=True)])

    body = table(["Inst", "Trd", "W", "L", "PnL"], rows, "lrrrr")
    emoji = "🟢" if total_pnl > 0 else "🔴" if total_pnl < 0 else "⚪"
    still_open = sum(1 for t in trades if t.status == "OPEN")
    parts = [
        f"📊 <b>TODAY SUMMARY</b>  {esc(now.strftime('%a %d-%b-%Y'))}",
        pre(body) if closed else "<i>No closed trades today.</i>",
        f"Capital ₹{esc(money(opening_capital))} → <b>₹{esc(money(closing_capital))}</b>  "
        f"{emoji} <b>₹{esc(money(total_pnl, signed=True))}</b>",
    ]
    if still_open:
        parts.append(f"⚠️ {still_open} position(s) still open")
    return "\n".join(parts)
