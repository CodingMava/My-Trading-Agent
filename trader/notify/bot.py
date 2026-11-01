"""Telegram commands: check on the system from your phone, stop new trades, or log in to Kite for the day.
Nothing here can trade.

    python -m trader.notify.bot        # runs until stopped; scripts/register_tasks.ps1 starts it at logon

Only messages from the chat in TELEGRAM_CHAT_ID are answered; every other chat is ignored. No command can
release the kill switch, change a limit or place an order: commands never bypass the risk controls. /login
makes today's Kite session here on the PC from the page Kite returns to after you log in: the API secret
and the session's access token never pass through Telegram, and the request token you send is single-use.
/myip compares this PC's internet address with KITE_STATIC_IP in .env, and /myip done writes the new one there
(that one line only) once it is in Kite's developer console, which only Kite's own site can change.
While live trading is on, a trading morning without a login gets a reminder at 08:30.
"""
from __future__ import annotations

import json
import logging
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, time as clock_time
from pathlib import Path
from html import escape
from zoneinfo import ZoneInfo

import requests

from trader.config import ENV_FILE, ROOT, load_settings, parse_env_file
from trader.data.kite import (LOGIN_URL, SESSION_FILE, KiteAuthError, KiteError, create_session, load_session,
                              request_token_from, save_session, session_secrets)
from trader.execution.kite_orders import from_session
from trader.execution.live import check as live_check, dry_run_waiting, public_ip
from trader.execution.store import PaperStore
from trader.gate import load_gate_config
from trader.logging_setup import configure_logging
from trader.markets.calendar import load_calendars
from trader.notify.telegram import notifier_from_settings
from trader.notify.templates import money, rupees
from trader.ops import console
from trader.ops.health import ACTIVE, ALERT, WARN, Health, health_checks, open_live_store, open_us_store
from trader.registry import StrategyRegistry
from trader.risk.killswitch import KillSwitch

log = logging.getLogger(__name__)
IST = ZoneInfo("Asia/Kolkata")
POLL_SECONDS = 50  # Telegram holds each request open this long while there is nothing new
RETRY_SECONDS = 30  # wait after a failed poll (no internet, Telegram down)
MAX_REASON = 200
REMIND_FROM, REMIND_UNTIL = clock_time(8, 30), clock_time(9, 15)  # the live jobs start at 09:20
HELP = ("<b>Commands</b>\n\n"
        "/status: health, mode, equity and positions\n"
        "/positions: open positions\n"
        "/trades: the latest closed trades\n"
        "/kill reason: stop all new trades (open positions still exit as planned)\n"
        "/login: log in to Kite for today (live trading needs it before 09:15)\n"
        "/kitecheck: check the Kite connection, read-only (after /login)\n"
        "/myip: is this PC's internet address the one Kite has? /myip done: save the new one in .env\n\n"
        "Releasing the kill switch, changing a limit or trading is only possible on the PC.")


@dataclass
class Context:
    """What a command may look at, read afresh for every command so it is always current."""
    store: PaperStore | None
    registry: StrategyRegistry
    kill_switch: KillSwitch
    checks: list[Health]
    us_store: PaperStore | None = None


def load_context(settings, kill_switch: KillSwitch) -> Context:
    database = ROOT / settings.paper_database
    store = PaperStore(database, settings.paper_starting_capital) if database.exists() else None
    registry = StrategyRegistry.load()
    us_store = open_us_store(settings)
    checks = health_checks(store, load_calendars()["NSE"], registry, kill_switch, settings, datetime.now(IST),
                           load_gate_config().max_evidence_age_days, backup_dir=database.parent / "backups",
                           live_store=open_live_store(settings), us_store=us_store)
    return Context(store, registry, kill_switch, checks, us_store)


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
    if ctx.us_store is not None:
        us = console.account(ctx.us_store)
        lines.append(f"US paper: equity ${us['equity']:,.2f} ({us['return']:+.2%}), {us['positions']} open "
                     f"position(s), last session {us['last_session'] or '-'}")
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


def signed(value: float, currency: str = "₹") -> str:
    return f"{'-' if value < 0 else '+'}{money(abs(value), currency)}"


def _accounts(ctx: Context) -> list[tuple[str, PaperStore, str]]:
    """The paper accounts that have records: India's in rupees, then the US one in dollars."""
    return [(title, store, currency) for title, store, currency in (("", ctx.store, "₹"), ("US ", ctx.us_store, "$"))
            if store is not None]


