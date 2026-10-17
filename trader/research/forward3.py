"""Forward test 3: round 10's E2, unchanged, on results meetings from 19 Oct 2026, in paper mode, judged against
docs/research/forward3-preregistration.md.

    python -m trader.research.forward3 daily      # scheduled each evening after forward test 2: notices, signals, paper account
    python -m trader.research.forward3 status     # the paper ledger: signals, entries, open positions, closed trades
    python -m trader.research.forward3 look       # informational any time; a decision look each January

E2 buys, two sessions after a company's results board meeting, a stock whose two-session price reaction (relative to
the 300 most liquid NSE stocks) is in the top 10% of the past year's reactions, holds it 40 sessions with a 15% stop, and
keeps at most 5 positions. Here it runs on new sessions only: NSE's board-meeting notices are fetched every evening and
the prices come from forward test 2's daily NSE files. Signals, entries, exits and the random-pick pools go into an
append-only paper ledger (state/forward3.db) as they happen, and nothing recorded is chosen again. Nothing here can
place an order or reach the gate's paper account: it is research.
"""
from __future__ import annotations

import argparse
import bisect
import gzip
import html
import json
import logging
import sqlite3
from dataclasses import asdict
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import requests

from trader.config import ROOT, load_settings
from trader.gate import Check, Evidence, save_evidence
from trader.logging_setup import configure_logging, make_console_utf8
from trader.research import forward2, round8, round10
from trader.research import nse_bhavcopy as nb
from trader.research.datasets import DATA_DIR, text_sha256

log = logging.getLogger(__name__)
IST = ZoneInfo("Asia/Kolkata")
PREREGISTRATION = ROOT / "docs" / "research" / "forward3-preregistration.md"
PREREGISTRATION_SHA256 = "a06ca559d92f2c9b9f1e7d139d3fe2f196b2e06942f91e6d441713fd53f2637e"  # pinned 2026-10-17 19:02 IST
STATUS = ROOT / "state" / "forward3-status.md"  # rewritten each evening; a look writes docs/research/forward3-look-<date>.md
LOOKS = ROOT / "docs" / "research"
BM_DIR = DATA_DIR / "forward3" / "board_meetings"
LEDGER = ROOT / "state" / "forward3.db"
KEY = "E2"
FIRST_MEETING_SESSION = date(2026, 10, 19)  # signals for results meetings whose session m is on or after this
FIRST_ENTRY = date(2026, 10, 22)  # the first possible paper entry (m = 19 Oct, signal 21 Oct; 20 Oct is a holiday)
FIRST_DECISION_YEAR, RETIRE_FROM_YEAR, LAST_YEAR = 2028, 2029, 2036
BACK, AHEAD, MAX_SPAN_DAYS = 20, 45, 31  # fetch window: meetings 20 days back to 45 days ahead, 31 days a request
EARLIEST_FETCH = date(2026, 9, 1)
WAIT_SESSIONS = 20  # a holding with no row this long after its exit date is closed at its last close
BM_URL = "https://www.nseindia.com/api/corporate-board-meetings?index=equities&from_date={a}&to_date={b}"
BM_REFERER = "https://www.nseindia.com/companies-listing/corporate-filings-board-meetings"
CLOSED = ("stop", "time", "time, delayed", "no further rows")
TABLES = ("board_notices", "fetches", "signals", "decisions", "trades", "pools", "runs", "notices")
SCHEMA = """
CREATE TABLE IF NOT EXISTS board_notices (id INTEGER PRIMARY KEY, symbol TEXT NOT NULL, meeting_date TEXT NOT NULL,
    purpose TEXT NOT NULL, nse_time TEXT NOT NULL, first_seen TEXT NOT NULL, UNIQUE (symbol, meeting_date, purpose, nse_time));
CREATE TABLE IF NOT EXISTS fetches (id INTEGER PRIMARY KEY, at TEXT NOT NULL, from_date TEXT NOT NULL, to_date TEXT NOT NULL,
    records INTEGER NOT NULL, file TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS signals (id INTEGER PRIMARY KEY, sid TEXT NOT NULL, meeting_session TEXT NOT NULL,
    signal_date TEXT NOT NULL, tier TEXT NOT NULL, month_end TEXT NOT NULL, reaction REAL NOT NULL, abnormal REAL NOT NULL,
    threshold REAL NOT NULL, late INTEGER NOT NULL, recorded_at TEXT NOT NULL, UNIQUE (sid, signal_date));
CREATE TABLE IF NOT EXISTS decisions (id INTEGER PRIMARY KEY, sid TEXT NOT NULL, signal_date TEXT NOT NULL,
    entry_date TEXT NOT NULL, status TEXT NOT NULL, recorded_at TEXT NOT NULL, UNIQUE (sid, signal_date));
CREATE TABLE IF NOT EXISTS trades (id INTEGER PRIMARY KEY, sid TEXT NOT NULL, signal_date TEXT NOT NULL, tier TEXT NOT NULL,
    month_end TEXT NOT NULL, entry_date TEXT NOT NULL, entry_price REAL, exit_date TEXT NOT NULL, exit_price REAL,
    gross REAL NOT NULL, net REAL NOT NULL, cost REAL NOT NULL, outcome TEXT NOT NULL, gapped INTEGER NOT NULL,
    recorded_at TEXT NOT NULL, UNIQUE (sid, signal_date));
CREATE TABLE IF NOT EXISTS pools (id INTEGER PRIMARY KEY, month_end TEXT NOT NULL, tier TEXT NOT NULL, entry_date TEXT NOT NULL,
    pool TEXT NOT NULL, recorded_at TEXT NOT NULL, UNIQUE (month_end, tier, entry_date));
CREATE TABLE IF NOT EXISTS runs (id INTEGER PRIMARY KEY, at TEXT NOT NULL, status TEXT NOT NULL, detail TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS notices (id INTEGER PRIMARY KEY, key TEXT NOT NULL, at TEXT NOT NULL, sent INTEGER NOT NULL);
CREATE UNIQUE INDEX IF NOT EXISTS notices_sent_once ON notices (key) WHERE sent = 1;
"""
for _table in TABLES:
    SCHEMA += (f"CREATE TRIGGER IF NOT EXISTS {_table}_no_update BEFORE UPDATE ON {_table} BEGIN SELECT RAISE(ABORT, "
               f"'the forward-test ledger is append-only'); END;\n"
               f"CREATE TRIGGER IF NOT EXISTS {_table}_no_delete BEFORE DELETE ON {_table} BEGIN SELECT RAISE(ABORT, "
               f"'the forward-test ledger is append-only'); END;\n")


