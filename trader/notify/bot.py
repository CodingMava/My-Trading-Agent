"""Telegram commands: check on the system from your phone, or stop new trades. Nothing here can trade.

    python -m trader.notify.bot        # runs until stopped; scripts/register_tasks.ps1 starts it at logon

Only messages from the chat in TELEGRAM_CHAT_ID are answered; every other chat is ignored. No command can
release the kill switch, change a limit or place an order: commands never bypass the risk controls.
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from datetime import datetime
from html import escape
from zoneinfo import ZoneInfo

import requests

from trader.config import ROOT, load_settings
from trader.data.kite import session_secrets
from trader.execution.store import PaperStore
from trader.gate import load_gate_config
from trader.logging_setup import configure_logging
from trader.markets.calendar import load_calendars
from trader.notify.telegram import notifier_from_settings
from trader.notify.templates import rupees
from trader.ops import console
from trader.ops.health import ACTIVE, ALERT, WARN, Health, health_checks, open_live_store
from trader.registry import StrategyRegistry
from trader.risk.killswitch import KillSwitch

log = logging.getLogger(__name__)
IST = ZoneInfo("Asia/Kolkata")
POLL_SECONDS = 50  # Telegram holds each request open this long while there is nothing new
RETRY_SECONDS = 30  # wait after a failed poll (no internet, Telegram down)
MAX_REASON = 200
HELP = ("<b>Commands</b>\n\n"
        "/status: health, mode, equity and positions\n"
        "/positions: open positions\n"
        "/trades: the latest closed trades\n"
        "/kill reason: stop all new trades (open positions still exit as planned)\n\n"
        "Releasing the kill switch, changing a limit or trading is only possible on the PC.")


@dataclass
class Context:
    """What a command may look at, read afresh for every command so it is always current."""
    store: PaperStore | None
    registry: StrategyRegistry
    kill_switch: KillSwitch
    checks: list[Health]


def load_context(settings, kill_switch: KillSwitch) -> Context:
    database = ROOT / settings.paper_database
    store = PaperStore(database, settings.paper_starting_capital) if database.exists() else None
    registry = StrategyRegistry.load()
    checks = health_checks(store, load_calendars()["NSE"], registry, kill_switch, settings, datetime.now(IST),
                           load_gate_config().max_evidence_age_days, backup_dir=database.parent / "backups",
                           live_store=open_live_store(settings))
    return Context(store, registry, kill_switch, checks)


def status_text(ctx: Context) -> str:
    active = [r.id for r in ctx.registry.records() if r.status in ACTIVE]
    lines = [f"<b>Status</b> ({datetime.now(IST):%d %b %H:%M} IST)", "",
             f"Mode: {'paper trading ' + ', '.join(active) if active else 'NO TRADE (no strategy has the evidence to trade)'}",
             f"Kill switch: {'ENGAGED (' + ctx.kill_switch.reason + ')' if ctx.kill_switch.engaged else 'off'}"]
    if ctx.store is None:
        lines.append("No paper-trading records yet: the first daily run creates them.")
    else:
        numbers = console.account(ctx.store)
        lines.append(f"Equity: {rupees(numbers['equity'])} ({numbers['return']:+.2%} since the start), "
                     f"cash {rupees(numbers['cash'])}, {numbers['positions']} open position(s), "
                     f"last session {numbers['last_session'] or '-'}")
    alerts = [c for c in ctx.checks if c.level == ALERT]
    warnings = [c for c in ctx.checks if c.level == WARN]
    lines.append("")
    if alerts:
        lines += ["Needs attention:"] + [f"- {c.name}: {c.detail}" for c in alerts]
    if warnings:
        lines += ["Warnings:"] + [f"- {c.name}: {c.detail}" for c in warnings]
    if not alerts and not warnings:
        lines.append("All health checks pass.")
    return "\n".join(lines[:1] + [escape(line) for line in lines[1:]])


def signed(value: float) -> str:
    return f"{'-' if value < 0 else '+'}{rupees(abs(value))}"


def positions_text(ctx: Context) -> str:
    if ctx.store is None or not ctx.store.positions():
        return "No open positions."
    lines = ["<b>Open positions</b>", ""]
    for row in console.positions_table(ctx.store).to_dict("records"):
        lines.append(escape(f"{row['Stock']} x{row['Quantity']}: entry {rupees(row['Entry'])}, last "
                            f"{rupees(row['Last'])}, stop {rupees(row['Stop'])}, P&L {signed(row['P&L'])}, "
                            f"held {row['Days held']} day(s)"))
    return "\n".join(lines)


def trades_text(ctx: Context, count: int = 10) -> str:
    trades = ctx.store.trades() if ctx.store is not None else None
    if trades is None or trades.empty:
        return "No closed trades yet."
    lines = [f"<b>Latest {min(count, len(trades))} closed trades</b>", ""]
    for t in console.newest_first(trades, count).to_dict("records"):
        lines.append(escape(f"{t['exit_session']} {t['symbol']} ({t['strategy_id']}): {t['reason']}, "
                            f"{signed(t['net_pnl'])} ({t['net_return']:+.2%})"))
    return "\n".join(lines)


def kill(ctx: Context, reason: str) -> str:
    if ctx.kill_switch.engaged:
        return f"The kill switch is already engaged: {escape(ctx.kill_switch.reason)}"
    ctx.kill_switch.engage(f"engaged from Telegram: {(reason.strip() or 'no reason given')[:MAX_REASON]}")
    return ("<b>Kill switch engaged.</b> No new trades until you release it on the PC "
            "(python -m trader.risk.killswitch release). Open positions still exit as planned.")


def reply_to(text: str, ctx: Context) -> str:
    command, _, argument = text.strip().partition(" ")
    command = command.split("@")[0].lower()  # "/status@YourBot" in a group chat
    if command == "/status":
        return status_text(ctx)
    if command == "/positions":
        return positions_text(ctx)
    if command == "/trades":
        return trades_text(ctx)
    if command == "/kill":
        return kill(ctx, argument)
    return HELP


class CommandBot:
    """Long-polls Telegram for messages and answers the commands from the configured chat."""

    def __init__(self, token: str, chat_id: str, notifier, context, http=requests, sleep=time.sleep):
        self._token, self.chat_id = token, str(chat_id)
        self._url = f"https://api.telegram.org/bot{token}/getUpdates"  # contains the token: never log it
        self.notifier, self.context, self.http, self.sleep = notifier, context, http, sleep
        self.offset = None

    def answer(self, text: str) -> str:
        try:
            ctx = self.context()
        except Exception as exc:  # e.g. the database is busy: say so rather than stay silent
            log.warning("Couldn't read the records for %r: %s", text[:40], exc, exc_info=True)
            return f"Couldn't read the records just now ({escape(type(exc).__name__)}); try again in a minute."
        try:
            return reply_to(text, ctx)
        finally:
            if ctx.store is not None:
                ctx.store.close()

    def poll_once(self) -> int:
        """One long poll: answer every command from the configured chat and return how many. Network
        trouble is logged (never with the token) and waited out; it never raises."""
        params = {"timeout": POLL_SECONDS, "allowed_updates": json.dumps(["message"])}
        if self.offset is not None:
            params["offset"] = self.offset
        try:
            payload = self.http.get(self._url, params=params, timeout=POLL_SECONDS + 15).json()
        except (requests.RequestException, ValueError) as exc:
            log.warning("Telegram polling failed (%s); retrying in %ds", type(exc).__name__, RETRY_SECONDS)
            self.sleep(RETRY_SECONDS)
            return 0
        if not payload.get("ok"):
            log.warning("Telegram refused getUpdates: %s", str(payload.get("description", ""))[:200])
            self.sleep(RETRY_SECONDS)
            return 0
        answered = 0
        for update in payload.get("result", []):
            self.offset = update["update_id"] + 1  # confirms it: Telegram won't send it again
            message = update.get("message") or {}
            chat = str((message.get("chat") or {}).get("id"))
            text = (message.get("text") or "").strip()
            if chat != self.chat_id:
                log.warning("Ignored a message from another chat (%s)", chat)
            elif text.startswith("/"):
                self.notifier.send(self.answer(text))
                answered += 1
        return answered

    def run(self) -> None:
        log.info("Answering Telegram commands")
        while True:
            try:
                self.poll_once()
            except Exception:  # an unattended listener must outlive any one bad update (logged with secrets masked)
                log.exception("Unexpected error while answering Telegram commands")
                self.sleep(RETRY_SECONDS)


def main() -> None:
    settings = load_settings()
    configure_logging(secrets=settings.secret_values() + session_secrets(), filename="bot.log")
    if not settings.telegram_enabled:  # a clean exit, so the scheduled task doesn't restart it every minute
        log.warning("Telegram is off (TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not set in .env): no commands to answer")
        return
    bot = CommandBot(settings.telegram_bot_token.reveal(), settings.telegram_chat_id,
                     notifier_from_settings(settings), lambda: load_context(settings, KillSwitch()))
    bot.run()


if __name__ == "__main__":
    main()
