"""The unattended daily run: every run recorded, failures alerted, missing data halts, heartbeat on success."""
import logging
from datetime import date

import pandas as pd
import requests

from tests.execution.test_paper_trader import CLOCK, IST, SIGNAL_DAY, UNIVERSE, FakeNotifier, make_trader
from trader.execution.eod import daily, ping_heartbeat
from trader.execution.store import PaperStore

URL = "https://hc.example/ping/SECRETUUID"


class FakeHTTP:
    def __init__(self, status=200):
        self.status, self.urls = status, []

    def get(self, url, timeout):
        self.urls.append(url)
        return type("Response", (), {"status_code": self.status})()


def run_daily(trader, http=None, **kwargs):
    return daily(trader.store, trader.notifier, lambda: trader, heartbeat=URL, http=http or FakeHTTP(),
                 clock=lambda: CLOCK, **kwargs)


def test_a_clean_run_is_recorded_and_pings_the_heartbeat(tmp_path):
    trader, http = make_trader(tmp_path), FakeHTTP()
    assert run_daily(trader, http, until=date(2026, 8, 18), start=SIGNAL_DAY) == 0
    run = trader.store.runs().iloc[0]
    assert run["status"] == "ok" and run["sessions"] == 7 and http.urls == [URL]


def test_a_failed_setup_is_recorded_and_alerted_with_secrets_masked(tmp_path):
    store, notifier, http = PaperStore(tmp_path / "p.db", 1_000_000), FakeNotifier(), FakeHTTP()

    def build():
        raise RuntimeError("Kite rejected the access token SECRET123")

    assert daily(store, notifier, build, heartbeat=URL, secrets=["SECRET123"], http=http, clock=lambda: CLOCK) == 1
    run = store.runs().iloc[0]
    assert run["status"] == "failed" and "SECRET123" not in run["detail"] and "***" in run["detail"]
    assert notifier.sent[0].startswith("<b>[PAPER] RISK ALERT: Daily run failed</b>")
    assert "SECRET123" not in notifier.sent[0] and http.urls == []  # no heartbeat after a failure


def test_a_failure_mid_run_keeps_every_finished_session_and_is_recorded(tmp_path, monkeypatch):
    trader, http = make_trader(tmp_path), FakeHTTP()
    original = trader.store.record_session

    def crash_on_13th(session, equity, cash):
        if session == date(2026, 8, 13):
            raise OSError("disk full")
        original(session, equity, cash)

    monkeypatch.setattr(trader.store, "record_session", crash_on_13th)
    assert run_daily(trader, http, until=date(2026, 8, 18), start=SIGNAL_DAY) == 1
    assert trader.store.last_session() == date(2026, 8, 12) and trader.store.runs().iloc[0]["status"] == "failed"
    assert any("Daily run failed" in text for text in trader.notifier.sent) and http.urls == []


def test_missing_market_data_halts_the_run_and_the_next_run_catches_up(tmp_path):
    cut = pd.Timestamp("2026-08-14", tz=IST)
    trader, http = make_trader(tmp_path, frames={s: f[f.index < cut] for s, f in UNIVERSE.items()}), FakeHTTP()
    assert run_daily(trader, http, until=date(2026, 8, 18), start=SIGNAL_DAY) == 2  # data ends on the 13th
    assert trader.store.last_session() == date(2026, 8, 13) and trader.store.runs().iloc[0]["status"] == "halted"
    assert any("RISK ALERT: Market data missing" in text and "2026-08-14" in text for text in trader.notifier.sent)
    assert http.urls == []
    trader.provider.frames = UNIVERSE  # the data arrives
    assert run_daily(trader, http, until=date(2026, 8, 18)) == 0
    uninterrupted = make_trader(tmp_path, db="single.db")
    uninterrupted.run(until=date(2026, 8, 18), start=SIGNAL_DAY)
    pd.testing.assert_frame_equal(trader.store.trades().drop(columns="id"),
                                  uninterrupted.store.trades().drop(columns="id"))


def test_heartbeat_failures_never_raise_or_log_the_url(caplog):
    class Down:
        def get(self, url, timeout):
            raise requests.ConnectionError(f"cannot reach {url}")

    with caplog.at_level(logging.WARNING):
        assert ping_heartbeat(URL, Down()) is False
        assert ping_heartbeat(URL, FakeHTTP(status=404)) is False
    assert "SECRETUUID" not in caplog.text and "ConnectionError" in caplog.text and "HTTP 404" in caplog.text


