"""Health checks for unattended operation: did the daily run happen, did it work, and is it safe?

    python -m trader.ops.health             # every check; exit code 1 when something needs attention
    python -m trader.ops.health --notify    # also send one Telegram alert listing the problems

Schedule it a few hours after the daily run (scripts/register_tasks.ps1 does both). It is what pages you
when the run didn't happen at all, which the run itself can never report.
"""
from __future__ import annotations

import argparse
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from trader.config import ROOT, load_settings
from trader.data.kite import SESSION_FILE, load_session, session_secrets
from trader.data.validate import DAILY_SETTLE
from trader.execution import broker
from trader.execution.oms import ORDER_PURPOSES, LiveStore
from trader.execution.store import PaperStore
from trader.gate import EVIDENCE_DIR, REQUIREMENTS, load_evidence, load_gate_config
from trader.logging_setup import configure_logging, make_console_utf8
from trader.markets.calendar import CalendarCoverageError, MarketCalendar, load_calendars
from trader.notify import templates
from trader.notify.telegram import notifier_from_settings
from trader.registry import StrategyRegistry
from trader.risk.killswitch import KillSwitch

IST = ZoneInfo("Asia/Kolkata")
OK, INFO, WARN, ALERT = "ok", "info", "warn", "alert"
RUN_DEADLINE = timedelta(hours=4)  # once a session's data has settled, the daily run should be done within this
RUN_TIMEOUT = timedelta(hours=2)  # a run still marked running after this long died without finishing
EVIDENCE_NOTICE = timedelta(days=30)
BACKUP_MAX_AGE = timedelta(days=3)
DRY_RUN_WINDOW = timedelta(days=30)
LIVE_SETTLE = timedelta(days=1)  # a live order still without a result after this needs a look
UNATTENDED_TARGET = 60  # clean sessions in a row that Level 5 asks for before any real order
ACTIVE = ("PAPER", "LIVE_SMALL", "LIVE")


@dataclass(frozen=True)
class Health:
    name: str
    level: str  # ok, info, warn or alert
    detail: str


def _when(stamp: str) -> str:
    return datetime.fromisoformat(stamp).astimezone(IST).strftime("%d %b %H:%M IST")


def _died(run, now: datetime) -> bool:
    return run.status == "running" and now - datetime.fromisoformat(run.started_at) >= RUN_TIMEOUT


def run_checks(store: PaperStore | None, calendar: MarketCalendar, now: datetime) -> list[Health]:
    """Did the daily run process the latest session it should have, and did the last run finish cleanly?"""
    try:
        expected = calendar.last_completed_session(now - DAILY_SETTLE - RUN_DEADLINE)
    except CalendarCoverageError as exc:
        return [Health("daily run", ALERT, f"can't tell which session to expect: {exc}")]
    runs = store.runs(limit=1) if store is not None else []
    latest = next(runs.itertuples(), None) if len(runs) else None
    last = store.last_session() if store is not None else None
    if last is None and latest is None:
        return [Health("daily run", WARN, "it hasn't run yet; the first run creates the records "
                                          "(scripts/register_tasks.ps1 schedules it daily)")]
    checks = []
    if last is not None and last >= expected:
        checks.append(Health("daily run", OK, f"processed through {last}"))
    elif latest is not None and latest.status == "running" and not _died(latest, now):
        checks.append(Health("daily run", INFO, f"a run started at {_when(latest.started_at)} is still going"))
    else:
        checks.append(Health("daily run", ALERT, f"the last processed session is {last or 'none'}, but {expected} "
                                                 "should be done by now: the daily run didn't happen or didn't finish"))
    if latest is not None:
        if latest.status in ("failed", "halted"):
            checks.append(Health("last run", ALERT, f"{latest.status} at {_when(latest.finished_at)}: {latest.detail}"))
        elif _died(latest, now):
            checks.append(Health("last run", ALERT, f"started at {_when(latest.started_at)} and never finished"))
        elif latest.status == "ok":
            checks.append(Health("last run", OK, f"finished cleanly at {_when(latest.finished_at)}"))
    return checks


