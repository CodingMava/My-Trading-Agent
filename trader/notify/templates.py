"""Telegram message texts (HTML parse mode). Every dynamic value is escaped, so names or reasons
containing <, > or & can't break a message. Paper-trading messages are labelled [PAPER]."""
from __future__ import annotations

from html import escape


def rupees(value: float) -> str:
    return f"₹{value:,.2f}"


def _message(title: str, rows: list[tuple[str, str]], paper: bool, footer: str | None = None) -> str:
    lines = [f"<b>{'[PAPER] ' if paper else ''}{escape(title)}</b>", ""]
    lines += [f"{escape(label)}: {escape(value)}" for label, value in rows]
    if footer:
        lines += ["", escape(footer)]
    return "\n".join(lines)


def buy_signal(*, symbol: str, market: str, last_close: float, stop_distance: float, quantity: int, strategy: str,
               exit_note: str, win_rate: float | None, expectancy: float | None, reason: str, paper: bool = True) -> str:
    return _message("BUY SIGNAL", [
        ("Stock", symbol),
        ("Market", market),
        ("Entry", f"next open (last close {rupees(last_close)})"),
        ("Stop Loss", f"{stop_distance:.1%} below the fill (about {rupees(last_close * (1 - stop_distance))})"),
        ("Target", f"none fixed; exits on {exit_note}"),
        ("Quantity", str(quantity)),
        ("Risk/Reward", "not fixed (no price target)"),
        ("Strategy", strategy),
        ("Profitable-Trade Rate", f"{win_rate:.0%} in research" if win_rate is not None else "unknown"),
        ("Expectancy", f"{expectancy:+.2%} per trade after costs, in research" if expectancy is not None else "unknown"),
        ("Confidence", "not estimated"),
    ], paper, f"Reason: {reason}")


def buy_executed(*, symbol: str, price: float, quantity: int, stop: float, strategy: str, exit_note: str,
                 paper: bool = True) -> str:
    return _message("BUY EXECUTED", [
        ("Stock", symbol), ("Entry", rupees(price)), ("Quantity", str(quantity)), ("Stop Loss", rupees(stop)),
        ("Target", f"none fixed; exits on {exit_note}"), ("Strategy", strategy),
    ], paper)


def sell_executed(*, symbol: str, price: float, quantity: int, pnl: float, net_return: float, reason: str,
                  paper: bool = True) -> str:
    return _message("SELL EXECUTED", [
        ("Stock", symbol), ("Exit", rupees(price)), ("Quantity", str(quantity)),
        ("P&L", f"{'-' if pnl < 0 else ''}{rupees(abs(pnl))} after costs"), ("Return", f"{net_return:+.2%}"),
        ("Reason", reason),
    ], paper)


def no_trade(*, symbol: str, strategy: str, reason: str, paper: bool = True) -> str:
    return _message("NO TRADE", [("Stock", symbol), ("Strategy", strategy), ("Reason", reason)], paper)


def risk_alert(*, title: str, detail: str, paper: bool = True) -> str:
    return _message(f"RISK ALERT: {title}", [("Detail", detail)], paper)


def live_update(*, title: str, lines: list[str]) -> str:
    """A message about real orders (Phase 11): labelled [LIVE], never [PAPER]."""
    return "\n".join([f"<b>[LIVE] {escape(title)}</b>", "", *(escape(line) for line in lines)])


def daily_summary(*, session: str, equity: float, day_change: float, cash: float, positions: list[tuple[str, int, float]],
                  strategies: int, paper: bool = True) -> str:
    held = "; ".join(f"{symbol} x{quantity} @ {rupees(price)}" for symbol, quantity, price in positions) or "none"
    return _message(f"DAILY SUMMARY {session}", [
        ("Equity", f"{rupees(equity)} ({day_change:+.2%} today)"), ("Cash", rupees(cash)),
        ("Open positions", held), ("Strategies trading", str(strategies)),
    ], paper, None if strategies else "NO TRADE: no strategy has the evidence to trade.")
