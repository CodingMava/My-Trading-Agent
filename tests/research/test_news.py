"""The news layer against a fake NSE (no network): collection with visible gaps, rule tags, AI tags that must
match a fixed shape, and no path from the news to any trading code."""
import ast
import logging
import sqlite3
from dataclasses import replace
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
import requests

from trader.config import ROOT, load_settings
from trader.research import news
from trader.research.news import (COMPANIES_URL, FEEDS, GeminiTagger, NewsStore, TagError, collect, gaps,
                                  news_events, parse_feed, rule_event, status_text, tag_with_ai, validate_tags)

IST = ZoneInfo("Asia/Kolkata")
NOW = datetime(2026, 10, 12, 10, 0, tzinfo=IST)


def rss(*items):
    body = "".join(f"<item><title>{t}</title><link>{link}</link><description>{d}</description><pubDate>{p}</pubDate></item>"
                   for t, link, d, p in items)
    return f"<?xml version='1.0'?><rss><channel><title>NSE</title>{body}</channel></rss>".encode()


def announcement(symbol, stamp, subject="has informed the Exchange about Board Meeting to consider Fund raising"):
    return (f"{symbol} Limited", f"https://nsearchives.nseindia.com/corporate/{symbol}_12102026_x.pdf", subject, stamp)


ACTIONS = rss(("Tata Consultancy Services Limited - Ex-Date: 14-Oct-2026 ",
               "https://www.nseindia.com/companies-listing/corporate-filings-actions",
               "SERIES:EQ |PURPOSE:INTERIM DIVIDEND - RS 12 PER SHARE", "12-Oct-2026 06:10:24"))
COMPANIES = b"SYMBOL,NAME OF COMPANY, SERIES\nTCS,Tata Consultancy Services Limited,EQ\nM&M,Mahindra & Mahindra Limited,EQ\n"


class FakeNSE:
    def __init__(self, announcements, actions=ACTIONS, companies=COMPANIES, failing=()):
        self.pages = {FEEDS["announcements"]: announcements, FEEDS["corporate actions"]: actions, COMPANIES_URL: companies}
        self.failing, self.calls = set(failing), []

    def get(self, url, headers=None, timeout=None):
        self.calls.append((url, headers))
        if url in self.failing:
            raise requests.ConnectionError("turned away")
        return type("Response", (), {"content": self.pages[url], "raise_for_status": lambda response: None})()


def test_both_feeds_are_parsed():
    items = parse_feed("announcements", rss(announcement("TCS", "12-Oct-2026 09:15:00"),
                                            ("No time", "x", "y", "not a date")))
    assert len(items) == 1 and (items[0].symbol, items[0].company) == ("TCS", "TCS Limited")
    assert items[0].published == datetime(2026, 10, 12, 9, 15, tzinfo=IST)
    action = parse_feed("corporate actions", ACTIONS)[0]
    assert action.company == "Tata Consultancy Services Limited" and action.symbol is None
    assert action.subject.endswith("|EX-DATE:14-Oct-2026")


def test_collecting_stores_tags_and_records_every_gap(tmp_path):
    store = NewsStore(tmp_path / "news.db")
    first = FakeNSE(rss(announcement("TCS", "12-Oct-2026 09:15:00"), announcement("INFY", "12-Oct-2026 09:30:00")))
    assert collect(store, first, NOW) == []
    stored = store.table("announcements")
    assert len(stored) == 3 and set(stored["symbol"]) == {"TCS", "INFY"}  # the dividend's TCS comes from NSE's list
    assert dict(zip(store.table("tags")["announcement"], store.table("tags")["event"])) == {
        1: "fund raising", 2: "fund raising", 3: "dividend"}
    assert first.calls[0][1]["User-Agent"].startswith("Mozilla/5.0") and "feed reader" in first.calls[0][1]["User-Agent"]
    overlapping = FakeNSE(rss(announcement("INFY", "12-Oct-2026 09:30:00"), announcement("LT", "12-Oct-2026 09:45:00")))
    collect(store, overlapping, NOW.replace(minute=15))
    assert len(store.table("announcements")) == 4 and gaps(store, NOW.replace(hour=0)).empty  # nothing missed
    assert COMPANIES_URL not in [url for url, _ in overlapping.calls]  # the company list is fetched once a day
    after_a_gap = FakeNSE(rss(announcement("ITC", "12-Oct-2026 11:00:00")))
    collect(store, after_a_gap, NOW.replace(hour=11, minute=15))
    assert gaps(store, NOW.replace(hour=0)).values.tolist() == [["2026-10-12T09:45:00+05:30", "2026-10-12T11:00:00+05:30"]]
    assert "Gaps in the last 7 days: 1" in status_text(store, NOW.replace(hour=12))
    events = news_events(store, date(2026, 10, 12), date(2026, 10, 13))
    assert list(events["symbol"]) == ["TCS", "TCS", "INFY", "LT", "ITC"] and set(events["date"]) == {"2026-10-12"}


