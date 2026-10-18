"""Paper trial 1: E2 x3 + V2 x2 in one paper account, on NSE's own daily files, as defined in
docs/research/trial1-definition.md.

    python -m trader.research.trial daily     # scheduled each evening after the forward tests
    python -m trader.research.trial status    # the account: open positions, closed trades, each part against its backtest
    python -m trader.research.trial look      # forward test 4 on the trial's trades: informational any time, a decision each January

E2 (round 10: drift after a strong results reaction) holds up to 3 positions and V2 (round 9: volatility-adjusted
mid-cap momentum, monthly) up to 2, one position per stock, with the risk engine's sizes (0.5% of equity at risk), its
kill switch (20R) and the gate's decay rule for each part. Signals, entries, exits and brakes go into an append-only
ledger (state/trial1.db) as they happen; nothing recorded is decided again. Research only: nothing here can place an
order or change a strategy's status in the gate. The bunch was chosen after seeing its history, so its backtest is not
evidence; its future trades are judged by forward test 4 (docs/research/forward4-preregistration.md), against the
project's criteria and a random baseline recorded here for every closed trade.
"""
from __future__ import annotations

import argparse
import html
import json
import logging
import sqlite3
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import requests

from trader.config import ROOT, load_settings
from trader.gate import Check, DecayThresholds, Evidence, decay_check, save_evidence
from trader.logging_setup import configure_logging, make_console_utf8
from trader.research import forward2, forward3, round8, round9, round10
from trader.research.datasets import text_sha256

log = logging.getLogger(__name__)
IST = ZoneInfo("Asia/Kolkata")
DEFINITION = ROOT / "docs" / "research" / "trial1-definition.md"
DEFINITION_SHA256 = "ec1e9ace330124b9b4552ea41e1615f75b859c3621aef69a13a674c7c16a2084"  # pinned 2026-10-17 21:00 IST
FORWARD4 = ROOT / "docs" / "research" / "forward4-preregistration.md"
FORWARD4_SHA256 = "4e7c3e27d9b52a8887030ddb1698eed2c6a81e38a36dde8f54ef8ac118509247"  # pinned 2026-10-18 12:24 IST
LOOKS = ROOT / "docs" / "research"
FIRST_ENTRY = date(2026, 10, 22)  # forward test 4 judges trades entered from here
FIRST_DECISION_YEAR, RETIRE_FROM_YEAR, LAST_YEAR = 2028, 2029, 2036
LEDGER = ROOT / "state" / "trial1.db"
STATUS = ROOT / "state" / "trial1-status.md"
CAPITAL, RISK = 1_000_000, 0.005
PLACES = {"E2": 3, "V2": 2}
STOPS = {"E2": round10.STOP, "V2": round8.STOP}
RESEARCH_WIN = {"E2": 0.550, "V2": 0.459}  # the gate's decay rule compares the last 50 trades with these
BACKTEST = {"E2": "54.5% winners, +1.7R a year (189 trades)", "V2": "45.2% winners, +5.1R a year (314 trades)"}  # 2013-2026
FIRST_V2_SIGNAL = date(2026, 10, 30)  # the first month-end of the trial
RANKED = 20  # V2: the month's ranked list kept in the ledger (replacements for held stocks come from it)
KILL_R = 20.0
DECAY = DecayThresholds()
TAG = "<b>[PAPER TRIAL 1 · paper only]</b>"
TABLES = ("signals", "decisions", "trades", "brakes", "pools", "runs", "notices")
SCHEMA = """
CREATE TABLE IF NOT EXISTS signals (id INTEGER PRIMARY KEY, part TEXT NOT NULL, sid TEXT NOT NULL, signal_date TEXT NOT NULL,
    rank INTEGER, strength REAL NOT NULL, tier TEXT NOT NULL, late INTEGER NOT NULL, recorded_at TEXT NOT NULL,
    UNIQUE (part, sid, signal_date));
CREATE TABLE IF NOT EXISTS decisions (id INTEGER PRIMARY KEY, part TEXT NOT NULL, sid TEXT NOT NULL, signal_date TEXT NOT NULL,
    entry_date TEXT NOT NULL, status TEXT NOT NULL, recorded_at TEXT NOT NULL, UNIQUE (part, sid, signal_date));
CREATE TABLE IF NOT EXISTS trades (id INTEGER PRIMARY KEY, part TEXT NOT NULL, sid TEXT NOT NULL, signal_date TEXT NOT NULL,
    tier TEXT NOT NULL, entry_date TEXT NOT NULL, entry_price REAL, exit_date TEXT NOT NULL, exit_price REAL, gross REAL NOT NULL,
    net REAL NOT NULL, cost REAL NOT NULL, r REAL NOT NULL, outcome TEXT NOT NULL, gapped INTEGER NOT NULL,
    recorded_at TEXT NOT NULL, UNIQUE (part, sid, signal_date));
CREATE TABLE IF NOT EXISTS brakes (id INTEGER PRIMARY KEY, scope TEXT UNIQUE NOT NULL, kind TEXT NOT NULL,
    effective_date TEXT NOT NULL, reason TEXT NOT NULL, recorded_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS pools (id INTEGER PRIMARY KEY, part TEXT NOT NULL, month_end TEXT NOT NULL, tier TEXT NOT NULL,
    entry_date TEXT NOT NULL, pool TEXT NOT NULL, recorded_at TEXT NOT NULL, UNIQUE (part, month_end, tier, entry_date));
CREATE TABLE IF NOT EXISTS runs (id INTEGER PRIMARY KEY, at TEXT NOT NULL, status TEXT NOT NULL, detail TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS notices (id INTEGER PRIMARY KEY, key TEXT NOT NULL, at TEXT NOT NULL, sent INTEGER NOT NULL);
CREATE UNIQUE INDEX IF NOT EXISTS notices_sent_once ON notices (key) WHERE sent = 1;
"""
for _table in TABLES:
    SCHEMA += (f"CREATE TRIGGER IF NOT EXISTS {_table}_no_update BEFORE UPDATE ON {_table} BEGIN SELECT RAISE(ABORT, "
               f"'the trial ledger is append-only'); END;\n"
               f"CREATE TRIGGER IF NOT EXISTS {_table}_no_delete BEFORE DELETE ON {_table} BEGIN SELECT RAISE(ABORT, "
               f"'the trial ledger is append-only'); END;\n")


