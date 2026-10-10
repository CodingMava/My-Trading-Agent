from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from trader.config import load_settings
from trader.execution.store import PaperStore
from trader.gate import Evidence, save_evidence
from trader.markets.calendar import load_calendars
from trader.ops.health import ALERT, INFO, OK, WARN, calendar_checks, data_checks, health_checks, run_checks, \
    safety_checks, strategy_checks, unattended_record
from trader.registry import StrategyRecord, StrategyRegistry
from trader.risk.killswitch import KillSwitch

IST = ZoneInfo("Asia/Kolkata")
NSE = load_calendars()["NSE"]
EVENING = datetime(2026, 8, 18, 21, 0, tzinfo=IST)  # a Tuesday, after the 18:00 run should have finished


def store_with(tmp_path, sessions=(), runs=()):
    store = PaperStore(tmp_path / "p.db", 1_000_000)
    for session in sessions:
        store.record_session(session, 1_000_000, 1_000_000)
    for status, count, started in runs:
        run_id = store.start_run(started)
        if status != "running":
            store.finish_run(run_id, status, started + timedelta(minutes=2), count, f"{status} detail")
    return store


def levels(checks):
    return {c.name: c.level for c in checks}


def test_a_run_that_never_started_is_reported_the_same_evening(tmp_path):
    assert levels(run_checks(None, NSE, EVENING)) == {"daily run": WARN}  # never set up
    on_time = store_with(tmp_path, [date(2026, 8, 18)], [("ok", 1, EVENING - timedelta(hours=3))])
    assert levels(run_checks(on_time, NSE, EVENING)) == {"daily run": OK, "last run": OK}
    missed = store_with(tmp_path / "b", [date(2026, 8, 17)], [("ok", 1, EVENING - timedelta(days=1, hours=3))])
    checks = run_checks(missed, NSE, EVENING)
    assert levels(checks)["daily run"] == ALERT and "2026-08-18 should be done" in checks[0].detail
    assert levels(run_checks(missed, NSE, EVENING - timedelta(hours=4)))["daily run"] == OK  # before the deadline


def test_failed_halted_and_dead_runs_are_alerts(tmp_path):
    failed = store_with(tmp_path, [date(2026, 8, 17)], [("failed", 0, EVENING - timedelta(hours=3))])
    assert levels(run_checks(failed, NSE, EVENING)) == {"daily run": ALERT, "last run": ALERT}
    assert "failed detail" in run_checks(failed, NSE, EVENING)[1].detail
    running = store_with(tmp_path / "b", [date(2026, 8, 17)], [("running", 0, EVENING - timedelta(minutes=20))])
    assert levels(run_checks(running, NSE, EVENING)) == {"daily run": INFO}  # still going: no alarm yet
    assert levels(run_checks(running, NSE, EVENING + timedelta(hours=3))) == {"daily run": ALERT, "last run": ALERT}


def test_kill_switch_reconciliation_and_undelivered_messages(tmp_path):
    store, switch = store_with(tmp_path), KillSwitch(tmp_path / "KILL")
    assert {c.level for c in safety_checks(store, switch)} == {OK}
    switch.engage("drawdown 10.4% breached the 10% limit")
    store.queue_message(date(2026, 8, 18), "hello")
    store.set_cash(5.0)
    assert levels(safety_checks(store, switch)) == {"kill switch": ALERT, "reconciliation": ALERT, "notifications": ALERT}


def test_the_unattended_record_counts_sessions_since_the_last_failure(tmp_path):
    start = EVENING - timedelta(days=10)
    store = store_with(tmp_path, runs=[("ok", 10, start), ("failed", 0, start + timedelta(days=1)),
                                       ("ok", 5, start + timedelta(days=2)), ("halted", 2, start + timedelta(days=3)),
                                       ("ok", 1, start + timedelta(days=4))])
    record = unattended_record(store, EVENING)
    assert record.level == INFO and record.detail.startswith("8 of 60 clean sessions")
    store.add_decision(date(2026, 8, 18), "T1", "AAA.NS", "NO_TRADE", "duplicate order prevented")
    assert unattended_record(store, EVENING).level == WARN


def test_evidence_about_to_expire_and_calendar_and_kite_warnings(tmp_path):
    registry = StrategyRegistry([StrategyRecord("T1", "Test", "PAPER"), StrategyRecord("T2", "Old", "REJECTED")])
    save_evidence(Evidence("T1", "research", "PAPER", "2025-09-20", "test"), tmp_path)
    checks = strategy_checks(registry, date(2026, 8, 25), 365, tmp_path)
    assert checks[0].detail == "T1 PAPER" and any(c.level == WARN and "2026-09-20" in c.detail for c in checks)
    assert strategy_checks(StrategyRegistry([]), date(2026, 8, 25), 365, tmp_path)[0].detail.startswith("NO TRADE")
    assert calendar_checks(NSE, date(2026, 8, 25)).level == OK
    assert calendar_checks(NSE, date(2026, 12, 5)).level == WARN  # NSE's 2027 holidays aren't in yet
    assert calendar_checks(NSE, date(2027, 1, 4)).level == ALERT
    kite = load_settings(env={"KITE_API_KEY": "k", "KITE_API_SECRET": "s"},
                         settings_file=_settings(tmp_path, 'provider = "kite"'))
    assert data_checks(kite, EVENING, tmp_path / "no_session.json").level == WARN


def test_all_checks_come_worst_first(tmp_path):
    switch = KillSwitch(tmp_path / "KILL")
    switch.engage("test")
    checks = health_checks(None, NSE, StrategyRegistry([]), switch, load_settings(env={}), EVENING)
    assert checks[0].level == ALERT and checks[0].name == "kill switch"
    assert [c.level for c in checks] == sorted((c.level for c in checks), key=[ALERT, WARN, INFO, OK].index)


def _settings(tmp_path, data_line):
    path = tmp_path / "settings.toml"
    path.write_text(f"[data]\n{data_line}\n", encoding="utf-8")
    return path