def safety_checks(store: PaperStore | None, kill_switch: KillSwitch) -> list[Health]:
    checks = [Health("kill switch", ALERT, f"engaged ({kill_switch.reason}). Once the cause is fixed, release it "
                                           "by hand: python -m trader.risk.killswitch release")
              if kill_switch.engaged else Health("kill switch", OK, "off")]
    if store is not None:
        problems = store.reconcile()
        checks.append(Health("reconciliation", ALERT if problems else OK,
                             "; ".join(problems) or "cash and holdings match the fills"))
        unsent = store.unsent_messages()
        checks.append(Health("notifications", ALERT if unsent else OK,
                             f"{len(unsent)} Telegram message(s) undelivered; the next run retries them" if unsent
                             else "all delivered"))
    return checks


def clean_sessions(store: PaperStore, now: datetime) -> int:
    """Sessions processed since the last run that failed or died (Level 5's 60 in a row)."""
    clean = 0
    for run in store.runs(limit=100_000).itertuples():  # newest first
        if run.status == "failed" or _died(run, now):
            break
        clean += int(run.sessions)
    return clean


def duplicate_orders(store: PaperStore) -> int:
    """Orders the database refused as duplicates: each one means something tried to place an order twice."""
    decisions = store.table("decisions")
    return int((decisions["detail"] == "duplicate order prevented").sum()) if len(decisions) else 0


def unattended_record(store: PaperStore | None, now: datetime) -> Health:
    """Sessions processed since the last run that failed or died: Level 5's 60-session requirement."""
    if store is None:
        return Health("unattended record", INFO, f"0 of {UNATTENDED_TARGET} clean sessions before live trading")
    clean, duplicates = clean_sessions(store, now), duplicate_orders(store)
    detail = f"{clean} of {UNATTENDED_TARGET} clean sessions in a row before live trading"
    if duplicates:
        return Health("unattended record", WARN, f"{detail}; {duplicates} duplicate order(s) were prevented: find out why")
    return Health("unattended record", OK if clean >= UNATTENDED_TARGET else INFO, detail)


def dry_run_check(store: PaperStore | None, today: date) -> Health:
    """Phase 8: Kite must accept every request the dry run prepares (python -m trader.execution.broker)."""
    rows = store.table("dry_run_orders") if store is not None else None
    if rows is None or rows.empty:
        return Health("dry-run orders", INFO, "no Kite requests prepared yet (none is ever sent)")
    refused = rows[(rows["problems"] != "") & (rows["session"] >= (today - DRY_RUN_WINDOW).isoformat())]
    if len(refused):
        last = refused.iloc[-1]
        return Health("dry-run orders", WARN, f"Kite would refuse {len(refused)} request(s) from the last 30 days, "
                      f"e.g. {last['symbol']} {last['purpose']} on {last['session']}: {last['problems']}. Fix the "
                      "order path before any live trading")
    return Health("dry-run orders", OK, f"{len(rows)} Kite request(s) prepared, none sent; Kite would accept all "
                  "from the last 30 days")


def open_live_store(settings) -> LiveStore | None:
    """The live account's records, if a live job has ever run."""
    path = ROOT / settings.live_database
    return LiveStore(path) if path.exists() else None


