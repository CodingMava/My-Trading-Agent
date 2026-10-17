"""Health checks for unattended operation: did the daily run happen, did it work, and is it safe?

    python -m trader.ops.health             # every check; exit code 1 when something needs attention
    python -m trader.ops.health --notify    # also send one Telegram alert listing the problems

Schedule it a few hours after the daily run (scripts/register_tasks.ps1 does both). It is what pages you
when the run didn't happen at all, which the run itself can never report.
"""
from __future__ import annotations

import argparse
import logging
import re
import sqlite3
from dataclasses import dataclass, replace
from datetime import date, datetime, time, timedelta
from pathlib import Path
from time import sleep as _sleep
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

log = logging.getLogger(__name__)
IST = ZoneInfo("Asia/Kolkata")
OK, INFO, WARN, ALERT = "ok", "info", "warn", "alert"
RUN_AT = time(18, 0)  # IST: when the daily run starts (scripts/register_tasks.ps1)
RUN_DEADLINE = timedelta(hours=2)  # ... and it should be done by this long after that
HEALTH_AT = time(21, 0)  # IST: when the scheduled check runs
LATE_AFTER = timedelta(minutes=5)  # a scheduled check starting this late was missed while the PC slept or was off
CATCH_UP_WAIT = timedelta(minutes=10)  # ... so it first gives the daily run's own catch-up time to finish
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


def expected_session(calendar: MarketCalendar, now: datetime) -> date:
    """The latest session the daily run should have processed by `now`. The run starts at 18:00 IST and takes
    the market's latest settled session: for NSE that day's, for the US the one that closed early that
    morning, India time (01:30 IST, or 02:30 in the northern winter)."""
    due = (now - RUN_DEADLINE).astimezone(IST)
    started = datetime.combine(due.date(), RUN_AT, IST)
    if started > due:
        started -= timedelta(days=1)
    return calendar.last_completed_session(started - DAILY_SETTLE)


def run_checks(store: PaperStore | None, calendar: MarketCalendar, now: datetime) -> list[Health]:
    """Did the daily run process the latest session it should have, and did the last run finish cleanly?"""
    try:
        expected = expected_session(calendar, now)
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


def records_checks(store: PaperStore) -> list[Health]:
    """Cash and holdings must match the fills, and every Telegram message must have gone out."""
    problems, unsent = store.reconcile(), store.unsent_messages()
    return [Health("reconciliation", ALERT if problems else OK, "; ".join(problems) or "cash and holdings match the fills"),
            Health("notifications", ALERT if unsent else OK,
                   f"{len(unsent)} Telegram message(s) undelivered; the next run retries them" if unsent
                   else "all delivered")]


def safety_checks(store: PaperStore | None, kill_switch: KillSwitch) -> list[Health]:
    checks = [Health("kill switch", ALERT, f"engaged ({kill_switch.reason}). Once the cause is fixed, release it "
                                           "by hand: python -m trader.risk.killswitch release")
              if kill_switch.engaged else Health("kill switch", OK, "off")]
    return checks + (records_checks(store) if store is not None else [])


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


def open_us_store(settings) -> PaperStore | None:
    """The US paper account's records, if a daily run has made them."""
    path = ROOT / settings.paper_us_database
    return PaperStore(path, settings.paper_us_starting_capital) if path.exists() else None


def us_checks(store: PaperStore | None, now: datetime, backup_dir: Path | None) -> list[Health]:
    """The US paper account's run, records and backups, on the NYSE calendar (names start with US)."""
    if store is None:
        return []
    checks = [*run_checks(store, load_calendars()["NYSE"], now), *records_checks(store),
              *backup_check(store, backup_dir, now.date()), *integrity_check(store, None, backup_dir)]
    return [replace(check, name=f"US {check.name}") for check in checks]


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