def test_every_run_that_did_not_fail_leaves_a_dated_backup(tmp_path):
    trader = make_trader(tmp_path)
    assert run_daily(trader, until=date(2026, 8, 18), start=SIGNAL_DAY, backup_dir=tmp_path / "backups") == 0
    assert [p.name for p in (tmp_path / "backups").iterdir()] == [f"paper-{CLOCK.date()}.db"]
    failing = PaperStore(tmp_path / "f.db", 1_000_000)

    def build():
        raise RuntimeError("broken config")

    daily(failing, FakeNotifier(), build, clock=lambda: CLOCK, backup_dir=tmp_path / "failed")
    assert not (tmp_path / "failed").exists()


def test_paper_evidence_carries_the_systems_record_and_the_review(tmp_path):
    from trader.execution.report import paper_evidence
    from trader.gate import Evidence, save_evidence

    trader = make_trader(tmp_path)
    run_daily(trader, until=date(2026, 8, 18), start=SIGNAL_DAY)
    save_evidence(Evidence("T1", "research", "PAPER", "2026-08-01", "test",
                           stats={"holdout_mean_net": 0.003, "holdout_sd_net": 0.02, "holdout_trades": 400,
                                  "holdout_win_rate": 0.6}), tmp_path / "evidence")
    evidence = paper_evidence(trader.store, "T1", date(2026, 8, 20), evidence_dir=tmp_path / "evidence",
                              reviewed_trades=25, now=CLOCK)
    stats = evidence.stats
    assert (stats["clean_sessions"], stats["duplicate_orders"], stats["reconciliation_problems"]) == (7, 0, 0)
    failed = {c["number"] for c in evidence.checks if not c["passed"]}
    assert {1, 2, 6} <= failed and 7 not in failed and 8 not in failed  # 25 reviewed >= 20
    assert evidence.decision in ("PAPER", "RESEARCH")



def test_the_daily_run_does_india_then_the_us_and_pings_only_when_both_were_clean(tmp_path, monkeypatch):
    from dataclasses import replace

    import pytest

    from trader.config import Secret, load_settings
    from trader.execution import eod
    settings = replace(load_settings(env={}), heartbeat_url=Secret("https://hc.example/ping"))
    calls, pings, results = [], [], [0, 0]

    def fake_daily(store, notifier, build, until, start, heartbeat, secrets, backup_dir, label):
        trader = build()
        calls.append((store.path.name, trader.market, trader.calendar.name, trader.currency,
                      type(trader.provider).__name__, trader.market_check, until, start, heartbeat, label,
                      trader.risk.account, trader.risk.limits.min_notional))
        return results[len(calls) - 1]
    monkeypatch.setattr(eod, "ROOT", tmp_path)
    monkeypatch.setattr(eod, "load_settings", lambda: settings)
    monkeypatch.setattr(eod, "configure_logging", lambda **kwargs: None)
    monkeypatch.setattr(eod, "notifier_from_settings", lambda s: FakeNotifier())
    monkeypatch.setattr(eod, "daily", fake_daily)
    monkeypatch.setattr(eod, "ping_heartbeat", lambda url: pings.append(url))
    with pytest.raises(SystemExit) as done:
        eod.main(["--start", "2026-10-01"])
    assert done.value.code == 0 and pings == ["https://hc.example/ping"]
    assert calls == [("paper.db", "NSE", "NSE", "₹", "YahooProvider", ("NIFTYBEES.NS",), None, date(2026, 10, 1), "",
                      "", "", 25_000),
                     ("paper-us.db", "US", "NYSE", "$", "YahooProvider", ("SPY",), None, None, "", "US", "US", 250)]
    calls.clear()
    results[:] = [0, 2]  # the US run halted
    with pytest.raises(SystemExit) as done:
        eod.main([])
    assert done.value.code == 2 and len(pings) == 1  # no heartbeat unless every market's run was clean



def test_the_us_accounts_alerts_say_so(tmp_path):
    store, notifier = PaperStore(tmp_path / "paper-us.db", 10_000), FakeNotifier()

    def build():
        raise RuntimeError("Yahoo is down")

    assert daily(store, notifier, build, clock=lambda: CLOCK, label="US") == 1
    assert notifier.sent[0].startswith("<b>[PAPER] RISK ALERT: US daily run failed</b>")