def live_checks(settings, store: LiveStore | None, now: datetime, session_file: Path = SESSION_FILE) -> list[Health]:
    """Phase 11: what the live account needs from a person (python -m trader.execution.live status)."""
    checks = []
    if store is not None and (store.orders() or store.positions()):
        unclear = store.orders(("SENDING", "UNKNOWN"))
        if unclear:
            checks.append(Health("live unknown orders", ALERT, f"{len(unclear)} request(s) whose outcome is unknown ("
                                 + ", ".join(f"{r['symbol']} {r['purpose']}" for r in unclear[:3]) + "): check "
                                 "Kite's order book; the next live job looks them up before sending anything"))
        held = store.positions()
        bare = [symbol for symbol, position in held.items()
                if (stop := store.order(broker.stop_order(position).tag)) is None or stop["status"] not in ("SENT", "TRIGGERED")]
        if bare:
            checks.append(Health("live stops", ALERT, f"no stop at Kite for {', '.join(bare)}: place one by hand "
                                 "(a GTT at the stop in python -m trader.execution.live status)"))
        stale = [r for r in store.orders(("SENT",)) if r["purpose"] in ORDER_PURPOSES
                 and datetime.fromisoformat(r["updated_at"]) < now - LIVE_SETTLE]
        if stale:
            checks.append(Health("live stale orders", WARN, f"{len(stale)} order(s) sent over a day ago still have no "
                                 "result: check Kite's order book"))
        refused = [r for r in store.orders(("REJECTED",)) if r["session"] >= (now.date() - timedelta(days=7)).isoformat()]
        if refused:
            last = refused[-1]
            checks.append(Health("live refusals", WARN, f"Kite refused {len(refused)} request(s) in the last 7 days, "
                                 f"e.g. {last['symbol']} {last['purpose']}: {last['detail']}"))
        if not checks:
            checks.append(Health("live trading", OK, f"{len(held)} live holding(s), each with a stop at Kite; "
                                 "nothing unsettled"))
    if settings.live_enabled and load_session(session_file) is None:
        checks.append(Health("live login", WARN, "no Kite login today: the 09:20, 15:15 and 18:30 live jobs need one "
                             "(python -m trader.data.kite login)"))
    return checks or [Health("live trading", INFO, "off: no real order has been sent; Indian orders are a dry run")]


def _quick_check(conn: sqlite3.Connection) -> str:
    try:
        rows = [row[0] for row in conn.execute("PRAGMA quick_check").fetchall()]
    except sqlite3.DatabaseError as exc:  # e.g. "file is not a database"
        return str(exc)
    return "ok" if rows == ["ok"] else "; ".join(rows[:3])


def _quick_check_file(path: Path) -> str:
    conn = sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True)  # read-only: a check must not change it
    try:
        return _quick_check(conn)
    finally:
        conn.close()


def integrity_check(store: PaperStore | None, live_store: LiveStore | None, backup_dir: Path | None) -> list[Health]:
    """SQLite's own check that the records and the newest backup are intact. The folder they live in is synced
    by OneDrive; damage caught the same day can be undone from a backup taken before it."""
    if store is None:
        return []
    found = {"paper records": _quick_check(store.conn)}
    if live_store is not None:
        found["live records"] = _quick_check(live_store.conn)
    copies = sorted(Path(backup_dir).glob("paper-*.db")) if backup_dir is not None else []
    if copies:
        found[f"backup {copies[-1].name}"] = _quick_check_file(copies[-1])
    damaged = [f"{name} ({result})" for name, result in found.items() if result != "ok"]
    if damaged:
        return [Health("integrity", ALERT, "damaged: " + "; ".join(damaged) + ". Stop the daily run and restore "
                       "an intact backup (docs/runbook.md, Backups and restoring)")]
    return [Health("integrity", OK, ", ".join(found) + " intact")]


def backup_check(store: PaperStore | None, backup_dir: Path | None, today: date) -> list[Health]:
    """The daily run copies the records to <database folder>/backups after every run that didn't fail."""
    if store is None or backup_dir is None:
        return []
    copies = sorted(Path(backup_dir).glob("paper-*.db"))
    if not copies:
        return [Health("backup", WARN, f"no backup in {backup_dir} yet; the next daily run makes one")]
    latest = date.fromisoformat(copies[-1].stem.removeprefix("paper-"))
    if today - latest > BACKUP_MAX_AGE:
        return [Health("backup", WARN, f"the newest backup is from {latest}: check the daily run's log")]
    count = f"{len(copies)} daily cop{'y' if len(copies) == 1 else 'ies'}"
    return [Health("backup", OK, f"{count}, the newest {copies[-1].name}")]