def test_a_failed_fetch_is_recorded_and_the_rest_carries_on(tmp_path):
    store = NewsStore(tmp_path / "news.db")
    nse = FakeNSE(rss(), failing={FEEDS["announcements"], COMPANIES_URL})
    assert collect(store, nse, NOW) == ["announcements: ConnectionError"]
    fetches = store.table("fetches")
    assert list(fetches["error"]) == ["ConnectionError", ""] and len(store.table("announcements")) == 1
    assert store.table("announcements")["symbol"].isna().all()  # no company list yet to name the dividend's stock
    assert "Last good fetch: 2026-10-12 10:00" in status_text(store, NOW)


def test_rule_tags():
    assert rule_event("Outcome of Board Meeting - Unaudited Financial Results for Q2") == "results"
    assert rule_event("PURPOSE:FACE VALUE SPLIT (SUB-DIVISION)") == "corporate action"
    assert rule_event("Receipt of order from NHAI worth Rs 500 crore") == "order win"
    assert rule_event("Resignation of Chief Financial Officer (CFO)") == "management"
    assert rule_event("Board Meeting to be held on 20-Oct-2026") == "board meeting"
    assert rule_event("Closure of Trading Window") == "routine"
    assert rule_event("Certificate under SEBI (Depositories and Participants) Regulations, 2018") == "routine"
    assert rule_event("the Net Asset Value (per unit) of Mirae Asset Mutual Fund") == "routine"
    assert rule_event("Change in Management") == "management"
    assert rule_event("Pendency of any litigation(s) or dispute(s)") == "regulatory"
    assert rule_event("Clarification sought on news item") == "other"


def test_ai_answers_must_have_exactly_the_shape_of_a_tag():
    assert validate_tags({"event": "results", "sentiment": 1, "materiality": "high"}) == news.Tags("results", 1, "high")
    for wrong in ({"event": "results", "sentiment": 1, "materiality": "high", "price": 2450.0},  # never a price
                  {"event": "buy now", "sentiment": 1, "materiality": "high"}, {"event": "results", "sentiment": True,
                  "materiality": "high"}, {"event": "results", "sentiment": 2, "materiality": "high"},
                  {"event": "results", "sentiment": 0, "materiality": "huge"}, ["results", 1, "high"]):
        with pytest.raises(TagError):
            validate_tags(wrong)


class FakeModel:
    name = "fake:model"

    def __init__(self, answers):
        self.answers, self.asked = list(answers), []

    def ask(self, company, subject):
        self.asked.append(company)
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer


def test_ai_tags_are_stored_once_and_bad_answers_are_refused(tmp_path):
    store = NewsStore(tmp_path / "news.db")
    collect(store, FakeNSE(rss(announcement("TCS", "12-Oct-2026 09:15:00"), announcement("INFY", "12-Oct-2026 09:30:00"))), NOW)
    model = FakeModel([{"event": "fund raising", "sentiment": 0, "materiality": "medium"},
                       {"event": "fund raising", "sentiment": 0, "materiality": "medium", "size": 100},
                       requests.Timeout("slow")])
    assert tag_with_ai(store, model, NOW) == (1, 2)
    model.answers = [{"event": "dividend", "sentiment": 1, "materiality": "low"}] * 2
    assert tag_with_ai(store, model, NOW) == (2, 0)  # the refused two are asked again; the tagged one isn't
    ai = store.table("tags").query("tagger == 'fake:model'")
    by_time = news_events(store, date(2026, 10, 12), date(2026, 10, 13), "fake:model")  # the 06:10 dividend first
    assert len(ai) == 3 and list(by_time["event"]) == ["dividend", "fund raising", "dividend"]


