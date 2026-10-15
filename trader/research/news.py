"""The news layer (Phase 9): NSE's corporate announcements, collected into a stored history and turned into
structured tags, for research only. Nothing here can reach an order, a size or a price: no trading code
imports this module (a test checks), and a tag is only an event name, a sentiment of -1, 0 or 1, and a
materiality.

    python -m trader.research.news collect     # fetch NSE's feeds; scheduled every 15 minutes
    python -m trader.research.news status      # what was collected, and every gap in it
    python -m trader.research.news backfill --from 2026-10-01 --to 2026-10-14   # whole days from NSE's API
    python -m trader.research.news tag-ai      # optional: AI tags for untagged announcements ([ai] in settings)

NSE's announcement feed keeps only its latest items, so it is read every 15 minutes, as a feed reader
would. A gap can't hide: when the feed's oldest item is newer than the newest one stored, items in
between may be missing, and the gap is recorded, so research knows which hours are complete.

A laptop sleeps, so every collection also catches up from NSE's announcement API, which serves any past day
whole: each recent day not yet seen whole (and today, when the feed left a gap) is fetched and recorded in
`coverage`. The API's items are rebuilt exactly as the feed writes them, so an announcement seen in both is
stored once. Every announcement is tagged by fixed rules when it's stored (what kind of event it is). AI tags
(event, sentiment, materiality) are optional, must match a fixed shape exactly, and are kept apart by tagger.

The audit's bar for this phase: the tags must demonstrably improve a strategy, judged by a pre-registered
research round on the collected history; otherwise the phase is cut.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import logging
import re
import sqlite3
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import requests

from trader.config import ROOT, load_settings
from trader.logging_setup import configure_logging, make_console_utf8

log = logging.getLogger(__name__)
IST = ZoneInfo("Asia/Kolkata")
FEEDS = {"announcements": "https://nsearchives.nseindia.com/content/RSS/Online_announcements.xml",
         "corporate actions": "https://nsearchives.nseindia.com/content/RSS/Corporate_action.xml"}
COMPANIES_URL = "https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv"
# NSE turns away requests that look like scripts; this says what it is: a personal feed reader.
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) trading-agent-news/1.0 (personal feed reader)"}
MAX_BYTES = 5_000_000
# NSE's announcement API serves a whole day at a time; its session cookies come from NSE's home page.
API_HOME = "https://www.nseindia.com/"
API_PAGE = "https://www.nseindia.com/companies-listing/corporate-filings-announcements"
API_URL = "https://www.nseindia.com/api/corporate-announcements?index=equities&from_date={day}&to_date={day}"
BACKFILL_DAYS = 14  # each collection checks this many days back for days not yet seen whole
RULES_TAGGER = "rules-v2"
EVENTS = ("results", "dividend", "corporate action", "deal", "fund raising", "order win", "rating", "management",
          "regulatory", "investor meeting", "board meeting", "routine", "other")
# First match wins, so what a board meeting will consider (results, fund raising) beats "board meeting", and a
# routine filing that names a regulation ("certificate under ... SEBI (Depositories ...)") isn't "regulatory".
# Tuned on a day of real announcements (12 Oct 2026); a change makes a new tagger version.
RULES = tuple((event, re.compile(pattern)) for event, pattern in (
    ("results", r"financial results|unaudited|audited results|quarterly results"),
    ("dividend", r"dividend"),
    ("corporate action", r"bonus|split|sub-division|buy ?back"),
    ("deal", r"acquisition|acquire|merger|amalgamation|demerger|scheme of arrangement|takeover"),
    ("fund raising", r"fund raising|qualified institutions placement|\bqip\b|preferential|rights issue|debenture|\bncds?\b"),
    ("order win", r"award|bagging|receipt of (?:an )?order|order (?:win|received)|contract"),
    ("rating", r"credit rating|\brating"),
    ("management", r"resignation|appointment|cessation|change in management|managing director|\bceo\b|\bcfo\b"),
    ("routine", r"certificate under|regulation 7[46]|depositories and participants|net asset value|isin for debt|"
                r"payment of interest|interest and principal|postal ballot|scruti|trading window|newspaper|"
                r"loss of share|duplicate share|investor grievance|regulation 13 ?\(3\)|regulation 50|"
                r"shareholding pattern|compliance certificate"),
    ("regulatory", r"penalty|show cause|litigation|dispute|tribunal|\bnclt\b|enforcement|adjudication"),
    ("investor meeting", r"analyst|investor(?:s)? meet|conference call|earnings call|presentation"),
    ("board meeting", r"board meeting"),
))
SCHEMA = """
CREATE TABLE IF NOT EXISTS announcements (id INTEGER PRIMARY KEY, guid TEXT UNIQUE NOT NULL, feed TEXT NOT NULL,
    symbol TEXT, company TEXT NOT NULL, subject TEXT NOT NULL, link TEXT NOT NULL, published TEXT NOT NULL,
    collected TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS fetches (id INTEGER PRIMARY KEY, feed TEXT NOT NULL, at TEXT NOT NULL, items INTEGER NOT NULL,
    added INTEGER NOT NULL, oldest TEXT, newest TEXT, gap_from TEXT, gap_to TEXT, error TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS tags (id INTEGER PRIMARY KEY, announcement INTEGER NOT NULL REFERENCES announcements (id),
    tagger TEXT NOT NULL, event TEXT NOT NULL, sentiment INTEGER, materiality TEXT, at TEXT NOT NULL,
    UNIQUE (announcement, tagger));
CREATE TABLE IF NOT EXISTS companies (name TEXT PRIMARY KEY, symbol TEXT NOT NULL, updated TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS coverage (id INTEGER PRIMARY KEY, day TEXT NOT NULL, at TEXT NOT NULL, items INTEGER NOT NULL,
    added INTEGER NOT NULL, complete INTEGER NOT NULL, error TEXT NOT NULL DEFAULT '');
CREATE TRIGGER IF NOT EXISTS coverage_no_update BEFORE UPDATE ON coverage BEGIN SELECT RAISE(ABORT, 'the news history is append-only'); END;
CREATE TRIGGER IF NOT EXISTS coverage_no_delete BEFORE DELETE ON coverage BEGIN SELECT RAISE(ABORT, 'the news history is append-only'); END;
CREATE TRIGGER IF NOT EXISTS announcements_no_update BEFORE UPDATE ON announcements BEGIN SELECT RAISE(ABORT, 'the news history is append-only'); END;
CREATE TRIGGER IF NOT EXISTS announcements_no_delete BEFORE DELETE ON announcements BEGIN SELECT RAISE(ABORT, 'the news history is append-only'); END;
CREATE TRIGGER IF NOT EXISTS fetches_no_update BEFORE UPDATE ON fetches BEGIN SELECT RAISE(ABORT, 'the news history is append-only'); END;
CREATE TRIGGER IF NOT EXISTS fetches_no_delete BEFORE DELETE ON fetches BEGIN SELECT RAISE(ABORT, 'the news history is append-only'); END;
CREATE TRIGGER IF NOT EXISTS tags_no_update BEFORE UPDATE ON tags BEGIN SELECT RAISE(ABORT, 'the news history is append-only'); END;
CREATE TRIGGER IF NOT EXISTS tags_no_delete BEFORE DELETE ON tags BEGIN SELECT RAISE(ABORT, 'the news history is append-only'); END;
"""


@dataclass(frozen=True)
class Item:
    feed: str
    guid: str
    company: str
    subject: str
    link: str
    published: datetime
    symbol: str | None = None


@dataclass(frozen=True)
class Tags:
    event: str
    sentiment: int
    materiality: str


class TagError(ValueError):
    """An AI answer that isn't exactly the shape a tag may take."""


def company_key(name: str) -> str:
    """A company name as NSE's list and its feeds both write it, whatever the case and punctuation."""
    words = re.sub(r"[^A-Z0-9]+", " ", name.upper().replace("&", " AND ")).split()
    while words and words[-1] in ("LIMITED", "LTD"):
        words.pop()
    return " ".join(words)


def symbol_from_link(link: str) -> str | None:
    """An announcement's filing is named after the company's NSE symbol (corporate/TCS_1110...pdf)."""
    match = re.search(r"/corporate/([A-Z0-9&-]+)_\d", link)
    return match.group(1) if match else None


def rule_event(subject: str) -> str:
    text = subject.lower()
    return next((event for event, pattern in RULES if pattern.search(text)), "other")


def parse_feed(feed: str, content: bytes) -> list[Item]:
    """A feed's items. One without a readable time can't be placed in the history, so it is skipped. A corporate
    action's time is when NSE rebuilt its list, not the action's own, so it doesn't make an item new."""
    items = []
    for node in ET.fromstring(content).iter("item"):
        title, link = (node.findtext("title") or "").strip(), (node.findtext("link") or "").strip()
        subject = (node.findtext("description") or "").strip()
        try:
            published = datetime.strptime((node.findtext("pubDate") or "").strip(), "%d-%b-%Y %H:%M:%S").replace(tzinfo=IST)
        except ValueError:
            continue
        company = title
        if feed == "corporate actions" and " - Ex-Date:" in title:
            company, ex_date = (part.strip() for part in title.split(" - Ex-Date:", 1))
            subject = f"{subject} |EX-DATE:{ex_date}"
        guid = hashlib.sha256(f"{feed}|{title}|{link}|{subject}".encode()).hexdigest()
        items.append(Item(feed, guid, company, subject, link, published, symbol_from_link(link)))
    return items


def fetch(http, url: str) -> bytes:
    response = http.get(url, headers=HEADERS, timeout=30)
    response.raise_for_status()
    if len(response.content) > MAX_BYTES:
        raise ValueError(f"{len(response.content)} bytes is more than a feed should be")
    return response.content


def api_items(rows) -> list[Item]:
    """A day's announcements from NSE's API, rebuilt exactly as the feed writes them (company, filing link, text
    with its subject, and time), so an announcement seen in both has the same guid and is stored once."""
    if not isinstance(rows, list):
        raise ValueError("NSE's announcement API answered with something other than a list")
    items = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        title, link = str(row.get("sm_name") or "").strip(), str(row.get("attchmntFile") or "").strip()
        subject = f"{str(row.get('attchmntText') or '').strip()} |SUBJECT: {str(row.get('desc') or '').strip()}"
        try:
            published = datetime.strptime(str(row.get("an_dt") or "").strip(), "%d-%b-%Y %H:%M:%S").replace(tzinfo=IST)
        except ValueError:
            continue
        if not title:
            continue
        guid = hashlib.sha256(f"announcements|{title}|{link}|{subject}".encode()).hexdigest()
        symbol = symbol_from_link(link) or (str(row.get("symbol") or "").strip() or None)
        items.append(Item("announcements", guid, title, subject, link, published, symbol))
    return items


class NseApi:
    """NSE's corporate-announcement API, one whole day per request. The session cookies come from one visit to
    NSE's home page; the same feed-reader user agent says what is asking."""

    def __init__(self, http=requests):
        self.http, self.session = http, None

    def day(self, day: date) -> list:
        if self.session is None:
            self.session = self.http.Session()
            self.session.headers.update({**HEADERS, "Accept": "application/json, text/plain, */*", "Referer": API_PAGE})
            self.session.get(API_HOME, timeout=30)
        response = self.session.get(API_URL.format(day=day.strftime("%d-%m-%Y")), timeout=60)
        response.raise_for_status()
        if len(response.content) > MAX_BYTES:
            raise ValueError(f"{len(response.content)} bytes is more than a day of announcements should be")
        return response.json()


class NewsStore:
    """The news history in SQLite (state/news.db), apart from every trading record."""

    def __init__(self, path: Path | str):
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(path), isolation_level=None)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)

    def close(self) -> None:
        self.conn.close()

    def add(self, items: list[Item], collected: datetime, companies: dict[str, str]) -> int:
        """Store the new items and tag them by the rules, in one transaction; returns how many were new."""
        added = 0
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            for item in items:
                symbol = item.symbol or companies.get(company_key(item.company))
                cursor = self.conn.execute(
                    "INSERT OR IGNORE INTO announcements (guid, feed, symbol, company, subject, link, published, collected) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (item.guid, item.feed, symbol, item.company, item.subject, item.link,
                                                       item.published.isoformat(), collected.isoformat()))
                if cursor.rowcount == 1:
                    self.add_tag(cursor.lastrowid, RULES_TAGGER, rule_event(item.subject), None, None, collected)
                    added += 1
            self.conn.execute("COMMIT")
        except BaseException:
            self.conn.execute("ROLLBACK")
            raise
        return added

    def record_coverage(self, day: date, at: datetime, items: int, added: int, error: str = "") -> None:
        """One API fetch of a whole day. It covers the day completely once it was made after the day ended."""
        complete = int(not error and at >= day_end(day))
        self.conn.execute("INSERT INTO coverage (day, at, items, added, complete, error) VALUES (?, ?, ?, ?, ?, ?)",
                          (day.isoformat(), at.isoformat(), items, added, complete, error))

    def complete_days(self) -> set[date]:
        rows = self.conn.execute("SELECT DISTINCT day FROM coverage WHERE complete = 1").fetchall()
        return {date.fromisoformat(r[0]) for r in rows}

    def covered_until(self, day: date) -> str | None:
        """The latest time up to which an API fetch has seen `day` (its fetch time, capped at the day's end)."""
        row = self.conn.execute("SELECT MAX(at) FROM coverage WHERE day = ? AND error = ''", (day.isoformat(),)).fetchone()
        return min(row[0], day_end(day).isoformat()) if row and row[0] else None

    def first_day(self) -> date | None:
        row = self.conn.execute("SELECT MIN(at) FROM fetches").fetchone()
        return datetime.fromisoformat(row[0]).astimezone(IST).date() if row and row[0] else None

    def add_tag(self, announcement: int, tagger: str, event: str, sentiment: int | None, materiality: str | None,
                at: datetime) -> None:
        self.conn.execute("INSERT OR IGNORE INTO tags (announcement, tagger, event, sentiment, materiality, at) "
                          "VALUES (?, ?, ?, ?, ?, ?)", (announcement, tagger, event, sentiment, materiality, at.isoformat()))

    def newest(self, feed: str) -> str | None:
        return self.conn.execute("SELECT MAX(published) FROM announcements WHERE feed = ?", (feed,)).fetchone()[0]

    def record_fetch(self, feed: str, at: datetime, items: list[Item], added: int, gap: tuple[str, str] | None,
                     error: str = "") -> None:
        stamps = [i.published.isoformat() for i in items]
        self.conn.execute("INSERT INTO fetches (feed, at, items, added, oldest, newest, gap_from, gap_to, error) "
                          "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                          (feed, at.isoformat(), len(items), added, min(stamps, default=None), max(stamps, default=None),
                           *(gap or (None, None)), error))

    def companies(self) -> tuple[dict[str, str], str | None]:
        rows = self.conn.execute("SELECT * FROM companies").fetchall()
        return {r["name"]: r["symbol"] for r in rows}, max((r["updated"] for r in rows), default=None)

    def set_companies(self, mapping: dict[str, str], at: datetime) -> None:
        """NSE's list of listed companies: reference data, replaced whole."""
        self.conn.execute("BEGIN IMMEDIATE")
        self.conn.execute("DELETE FROM companies")
        self.conn.executemany("INSERT OR REPLACE INTO companies VALUES (?, ?, ?)",
                              [(name, symbol, at.isoformat()) for name, symbol in mapping.items()])
        self.conn.execute("COMMIT")

    def untagged(self, tagger: str, limit: int) -> list[sqlite3.Row]:
        return self.conn.execute("SELECT * FROM announcements WHERE id NOT IN (SELECT announcement FROM tags WHERE tagger = ?) "
                                 "ORDER BY id LIMIT ?", (tagger, limit)).fetchall()

    def table(self, name: str) -> pd.DataFrame:
        if name not in {"announcements", "fetches", "tags", "companies", "coverage"}:
            raise ValueError(name)
        return pd.read_sql_query(f"SELECT * FROM {name} ORDER BY rowid", self.conn)