def check_preregistration() -> str:
    digest = text_sha256(PREREGISTRATION)
    if digest != PREREGISTRATION_SHA256:
        raise SystemExit(f"{PREREGISTRATION.name} changed after it was pinned (sha256 {digest}); "
                         "pre-register a new forward test instead of editing this one.")
    return digest


# ----------------------------------------------------------------------------------------------- ledger
class Ledger:
    """The paper ledger, apart from every trading record."""

    def __init__(self, path: Path | str = LEDGER):
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(path), isolation_level=None)
        self.conn.executescript(SCHEMA)

    def close(self) -> None:
        self.conn.close()

    def table(self, name: str) -> pd.DataFrame:
        if name not in TABLES:
            raise ValueError(name)
        return pd.read_sql_query(f"SELECT * FROM {name} ORDER BY id", self.conn)

    def add_board_notices(self, rows: list[dict], at: datetime) -> int:
        before = self.conn.total_changes
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            for r in rows:
                self.conn.execute("INSERT OR IGNORE INTO board_notices (symbol, meeting_date, purpose, nse_time, first_seen) "
                                  "VALUES (?, ?, ?, ?, ?)", (r["symbol"], r["meeting_date"], r["purpose"], r["nse_time"],
                                                             at.isoformat()))
            self.conn.execute("COMMIT")
        except BaseException:
            self.conn.execute("ROLLBACK")
            raise
        return self.conn.total_changes - before

    def add_fetch(self, at: datetime, a: date, b: date, records: int, file: str) -> None:
        self.conn.execute("INSERT INTO fetches (at, from_date, to_date, records, file) VALUES (?, ?, ?, ?, ?)",
                          (at.isoformat(), a.isoformat(), b.isoformat(), records, file))

    def last_fetch(self) -> date | None:
        row = self.conn.execute("SELECT MAX(at) FROM fetches").fetchone()[0]
        return datetime.fromisoformat(row).astimezone(IST).date() if row else None

    def add_signal(self, s: dict, late: bool, at: datetime) -> None:
        self.conn.execute(
            "INSERT INTO signals (sid, meeting_session, signal_date, tier, month_end, reaction, abnormal, threshold, late, "
            "recorded_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (s["sid"], s["meeting_session"].isoformat(), s["signal_date"].isoformat(), s["tier"], s["month_end"].isoformat(),
             s["reaction"], s["abnormal"], s["threshold"], int(late), at.isoformat()))

    def decided_entry_dates(self) -> set[str]:
        return {r[0] for r in self.conn.execute("SELECT DISTINCT entry_date FROM decisions")}

    def add_decision(self, sid: str, signal: date, entry: date, status: str, at: datetime) -> None:
        self.conn.execute("INSERT INTO decisions (sid, signal_date, entry_date, status, recorded_at) VALUES (?, ?, ?, ?, ?)",
                          (sid, signal.isoformat(), entry.isoformat(), status, at.isoformat()))

    def add_trade(self, sid: str, signal: date, tier: str, month_end: date, t: dict, at: datetime) -> None:
        self.conn.execute(
            "INSERT INTO trades (sid, signal_date, tier, month_end, entry_date, entry_price, exit_date, exit_price, gross, "
            "net, cost, outcome, gapped, recorded_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (sid, signal.isoformat(), tier, month_end.isoformat(), t["entry_date"].isoformat(), t["entry_price"],
             t["exit_date"].isoformat(), t["exit_price"], t["gross"], t["net"], t["cost"], t["outcome"], int(t["gapped"]),
             at.isoformat()))

    def has_pool(self, month_end: date, tier: str, entry: date) -> bool:
        return self.conn.execute("SELECT 1 FROM pools WHERE month_end = ? AND tier = ? AND entry_date = ?",
                                 (month_end.isoformat(), tier, entry.isoformat())).fetchone() is not None

    def add_pool(self, month_end: date, tier: str, entry: date, pool: list[float], at: datetime) -> None:
        self.conn.execute("INSERT INTO pools (month_end, tier, entry_date, pool, recorded_at) VALUES (?, ?, ?, ?, ?)",
                          (month_end.isoformat(), tier, entry.isoformat(), json.dumps([round(float(x), 8) for x in pool]),
                           at.isoformat()))

    def add_run(self, at: datetime, status: str, detail: str) -> None:
        self.conn.execute("INSERT INTO runs (at, status, detail) VALUES (?, ?, ?)", (at.isoformat(), status, detail[:2000]))

    def sent(self, key: str) -> bool:
        return self.conn.execute("SELECT 1 FROM notices WHERE key = ? AND sent = 1", (key,)).fetchone() is not None

    def add_notice(self, key: str, at: datetime, sent: bool) -> None:
        self.conn.execute("INSERT INTO notices (key, at, sent) VALUES (?, ?, ?)", (key, at.isoformat(), int(sent)))