def store_backups(store: PaperStore, backup_dir: Path | None) -> list[Path]:
    """One store's daily backups, oldest first: <its name>-<day>.db (paper-us-... is not paper's)."""
    if backup_dir is None:
        return []
    pattern = re.compile(rf"{re.escape(store.path.stem)}-\d{{4}}-\d{{2}}-\d{{2}}")
    return sorted(p for p in Path(backup_dir).glob(f"{store.path.stem}-*.db") if pattern.fullmatch(p.stem))


def integrity_check(store: PaperStore | None, live_store: LiveStore | None, backup_dir: Path | None) -> list[Health]:
    """SQLite's own check that the records and the newest backup are intact. The folder they live in is synced
    by OneDrive; damage caught the same day can be undone from a backup taken before it."""
    if store is None:
        return []
    found = {"paper records": _quick_check(store.conn)}
    if live_store is not None:
        found["live records"] = _quick_check(live_store.conn)
    copies = store_backups(store, backup_dir)
    if copies:
        found[f"backup {copies[-1].name}"] = _quick_check_file(copies[-1])
    damaged = [f"{name} ({result})" for name, result in found.items() if result != "ok"]
    if damaged:
        return [Health("integrity", ALERT, "damaged: " + "; ".join(damaged) + ". Stop the daily run and restore "
                       "an intact backup (docs/runbook.md, Backups and restoring)")]
    return [Health("integrity", OK, ", ".join(found) + " intact")]


NEWS_STALE = timedelta(hours=2)  # collection runs every 15 minutes; missed hours are fetched whole later
NEWS_PAUSE = (time(0, 0), time(7, 0))  # IST: no collection overnight, so these hours don't count


def collection_time(since: datetime, until: datetime) -> timedelta:
    """The time between two moments, leaving out the nightly pause in news collection."""
    elapsed, day = until - since, since.astimezone(IST).date()
    while day <= until.astimezone(IST).date():
        pause = [datetime.combine(day, moment, IST) for moment in NEWS_PAUSE]
        overlap = min(until, pause[1]) - max(since, pause[0])
        if overlap > timedelta(0):
            elapsed -= overlap
        day += timedelta(days=1)
    return elapsed


def news_check(settings, now: datetime) -> list[Health]:
    """Phase 9: is the news history still being collected? (Research only: never an alert.)"""
    path = ROOT / settings.news_database
    if not settings.news_enabled or not path.exists():
        return []
    conn = sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True)
    try:
        last = conn.execute("SELECT MAX(at) FROM fetches WHERE error = ''").fetchone()[0]
        first = conn.execute("SELECT MIN(at) FROM fetches").fetchone()[0]
        count = conn.execute("SELECT COUNT(*) FROM announcements").fetchone()[0]
        recent_gaps = conn.execute("SELECT COUNT(*) FROM fetches WHERE gap_to >= ?",
                                   ((now - timedelta(days=7)).isoformat(),)).fetchone()[0]
        try:  # whole days fetched from NSE's API (the catch-up after a sleeping laptop)
            whole = {r[0] for r in conn.execute("SELECT DISTINCT day FROM coverage WHERE complete = 1")}
        except sqlite3.OperationalError:  # a history from before the catch-up existed
            whole = None
    finally:
        conn.close()
    if last is None or collection_time(datetime.fromisoformat(last), now) > NEWS_STALE:
        return [Health("news", WARN, f"no successful fetch since {_when(last) if last else 'it began'}: check "
                       "logs/news.log (NSE may be turning the requests away)")]
    today = now.astimezone(IST).date()
    if whole is not None and first is not None:
        # each day is fetched whole after it ends; one still missing two days on means NSE's API is refusing
        start = max(datetime.fromisoformat(first).astimezone(IST).date(), today - timedelta(days=7))
        behind = [start + timedelta(days=k) for k in range((today - start).days - 1)
                  if (start + timedelta(days=k)).isoformat() not in whole]
        if behind:
            return [Health("news", WARN, f"{len(behind)} day(s) not yet fetched whole from NSE's API "
                           f"({', '.join(str(d) for d in behind)}): check logs/news.log")]
    return [Health("news", OK, f"{count} announcements, last fetched {_when(last)}; {recent_gaps} gap(s) in 7 days, "
                   "every finished day fetched whole")]