def check_definition() -> str:
    digest = text_sha256(DEFINITION)
    if digest != DEFINITION_SHA256:
        raise SystemExit(f"{DEFINITION.name} changed after it was pinned (sha256 {digest}); define a new trial instead.")
    return digest


def check_forward4() -> str:
    digest = text_sha256(FORWARD4)
    if digest != FORWARD4_SHA256:
        raise SystemExit(f"{FORWARD4.name} changed after it was pinned (sha256 {digest}); "
                         "pre-register a new forward test instead of editing this one.")
    return digest


# ----------------------------------------------------------------------------------------------- ledger
class Ledger:
    """The trial's paper ledger, apart from every trading record."""

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

    def add_signal(self, part: str, sid: str, signal: date, rank, strength: float, tier: str, late: bool, at: datetime) -> None:
        self.conn.execute("INSERT INTO signals (part, sid, signal_date, rank, strength, tier, late, recorded_at) "
                          "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                          (part, sid, signal.isoformat(), rank, strength, tier, int(late), at.isoformat()))

    def add_decision(self, part: str, sid: str, signal: date, entry: date, status: str, at: datetime) -> None:
        self.conn.execute("INSERT INTO decisions (part, sid, signal_date, entry_date, status, recorded_at) "
                          "VALUES (?, ?, ?, ?, ?, ?)", (part, sid, signal.isoformat(), entry.isoformat(), status, at.isoformat()))

    def add_trade(self, part: str, sid: str, signal: date, tier: str, t: dict, at: datetime) -> None:
        self.conn.execute(
            "INSERT INTO trades (part, sid, signal_date, tier, entry_date, entry_price, exit_date, exit_price, gross, net, cost, "
            "r, outcome, gapped, recorded_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (part, sid, signal.isoformat(), tier, t["entry_date"].isoformat(), t["entry_price"], t["exit_date"].isoformat(),
             t["exit_price"], t["gross"], t["net"], t["cost"], t["net"] / STOPS[part], t["outcome"], int(t["gapped"]),
             at.isoformat()))

    def add_brake(self, scope: str, kind: str, effective: date, reason: str, at: datetime) -> None:
        self.conn.execute("INSERT INTO brakes (scope, kind, effective_date, reason, recorded_at) VALUES (?, ?, ?, ?, ?)",
                          (scope, kind, effective.isoformat(), reason, at.isoformat()))

    def has_pool(self, part: str, month_end: date, tier: str, entry: date) -> bool:
        return self.conn.execute("SELECT 1 FROM pools WHERE part = ? AND month_end = ? AND tier = ? AND entry_date = ?",
                                 (part, month_end.isoformat(), tier, entry.isoformat())).fetchone() is not None

    def add_pool(self, part: str, month_end: date, tier: str, entry: date, pool: list[float], at: datetime) -> None:
        self.conn.execute("INSERT INTO pools (part, month_end, tier, entry_date, pool, recorded_at) VALUES (?, ?, ?, ?, ?, ?)",
                          (part, month_end.isoformat(), tier, entry.isoformat(),
                           json.dumps([round(float(x), 8) for x in pool]), at.isoformat()))

    def add_run(self, at: datetime, status: str, detail: str) -> None:
        self.conn.execute("INSERT INTO runs (at, status, detail) VALUES (?, ?, ?)", (at.isoformat(), status, detail[:2000]))

    def sent(self, key: str) -> bool:
        return self.conn.execute("SELECT 1 FROM notices WHERE key = ? AND sent = 1", (key,)).fetchone() is not None

    def add_notice(self, key: str, at: datetime, sent: bool) -> None:
        self.conn.execute("INSERT INTO notices (key, at, sent) VALUES (?, ?, ?)", (key, at.isoformat(), int(sent)))