class _ReadOnly:
    """The ledger, answering questions but recording nothing (for `status`)."""

    def __init__(self, ledger: Ledger):
        self._ledger = ledger
        self._signals, self._decisions, self._trades = [], [], []

    def __getattr__(self, name):
        return getattr(self._ledger, name)

    def table(self, name: str) -> pd.DataFrame:
        frame = self._ledger.table(name)
        extra = {"signals": self._signals, "decisions": self._decisions, "trades": self._trades}.get(name)
        return pd.concat([frame, pd.DataFrame(extra)], ignore_index=True) if extra else frame

    def add_signal(self, s: dict, late: bool, at: datetime) -> None:
        self._signals.append({"sid": s["sid"], "meeting_session": s["meeting_session"].isoformat(),
                              "signal_date": s["signal_date"].isoformat(), "tier": s["tier"],
                              "month_end": s["month_end"].isoformat(), "reaction": s["reaction"], "abnormal": s["abnormal"],
                              "threshold": s["threshold"], "late": int(late)})

    def decided_entry_dates(self) -> set[str]:
        return self._ledger.decided_entry_dates() | {d["entry_date"] for d in self._decisions}

    def add_decision(self, sid, signal, entry, status, at) -> None:
        self._decisions.append({"sid": sid, "signal_date": signal.isoformat(), "entry_date": entry.isoformat(), "status": status})

    def add_trade(self, sid, signal, tier, month_end, t, at) -> None:
        self._trades.append({"sid": sid, "signal_date": signal.isoformat(), "tier": tier, "month_end": month_end.isoformat(),
                             "entry_date": t["entry_date"].isoformat(), "entry_price": t["entry_price"],
                             "exit_date": t["exit_date"].isoformat(), "exit_price": t["exit_price"], "gross": t["gross"],
                             "net": t["net"], "cost": t["cost"], "outcome": t["outcome"], "gapped": int(t["gapped"])})

    def has_pool(self, *args) -> bool:
        return True

    def add_pool(self, *args, **kwargs) -> None:
        pass


# ------------------------------------------------------------------------------------------ board meetings
def parse_board(rows: list) -> list[dict]:
    """NSE's board-meeting records as stored: every purpose, unchanged values."""
    out = []
    for r in rows:
        if not isinstance(r, dict) or not r.get("bm_symbol") or not r.get("bm_date") or not r.get("bm_timestamp"):
            continue
        out.append({"symbol": str(r["bm_symbol"]).strip(), "meeting_date": str(r["bm_date"]).strip(),
                    "purpose": str(r.get("bm_purpose") or "").strip(), "nse_time": str(r["bm_timestamp"]).strip()})
    return out