def positions_text(ctx: Context) -> str:
    sections = []
    for title, store, currency in _accounts(ctx):
        if store.positions():
            sections.append([f"<b>{title}Open positions</b>", ""] + [
                escape(f"{row['Stock']} x{row['Quantity']}: entry {money(row['Entry'], currency)}, last "
                       f"{money(row['Last'], currency)}, stop {money(row['Stop'], currency)}, "
                       f"P&L {signed(row['P&L'], currency)}, held {row['Days held']} day(s)")
                for row in console.positions_table(store).to_dict("records")])
    return "\n\n".join("\n".join(section) for section in sections) or "No open positions."


def trades_text(ctx: Context, count: int = 10) -> str:
    sections = []
    for title, store, currency in _accounts(ctx):
        trades = console.newest_first(store.trades(), count)
        if len(trades):
            sections.append([f"<b>{title}Latest {len(trades)} closed trades</b>", ""] + [
                escape(f"{t['exit_session']} {t['symbol']} ({t['strategy_id']}): {t['reason']}, "
                       f"{signed(t['net_pnl'], currency)} ({t['net_return']:+.2%})")
                for t in trades.to_dict("records")])
    return "\n\n".join("\n".join(section) for section in sections) or "No closed trades yet."


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


def kite_login(settings, argument: str, session_file: Path = SESSION_FILE, http=requests,
               now: datetime | None = None) -> str:
    """/login alone: the link to log in at. /login <address>: the session, made here on the PC from the page
    Kite returned to (or just its request_token)."""
    key, secret = settings.kite_api_key.reveal(), settings.kite_api_secret.reveal()
    if not (key and secret):
        return "Kite isn't set up: add KITE_API_KEY and KITE_API_SECRET to .env on the PC."
    if not argument.strip():
        session = load_session(session_file, now)
        state = (f"Logged in until {session.expires_at:%d %b %H:%M} IST." if session else "Not logged in today.")
        return escape(f"{state}\n\n1. Log in to Kite: {LOGIN_URL.format(api_key=key)}\n2. Kite then opens your app's "
                      "redirect page (it may not load on a phone; that's fine). Copy the page's full address "
                      "and send it here as: /login <address>")
    try:
        session = create_session(key, secret, request_token_from(argument), http=http, now=now)
    except (ValueError, KiteError) as exc:
        return f"Login failed: {escape(str(exc))}"
    except requests.RequestException as exc:  # its text could hold the request: name the type only
        return f"Login failed: couldn't reach Kite ({type(exc).__name__}). Try again."
    save_session(session, session_file)
    return escape(f"Logged in to Kite as {session.user_id} until {session.expires_at:%d %b %H:%M} IST.")


def kite_check_text(settings, connect: Callable[[], object] | None = None) -> str:
    """/kitecheck: python -m trader.execution.live check, from the phone. Counts and a verdict only: no funds
    or holdings pass through Telegram."""
    try:
        seen, problems = live_check((connect or (lambda: from_session(settings)))(), open_live_store(settings),
                                    detail=False)
    except KiteAuthError as exc:
        return f"Log in first: send /login. ({escape(str(exc))})"
    except KiteError as exc:
        return f"Kite check failed: {escape(str(exc))}"
    except requests.RequestException as exc:  # its text could hold the request: name the type only
        return f"Kite check failed: couldn't reach Kite ({type(exc).__name__})."
    verdict = ("\n".join(f"PROBLEM: {p}" for p in problems) or "Every field the order system relies on is there, "
               "and the account holds every share the system believes it holds.")
    return "<b>Kite check (read-only)</b>\n\n" + escape("\n".join(seen) + "\n\n" + verdict)


STATIC_IP_LINE = re.compile(r"^[ \t]*(export[ \t]+)?KITE_STATIC_IP[ \t]*=.*$", re.MULTILINE)