def day_end(day: date) -> datetime:
    """Midnight at the end of an IST day."""
    return datetime.combine(day + timedelta(days=1), datetime.min.time(), tzinfo=IST)


def refresh_companies(store: NewsStore, http, now: datetime) -> dict[str, str]:
    """NSE's list of listed companies (name to symbol), fetched at most once a day; the last good one on failure."""
    known, updated = store.companies()
    if updated is not None and updated[:10] == now.date().isoformat():
        return known
    try:
        frame = pd.read_csv(io.BytesIO(fetch(http, COMPANIES_URL)))
        frame.columns = [c.strip() for c in frame.columns]
        mapping = {company_key(name): str(symbol).strip() for symbol, name in zip(frame["SYMBOL"], frame["NAME OF COMPANY"])}
    except (requests.RequestException, ValueError, KeyError) as exc:
        log.warning("Couldn't refresh NSE's company list (%s); using the last one", type(exc).__name__)
        return known
    store.set_companies(mapping, now)
    return mapping


def collect(store: NewsStore, http=requests, now: datetime | None = None, api: NseApi | None = None) -> list[str]:
    """One pass over the feeds: store what's new, tag it by the rules, and record what each fetch covered,
    with any gap; then, given NSE's API, catch up on the days not yet seen whole. Returns what failed."""
    now, failed = now or datetime.now(IST), []
    companies = refresh_companies(store, http, now)
    for feed, url in FEEDS.items():
        try:
            items = parse_feed(feed, fetch(http, url))
        except (requests.RequestException, ET.ParseError, ValueError) as exc:  # recorded; the next run tries again
            store.record_fetch(feed, now, [], 0, None, type(exc).__name__)
            failed.append(f"{feed}: {type(exc).__name__}")
            continue
        newest_stored = store.newest(feed)
        oldest = min((i.published.isoformat() for i in items), default=None)
        # Only the announcement feed is a rolling window of timed items, where a gap can open.
        gap = ((newest_stored, oldest) if feed == "announcements" and newest_stored and oldest and oldest > newest_stored
               else None)
        store.record_fetch(feed, now, items, store.add(items, now, companies), gap)
    if api is not None:
        failed += catch_up(store, api, now, companies)
    return failed