def test_the_gemini_request_keeps_the_key_out_of_the_url():
    class FakeGoogle:
        def post(self, url, json=None, timeout=None, headers=None):
            self.call = (url, json, headers)
            text = '{"event": "results", "sentiment": 1, "materiality": "high"}'
            return type("Response", (), {"raise_for_status": lambda r: None,
                                         "json": lambda r: {"candidates": [{"content": {"parts": [{"text": text}]}}]}})()
    google = FakeGoogle()
    tagger = GeminiTagger("SECRET-KEY", "gemini-2.5-flash", http=google)
    assert tagger.ask("TCS Limited", "Financial results") == {"event": "results", "sentiment": 1, "materiality": "high"}
    url, body, headers = google.call
    assert "SECRET-KEY" not in url and headers == {"x-goog-api-key": "SECRET-KEY"} and tagger.name == "gemini:gemini-2.5-flash"
    assert body["generationConfig"]["responseSchema"]["properties"]["event"]["enum"][-1] == "other"


def test_the_news_history_is_append_only(tmp_path):
    store = NewsStore(tmp_path / "news.db")
    collect(store, FakeNSE(rss(announcement("TCS", "12-Oct-2026 09:15:00"))), NOW)
    for statement in ("UPDATE announcements SET subject = 'x'", "DELETE FROM announcements", "DELETE FROM fetches",
                      "UPDATE tags SET event = 'x'", "DELETE FROM tags"):
        with pytest.raises(sqlite3.DatabaseError, match="append-only"):
            store.conn.execute(statement)
    with pytest.raises(ValueError):
        store.table("sqlite_master")
    store.close()


def test_no_trading_code_imports_the_news_layer():
    """The audit's rule for this phase: research output can't reach the risk gate as a size or a price."""
    trading = [p for folder in ("risk", "portfolio", "execution", "strategies", "notify", "ops")
               for p in (ROOT / "trader" / folder).glob("*.py")] + [ROOT / "trader" / "gate.py", ROOT / "trader" / "registry.py"]
    for path in trading:
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            names = ([a.name for a in node.names] if isinstance(node, ast.Import) else
                     [node.module or ""] + [f"{node.module}.{a.name}" for a in node.names] if isinstance(node, ast.ImportFrom)
                     else [])
            assert not any(name.startswith("trader.research.news") for name in names), path.name


def test_the_command(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(news, "ROOT", tmp_path)
    monkeypatch.setattr(news, "configure_logging", lambda **kwargs: None)  # not into the real logs/
    off = replace(load_settings(env={}), news_enabled=False)
    monkeypatch.setattr(news, "load_settings", lambda: off)
    news.main(["collect"])
    assert not (tmp_path / "state" / "news.db").exists()  # off: nothing fetched, nothing made
    monkeypatch.setattr(news, "load_settings", lambda: replace(off, news_enabled=True))
    monkeypatch.setattr(news, "collect", lambda store, now: ["announcements: ConnectionError"])
    with pytest.raises(SystemExit) as failed:
        news.main(["collect"])
    assert failed.value.code == 1
    news.main(["status"])
    assert "0 announcements" in capsys.readouterr().out
    with pytest.raises(SystemExit, match="AI tagging is off"):
        news.main(["tag-ai"])
    assert Path(news.__file__).name == "news.py"



def test_each_collection_leaves_a_line_in_the_log(tmp_path, monkeypatch, caplog):
    monkeypatch.setattr(news, "ROOT", tmp_path)
    monkeypatch.setattr(news, "configure_logging", lambda **kwargs: None)  # not into the real logs/
    monkeypatch.setattr(news, "load_settings", lambda: replace(load_settings(env={}), news_enabled=True))

    def fake_collect(store, now):
        store.record_fetch("announcements", now, [], 0, None)
        store.record_fetch("corporate actions", now, [], 0, None, "HTTPError")
        return []

    monkeypatch.setattr(news, "collect", fake_collect)
    caplog.set_level(logging.INFO, logger=news.__name__)
    with pytest.raises(SystemExit) as done:
        news.main(["collect"])
    assert done.value.code == 0
    assert ("Collected: announcements 0 item(s), 0 new; corporate actions 0 item(s), 0 new, failed (HTTPError)"
            in caplog.text)
