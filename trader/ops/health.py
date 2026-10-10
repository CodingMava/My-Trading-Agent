"""Health checks for unattended operation: did the daily run happen, did it work, and is it safe?

    python -m trader.ops.health             # every check; exit code 1 when something needs attention
    python -m trader.ops.health --notify    # also send one Telegram alert listing the problems

Schedule it a few hours after the daily run (scripts/register_tasks.ps1 does both). It is what pages you
when the run didn't happen at all, which the run itself can never report.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from trader.config import ROOT, load_settings
from trader.data.kite import SESSION_FILE, load_session, session_secrets
from trader.data.validate import DAILY_SETTLE
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
UNATTENDED_TARGET = 60  # clean sessions in a row that Phase 7 asks for before broker integration
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


def unattended_record(store: PaperStore | None, now: datetime) -> Health:
    """Sessions processed since the last run that failed or died: Phase 7's 60-session requirement."""
    if store is None:
        return Health("unattended record", INFO, f"0 of {UNATTENDED_TARGET} clean sessions before broker integration")
    clean = 0
    for run in store.runs(limit=100_000).itertuples():  # newest first
        if run.status == "failed" or _died(run, now):
            break
        clean += int(run.sessions)
    decisions = store.table("decisions")
    duplicates = int((decisions["detail"] == "duplicate order prevented").sum()) if len(decisions) else 0
    detail = f"{clean} of {UNATTENDED_TARGET} clean sessions in a row before broker integration"
    if duplicates:
        return Health("unattended record", WARN, f"{detail}; {duplicates} duplicate order(s) were prevented: find out why")
    return Health("unattended record", OK if clean >= UNATTENDED_TARGET else INFO, detail)


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
                  backup_dir: Path | None = None) -> list[Health]:
    """Every check, worst first. `store` is None before the first daily run."""
    checks = [*run_checks(store, calendar, now), *safety_checks(store, kill_switch), unattended_record(store, now),
              *backup_check(store, backup_dir, now.date()),
              *strategy_checks(registry, now.date(), max_age_days, evidence_dir), calendar_checks(calendar, now.date()),
              data_checks(settings, now, session_file)]
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
                           load_gate_config().max_evidence_age_days, backup_dir=database.parent / "backups")
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