class _ReadOnly:
    """The ledger, answering questions but recording nothing (for `status`)."""

    def __init__(self, ledger: Ledger):
        self._ledger, self._extra = ledger, {name: [] for name in TABLES}

    def table(self, name: str) -> pd.DataFrame:
        frame = self._ledger.table(name)
        return pd.concat([frame, pd.DataFrame(self._extra[name])], ignore_index=True) if self._extra[name] else frame

    def add_signal(self, part, sid, signal, rank, strength, tier, late, at) -> None:
        self._extra["signals"].append({"part": part, "sid": sid, "signal_date": signal.isoformat(), "rank": rank,
                                       "strength": strength, "tier": tier, "late": int(late)})

    def add_decision(self, part, sid, signal, entry, status, at) -> None:
        self._extra["decisions"].append({"part": part, "sid": sid, "signal_date": signal.isoformat(),
                                         "entry_date": entry.isoformat(), "status": status})

    def add_trade(self, part, sid, signal, tier, t, at) -> None:
        self._extra["trades"].append({"part": part, "sid": sid, "signal_date": signal.isoformat(), "tier": tier,
                                      "entry_date": t["entry_date"].isoformat(), "entry_price": t["entry_price"],
                                      "exit_date": t["exit_date"].isoformat(), "exit_price": t["exit_price"],
                                      "gross": t["gross"], "net": t["net"], "cost": t["cost"], "r": t["net"] / STOPS[part],
                                      "outcome": t["outcome"], "gapped": int(t["gapped"])})

    def add_brake(self, scope, kind, effective, reason, at) -> None:
        self._extra["brakes"].append({"scope": scope, "kind": kind, "effective_date": effective.isoformat(), "reason": reason})

    def has_pool(self, *args) -> bool:
        return True

    def add_pool(self, *args, **kwargs) -> None:
        pass

    def __getattr__(self, name):
        return getattr(self._ledger, name)


# ---------------------------------------------------------------------------------------------- signals
def v2_lists(sessions: list[date], secs: dict, table: pd.DataFrame) -> dict[int, pd.DataFrame]:
    """Each known month-end from 30 Oct 2026: the eligible stocks of ranks 101-300, highest volatility-adjusted momentum
    first (ties by symbol), the first 20 kept."""
    ends = forward2.month_ends_known(sessions)
    wanted = [i for i in ends if sessions[i] >= FIRST_V2_SIGNAL]
    if not wanted:
        return {}
    scored = round9.add_scores(table[table["i"].isin(wanted)], secs)
    lo, hi = round8.TIERS["N2"]
    out = {}
    for i in wanted:
        tier = scored[(scored["i"] == i) & scored["rank"].between(lo, hi)].dropna(subset=["score_V"])
        out[i] = tier.sort_values(["score_V", "sid"], ascending=[False, True]).head(RANKED)[["sid", "score_V"]]
    return out


def record_signals(ledger, sessions: list[date], e2: pd.DataFrame, v2: dict[int, pd.DataFrame], now: datetime,
                   events: dict) -> None:
    """New signals, once each. One first seen after its entry session was already decided is late: not a candidate."""
    n = len(sessions)
    recorded = ledger.table("signals")
    known = set(zip(recorded["part"], recorded["sid"], recorded["signal_date"])) if len(recorded) else set()
    decided = set(ledger.table("decisions")["entry_date"])
    for row in e2.itertuples(index=False):
        signal = sessions[row.signal]
        if ("E2", row.sid, signal.isoformat()) in known:
            continue
        late = row.signal + 1 < n and sessions[row.signal + 1].isoformat() in decided
        ledger.add_signal("E2", row.sid, signal, None, float(row.abnormal), row.tier, late, now)
        events["signals"].append(("E2", row.sid, signal, float(row.abnormal), late))
    for i, ranked in v2.items():
        signal = sessions[i]
        if any(("V2", s, signal.isoformat()) in known for s in ranked["sid"]):
            continue
        late = i + 1 < n and sessions[i + 1].isoformat() in decided
        for rank, (sid, score) in enumerate(zip(ranked["sid"], ranked["score_V"]), start=1):
            ledger.add_signal("V2", sid, signal, rank, float(score), "N2", late, now)
        events["signals"].append(("V2", ", ".join(ranked["sid"].head(PLACES["V2"])), signal, np.nan, late))


# ------------------------------------------------------------------------------------------------ account
def e2_position(sec, e: int, n: int, tier: str) -> dict:
    t = forward3.position(sec, e, n)
    return forward3.with_costs(t, tier) if t["outcome"] in forward3.CLOSED else t


def v2_position(sec, e: int, x0: int, n: int) -> dict:
    t = forward2.trade(sec, e, x0, n)
    if t["outcome"] in forward2.CLOSED:
        net, cost = forward2.net_of_costs(t)
        t = {**t, "net": net, "cost": cost}
    return t


def free_from(outcome: str, exit_i: int) -> int:
    return exit_i + 1 if outcome in ("stop", "no further rows") else exit_i


def brake_states(trades: pd.DataFrame) -> dict:
    """("Brakes") From closed trades in exit order: the account's kill switch and each part's decay rule. Returns
    {scope: (kind, effective exit date, reason)} for brakes that fired, at the trade that fired them."""
    out = {}
    if trades.empty:
        return out
    t = trades.sort_values(["exit_date", "id"] if "id" in trades else ["exit_date"]).reset_index(drop=True)
    path = t["r"].cumsum().to_numpy()
    peak = np.maximum.accumulate(np.r_[0.0, path])[1:]
    hit = np.flatnonzero(peak - path >= KILL_R)
    if len(hit):
        j = int(hit[0])
        out["account"] = ("kill switch", t["exit_date"].iat[j], f"closed trades fell {peak[j] - path[j]:.1f}R below their peak")
    for part in PLACES:
        own = t[t["part"] == part]
        for j in range(1, len(own) + 1):
            verdict, reason = decay_check(own["r"].iloc[:j].to_numpy(), RESEARCH_WIN[part], DECAY)
            if verdict != "keep":
                out[part] = ("paused" if verdict == "demote" else "stopped", own["exit_date"].iat[j - 1], reason)
                break
    return out


