"""Telegram message texts (HTML parse mode). Every dynamic value is escaped, so names or reasons
containing <, > or & can't break a message. Paper-trading messages are labelled [PAPER]."""
from __future__ import annotations

from html import escape


def rupees(value: float) -> str:
    return f"₹{value:,.2f}"


def money(value: float, currency: str = "₹") -> str:
    return f"{currency}{value:,.2f}"


def _message(title: str, rows: list[tuple[str, str]], paper: bool, footer: str | None = None) -> str:
    lines = [f"<b>{'[PAPER] ' if paper else ''}{escape(title)}</b>", ""]
    lines += [f"{escape(label)}: {escape(value)}" for label, value in rows]
    if footer:
        lines += ["", escape(footer)]
    return "\n".join(lines)


def buy_signal(*, symbol: str, market: str, last_close: float, stop_distance: float, quantity: int, strategy: str,
               exit_note: str, win_rate: float | None, expectancy: float | None, reason: str, paper: bool = True,
               currency: str = "₹") -> str:
    by_hand = [("Execution", "by hand: buy at the next US open, then place the stop order")] if market == "US" else []
    return _message("BUY SIGNAL", [
        ("Stock", symbol),
        ("Market", market),
        *by_hand,
        ("Entry", f"next open (last close {money(last_close, currency)})"),
        ("Stop Loss", f"{stop_distance:.1%} below the fill (about {money(last_close * (1 - stop_distance), currency)})"),
        ("Target", f"none fixed; exits on {exit_note}"),
        ("Quantity", str(quantity)),
        ("Risk/Reward", "not fixed (no price target)"),
        ("Strategy", strategy),
        ("Profitable-Trade Rate", f"{win_rate:.0%} in research" if win_rate is not None else "unknown"),
        ("Expectancy", f"{expectancy:+.2%} per trade after costs, in research" if expectancy is not None else "unknown"),
        ("Confidence", "not estimated"),
    ], paper, f"Reason: {reason}")


def sell_signal(*, symbol: str, market: str, quantity: int, last_close: float, at: str, reason: str, strategy: str,
                paper: bool = True, currency: str = "₹") -> str:
    """An exit decided at a close: sell at the next session's open (an exit rule) or close (the time limit)."""
    by_hand = [("Execution", f"by hand: sell at the next US {at}, and cancel its stop order")] if market == "US" else []
    return _message("SELL SIGNAL", [
        ("Stock", symbol), ("Market", market), *by_hand,
        ("Exit", f"next {at} (last close {money(last_close, currency)})"), ("Quantity", str(quantity)),
        ("Strategy", strategy),
    ], paper, f"Reason: {reason}")


def buy_executed(*, symbol: str, price: float, quantity: int, stop: float, strategy: str, exit_note: str,
                 paper: bool = True, currency: str = "₹") -> str:
    return _message("BUY EXECUTED", [
        ("Stock", symbol), ("Entry", money(price, currency)), ("Quantity", str(quantity)),
        ("Stop Loss", money(stop, currency)),
        ("Target", f"none fixed; exits on {exit_note}"), ("Strategy", strategy),
    ], paper)


def sell_executed(*, symbol: str, price: float, quantity: int, pnl: float, net_return: float, reason: str,
                  paper: bool = True, currency: str = "₹") -> str:
    return _message("SELL EXECUTED", [
        ("Stock", symbol), ("Exit", money(price, currency)), ("Quantity", str(quantity)),
        ("P&L", f"{'-' if pnl < 0 else ''}{money(abs(pnl), currency)} after costs"), ("Return", f"{net_return:+.2%}"),
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
                  strategies: int, paper: bool = True, market: list[str] = (), record: str = "", currency: str = "₹",
                  label: str = "") -> str:
    held = "; ".join(f"{symbol} x{quantity} @ {money(price, currency)}" for symbol, quantity, price in positions) or "none"
    rows = [("Equity", f"{money(equity, currency)} ({day_change:+.2%} today)"), ("Cash", money(cash, currency)),
            ("Open positions", held), ("Strategies trading", str(strategies))]
    rows += [("Market check", "; ".join(market))] if market else []
    rows += [("Unattended record", record)] if record else []
    return _message(f"{label + ' ' if label else ''}DAILY SUMMARY {session}", rows, paper,
                    None if strategies else "NO TRADE: no strategy has the evidence to trade.")