def my_ip_text(argument: str, env_file: Path = ENV_FILE, address: Callable[[], str | None] = public_ip) -> str:
    """/myip: this PC's internet address against KITE_STATIC_IP in .env. /myip done: write it there, once it is in
    Kite's developer console: before that, the live jobs would send orders Kite refuses, and a refused stop isn't
    sent again."""
    if argument.lower() not in ("", "done"):
        return "Send /myip to check the address, or /myip done once the new one is in Kite's developer console."
    seen = address()
    if seen is None:
        return "Couldn't look up this PC's internet address just now. Try again in a minute."
    registered = parse_env_file(env_file).get("KITE_STATIC_IP", "").strip()
    if seen == registered:
        return escape(f"This PC's internet address is {seen}, the one in .env. Nothing to do.")
    if not argument:
        return escape(f"This PC's internet address is now {seen}, but .env has {registered or 'none'}.\n\n"
                      f"1. On developers.kite.trade, open your app and put {seen} as its IP address.\n"
                      "2. Then send /myip done.\n\n"
                      "Kite allows only one change a week. If you can't change it, that's OK: I'll send you each "
                      "order to do by hand in the Kite app.")
    text = env_file.read_text(encoding="utf-8-sig") if env_file.is_file() else ""
    line = f"KITE_STATIC_IP={seen}"
    text = (STATIC_IP_LINE.sub(line, text, count=1) if STATIC_IP_LINE.search(text)
            else text + ("" if not text or text.endswith("\n") else "\n") + line + "\n")
    temporary = env_file.with_name(env_file.name + ".tmp")  # written whole, then swapped in: .env is never half-written
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(env_file)
    log.info("KITE_STATIC_IP in .env changed from %s to %s from Telegram", registered or "none", seen)
    return escape(f"Saved {seen} in .env (it had {registered or 'none'}). The next live job sends what is waiting.")


def login_reminder(settings, calendar, now: datetime, session_file: Path = SESSION_FILE,
                   dry_run: Callable[[], bool] = dry_run_waiting) -> str | None:
    """While live trading is on, or a live dry run holds simulated orders or shares: a trading morning between 08:30
    and 09:15 without today's Kite login."""
    if (not calendar.is_trading_day(now.date()) or not REMIND_FROM <= now.time() < REMIND_UNTIL
            or load_session(session_file, now) is not None):
        return None
    if settings.live_enabled:
        return ("<b>Kite login needed</b>\n\nLive trading is on, and today's jobs (09:20, 15:15, and the evening one "
                "after paper trial 1) need a Kite login. Send /login.")
    if dry_run():
        return ("<b>Kite login needed</b>\n\nThe live dry run holds simulated orders or shares: its 09:20 job needs "
                "today's Kite prices. Send /login.")
    return None


class CommandBot:
    """Long-polls Telegram for messages and answers the commands from the configured chat."""

    def __init__(self, token: str, chat_id: str, notifier, context, http=requests, sleep=time.sleep,
                 direct: dict[str, Callable[[str], str]] | None = None,
                 reminder: Callable[[], str | None] | None = None):
        self._token, self.chat_id = token, str(chat_id)
        self._url = f"https://api.telegram.org/bot{token}/getUpdates"  # contains the token: never log it
        self.notifier, self.context, self.http, self.sleep = notifier, context, http, sleep
        self.direct, self.reminder = direct or {}, reminder  # direct: commands that need no paper records
        self.offset, self.reminded = None, None

    def answer(self, text: str) -> str:
        command, _, argument = text.strip().partition(" ")
        handler = self.direct.get(command.split("@")[0].lower())
        if handler is not None:
            return handler(argument.strip())  # needs no records, and what it is given is never logged
        try:
            ctx = self.context()
        except Exception as exc:  # e.g. the database is busy: say so rather than stay silent
            log.warning("Couldn't read the records for %r: %s", text[:40], exc, exc_info=True)
            return f"Couldn't read the records just now ({escape(type(exc).__name__)}); try again in a minute."
        try:
            return reply_to(text, ctx)
        finally:
            for store in (ctx.store, ctx.us_store):
                if store is not None:
                    store.close()

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

    def remind(self, today: date) -> None:
        """Send the reminder, if there is one, at most once a day."""
        if self.reminder is not None and self.reminded != today and (text := self.reminder()):
            self.notifier.send(text)
            self.reminded = today

    def run(self) -> None:
        log.info("Answering Telegram commands")
        while True:
            try:
                self.remind(datetime.now(IST).date())
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
    calendar = load_calendars()["NSE"]
    bot = CommandBot(settings.telegram_bot_token.reveal(), settings.telegram_chat_id,
                     notifier_from_settings(settings), lambda: load_context(settings, KillSwitch()),
                     direct={"/login": lambda argument: kite_login(settings, argument),
                             "/kitecheck": lambda argument: kite_check_text(settings),
                             "/myip": my_ip_text},
                     reminder=lambda: login_reminder(settings, calendar, datetime.now(IST)))
    bot.run()


if __name__ == "__main__":
    main()