def update(ledger, sessions: list[date], secs: dict, e2: pd.DataFrame, v2: dict[int, pd.DataFrame], now: datetime) -> dict:
    """Record what has happened since the last update: new signals, entry decisions, closed positions, brakes.
    Recorded rows are never recomputed."""
    n = len(sessions)
    index = {d.isoformat(): i for i, d in enumerate(sessions)}
    events = {"signals": [], "entries": [], "closed": [], "open": [], "brakes": [], "waiting": []}
    record_signals(ledger, sessions, e2, v2, now, events)
    sig = ledger.table("signals")
    if sig.empty:
        return events
    sig = sig[sig["late"] == 0].assign(entry_i=lambda f: [index[d] + 1 if d in index else n for d in f["signal_date"]])
    decisions = ledger.table("decisions")
    status_of = {(p, s, d): st for p, s, d, st in zip(decisions["part"], decisions["sid"], decisions["signal_date"],
                                                       decisions["status"])}
    closed = ledger.table("trades")
    closed_of = {(p, s, d): (o, ed) for p, s, d, o, ed in zip(closed["part"], closed["sid"], closed["signal_date"],
                                                              closed["outcome"], closed["exit_date"])}
    brakes_seen = set(ledger.table("brakes")["scope"])
    ends = forward2.month_ends_known(sessions)
    places = {part: [0] * k for part, k in PLACES.items()}
    held: dict[str, int] = {}

    def exit_session(signal_i: int) -> int:
        later = [j for j in ends if j > signal_i]
        return later[0] + 1 if later else n + 1

    def blocked(part: str, entry: date) -> bool:
        states = brake_states(ledger.table("trades"))
        for scope in ("account", part):
            if scope in states:
                kind, when, reason = states[scope]
                if scope not in brakes_seen:
                    ledger.add_brake(scope, kind, date.fromisoformat(when), reason, now)
                    brakes_seen.add(scope)
                    events["brakes"].append((scope, kind, when, reason))
                if when < entry.isoformat():
                    return True
        return False

    def take(part: str, c, entry_i: int, status: str) -> None:
        key = (part, c.sid, c.signal_date)
        k = int(np.argmin(places[part]))
        sec = secs.get(c.sid)
        if key in closed_of:
            outcome, exit_date = closed_of[key]
            free = free_from(outcome, index[exit_date]) if exit_date in index else n
        elif sec is None:
            free = n
        else:
            t = (e2_position(sec, entry_i, n, c.tier) if part == "E2"
                 else v2_position(sec, entry_i, exit_session(entry_i - 1), n))
            if t["outcome"] in forward3.CLOSED:
                record = {**t, "entry_date": sessions[entry_i], "entry_price": t["entry_raw"],
                          "exit_date": sessions[t["exit_i"]], "exit_price": t["exit_raw"]}
                ledger.add_trade(part, c.sid, date.fromisoformat(c.signal_date), c.tier, record, now)
                events["closed"].append((part, c.sid, sessions[entry_i], record))
                free = free_from(t["outcome"], t["exit_i"])
            else:
                events["open"].append((part, c.sid, sessions[entry_i], t))
                free = n
        places[part][k] = max(places[part][k], free)
        held[c.sid] = free

    for entry_i in sorted(sig["entry_i"].unique()):
        if entry_i >= n:
            events["waiting"] += [(r.part, r.sid, r.signal_date) for r in sig[sig["entry_i"] == entry_i].itertuples(index=False)]
            continue
        entry = sessions[entry_i]
        group = sig[sig["entry_i"] == entry_i]
        # E2 first: strongest abnormal reaction first, ties by symbol.
        for c in group[group["part"] == "E2"].sort_values(["strength", "sid"], ascending=[False, True]).itertuples(index=False):
            key = ("E2", c.sid, c.signal_date)
            status = status_of.get(key)
            if status is None:
                sec = secs.get(c.sid)
                if held.get(c.sid, -1) > entry_i:
                    status = "already held"
                elif sec is None or not round8.enterable(sec, entry_i):
                    status = "not bought"
                elif min(places["E2"]) > entry_i:
                    status = "no free place"
                elif blocked("E2", entry):
                    status = "brake"
                else:
                    status = "bought"
                ledger.add_decision("E2", c.sid, date.fromisoformat(c.signal_date), entry, status, now)
                events["entries"].append(("E2", c.sid, entry, status))
            if status == "bought":
                take("E2", c, entry_i, status)
        # V2: down the month's ranked list until its places are used; a pick that can't be bought keeps its place in cash.
        used = 0
        for c in group[group["part"] == "V2"].sort_values("rank").itertuples(index=False):
            key = ("V2", c.sid, c.signal_date)
            status = status_of.get(key)
            if status is None:
                if used >= PLACES["V2"]:
                    break
                sec = secs.get(c.sid)
                if held.get(c.sid, -1) > entry_i:
                    status = "already held"
                elif min(places["V2"]) > entry_i:
                    status = "no free place"
                elif blocked("V2", entry):
                    status = "brake"
                elif sec is None or not round8.enterable(sec, entry_i):
                    status = "not bought"
                else:
                    status = "bought"
                ledger.add_decision("V2", c.sid, date.fromisoformat(c.signal_date), entry, status, now)
                events["entries"].append(("V2", c.sid, entry, status))
            if status in ("no free place", "brake"):
                break  # the month's later picks are not candidates
            if status in ("bought", "not bought"):
                used += 1
                if status == "bought":
                    take("V2", c, entry_i, status)
                else:  # "Not bought": the place stays in cash until the month's exit
                    k = int(np.argmin(places["V2"]))
                    places["V2"][k] = max(places["V2"][k], exit_session(entry_i - 1))
    blocked_now = brake_states(ledger.table("trades"))
    for scope, (kind, when, reason) in blocked_now.items():
        if scope not in brakes_seen:
            ledger.add_brake(scope, kind, date.fromisoformat(when), reason, now)
            events["brakes"].append((scope, kind, when, reason))
    return events