def fetch_board_meetings(now: datetime, ledger: Ledger, http=requests, session=None, out_dir: Path = BM_DIR) -> dict:
    """NSE's board-meeting records for meetings from 20 days back (or 20 days before the last fetch, after missed days)
    to 45 days ahead, each answer saved unchanged (gzipped) and its records added to the ledger once."""
    local = now.astimezone(IST)
    today = local.date()
    start = today - timedelta(days=BACK)
    last = ledger.last_fetch()
    if last is not None:
        start = min(start, last - timedelta(days=BACK))
    start, end = max(start, EARLIEST_FETCH), today + timedelta(days=AHEAD)
    session = session or nb.nse_session(http, referer=BM_REFERER)
    out_dir.mkdir(parents=True, exist_ok=True)
    records = added = 0
    a = start
    while a <= end:
        b = min(a + timedelta(days=MAX_SPAN_DAYS - 1), end)
        response = session.get(BM_URL.format(a=a.strftime("%d-%m-%Y"), b=b.strftime("%d-%m-%Y")), timeout=60)
        response.raise_for_status()
        payload = response.json()
        rows = payload if isinstance(payload, list) else payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(rows, list):
            raise ValueError(f"{a}..{b}: NSE's board-meeting API answered without a list of records")
        name = f"{local:%Y%m%dT%H%M%S}_{a}_{b}.json.gz"
        (out_dir / name).write_bytes(gzip.compress(response.content, mtime=0))
        added += ledger.add_board_notices(parse_board(rows), now)
        ledger.add_fetch(now, a, b, len(rows), name)
        records += len(rows)
        a = b + timedelta(days=1)
    return {"records": records, "new": added, "from": start, "to": end}


def all_notices(ledger: Ledger, archive: Path = round10.BOARD_DIR) -> pd.DataFrame:
    """Round 10's frozen archive plus every record fetched since, in round 10's columns, duplicates removed."""
    fetched = ledger.table("board_notices").rename(columns={"symbol": "bm_symbol", "meeting_date": "bm_date",
                                                           "purpose": "bm_purpose", "nse_time": "bm_timestamp"})
    frame = pd.concat([round10.load_board_meetings(archive), fetched[["bm_symbol", "bm_date", "bm_purpose", "bm_timestamp"]]],
                      ignore_index=True)
    return frame.astype(str).drop_duplicates().reset_index(drop=True)


# ------------------------------------------------------------------------------------------------ signals
def forward_signals(notices: pd.DataFrame, sessions: list[date], secs: dict, universe: round10.Universe) -> pd.DataFrame:
    """E2's signals, exactly as round 10 computes them, for meetings whose session is on or after 19 Oct 2026."""
    events = round10.flag_signals(round10.reaction_events(round10.results_notices(notices, sessions, secs), sessions, secs,
                                                          universe))
    first = bisect.bisect_left(sessions, FIRST_MEETING_SESSION)
    return events[events["is_signal"] & (events["m"] >= first)].reset_index(drop=True)


# ---------------------------------------------------------------------------------------------- positions
def position(sec: round8.Security, e: int, n: int) -> dict:
    """One paper position bought at the open of e: "open" (marked at the latest close), or closed by "stop", "time",
    "time, delayed" or "no further rows" (no row for 20 sessions after its exit date), with prices as NSE printed them
    and returns in adjusted prices, as in round 10."""
    x0 = e + round10.HOLD
    entry = float(sec.adj_open[e])
    level = entry * (1 - round10.STOP)
    base = {"entry_i": e, "entry_raw": float(sec.raw_open[e])}
    for j in range(e, min(x0, n)):
        if sec.present[j] and sec.adj_low[j] <= level:
            fill = min(level, float(sec.adj_open[j]))
            return {**base, "outcome": "stop", "exit_i": j, "gross": fill / entry - 1, "gapped": bool(sec.adj_open[j] < level),
                    "exit_raw": fill / (float(sec.adj_open[j]) / float(sec.raw_open[j]))}
    mark = {"outcome": "open", "stop_raw": base["entry_raw"] * (1 - round10.STOP)}
    if x0 >= n:
        return {**base, **mark, "mark": float(sec.adj_close[int(sec.last_row[n - 1])]) / entry - 1}
    j = x0
    while j < n and not sec.present[j]:
        j += 1
    if j < n:
        return {**base, "outcome": "time" if j == x0 else "time, delayed", "exit_i": j, "gapped": False,
                "gross": float(sec.adj_open[j]) / entry - 1, "exit_raw": float(sec.raw_open[j])}
    if n - 1 - x0 < WAIT_SESSIONS:
        return {**base, **mark, "mark": float(sec.adj_close[int(sec.last_row[n - 1])]) / entry - 1}
    last = int(sec.last_row[n - 1])
    return {**base, "outcome": "no further rows", "exit_i": last, "gapped": False,
            "gross": float(sec.adj_close[last]) / entry - 1, "exit_raw": float(sec.raw_close[last])}


def with_costs(t: dict, tier: str) -> dict:
    cost = round10.ROUND_TRIP[tier] + (round8.SLIPPAGE[tier] if t["outcome"] == "stop" else 0.0)
    return {**t, "cost": cost, "net": t["gross"] - cost}


def release(outcome: str, exit_i: int) -> int:
    """When a closed position's place is free again (round 10's rule)."""
    return round10.release_at({"reason": outcome, "exit_i": exit_i})