def days_to_catch_up(store: NewsStore, now: datetime, days_back: int = BACKFILL_DAYS) -> list[date]:
    """Every day since collection began (at most `days_back`) not yet seen whole by the API, and today when the feed
    has left a gap the API hasn't filled."""
    today, first = now.astimezone(IST).date(), store.first_day()
    if first is None:
        return []
    complete, start = store.complete_days(), max(first, today - timedelta(days=days_back))
    days = [start + timedelta(days=k) for k in range((today - start).days) if start + timedelta(days=k) not in complete]
    if any(datetime.fromisoformat(g).astimezone(IST).date() == today for g in open_gaps(store, now)["gap_to"]):
        days.append(today)
    return days


def catch_up(store: NewsStore, api: NseApi, now: datetime, companies: dict[str, str] | None = None,
             days: list[date] | None = None, pause: float = 1.0) -> list[str]:
    """Fetch whole days from NSE's API and store what the feed missed, a second apart. Stops at the first failure
    (NSE may be refusing), which is recorded; the next run tries again."""
    companies = companies if companies is not None else store.companies()[0]
    for k, day in enumerate(days if days is not None else days_to_catch_up(store, now)):
        if k and pause:
            time.sleep(pause)
        try:
            items = api_items(api.day(day))
        except (requests.RequestException, ValueError) as exc:
            store.record_coverage(day, now, 0, 0, type(exc).__name__)
            return [f"announcements API, {day}: {type(exc).__name__}"]
        store.record_coverage(day, now, len(items), store.add(items, now, companies))
    return []


