from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from dataclasses import replace

from trader.config import load_settings
from trader.core.models import Position
from trader.execution import broker
from trader.execution.oms import LiveStore
from trader.execution.store import PaperStore
from trader.gate import Evidence, save_evidence
from trader.markets.calendar import load_calendars
from trader.ops import health
from trader.ops.health import ALERT, INFO, OK, WARN, backup_check, calendar_checks, data_checks, dry_run_check, \
    health_checks, integrity_check, live_checks, news_check, run_checks, safety_checks, strategy_checks, \
    unattended_record
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


def test_backups_must_exist_and_be_recent(tmp_path):
    store, backups = store_with(tmp_path), tmp_path / "backups"
    assert backup_check(None, backups, EVENING.date()) == []  # nothing to back up before the first run
    assert backup_check(store, backups, EVENING.date())[0].level == WARN
    PaperStore(tmp_path / "p-us.db", 1).backup(backups, date(2026, 8, 18))  # another store's: not this one's
    assert backup_check(store, backups, EVENING.date())[0].level == WARN
    store.backup(backups, date(2026, 8, 17))
    assert backup_check(store, backups, EVENING.date())[0].level == OK
    assert backup_check(store, backups, date(2026, 8, 25))[0].level == WARN  # a week without a backup


def _settings(tmp_path, data_line):
    path = tmp_path / "settings.toml"
    path.write_text(f"[data]\n{data_line}\n", encoding="utf-8")
    return path


def test_dry_run_orders_kite_would_refuse_are_a_warning(tmp_path):
    today = EVENING.date()
    assert dry_run_check(None, today).level == INFO
    store = store_with(tmp_path)
    assert dry_run_check(store, today).level == INFO  # nothing prepared yet
    store.add_dry_run_order(date(2026, 8, 17), "E1", "AAA.NS", "entry", "18:00", "{}")
    assert dry_run_check(store, today).level == OK
    store.add_dry_run_order(date(2026, 8, 18), "S1", "AAA.NS", "stop", "09:20", "{}", "trigger 96.003 isn't on the tick")
    check = dry_run_check(store, today)
    assert check.level == WARN and "AAA.NS stop on 2026-08-18: trigger 96.003" in check.detail
    assert dry_run_check(store, today + timedelta(days=31)).level == OK  # fixed a month ago


def test_the_live_account_is_watched(tmp_path):
    settings, no_login = load_settings(env={}), tmp_path / "session.json"
    assert levels(live_checks(settings, None, EVENING, no_login)) == {"live trading": INFO}  # off
    assert levels(live_checks(replace(settings, live_enabled=True), None, EVENING, no_login)) == {"live login": WARN}
    store = LiveStore(tmp_path / "live.db")
    assert levels(live_checks(settings, store, EVENING, no_login)) == {"live trading": INFO}  # empty: still off
    held = Position("T1", "AAA.NS", 10, 100.0, 95.0, date(2026, 8, 17))
    store.save_position(held)
    checks = live_checks(settings, store, EVENING, no_login)
    assert levels(checks) == {"live stops": ALERT} and "no stop at Kite for AAA.NS" in checks[0].detail
    store.record(EVENING, date(2026, 8, 17), "T1", broker.stop_order(held), "SENT")
    assert levels(live_checks(settings, store, EVENING, no_login)) == {"live trading": OK}
    day = date(2026, 8, 18)
    store.record(EVENING - timedelta(days=2), day, "T1", broker.entry_order("k1", "BBB.NS", 5), "SENT")
    store.record(EVENING, day, "T1", broker.entry_order("k2", "CCC.NS", 5), "UNKNOWN")
    store.record(EVENING, day, "T1", broker.entry_order("k3", "DDD.NS", 5), "REJECTED", "MarginException: no funds")
    checks = live_checks(settings, store, EVENING, no_login)
    assert levels(checks) == {"live unknown orders": ALERT, "live stale orders": WARN, "live refusals": WARN}
    assert "DDD.NS entry: MarginException: no funds" in checks[-1].detail
    everything = health_checks(None, NSE, StrategyRegistry([]), KillSwitch(tmp_path / "KILL"), settings, EVENING,
                               session_file=no_login, live_store=store)
    assert everything[0].name == "live unknown orders"  # worst first



