"""Tests for telegram_format.py + TelegramNotifier.send_html. Run: python test_telegram_format.py"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Optional
from unittest import mock

import telegram_format as tf
from config import AppConfig
from notifier import TelegramNotifier

NOW = datetime(2026, 9, 21, 10, 40, 6)


@dataclass
class T:
    instrument: str
    trade_type: str
    entry_price: float
    quantity: int
    status: str
    opened_at: str = "2026-09-21T09:20:00"
    exit_price: Optional[float] = None
    pnl: Optional[float] = None
    closed_at: Optional[str] = None


def _plain(html_text: str) -> str:
    import html
    return html.unescape(re.sub(r"<[^>]+>", "", html_text))


def _balanced(html_text: str) -> bool:
    for tag in ("b", "i", "pre"):
        if html_text.count(f"<{tag}>") != html_text.count(f"</{tag}>"):
            return False
    return True


def _cfg():
    return AppConfig.load()


def test_startup():
    cfg = _cfg()
    msg = tf.startup_message(200000, True, cfg.instruments, cfg.risk, now=NOW)
    plain = _plain(msg)
    assert "EC2 STARTED" in plain and "200,000" in plain and "PAPER" in plain
    for i in cfg.instruments:
        assert tf.short_name(i.name) in plain
    assert _balanced(msg) and len(msg) < 4096


def test_dashboard_empty_and_mixed():
    empty = tf.dashboard([], 200000)
    assert "none" in empty and "200,000" in empty and _balanced(empty)

    trades = [
        T("NIFTY", "CE", 150.0, 65, "CLOSED", exit_price=170.0, pnl=1300.0, closed_at="2026-09-21T10:00:00"),
        T("BANKNIFTY", "PE", 400.0, 30, "CLOSED", exit_price=380.0, pnl=-600.0, closed_at="2026-09-21T10:10:00"),
        T("SENSEX", "CE", 900.0, 20, "OPEN"),
    ]
    d = tf.dashboard(trades, 200700)
    plain = _plain(d)
    assert "1 open" in plain and "2 closed" in plain
    assert "+1,300" in plain and "-600" in plain
    assert "Day PnL ₹+700" in plain and "W1 L1" in plain
    assert "🟢" in d
    assert _balanced(d)


def test_dashboard_truncates_long_history():
    trades = [T("NIFTY", "CE", 100.0, 65, "CLOSED", exit_price=101.0, pnl=65.0, closed_at=f"2026-09-21T10:{i:02d}:00")
              for i in range(50)]
    d = tf.dashboard(trades, 1)
    assert "earlier not shown" in d and len(d) < 4096


def test_signal_levels():
    cfg = _cfg().instruments[0]  # NIFTY
    buy = _plain(tf.signal_message(cfg, "BUY", 25000.0, datetime(2026, 9, 21, 10, 35), [], 200000, now=NOW))
    assert f"{25000 + cfg.take_profit_points:.2f}" in buy and f"{25000 - cfg.stop_loss_points:.2f}" in buy
    sell = _plain(tf.signal_message(cfg, "SELL", 25000.0, "2026-09-21T10:35:00", [], 200000, now=NOW))
    assert f"{25000 - cfg.take_profit_points:.2f}" in sell and "SELL -> PE" in sell


def test_entry_and_exit():
    cfg = _cfg().instruments[0]
    greek = {"delta": 0.52, "impliedVolatility": 11.3}
    e = tf.entry_message(cfg, "PAPER", "CE", "NIFTY29SEP2625000CE", 150.0, 65, 25000.0, 25000.0, greek, [], 200000,
                         now=NOW)
    assert _balanced(e) and "0.520" in e and "9,750" in e
    e2 = tf.entry_message(cfg, "PAPER", "CE", "X", 150.0, 65, 25000.0, 25000.0, None, [], 200000, now=NOW)
    assert "Delta" not in e2

    x = tf.exit_message(cfg, "stop_loss", "NIFTY29SEP2625000CE", 150.0, 120.0, 65, -1950.0, 198050.0,
                        "2026-09-21T10:00:00", [], now=NOW)
    assert "🔴" in x and "-1,950" in x and "40m" in x and _balanced(x)
    bad = tf.exit_message(cfg, "x", "S", 0.0, 0.0, 1, 0.0, 1.0, None, [], now=NOW)  # bad opened_at, zero cost
    assert "n/a" in bad


def test_escaping():
    cfg = _cfg().instruments[0]
    x = tf.exit_message(cfg, "a<b&c", "S<1>", 1.0, 2.0, 1, 1.0, 1.0, "2026-09-21T10:00:00", [], now=NOW)
    assert "a<b" not in x and "a&lt;b&amp;c" in x


def test_summary():
    trades = [
        T("NIFTY", "CE", 150.0, 65, "CLOSED", exit_price=170.0, pnl=1300.0, closed_at="2026-09-21T10:00:00"),
        T("NIFTY", "PE", 150.0, 65, "CLOSED", exit_price=140.0, pnl=-650.0, closed_at="2026-09-21T11:00:00"),
        T("SENSEX", "CE", 900.0, 20, "OPEN"),
    ]
    s = tf.summary_message(200000, 200650, trades, now=NOW)
    plain = _plain(s)
    assert "TOTAL" in plain and "+650" in plain and "1 position(s) still open" in plain and _balanced(s)
    assert "No closed trades" in _plain(tf.summary_message(200000, 200000, [], now=NOW))


def test_send_html_fallback():
    n = TelegramNotifier("tok", "chat")
    bad = mock.Mock(ok=False, status_code=400, text="can't parse entities")
    good = mock.Mock(ok=True)
    with mock.patch("notifier.requests.post", side_effect=[bad, good]) as post:
        n.send_html("<b>Hi</b> a &amp; b", plain_fallback=None)
    assert post.call_count == 2
    first, second = post.call_args_list[0].kwargs["json"], post.call_args_list[1].kwargs["json"]
    assert first["parse_mode"] == "HTML" and "parse_mode" not in second
    assert second["text"] == "Hi a & b"

    with mock.patch("notifier.requests.post", side_effect=RuntimeError("net")) as post:
        n.send_html("<b>x</b>", plain_fallback="plain")  # must not raise
    assert post.call_count == 2

    with mock.patch("notifier.requests.post") as post:
        TelegramNotifier(None, None).send_html("<b>x</b>")
    assert post.call_count == 0


def test_engine_falls_back_when_formatter_raises():
    from instrument_engine import InstrumentEngine
    engine = InstrumentEngine.__new__(InstrumentEngine)
    engine.cfg = _cfg().instruments[0]
    engine.notifier = mock.Mock()

    def boom():
        raise ValueError("bad")

    engine._notify_html(boom, "plain text")
    engine.notifier.send.assert_called_once_with("plain text")
    engine.notifier.send_html.assert_not_called()


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"PASS {t.__name__}")
    print(f"{len(tests)}/{len(tests)} passed")