def open_gaps(store: NewsStore, now: datetime, since: datetime | None = None) -> pd.DataFrame:
    """The gaps the feed recorded that the API hasn't filled since: a gap is filled once every day it touches was
    fetched whole after the gap ended."""
    gaps_ = gaps(store, since or now - timedelta(days=BACKFILL_DAYS))
    keep = []
    for start, end in zip(gaps_["gap_from"], gaps_["gap_to"]):
        first, last = (datetime.fromisoformat(t).astimezone(IST).date() for t in (start, end))
        days = [first + timedelta(days=k) for k in range((last - first).days + 1)]
        # each day only has to be seen up to its own part of the gap (a gap can cross midnight)
        filled = all((c := store.covered_until(d)) is not None and c >= min(end, day_end(d).isoformat()) for d in days)
        keep.append(not filled)
    return gaps_[keep].reset_index(drop=True) if len(gaps_) else gaps_


def validate_tags(raw) -> Tags:
    """The only shape an AI answer may take: exactly an event from EVENTS, a sentiment of -1, 0 or 1, and a
    materiality of low, medium or high. Anything else, a price or a size included, is refused."""
    if not isinstance(raw, dict) or set(raw) != {"event", "sentiment", "materiality"}:
        raise TagError(f"expected exactly event, sentiment and materiality, got {raw!r}"[:200])
    if raw["event"] not in EVENTS:
        raise TagError(f"unknown event {raw['event']!r}")
    if type(raw["sentiment"]) is not int or raw["sentiment"] not in (-1, 0, 1):
        raise TagError(f"sentiment must be -1, 0 or 1, got {raw['sentiment']!r}")
    if raw["materiality"] not in ("low", "medium", "high"):
        raise TagError(f"materiality must be low, medium or high, got {raw['materiality']!r}")
    return Tags(raw["event"], raw["sentiment"], raw["materiality"])