# ------------------------------------------------------------------------------------------------- update
def update(ledger, sessions: list[date], secs: dict, universe: round10.Universe, signals: pd.DataFrame, now: datetime) -> dict:
    """Record what has happened since the last update: new signals, entry decisions, closed positions, random-pick pools.
    Recorded rows are never recomputed; later data that disagrees is reported as a difference."""
    n = len(sessions)
    index = {d.isoformat(): i for i, d in enumerate(sessions)}
    events = {"signals": [], "late": [], "entries": [], "closed": [], "pools": [], "open": [], "waiting": [],
              "differences": []}
    recorded = ledger.table("signals")
    known = {(s, d): (a, l) for s, d, a, l in zip(recorded["sid"], recorded["signal_date"], recorded["abnormal"],
                                                   recorded["late"])} if len(recorded) else {}
    decided = ledger.decided_entry_dates()
    computed = set()
    for row in signals.itertuples(index=False):
        signal = sessions[row.signal]
        key = (row.sid, signal.isoformat())
        computed.add(key)
        if key in known:
            if abs(known[key][0] - row.abnormal) > 1e-9:
                events["differences"].append(f"{row.sid} {signal}: abnormal reaction now {row.abnormal:+.4f}, "
                                             f"recorded {known[key][0]:+.4f}")
            continue
        entry_i = row.signal + 1
        late = entry_i < n and sessions[entry_i].isoformat() in decided
        s = {"sid": row.sid, "meeting_session": sessions[row.m], "signal_date": signal, "tier": row.tier,
             "month_end": sessions[int(row.i_me)], "reaction": float(row.reaction), "abnormal": float(row.abnormal),
             "threshold": float(row.threshold)}
        ledger.add_signal(s, late, now)
        events["late" if late else "signals"].append(s)
    for key in known:
        if key not in computed:
            events["differences"].append(f"{key[0]} {key[1]}: recorded as a signal, which the data no longer gives")

    sig = ledger.table("signals")
    if sig.empty:
        return events
    sig = sig[sig["late"] == 0]
    decisions = ledger.table("decisions")
    status_of = {(s, d): st for s, d, st in zip(decisions["sid"], decisions["signal_date"], decisions["status"])}
    trades = ledger.table("trades")
    closed_of = {(s, d): (o, ed) for s, d, o, ed in zip(trades["sid"], trades["signal_date"], trades["outcome"], trades["exit_date"])}
    places, held = [0] * round10.CAP, {}
    sig = sig.assign(entry_i=[index[d] + 1 for d in sig["signal_date"]])
    for entry_i, group in sig.sort_values(["entry_i"]).groupby("entry_i", sort=True):
        if entry_i >= n:
            events["waiting"] += [(r.sid, r.signal_date, float(r.abnormal)) for r in group.itertuples(index=False)]
            continue
        entry = sessions[entry_i]
        for c in group.sort_values(["abnormal", "sid"], ascending=[False, True]).itertuples(index=False):
            key, sec = (c.sid, c.signal_date), secs.get(c.sid)
            status = status_of.get(key)
            if status is None:
                if held.get(c.sid, -1) > entry_i:
                    status = "already held"
                elif sec is None or not round8.enterable(sec, entry_i):
                    status = "not bought"
                else:
                    status = "bought" if min(places) <= entry_i else "no free place"
                ledger.add_decision(c.sid, date.fromisoformat(c.signal_date), entry, status, now)
                events["entries"].append((c.sid, entry, status, float(c.abnormal)))
            if status != "bought":
                continue
            k = int(np.argmin(places))
            if places[k] > entry_i:
                events["differences"].append(f"{c.sid} {entry}: recorded as bought, but the data now shows no free place")
            if key in closed_of:
                outcome, exit_date = closed_of[key]
                free_at = release(outcome, index[exit_date]) if exit_date in index else n
            elif sec is None:
                free_at = n
            else:
                t = position(sec, entry_i, n)
                if t["outcome"] in CLOSED:
                    t = with_costs(t, c.tier)
                    record = {**t, "entry_date": entry, "entry_price": t["entry_raw"], "exit_date": sessions[t["exit_i"]],
                              "exit_price": t["exit_raw"]}
                    ledger.add_trade(c.sid, date.fromisoformat(c.signal_date), c.tier, date.fromisoformat(c.month_end), record, now)
                    events["closed"].append((c.sid, entry, record))
                    free_at = release(t["outcome"], t["exit_i"])
                else:
                    events["open"].append((c.sid, entry, t))
                    free_at = n
            places[k] = max(places[k], free_at)
            held[c.sid] = free_at
    record_pools(ledger, sessions, secs, universe, now, events)
    return events