def record_pools(ledger, sessions: list[date], secs: dict, universe: round10.Universe, now: datetime, events: dict) -> None:
    """(Forward test 4, "The random baseline") Once every member's outcome has closed: for an E2 trade, every member of
    its tier at the month-end that defined the universe on its signal session that could be bought at its entry open,
    held by E2's rules; for a V2 trade, every member of ranks 101-300 at its signal month-end that could be bought at
    its entry open, held by V2's rules."""
    trades = ledger.table("trades")
    if trades.empty:
        return
    n = len(sessions)
    index = {d.isoformat(): i for i, d in enumerate(sessions)}
    ends = forward2.month_ends_known(sessions)
    for part, tier, signal, entry in trades.drop_duplicates(["part", "tier", "entry_date"])[
            ["part", "tier", "signal_date", "entry_date"]].itertuples(index=False):
        if signal not in index or entry not in index:
            continue
        s_i, e = index[signal], index[entry]
        i_me, members = universe.at(s_i) if part == "E2" else (s_i, universe.members.get(s_i, {}))
        if i_me is None or ledger.has_pool(part, sessions[i_me], tier, sessions[e]):
            continue
        names = [s for s, t in members.items() if t == tier and s in secs and round8.enterable(secs[s], e)]
        if part == "E2":
            outcomes = [e2_position(secs[s], e, n, tier) for s in names]
        else:
            later = [j for j in ends if j > s_i]
            if not later:
                continue
            outcomes = [v2_position(secs[s], e, later[0] + 1, n) for s in names]
        if outcomes and all(o["outcome"] in forward3.CLOSED for o in outcomes):
            ledger.add_pool(part, sessions[i_me], tier, sessions[e], [o["net"] for o in outcomes], now)
            events.setdefault("pools", []).append((part, sessions[i_me], tier, sessions[e], len(outcomes)))


def forward4_trades(ledger, end: date | None = None) -> pd.DataFrame:
    """The trial's closed trades entered from 22 Oct 2026, as round 10's criteria want them."""
    t = ledger.table("trades")
    if len(t):
        keep = t["entry_date"] >= FIRST_ENTRY.isoformat()
        if end is not None:
            keep &= t["entry_date"] <= end.isoformat()
        t = t[keep]
    if t.empty:
        return t
    t = t.copy()
    t["entry_date"] = pd.to_datetime(t["entry_date"]).dt.date
    t["signal_date"] = t["entry_date"]  # halves and years use entry dates
    t["exit_date"] = pd.to_datetime(t["exit_date"]).dt.date
    t["signal_i"] = [d.year * 12 + d.month for d in t["entry_date"]]  # clusters: entry months
    t["ticker"], t["R"] = t["sid"], t["r"]
    t["stopped"], t["gapped"] = t["outcome"] == "stop", t["gapped"].astype(bool)
    return t.reset_index(drop=True)


def judge(ledger, as_of: date) -> dict:
    """Forward test 4 at a look on `as_of`: the criteria and decision ("Criteria at a decision look", "Decisions")."""
    look, end = forward3.look_number(as_of), forward3.cutoff(as_of)
    trades = forward4_trades(ledger, end)
    if trades.empty:
        return {"look": look, "cutoff": end, "trades": trades, "decision": "WAITING", "checks": [], "raw_p": np.nan}
    pt = ledger.table("pools")
    pools = {(0, f"{p}:{tier}", date.fromisoformat(e).toordinal()): np.asarray(json.loads(v))
             for p, tier, e, v in zip(pt["part"], pt["tier"], pt["entry_date"], pt["pool"])}
    base = pd.DataFrame({"i_me": 0, "tier": trades["part"] + ":" + trades["tier"], "net": trades["net"],
                         "entry_i": [d.toordinal() for d in trades["entry_date"]]})
    covered = base[[(0, k, e) in pools for k, e in zip(base["tier"], base["entry_i"])]]
    random_mean, raw_p = round10.baseline(covered, pools) if len(covered) else (np.nan, 1.0)
    alpha = 0.05 / max(look, 1)
    checks, stats = round8.criteria(trades, (FIRST_ENTRY, end), raw_p * max(look, 1), raw_p)
    out = []
    for c in checks:
        if c.number == 12:
            continue
        if c.number == 5:
            c = Check(5, f"Beats the random baseline: p below 0.05/{max(look, 1)} = {alpha:.4f}", f"{raw_p:.5f}",
                      bool(raw_p < alpha))
        elif c.number == 11:
            c = Check(11, "Cluster-robust t-statistic (entry months as clusters) at least 2.0", c.value, c.passed)
        out.append(c)
    if stats["max_drawdown_r"] > KILL_R:
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
            "random_mean": random_mean, "covered": len(covered), "decision": decision}