FORWARD2_LEDGER = Path("state") / "forward2.db"
FORWARD2_STALE = timedelta(days=3)  # it updates every evening; three days without a good update means it has stopped


def forward2_check(now: datetime) -> list[Health]:
    """Forward test 2 (N2 in paper mode, research only): is its evening update still running? Never an alert."""
    path = ROOT / FORWARD2_LEDGER
    if not path.exists():
        return []
    conn = sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True)
    try:
        last_ok = conn.execute("SELECT MAX(at) FROM runs WHERE status = 'ok'").fetchone()[0]
        closed = conn.execute("SELECT COUNT(*) FROM trades WHERE outcome != 'not bought'").fetchone()[0]
    finally:
        conn.close()
    if last_ok is None or now - datetime.fromisoformat(last_ok) > FORWARD2_STALE:
        return [Health("forward test 2", WARN, f"no good update since {_when(last_ok) if last_ok else 'it began'}: "
                       "check logs/forward2.log")]
    return [Health("forward test 2", OK, f"updated {_when(last_ok)}; {closed} closed paper trade(s)")]


FORWARD3_LEDGER = Path("state") / "forward3.db"


def forward3_check(now: datetime) -> list[Health]:
    """Forward test 3 (round 10's E2 in paper mode, research only): is its evening update still running? Never an alert."""
    path = ROOT / FORWARD3_LEDGER
    if not path.exists():
        return []
    conn = sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True)
    try:
        last_ok = conn.execute("SELECT MAX(at) FROM runs WHERE status = 'ok'").fetchone()[0]
        closed = conn.execute("SELECT COUNT(*) FROM trades").fetchone()[0]
        signals = conn.execute("SELECT COUNT(*) FROM signals WHERE late = 0").fetchone()[0]
    finally:
        conn.close()
    if last_ok is None or now - datetime.fromisoformat(last_ok) > FORWARD2_STALE:
        return [Health("forward test 3", WARN, f"no good update since {_when(last_ok) if last_ok else 'it began'}: "
                       "check logs/forward3.log")]
    return [Health("forward test 3", OK, f"updated {_when(last_ok)}; {signals} signal(s), {closed} closed paper trade(s)")]


TRIAL_LEDGER = Path("state") / "trial1.db"


def trial_check(now: datetime) -> list[Health]:
    """Paper trial 1 (E2 x3 + V2 x2 in one paper account, research only): still updating? Its brakes, if any. Never an alert."""
    path = ROOT / TRIAL_LEDGER
    if not path.exists():
        return []
    conn = sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True)
    try:
        last_ok = conn.execute("SELECT MAX(at) FROM runs WHERE status = 'ok'").fetchone()[0]
        closed, r = conn.execute("SELECT COUNT(*), COALESCE(SUM(r), 0) FROM trades").fetchone()
        brakes = [f"{scope} {kind}" for scope, kind in conn.execute("SELECT scope, kind FROM brakes ORDER BY id")]
    finally:
        conn.close()
    if last_ok is None or now - datetime.fromisoformat(last_ok) > FORWARD2_STALE:
        return [Health("paper trial 1", WARN, f"no good update since {_when(last_ok) if last_ok else 'it began'}: "
                       "check logs/trial1.log")]
    return [Health("paper trial 1", OK, f"updated {_when(last_ok)}; {closed} closed paper trade(s), {r:+.2f}R"
                   + (f"; brakes: {', '.join(brakes)}" if brakes else ""))]