def record_pools(ledger, sessions, secs, universe, now, events) -> None:
    """("Random baseline") Once every member's outcome has closed, the net returns of every member of a trade's tier at
    its month-end that could have been bought at its entry open, traded by the same rules."""
    n = len(sessions)
    index = {d.isoformat(): i for i, d in enumerate(sessions)}
    trades = ledger.table("trades")
    for month_end, tier, entry in trades[["month_end", "tier", "entry_date"]].drop_duplicates().itertuples(index=False):
        m_date, e_date = date.fromisoformat(month_end), date.fromisoformat(entry)
        if ledger.has_pool(m_date, tier, e_date) or month_end not in index or entry not in index:
            continue
        i_me, e = index[month_end], index[entry]
        members = [s for s, t in universe.members.get(i_me, {}).items() if t == tier and s in secs and round8.enterable(secs[s], e)]
        outcomes = [position(secs[s], e, n) for s in members]
        if outcomes and all(o["outcome"] in CLOSED for o in outcomes):
            pool = [with_costs(o, tier)["net"] for o in outcomes]
            ledger.add_pool(m_date, tier, e_date, pool, now)
            events["pools"].append((month_end, tier, entry, len(pool)))


# -------------------------------------------------------------------------------------------------- looks
def ledger_trades(ledger, cutoff: date | None = None) -> pd.DataFrame:
    """The closed trades as round 10's criteria want them."""
    t = ledger.table("trades")
    if cutoff is not None and len(t):
        t = t[pd.to_datetime(t["entry_date"]).dt.date <= cutoff]
    if t.empty:
        return t
    t = t.copy()
    t["signal_date"] = pd.to_datetime(t["entry_date"]).dt.date  # round 10 reads entry dates for halves and years
    t["entry_date"] = t["signal_date"]
    t["exit_date"] = pd.to_datetime(t["exit_date"]).dt.date
    t["signal_i"] = [d.year * 12 + d.month for d in t["entry_date"]]  # clusters: entry months
    t["ticker"], t["R"] = t["sid"], t["net"] / round10.STOP
    t["stopped"], t["gapped"] = t["outcome"] == "stop", t["gapped"].astype(bool)
    t["i_me"] = [date.fromisoformat(d).toordinal() for d in t["month_end"]]
    t["entry_i"] = [d.toordinal() for d in t["entry_date"]]
    return t.reset_index(drop=True)


def look_number(as_of: date) -> int:
    return as_of.year - FIRST_DECISION_YEAR + 1 if as_of.month == 1 and FIRST_DECISION_YEAR <= as_of.year <= LAST_YEAR else 0


def cutoff(as_of: date) -> date:
    return date(as_of.year - 1, 12, 31) if as_of.month == 1 else as_of


def judge(ledger, as_of: date) -> dict:
    """The forward trades, criteria and decision at a look on `as_of` ("Criteria at a decision look", "Decisions")."""
    look, end = look_number(as_of), cutoff(as_of)
    trades = ledger_trades(ledger, end)
    if trades.empty:
        return {"look": look, "cutoff": end, "trades": trades, "decision": "WAITING", "checks": [], "raw_p": np.nan}
    pools_table = ledger.table("pools")
    pools = {(date.fromisoformat(m).toordinal(), t, date.fromisoformat(e).toordinal()): np.asarray(json.loads(p))
             for m, t, e, p in zip(pools_table["month_end"], pools_table["tier"], pools_table["entry_date"], pools_table["pool"])}
    covered = trades[[(i, t, e) in pools for i, t, e in zip(trades["i_me"], trades["tier"], trades["entry_i"])]]
    random_mean, raw_p = round10.baseline(covered, pools) if len(covered) else (np.nan, 1.0)
    alpha = 0.05 / max(look, 1)
    checks, stats = round8.criteria(trades, (FIRST_ENTRY, end), raw_p * max(look, 1), raw_p)
    out = []
    for c in checks:
        if c.number == 12:
            continue
        if c.number == 5:
            c = Check(5, f"Beats the random baseline: p below 0.05/{max(look, 1)} = {alpha:.4f}", f"{raw_p:.5f}", bool(raw_p < alpha))
        elif c.number == 11:
            c = Check(11, "Cluster-robust t-statistic (entry months as clusters) at least 2.0", c.value, c.passed)
        out.append(c)
    depth = stats["max_drawdown_r"]
    if depth > 20.0:
        decision = "REJECTED"
    elif look == 0:
        decision = "INFORMATIONAL"
    elif all(c.passed for c in out):
        decision = "PAPER"
    elif look >= LAST_YEAR - FIRST_DECISION_YEAR + 1 or (look >= RETIRE_FROM_YEAR - FIRST_DECISION_YEAR + 1
                                                        and not stats["mean_net"] > 0):
        decision = "REJECTED"
    else:
        decision = "CONTINUE"
    return {"look": look, "cutoff": end, "trades": trades, "checks": out, "stats": stats, "raw_p": raw_p,
            "random_mean": random_mean, "decision": decision}