def strategy_checks(registry: StrategyRegistry, today: date, max_age_days: int,
                    evidence_dir: Path = EVIDENCE_DIR) -> list[Health]:
    active = [r for r in registry.records() if r.status in ACTIVE]
    checks = [Health("strategies", INFO, ", ".join(f"{r.id} {r.status}" for r in active) if active
                     else "NO TRADE: no strategy has the evidence to trade")]
    checks += [Health("registry", WARN, problem) for problem in registry.problems]
    for record in active:
        for step in ACTIVE[:ACTIVE.index(record.status) + 1]:
            kind = REQUIREMENTS[step][0]
            evidence = load_evidence(record.id, kind, evidence_dir)
            if evidence is not None:
                expires = evidence.generated_date + timedelta(days=max_age_days)
                if expires - today <= EVIDENCE_NOTICE:
                    checks.append(Health("evidence", WARN, f"{record.id}'s {kind} evidence expires on {expires}; "
                                                           f"after that it can't hold {record.status}"))
    return checks


def calendar_checks(calendar: MarketCalendar, today: date) -> Health:
    if not calendar.covers(today):
        return Health("calendar", ALERT, f"config/market_calendars.toml doesn't cover {today.year}, so nothing "
                                         "will trade: add NSE's holidays for the year")
    if today.month == 12 and not calendar.covers(date(today.year + 1, 1, 1)):
        return Health("calendar", WARN, f"add NSE's {today.year + 1} holidays to config/market_calendars.toml "
                                        "before 1 January")
    return Health("calendar", OK, f"covers {today.year}")


def data_checks(settings, now: datetime, session_file: Path = SESSION_FILE) -> Health:
    if settings.data_provider != "kite":
        return Health("data source", OK, settings.data_provider)
    session = load_session(session_file, now)
    if session is None:
        return Health("data source", WARN, "Kite has no session for today, so the next run will fail: "
                                           "python -m trader.data.kite login")
    return Health("data source", OK, f"Kite session valid until {session.expires_at:%d %b %H:%M} IST")


def health_checks(store: PaperStore | None, calendar: MarketCalendar, registry: StrategyRegistry,
                  kill_switch: KillSwitch, settings, now: datetime, max_age_days: int = 365,
                  evidence_dir: Path = EVIDENCE_DIR, session_file: Path = SESSION_FILE,
                  backup_dir: Path | None = None, live_store: LiveStore | None = None) -> list[Health]:
    """Every check, worst first. `store` is None before the first daily run."""
    checks = [*run_checks(store, calendar, now), *safety_checks(store, kill_switch), unattended_record(store, now),
              dry_run_check(store, now.date()), *backup_check(store, backup_dir, now.date()),
              *integrity_check(store, live_store, backup_dir),
              *strategy_checks(registry, now.date(), max_age_days, evidence_dir), calendar_checks(calendar, now.date()),
              data_checks(settings, now, session_file), *live_checks(settings, live_store, now, session_file)]
    order = (ALERT, WARN, INFO, OK)
    return sorted(checks, key=lambda c: order.index(c.level))


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Health checks for unattended operation.")
    parser.add_argument("--notify", action="store_true", help="send a Telegram alert when something needs attention")
    args = parser.parse_args(argv)
    make_console_utf8()
    settings = load_settings()
    configure_logging(secrets=settings.secret_values() + session_secrets(), filename="health.log")
    database = ROOT / settings.paper_database
    store = PaperStore(database, settings.paper_starting_capital) if database.exists() else None
    now = datetime.now(IST)
    checks = health_checks(store, load_calendars()["NSE"], StrategyRegistry.load(), KillSwitch(), settings, now,
                           load_gate_config().max_evidence_age_days, backup_dir=database.parent / "backups",
                           live_store=open_live_store(settings))
    print(f"Health at {now:%Y-%m-%d %H:%M} IST")
    width = max(len(c.name) for c in checks)
    for check in checks:
        print(f"  [{check.level.upper():5s}] {check.name:<{width}}  {check.detail}")
    alerts = [c for c in checks if c.level == ALERT]
    if alerts and args.notify:
        notifier_from_settings(settings).send(templates.risk_alert(
            title="Health check", detail="; ".join(f"{c.name}: {c.detail}" for c in alerts)))
    raise SystemExit(1 if alerts else 0)


if __name__ == "__main__":
    main()