class GeminiTagger:
    """AI tags through Google's Gemini API (REST, structured JSON output). Used only when [ai] enabled = true
    and GEMINI_API_KEY holds a current key (the old one leaked: make a new one)."""
    URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    PROMPT = ("Classify this announcement by a company listed on India's NSE.\nCompany: {company}\nAnnouncement: {subject}\n"
              "event: what kind of announcement it is. sentiment: its likely effect on the share price, -1, 0 or 1 "
              "(0 when routine or unclear). materiality: low, medium or high.")
    RESPONSE_SCHEMA = {"type": "OBJECT", "required": ["event", "sentiment", "materiality"], "properties": {
        "event": {"type": "STRING", "enum": list(EVENTS)}, "sentiment": {"type": "INTEGER", "enum": [-1, 0, 1]},
        "materiality": {"type": "STRING", "enum": ["low", "medium", "high"]}}}

    def __init__(self, api_key: str, model: str, http=requests, timeout: float = 20):
        self._key, self.model, self.http, self.timeout = api_key, model, http, timeout

    @property
    def name(self) -> str:
        return f"gemini:{self.model}"

    def ask(self, company: str, subject: str):
        body = {"contents": [{"parts": [{"text": self.PROMPT.format(company=company, subject=subject)}]}],
                "generationConfig": {"responseMimeType": "application/json", "responseSchema": self.RESPONSE_SCHEMA}}
        response = self.http.post(self.URL.format(model=self.model), json=body, timeout=self.timeout,
                                  headers={"x-goog-api-key": self._key})  # in a header, never in a URL that could be logged
        response.raise_for_status()
        return json.loads(response.json()["candidates"][0]["content"]["parts"][0]["text"])