def evidence_for(r: dict, digest: str) -> Evidence:
    s = r["stats"]
    return Evidence(
        strategy_id="E2F", kind="research", decision=r["decision"], generated=date.today().isoformat(),
        source="docs/research/forward3-look-*.md (python -m trader.research.forward3 look)",
        checks=tuple(asdict(c) for c in r["checks"]),
        stats={"evaluation_span": f"{FIRST_ENTRY} to {r['cutoff']}", "holdout_trades": s["trades"],
               "holdout_win_rate": s["win_rate"], "holdout_mean_net": s["mean_net"], "holdout_sd_net": s["sd_net"],
               "holdout_profit_factor": s["profit_factor"], "holdout_t": s["t"], "holdout_t_clustered": s["t_clustered"],
               "p_random_raw": r["raw_p"], "round_trip_cost": round10.ROUND_TRIP["N2"], "max_drawdown_r": s["max_drawdown_r"],
               "look": r["look"]},
        preregistration_sha256=digest)


# ------------------------------------------------------------------------------------------------ reports
def _pct(v, digits: int = 2) -> str:
    return f"{100 * v:+.{digits}f}%" if v is not None and not pd.isna(v) else "-"


TAG = "<b>[FORWARD TEST 3 · paper only]</b>"


def messages(events: dict, latest: date) -> list[tuple[str, str]]:
    """(key, text) for each event worth a Telegram message; a key is sent once."""
    out = []
    fresh = [s for s in events["signals"] if s["signal_date"] == latest]
    if fresh:
        names = ", ".join(f"{html.escape(s['sid'])} ({_pct(s['abnormal'], 1)} vs the market)" for s in fresh)
        out.append((f"signals {latest}", f"{TAG} E2 signals at the {latest:%d %b %Y} close, after results: {names}. Bought in "
                    "paper at the next open if one of the 5 places is free. Research, not a trading signal."))
    by_entry: dict = {}
    for sid, entry, status, _ in events["entries"]:
        by_entry.setdefault(entry, []).append((sid, status))
    for entry, rows in by_entry.items():
        parts = [f"{html.escape(sid)}: {status}" for sid, status in rows]
        out.append((f"entries {entry} {'|'.join(s for s, _ in rows)}", f"{TAG} Paper entries at the {entry:%d %b %Y} open: "
                    + "; ".join(parts) + "."))
    for sid, entry, record in events["closed"]:
        out.append((f"closed {sid} {entry}", f"{TAG} Closed {html.escape(sid)} (bought {entry:%d %b %Y}): {_pct(record['net'], 1)} "
                    f"net ({record['outcome']}, {record['exit_date']:%d %b %Y})."))
    return out


def write_status(ledger, events: dict | None, now: datetime) -> str:
    trades = ledger_trades(ledger)
    signals, decisions = ledger.table("signals"), ledger.table("decisions")
    lines = ["# Forward test 3: status", "",
             f"Updated {now.astimezone(IST):%Y-%m-%d %H:%M} IST by `python -m trader.research.forward3`, against the "
             "pre-registration (docs/research/forward3-preregistration.md). Paper only: nothing here is a trade, and nothing "
             "here can place one. Signals for results meetings from 19 Oct 2026; the first possible entry is 22 Oct 2026.", ""]
    notices = ledger.table("board_notices")
    lines.append(f"Board-meeting records fetched since the start: {len(notices)}; last fetch {ledger.last_fetch() or 'never'}.")
    if signals.empty:
        lines += ["", "No signals yet."]
    else:
        status_of = {(s, d): st for s, d, st in zip(decisions["sid"], decisions["signal_date"], decisions["status"])}
        lines += ["", "| Signal | Stock | Tier | Abnormal reaction | Threshold | Entry |", "|---|---|---|---:|---:|---|"]
        for r in signals.itertuples(index=False):
            entry = "late (not a candidate)" if r.late else status_of.get((r.sid, r.signal_date), "waiting for the next open")
            lines.append(f"| {r.signal_date} | {r.sid} | {r.tier} | {_pct(r.abnormal, 1)} | {_pct(r.threshold, 1)} | {entry} |")
    if events and events["open"]:
        lines += ["", "Open positions:", "", "| Stock | Entered | Mark | Stop |", "|---|---|---:|---:|"]
        lines += [f"| {sid} | {entry} | {_pct(t['mark'], 1)} | {t['stop_raw']:.2f} |" for sid, entry, t in events["open"]]
    if not trades.empty:
        net = trades["net"]
        lines += ["", f"Closed trades: {len(trades)}, {100 * (net > 0).mean():.1f}% winners, {_pct(net.mean())} a trade net; "
                  f"drawdown {round8.drawdown_r(round8.r_in_exit_order(trades)):.1f}R (limit 20R).", "",
                  "| Stock | Entry | Exit | How | Net |", "|---|---|---|---|---:|"]
        lines += [f"| {t.sid} | {t.entry_date} | {t.exit_date} | {t.outcome} | {_pct(t.net, 1)} |" for t in trades.itertuples(index=False)]
    if events and events["differences"]:
        lines += ["", "Rebuilt data that now disagrees with the ledger (the ledger keeps what it recorded):", ""]
        lines += [f"- {d}" for d in events["differences"]]
    text = "\n".join(lines) + "\n"
    STATUS.parent.mkdir(parents=True, exist_ok=True)
    STATUS.write_text(text, encoding="utf-8")
    return text