def evidence_for(r: dict, digest: str) -> Evidence:
    s = r["stats"]
    return Evidence(
        strategy_id="B1F", kind="research", decision=r["decision"], generated=date.today().isoformat(),
        source="docs/research/forward4-look-*.md (python -m trader.research.trial look)",
        checks=tuple({"number": c.number, "criterion": c.criterion, "value": c.value, "passed": c.passed}
                     for c in r["checks"]),
        stats={"evaluation_span": f"{FIRST_ENTRY} to {r['cutoff']}", "holdout_trades": s["trades"],
               "holdout_win_rate": s["win_rate"], "holdout_mean_net": s["mean_net"], "holdout_sd_net": s["sd_net"],
               "holdout_profit_factor": s["profit_factor"], "holdout_t": s["t"], "holdout_t_clustered": s["t_clustered"],
               "p_random_raw": r["raw_p"], "round_trip_cost": round8.ROUND_TRIP["N2"], "max_drawdown_r": s["max_drawdown_r"],
               "look": r["look"]},
        preregistration_sha256=digest)


def write_look(r: dict, digest: str, as_of: date) -> None:
    lines = [f"# Forward test 4: look on {as_of}", "",
             f"Look {r['look'] or 'informational'}; paper trial 1's trades entered {FIRST_ENTRY} to {r['cutoff']}; "
             f"pre-registration SHA-256 `{digest[:16]}...`.", "", f"**Decision: {r['decision']}.**", ""]
    if r["checks"]:
        lines += [f"Random picks with the same rules earned {_pct(r['random_mean'], 3)} a trade "
                  f"({r['covered']} of {len(r['trades'])} trades have a recorded pool).", "",
                  "| # | Criterion | Value | Result |", "|---|---|---|---|"]
        lines += [f"| {c.number} | {c.criterion} | {c.value} | {'pass' if c.passed else '**fail**'} |" for c in r["checks"]]
    (LOOKS / f"forward4-look-{as_of}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


# ----------------------------------------------------------------------------------------------- reports
def _pct(v, digits: int = 1) -> str:
    return f"{100 * v:+.{digits}f}%" if v is not None and not pd.isna(v) else "-"


def account(trades: pd.DataFrame, events: dict | None = None) -> dict:
    closed_r = float(trades["r"].sum()) if len(trades) else 0.0
    open_r = sum(t["mark"] / STOPS[p] for p, _, _, t in (events or {}).get("open", []) if "mark" in t)
    return {"closed_r": closed_r, "open_r": open_r, "equity": CAPITAL * (1 + RISK * (closed_r + open_r))}


def performance(verdict: dict | None) -> dict | None:
    """Forward test 4's headline numbers so far, after costs (None before the first closed trade)."""
    if not verdict or not verdict.get("stats"):
        return None
    s = verdict["stats"]
    return {"trades": s["trades"], "win_rate": s["win_rate"], "mean_net": s["mean_net"], "avg_win": s["avg_win"],
            "avg_loss": s["avg_loss"], "profit_factor": s["profit_factor"], "drawdown_r": s["max_drawdown_r"], "t": s["t"],
            "t_clustered": s["t_clustered"], "random_mean": verdict["random_mean"], "p": verdict["raw_p"],
            "covered": verdict["covered"], "passing": sum(c.passed for c in verdict["checks"]), "of": len(verdict["checks"]),
            "decision": verdict["decision"]}


def performance_text(perf: dict) -> str:
    return (f"{perf['trades']} closed trade(s), {100 * perf['win_rate']:.1f}% winners, {_pct(perf['mean_net'], 2)} a trade after "
            f"costs (average win {_pct(perf['avg_win'])}, average loss {_pct(perf['avg_loss'])}, profit factor "
            f"{perf['profit_factor']:.2f}), drawdown {perf['drawdown_r']:.1f}R; random picks {_pct(perf['random_mean'], 2)} a "
            f"trade, p {perf['p']:.4f} ({perf['covered']} trades compared); {perf['passing']} of {perf['of']} criteria passing")


def comparison_messages(events: dict, trades: pd.DataFrame, pools: pd.DataFrame) -> list[tuple[str, str]]:
    """("Ensure every random-pick comparison is logged") One message per random-pick pool recorded this run: the trial's
    trades with that part, tier and entry open, against the pool's mean."""
    out = []
    for part, month_end, tier, entry, n in events.get("pools", []):
        row = pools[(pools["part"] == part) & (pools["tier"] == tier) & (pools["entry_date"] == entry.isoformat())]
        if row.empty:
            continue
        mean = float(np.mean(json.loads(row["pool"].iat[0])))
        mine = trades[(trades["part"] == part) & (trades["tier"] == tier) & (trades["entry_date"] == entry.isoformat())]
        names = "; ".join(f"{html.escape(s)} {_pct(net)}" for s, net in zip(mine["sid"], mine["net"]))
        beat = float(mine["net"].mean()) - mean if len(mine) else np.nan
        out.append((f"pool {part} {tier} {entry}", f"{TAG} Random-pick comparison, {part} bought {entry:%d %b %Y} ({tier}): {names}. "
                    f"{n} random stocks from the same tier bought that open with the same rules: {_pct(mean)} on average "
                    f"(the trial {'beat' if beat > 0 else 'trailed'} them by {_pct(abs(beat))}). After costs."))
    return out


def messages(events: dict, trades: pd.DataFrame, latest: date, pools: pd.DataFrame | None = None,
             verdict: dict | None = None) -> list[tuple[str, str]]:
    out = []
    for part, sid, signal, strength, late in events["signals"]:
        if late or signal != latest:
            continue
        what = (f"results reaction {_pct(strength)} vs the market" if part == "E2" else "this month's top picks")
        out.append((f"signal {part} {sid} {signal}", f"{TAG} {part} signal at the {signal:%d %b %Y} close: {html.escape(sid)} "
                    f"({what}). Bought in paper at the next open if its part has a free place. Research, not a trading signal."))
    by_entry: dict = {}
    for part, sid, entry, status in events["entries"]:
        by_entry.setdefault(entry, []).append(f"{part} {html.escape(sid)}: {status}")
    for entry, rows in by_entry.items():
        out.append((f"entries {entry} {'|'.join(rows)}", f"{TAG} Paper entries at the {entry:%d %b %Y} open: " + "; ".join(rows) + "."))
    for part, sid, entry, record in events["closed"]:
        out.append((f"closed {part} {sid} {entry}", f"{TAG} Closed {part} {html.escape(sid)} (bought {entry:%d %b %Y}): "
                    f"{_pct(record['net'])} net, {record['net'] / STOPS[part]:+.2f}R ({record['outcome']}, {record['exit_date']:%d %b %Y})."))
    for scope, kind, when, reason in events["brakes"]:
        out.append((f"brake {scope}", f"{TAG} Brake: {'the account' if scope == 'account' else scope} {kind} from the session "
                    f"after {when} ({html.escape(reason)}). As defined; nothing is changed."))
    if len(trades) and latest.day <= 7:
        month = (latest.replace(day=1) - pd.Timedelta(days=1))
        done = trades[[d[:7] == f"{month:%Y-%m}" for d in trades["exit_date"]]]
        if len(done):
            perf = performance(verdict)
            out.append((f"month {month:%Y-%m}", f"{TAG} {month:%B %Y}: {len(done)} closed trade(s), {done['r'].sum():+.2f}R; "
                        f"the account {_pct(RISK * trades['r'].sum())} since the start on closed trades."
                        + (f" Forward test 4 so far: {performance_text(perf)}; decision {perf['decision']} (decisions only at "
                           "the January looks from 2028)." if perf else "")))
    if pools is not None and len(trades):
        out += comparison_messages(events, trades, pools)
    return out


def write_status(ledger, events: dict | None, now: datetime, verdict: dict | None = None) -> str:
    trades, brakes = ledger.table("trades"), ledger.table("brakes")
    acct = account(trades, events)
    lines = ["# Paper trial 1: status (E2 x3 + V2 x2)", "",
             f"Updated {now.astimezone(IST):%Y-%m-%d %H:%M} IST by `python -m trader.research.trial`, as defined in "
             "docs/research/trial1-definition.md. Paper only and not evidence: nothing here is a trade or can place one, and "
             "no strategy's status changes because of it.", "",
             f"Account: Rs {acct['equity']:,.0f} (closed trades {acct['closed_r']:+.2f}R, open positions {acct['open_r']:+.2f}R; "
             "0.5% of Rs 10,00,000 at risk per position).", ""]
    if verdict is not None:
        lines += [f"Forward test 4 (these trades against the project's criteria, decisions each January from 2028): "
                  f"{len(verdict['trades'])} closed trade(s) judged so far; now {verdict['decision']}"
                  + (f", {sum(c.passed for c in verdict['checks'])} of {len(verdict['checks'])} criteria passing"
                     if verdict["checks"] else "")
                  + ". Real money stays NO TRADE unless every criterion passes and the approval stages follow.", ""]
    perf = performance(verdict)
    if perf:
        lines += ["| Forward test 4 so far (after costs) | Value |", "|---|---:|",
                  f"| Closed trades | {perf['trades']} |", f"| Win rate | {100 * perf['win_rate']:.1f}% |",
                  f"| Net per trade | {_pct(perf['mean_net'], 2)} |",
                  f"| Average win / average loss | {_pct(perf['avg_win'])} / {_pct(perf['avg_loss'])} |",
                  f"| Profit factor | {perf['profit_factor']:.2f} |", f"| Drawdown | {perf['drawdown_r']:.1f}R |",
                  f"| Random picks, same rules (trades compared) | {_pct(perf['random_mean'], 2)} ({perf['covered']}) |",
                  f"| p against random (bar at a look: 0.05 / L) | {perf['p']:.4f} |",
                  f"| t / month-clustered t | {perf['t']:.2f} / {perf['t_clustered']:.2f} |",
                  f"| Criteria passing (informational until January 2028) | {perf['passing']} of {perf['of']} |", ""]
    if len(brakes):
        lines += ["Brakes: " + "; ".join(f"{b.scope} {b.kind} from after {b.effective_date} ({b.reason})"
                                         for b in brakes.itertuples(index=False)), ""]
    if events and events["open"]:
        lines += ["Open positions:", "", "| Part | Stock | Entered | Mark | Stop |", "|---|---|---|---:|---:|"]
        lines += [f"| {p} | {sid} | {entry} | {_pct(t['mark'])} | {t['stop_raw']:.2f} |" for p, sid, entry, t in events["open"]]
        lines.append("")
    lines += ["| Part | Closed trades | Win rate | Net per trade | R | Backtest 2013-2026 (win rate, R a year) |",
              "|---|---:|---:|---:|---:|---|"]
    for part in PLACES:
        own = trades[trades["part"] == part]
        bt = BACKTEST[part]
        lines.append(f"| {part} | {len(own)} | {(100 * (own['net'] > 0).mean()):.1f}% | {_pct(own['net'].mean(), 2)} | "
                     f"{own['r'].sum():+.2f} | {bt} |" if len(own) else f"| {part} | 0 | - | - | - | {bt} |")
    if len(trades):
        lines += ["", "| Part | Stock | Entry | Exit | How | Net | R |", "|---|---|---|---|---|---:|---:|"]
        lines += [f"| {t.part} | {t.sid} | {t.entry_date} | {t.exit_date} | {t.outcome} | {_pct(t.net)} | {t.r:+.2f} |"
                  for t in trades.itertuples(index=False)]
    text = "\n".join(lines) + "\n"
    STATUS.parent.mkdir(parents=True, exist_ok=True)
    STATUS.write_text(text, encoding="utf-8")
    return text


# -------------------------------------------------------------------------------------------------- main
def inputs(ledger_for_notices):
    """Forward test 2's rebuilt panel, round 10's universe, E2's signals (as forward test 3 computes them) and V2's lists."""
    sessions, secs, table = forward2.load_inputs()
    universe = round10.Universe(table)
    notices_ledger = forward3.Ledger(forward3.LEDGER) if ledger_for_notices is None else ledger_for_notices
    try:
        e2 = forward3.forward_signals(forward3.all_notices(notices_ledger), sessions, secs, universe)
    finally:
        if ledger_for_notices is None:
            notices_ledger.close()
    return sessions, secs, universe, e2, v2_lists(sessions, secs, table)


def daily(now: datetime | None = None, notify: bool = True) -> int:
    from trader.notify.telegram import notifier_from_settings
    now = now or datetime.now(IST)
    ledger = Ledger()
    try:
        sessions, secs, universe, e2, v2 = inputs(None)
        events = update(ledger, sessions, secs, e2, v2, now)
        record_pools(ledger, sessions, secs, universe, now, events)
        trades = ledger.table("trades")
        verdict = judge(ledger, now.astimezone(IST).date())
        notes = messages(events, trades, sessions[-1], ledger.table("pools"), verdict)
        if verdict.get("stats") and verdict["stats"]["max_drawdown_r"] > KILL_R:  # forward test 4: "passes 20R"
            if not ledger.sent("forward 4 rejected: drawdown"):
                save_evidence(evidence_for(verdict, check_forward4()))
            notes.append(("forward 4 rejected: drawdown", f"{TAG} Forward test 4: the bunch's paper drawdown passed 20R "
                          f"({verdict['stats']['max_drawdown_r']:.1f}R): REJECTED, as pre-registered. Real money stays NO TRADE."))
        write_status(ledger, events, now, verdict)
        if notify:
            notifier = notifier_from_settings(load_settings())
            for key, text in notes:
                if not ledger.sent(key):
                    ledger.add_notice(key, now, notifier.send(text))
        acct = account(trades, events)
        detail = (f"data to {sessions[-1]}; signals {len(events['signals'])}, entries {len(events['entries'])}, closed "
                  f"{len(events['closed'])}, open {len(events['open'])}, brakes {len(events['brakes'])}, pools "
                  f"{len(events.get('pools', []))}; account Rs {acct['equity']:,.0f}; forward test 4 {verdict['decision']}")
        ledger.add_run(now, "ok", detail)
        log.info("Paper trial 1: %s", detail)
        return 0
    except (requests.RequestException, ValueError, OSError, KeyError) as exc:
        ledger.add_run(now, "failed", f"{type(exc).__name__}: {exc}")
        log.warning("Paper trial 1 failed: %s: %s", type(exc).__name__, exc)
        return 1
    finally:
        ledger.close()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Paper trial 1: E2 x3 + V2 x2 in one paper account (research only).")
    parser.add_argument("command", choices=["daily", "status", "look"])
    parser.add_argument("--no-notify", action="store_true", help="daily: don't send Telegram messages")
    args = parser.parse_args(argv)
    make_console_utf8()
    settings = load_settings()
    configure_logging(secrets=settings.secret_values(), filename="trial1.log")
    check_definition()
    digest = check_forward4()
    if args.command == "daily":
        raise SystemExit(daily(notify=not args.no_notify))
    ledger = Ledger()
    try:
        if args.command == "status":
            sessions, secs, universe, e2, v2 = inputs(None)
            view = _ReadOnly(ledger)
            now = datetime.now(IST)
            events = update(view, sessions, secs, e2, v2, now)
            print(write_status(view, events, now, judge(ledger, now.date())))
            return
        as_of = datetime.now(IST).date()
        r = judge(ledger, as_of)
        write_look(r, digest, as_of)
        if r["look"] and r["decision"] in ("PAPER", "REJECTED"):
            save_evidence(evidence_for(r, digest))
        print(f"Forward test 4, look {r['look'] or 'informational'}: {r['decision']}")
        for c in r["checks"]:
            print(f"   [{'x' if c.passed else ' '}] {c.number}. {c.criterion}: {c.value}")
    finally:
        ledger.close()


if __name__ == "__main__":
    main()