def tag_with_ai(store: NewsStore, tagger, now: datetime, limit: int = 50) -> tuple[int, int]:
    """AI tags for up to `limit` announcements this tagger hasn't tagged; returns (tagged, refused). A refused
    answer stores nothing, so the announcement stays untagged rather than tagged wrongly."""
    tagged = refused = 0
    for row in store.untagged(tagger.name, limit):
        try:
            tags = validate_tags(tagger.ask(row["company"], row["subject"]))
        except (TagError, ValueError, KeyError, IndexError, TypeError, requests.RequestException) as exc:
            log.warning("AI tag refused for announcement %s: %s", row["id"], type(exc).__name__)
            refused += 1
            continue
        store.add_tag(row["id"], tagger.name, tags.event, tags.sentiment, tags.materiality, now)
        tagged += 1
    return tagged, refused


def news_events(store: NewsStore, start: date, end: date, tagger: str = RULES_TAGGER) -> pd.DataFrame:
    """For research: each announcement published from `start` up to `end` (IST dates), with one tagger's tags."""
    query = ("SELECT substr(a.published, 1, 10) AS date, a.symbol, a.company, a.feed, t.event, t.sentiment, "
             "t.materiality FROM announcements a JOIN tags t ON t.announcement = a.id WHERE t.tagger = ? "
             "AND a.published >= ? AND a.published < ? ORDER BY a.published")
    return pd.read_sql_query(query, store.conn, params=[tagger, start.isoformat(), end.isoformat()])