def backup_check(store: PaperStore | None, backup_dir: Path | None, today: date) -> list[Health]:
    """The daily run copies the records to <database folder>/backups after every run that didn't fail."""
    if store is None or backup_dir is None:
        return []
    copies = store_backups(store, backup_dir)
    if not copies:
        return [Health("backup", WARN, f"no backup in {backup_dir} yet; the next daily run makes one")]
    latest = date.fromisoformat(copies[-1].stem[-10:])
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
                  backup_dir: Path | None = None, live_store: LiveStore | None = None,
                  us_store: PaperStore | None = None) -> list[Health]:
    """Every check, worst first. `store` is None before the first daily run."""
    checks = [*run_checks(store, calendar, now), *safety_checks(store, kill_switch), unattended_record(store, now),
              dry_run_check(store, now.date()), *backup_check(store, backup_dir, now.date()),
              *integrity_check(store, live_store, backup_dir), *news_check(settings, now), *forward2_check(now), *forward3_check(now), *trial_check(now),
              *us_checks(us_store, now, backup_dir),
              *strategy_checks(registry, now.date(), max_age_days, evidence_dir), calendar_checks(calendar, now.date()),
              data_checks(settings, now, session_file), *live_checks(settings, live_store, now, session_file)]
    order = (ALERT, WARN, INFO, OK)
    return sorted(checks, key=lambda c: order.index(c.level))


def started_late(now: datetime) -> bool:
    """Is the 21:00 check only starting now, because the PC was asleep or off at 21:00?"""
    local = now.astimezone(IST)
    scheduled = datetime.combine(local.date(), HEALTH_AT, IST)
    if scheduled > local:
        scheduled -= timedelta(days=1)  # e.g. a laptop that slept from the evening until the morning
    return local - scheduled > LATE_AFTER


def main(argv: list[str] | None = None, sleep=_sleep) -> None:
    parser = argparse.ArgumentParser(description="Health checks for unattended operation.")
    parser.add_argument("--notify", action="store_true", help="send a Telegram alert when something needs attention")
    parser.add_argument("--scheduled", action="store_true",
                        help="the 21:00 task: when it starts late, it first gives a catch-up daily run time to finish")
    args = parser.parse_args(argv)
    make_console_utf8()
    settings = load_settings()
    configure_logging(secrets=settings.secret_values() + session_secrets(), filename="health.log")
    if args.scheduled and started_late(datetime.now(IST)):  # the daily run is catching up at the same time
        log.info("The 21:00 check is starting late (the PC was asleep or off): waiting %d minutes for the daily "
                 "run's own catch-up first", CATCH_UP_WAIT.total_seconds() // 60)
        sleep(CATCH_UP_WAIT.total_seconds())
    database = ROOT / settings.paper_database
    store = PaperStore(database, settings.paper_starting_capital) if database.exists() else None
    now = datetime.now(IST)
    checks = health_checks(store, load_calendars()["NSE"], StrategyRegistry.load(), KillSwitch(), settings, now,
                           load_gate_config().max_evidence_age_days, backup_dir=database.parent / "backups",
                           live_store=open_live_store(settings), us_store=open_us_store(settings))
    print(f"Health at {now:%Y-%m-%d %H:%M} IST")
    width = max(len(c.name) for c in checks)
    for check in checks:
        print(f"  [{check.level.upper():5s}] {check.name:<{width}}  {check.detail}")
    alerts, warnings = [c for c in checks if c.level == ALERT], [c for c in checks if c.level == WARN]
    log.info("%d alert(s), %d warning(s)%s", len(alerts), len(warnings),  # a trace of every run, even a clean one
             "".join(f"; {c.level} {c.name}: {c.detail}" for c in alerts + warnings))
    if alerts and args.notify:
        notifier_from_settings(settings).send(templates.risk_alert(
            title="Health check", detail="; ".join(f"{c.name}: {c.detail}" for c in alerts)))
    raise SystemExit(1 if alerts else 0)


if __name__ == "__main__":
    main()