def test_damaged_records_or_backups_are_caught(tmp_path):
    assert integrity_check(None, None, tmp_path) == []  # no records yet
    store, live = store_with(tmp_path, [date(2026, 8, 17)]), LiveStore(tmp_path / "live.db")
    backup = store.backup(tmp_path / "backups", date(2026, 8, 17))
    check = integrity_check(store, live, tmp_path / "backups")[0]
    assert check.level == OK and check.detail == "paper records, live records, backup p-2026-08-17.db intact"
    assert integrity_check(store, None, None)[0].detail == "paper records intact"
    with open(backup, "r+b") as damaged:  # overwrite the file's header
        damaged.write(b"not a database file at all")
    check = integrity_check(store, live, tmp_path / "backups")[0]
    assert check.level == ALERT and "backup p-2026-08-17.db (file is not a database)" in check.detail



def test_news_collection_that_stalls_is_a_warning(tmp_path, monkeypatch):
    from trader.research.news import NewsStore
    monkeypatch.setattr(health, "ROOT", tmp_path)
    settings = replace(load_settings(env={}), news_enabled=True)
    assert news_check(settings, EVENING) == []  # not started
    store = NewsStore(tmp_path / settings.news_database)
    store.record_fetch("announcements", EVENING - timedelta(minutes=20), [], 0, None)
    store.record_fetch("announcements", EVENING - timedelta(minutes=5), [], 0, None, "ConnectionError")
    check = news_check(settings, EVENING)[0]
    assert check.level == OK and check.detail.startswith("0 announcements, last fetched 18 Aug 20:40 IST")
    assert news_check(settings, EVENING + timedelta(hours=3))[0].level == WARN
    assert news_check(replace(settings, news_enabled=False), EVENING) == []
    store.close()



def test_the_us_account_has_its_own_checks(tmp_path):
    from trader.ops.health import us_checks
    assert us_checks(None, EVENING, tmp_path) == []
    store = PaperStore(tmp_path / "paper-us.db", 10_000)
    store.record_session(date(2026, 8, 17), 10_000, 10_000)  # Monday's US session, processed on Tuesday evening IST
    run_id = store.start_run(EVENING - timedelta(hours=3))
    store.finish_run(run_id, "ok", EVENING - timedelta(hours=3), 1)
    checks = {c.name: c.level for c in us_checks(store, EVENING, tmp_path / "backups")}
    assert checks == {"US daily run": OK, "US last run": OK, "US reconciliation": OK, "US notifications": OK,
                      "US backup": WARN, "US integrity": OK}



def test_a_us_session_is_due_from_the_evening_run_after_it_closes(tmp_path):
    nyse = load_calendars()["NYSE"]
    store = store_with(tmp_path, [date(2026, 8, 17)], [("ok", 1, EVENING - timedelta(hours=3))])  # Monday's
    wednesday = EVENING + timedelta(days=1)  # Tuesday's US session closed at 01:30 IST that morning
    assert levels(run_checks(store, nyse, wednesday - timedelta(hours=11)))["daily run"] == OK  # 10:00: not due
    checks = run_checks(store, nyse, wednesday)  # 21:00: the 18:00 run should have processed it
    assert levels(checks)["daily run"] == ALERT and "2026-08-18 should be done" in checks[0].detail
    winter = datetime(2026, 12, 2, 19, 30, tzinfo=IST)  # Tuesday's session closed at 02:30 IST; the run is due by 20:00
    december = store_with(tmp_path / "b", [date(2026, 11, 30)], [("ok", 1, winter - timedelta(days=1))])
    assert levels(run_checks(december, nyse, winter))["daily run"] == OK
    assert levels(run_checks(december, nyse, winter + timedelta(hours=1)))["daily run"] == ALERT