def gaps(store: NewsStore, since: datetime) -> pd.DataFrame:
    """The recorded gaps (from, to) that end after `since`: hours whose announcements may be incomplete."""
    return pd.read_sql_query("SELECT gap_from, gap_to FROM fetches WHERE gap_to IS NOT NULL AND gap_to >= ? ORDER BY id",
                             store.conn, params=[since.isoformat()])


def status_text(store: NewsStore, now: datetime) -> str:
    fetches = store.table("fetches")
    good = fetches[fetches["error"] == ""]
    announcements, tags = store.table("announcements"), store.table("tags")
    behind = days_to_catch_up(store, now)
    lines = [f"{len(announcements)} announcements ({announcements['symbol'].notna().sum()} with a symbol), "
             f"{len(tags)} tags",
             "Last good fetch: " + (good["at"].iloc[-1][:16].replace("T", " ") if len(good) else "none"),
             f"Gaps in the last 7 days: {len(gaps(store, now - timedelta(days=7)))}, "
             f"of which not yet filled from NSE's API: {len(open_gaps(store, now, now - timedelta(days=7)))}",
             "Days since collection began not yet seen whole: " + (", ".join(str(d) for d in behind) or "none")]
    if len(tags):
        rules = tags[tags["tagger"] == RULES_TAGGER]["event"].value_counts()
        lines.append("Events: " + ", ".join(f"{event} {count}" for event, count in rules.items()))
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="NSE announcements: collect, tag, and report coverage (research only).")
    parser.add_argument("command", choices=["collect", "status", "tag-ai", "backfill"])
    parser.add_argument("--from", dest="start", type=date.fromisoformat, help="backfill: first day (YYYY-MM-DD)")
    parser.add_argument("--to", dest="end", type=date.fromisoformat, help="backfill: last day (default: today)")
    args = parser.parse_args(argv)
    if args.command == "backfill" and args.start is None:
        parser.error("backfill needs --from")
    make_console_utf8()
    settings = load_settings()
    configure_logging(secrets=settings.secret_values(), filename="news.log")
    if args.command == "collect" and not settings.news_enabled:
        log.info("News collection is off ([news] enabled = false)")
        return
    store, now = NewsStore(ROOT / settings.news_database), datetime.now(IST)
    if args.command == "collect":
        failed = collect(store, now=now, api=NseApi())
        for problem in failed:
            log.warning("News fetch failed: %s", problem)
        fetches, coverage = store.table("fetches"), store.table("coverage")  # a trace of every run, even a quiet one
        done = [f"{r.feed} {r.items} item(s), {r.added} new" + (f", failed ({r.error})" if r.error else "")
                for r in fetches[fetches["at"] == now.isoformat()].itertuples()]
        done += [f"API {r.day} {r.items} item(s), {r.added} new" + (f", failed ({r.error})" if r.error else "")
                 for r in coverage[coverage["at"] == now.isoformat()].itertuples()]
        log.info("Collected: %s", "; ".join(done) or "nothing")
        raise SystemExit(1 if failed else 0)
    if args.command == "backfill":
        end = args.end or now.date()
        days = [args.start + timedelta(days=k) for k in range((end - args.start).days + 1)]
        failed = catch_up(store, NseApi(), now, days=days)
        coverage = store.table("coverage")
        added = int(coverage.loc[coverage["at"] == now.isoformat(), "added"].sum())
        print(f"{len(days)} day(s) from {args.start} to {end}: {added} announcement(s) added"
              + (f"; stopped: {failed[0]}" if failed else ""))
        raise SystemExit(1 if failed else 0)
    if args.command == "tag-ai":
        if not settings.ai_enabled:
            raise SystemExit("AI tagging is off: set [ai] enabled = true and a new GEMINI_API_KEY in .env first.")
        tagged, refused = tag_with_ai(store, GeminiTagger(settings.gemini_api_key.reveal(), settings.ai_model,
                                                          timeout=settings.ai_timeout_seconds), now)
        print(f"{tagged} tagged, {refused} refused")
        return
    print(status_text(store, now))


if __name__ == "__main__":
    main()