def write_look(r: dict, digest: str, as_of: date) -> None:
    lines = [f"# Forward test 3: look on {as_of}", "",
             f"Look {r['look'] or 'informational'}; trades entered {FIRST_ENTRY} to {r['cutoff']}; pre-registration SHA-256 "
             f"`{digest[:16]}...`.", "", f"**Decision: {r['decision']}.**", ""]
    if r["checks"]:
        lines += ["| # | Criterion | Value | Result |", "|---|---|---|---|"]
        lines += [f"| {c.number} | {c.criterion} | {c.value} | {'pass' if c.passed else '**fail**'} |" for c in r["checks"]]
    (LOOKS / f"forward3-look-{as_of}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


# --------------------------------------------------------------------------------------------------- main
def load_market():
    """Forward test 2's panel (rebuilt each evening just before this runs) and round 10's universe on it."""
    sessions, secs, table = forward2.load_inputs()
    return sessions, secs, round10.Universe(table)


def daily(now: datetime | None = None, notify: bool = True) -> int:
    from trader.notify.telegram import notifier_from_settings
    now = now or datetime.now(IST)
    ledger = Ledger()
    try:
        try:
            round10.verify_manifest(round10.BOARD_DIR, round10.BOARD_MANIFEST, round10.BOARD_MANIFEST_SHA256)
        except SystemExit as exc:
            raise ValueError(str(exc)) from None
        got = fetch_board_meetings(now, ledger)
        sessions, secs, universe = load_market()
        signals = forward_signals(all_notices(ledger), sessions, secs, universe)
        events = update(ledger, sessions, secs, universe, signals, now)
        verdict = judge(ledger, now.astimezone(IST).date())
        notes = messages(events, sessions[-1])
        if verdict.get("stats") and verdict["stats"]["max_drawdown_r"] > 20.0:  # "Any update: ... passes 20R"
            if not ledger.sent("rejected: drawdown"):
                save_evidence(evidence_for(verdict, check_preregistration()))
            notes.append(("rejected: drawdown", f"{TAG} E2's paper drawdown passed 20R "
                          f"({verdict['stats']['max_drawdown_r']:.1f}R): REJECTED, as pre-registered. The test ends."))
        write_status(ledger, events, now)
        if notify:
            notifier = notifier_from_settings(load_settings())
            for key, text in notes:
                if not ledger.sent(key):
                    ledger.add_notice(key, now, notifier.send(text))
        detail = (f"board meetings {got['from']}..{got['to']}: {got['records']} records, {got['new']} new; data to "
                  f"{sessions[-1]}; signals {len(events['signals'])} (late {len(events['late'])}), entries "
                  f"{len(events['entries'])}, closed {len(events['closed'])}, open {len(events['open'])}, pools "
                  f"{len(events['pools'])}" + (f"; differences: {events['differences']}" if events["differences"] else ""))
        ledger.add_run(now, "ok", detail)
        log.info("Forward test 3: %s", detail)
        return 0
    except (requests.RequestException, ValueError, OSError, KeyError) as exc:
        ledger.add_run(now, "failed", f"{type(exc).__name__}: {exc}")
        log.warning("Forward test 3 failed: %s: %s", type(exc).__name__, exc)
        return 1
    finally:
        ledger.close()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Forward test 3: E2 on new results meetings, in paper mode (research only).")
    parser.add_argument("command", choices=["daily", "status", "look"])
    parser.add_argument("--no-notify", action="store_true", help="daily: don't send Telegram messages")
    args = parser.parse_args(argv)
    make_console_utf8()
    settings = load_settings()
    configure_logging(secrets=settings.secret_values(), filename="forward3.log")
    digest = check_preregistration()
    if args.command == "daily":
        raise SystemExit(daily(notify=not args.no_notify))
    ledger = Ledger()
    try:
        if args.command == "status":
            sessions, secs, universe = load_market()
            now = datetime.now(IST)
            view = _ReadOnly(ledger)
            events = update(view, sessions, secs, universe, forward_signals(all_notices(ledger), sessions, secs, universe), now)
            print(write_status(view, events, now))
            return
        as_of = datetime.now(IST).date()
        r = judge(ledger, as_of)
        write_look(r, digest, as_of)
        if r["look"] and r["decision"] in ("PAPER", "REJECTED"):
            save_evidence(evidence_for(r, digest))
        print(f"Look {r['look'] or 'informational'}: {r['decision']}")
        for c in r["checks"]:
            print(f"   [{'x' if c.passed else ' '}] {c.number}. {c.criterion}: {c.value}")
    finally:
        ledger.close()


if __name__ == "__main__":
    main()
