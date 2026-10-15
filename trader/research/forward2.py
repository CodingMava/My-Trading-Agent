"""Forward test 2: round 8's N2, unchanged, on months after it was pinned, in paper mode, judged against
docs/research/forward2-preregistration.md.

    python -m trader.research.forward2 daily      # scheduled each evening: new NSE files, rebuild, record, notify
    python -m trader.research.forward2 status     # the paper ledger: picks, open positions, closed trades
    python -m trader.research.forward2 look       # informational any time; a decision look each January

N2 buys at the first session of each month the 5 NSE stocks with the best 12-1 month return among liquidity ranks
101-300, with a 10% stop, and sells at the first session of the next month. Here it runs on new sessions only, from
NSE's own daily files collected every evening. Each month's picks, fills, stops and exits go into an append-only paper
ledger (state/forward2.db) as they happen, and a month's picks are never chosen again. Nothing here can place an
order or reach the gate's paper account: it is research.
"""
from __future__ import annotations

import argparse
import html
import json
import logging
import sqlite3
from dataclasses import asdict
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import requests

from trader.config import ROOT, load_settings
from trader.gate import Check, Evidence, save_evidence
from trader.logging_setup import configure_logging, make_console_utf8
from trader.markets.calendar import CalendarCoverageError, load_calendars
from trader.research import nse_bhavcopy as nb
from trader.research import round8
from trader.research.datasets import DATA_DIR, text_sha256

log = logging.getLogger(__name__)
IST = ZoneInfo("Asia/Kolkata")
PREREGISTRATION = ROOT / "docs" / "research" / "forward2-preregistration.md"
PREREGISTRATION_SHA256 = "cea7004848820eb7bc1c0b2961958224f6aaed80d45fa3c698544ec3154c7fa4"  # pinned 2026-10-14 23:27 IST
STATUS = ROOT / "state" / "forward2-status.md"  # rewritten each evening; a look writes docs/research/forward2-look-<date>.md
LOOKS = ROOT / "docs" / "research"
DATA = DATA_DIR / "forward2"
RAW, CA, CHANGES, PANEL = DATA / "bhavcopy_raw", DATA / "corporate_actions", DATA / "symbolchange.csv", DATA / "panel"
LEDGER = ROOT / "state" / "forward2.db"
KEY = "N2"
FIRST_SIGNAL = date(2026, 10, 30)  # the last session of October 2026, the first month-end after the pin
FIRST_DECISION_YEAR, RETIRE_FROM_YEAR, LAST_YEAR = 2028, 2029, 2036
READY_AFTER = time(19, 0)  # NSE has published a session's file by the evening
WAIT_SESSIONS = 20  # a holding with no row this long after its exit date is closed at its last close
CHANGES_MAX_AGE = timedelta(days=7)
SCHEMA = """
CREATE TABLE IF NOT EXISTS picks (id INTEGER PRIMARY KEY, signal_date TEXT NOT NULL, sid TEXT NOT NULL, score REAL NOT NULL,
    tier_rank INTEGER NOT NULL, recorded_at TEXT NOT NULL, UNIQUE (signal_date, sid));
CREATE TABLE IF NOT EXISTS trades (id INTEGER PRIMARY KEY, signal_date TEXT NOT NULL, sid TEXT NOT NULL, entry_date TEXT,
    entry_price REAL, exit_date TEXT, exit_price REAL, gross REAL, net REAL, cost REAL, outcome TEXT NOT NULL,
    gapped INTEGER NOT NULL DEFAULT 0, recorded_at TEXT NOT NULL, UNIQUE (signal_date, sid));
CREATE TABLE IF NOT EXISTS months (id INTEGER PRIMARY KEY, signal_date TEXT UNIQUE NOT NULL, tier_size INTEGER NOT NULL,
    pool TEXT NOT NULL, recorded_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS runs (id INTEGER PRIMARY KEY, at TEXT NOT NULL, status TEXT NOT NULL, detail TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS notices (id INTEGER PRIMARY KEY, key TEXT NOT NULL, at TEXT NOT NULL, sent INTEGER NOT NULL);
CREATE UNIQUE INDEX IF NOT EXISTS notices_sent_once ON notices (key) WHERE sent = 1;
"""
for _table in ("picks", "trades", "months", "runs", "notices"):
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
        if name not in {"picks", "trades", "months", "runs", "notices"}:
            raise ValueError(name)
        return pd.read_sql_query(f"SELECT * FROM {name} ORDER BY id", self.conn)

    def has_picks(self, signal: date) -> bool:
        return self.conn.execute("SELECT 1 FROM picks WHERE signal_date = ?", (signal.isoformat(),)).fetchone() is not None

    def add_picks(self, signal: date, picks: list[dict], at: datetime) -> None:
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            for p in picks:
                self.conn.execute("INSERT INTO picks (signal_date, sid, score, tier_rank, recorded_at) VALUES (?, ?, ?, ?, ?)",
                                  (signal.isoformat(), p["sid"], p["score"], p["tier_rank"], at.isoformat()))
            self.conn.execute("COMMIT")
        except BaseException:
            self.conn.execute("ROLLBACK")
            raise

    def picks_for(self, signal: date) -> list[str]:
        rows = self.conn.execute("SELECT sid FROM picks WHERE signal_date = ? ORDER BY id", (signal.isoformat(),)).fetchall()
        return [r[0] for r in rows]

    def has_trade(self, signal: date, sid: str) -> bool:
        return self.conn.execute("SELECT 1 FROM trades WHERE signal_date = ? AND sid = ?",
                                 (signal.isoformat(), sid)).fetchone() is not None

    def add_trade(self, signal: date, sid: str, t: dict, at: datetime) -> None:
        self.conn.execute(
            "INSERT INTO trades (signal_date, sid, entry_date, entry_price, exit_date, exit_price, gross, net, cost, outcome, "
            "gapped, recorded_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (signal.isoformat(), sid, _iso(t.get("entry_date")), t.get("entry_price"), _iso(t.get("exit_date")),
             t.get("exit_price"), t.get("gross"), t.get("net"), t.get("cost"), t["outcome"], int(t.get("gapped", False)),
             at.isoformat()))

    def has_month(self, signal: date) -> bool:
        return self.conn.execute("SELECT 1 FROM months WHERE signal_date = ?", (signal.isoformat(),)).fetchone() is not None

    def add_month(self, signal: date, tier_size: int, pool: list[float], at: datetime) -> None:
        self.conn.execute("INSERT INTO months (signal_date, tier_size, pool, recorded_at) VALUES (?, ?, ?, ?)",
                          (signal.isoformat(), tier_size, json.dumps([round(float(x), 8) for x in pool]), at.isoformat()))

    def add_run(self, at: datetime, status: str, detail: str) -> None:
        self.conn.execute("INSERT INTO runs (at, status, detail) VALUES (?, ?, ?)", (at.isoformat(), status, detail[:2000]))

    def sent(self, key: str) -> bool:
        return self.conn.execute("SELECT 1 FROM notices WHERE key = ? AND sent = 1", (key,)).fetchone() is not None

    def add_notice(self, key: str, at: datetime, sent: bool) -> None:
        self.conn.execute("INSERT INTO notices (key, at, sent) VALUES (?, ?, ?)", (key, at.isoformat(), int(sent)))


class _ReadOnly:
    """The ledger, answering questions but recording nothing (for `status`)."""

    def __init__(self, ledger: Ledger):
        self._ledger, self._picks = ledger, {}

    def __getattr__(self, name):
        return getattr(self._ledger, name)

    def has_picks(self, signal: date) -> bool:
        return self._ledger.has_picks(signal) or signal in self._picks

    def add_picks(self, signal: date, picks: list[dict], at: datetime) -> None:
        self._picks[signal] = [p["sid"] for p in picks]

    def picks_for(self, signal: date) -> list[str]:
        return self._picks.get(signal) or self._ledger.picks_for(signal)

    def add_trade(self, *args, **kwargs) -> None:
        pass

    def add_month(self, *args, **kwargs) -> None:
        pass


def _iso(value) -> str | None:
    return value.isoformat() if isinstance(value, date) else value


# ----------------------------------------------------------------------------------------------- collect
def collect(now: datetime, http=requests, raw_dir: Path = RAW, ca_dir: Path = CA, changes: Path = CHANGES,
            have_through: date | None = None, session=None) -> dict:
    """Download every session's file NSE has published since the last one held (weekends and holidays are asked too:
    NSE answers 404 for them, and special sessions such as Muhurat trading do exist), this month's and last month's
    corporate actions, and, weekly, the list of symbol changes."""
    today = now.astimezone(IST).date()
    if have_through is None:
        have_through = nb.file_date(nb.raw_files([nb.RAW_DIR, raw_dir])[-1])
    last_day = today if now.astimezone(IST).time() >= READY_AFTER else today - timedelta(days=1)
    saved, absent = [], []
    day = have_through + timedelta(days=1)
    while day <= last_day:
        status = nb.fetch_bhavcopy(day, raw_dir, http)  # an error stops the run here; the next run starts again
        (saved if status == "saved" else absent).append(day)
        day += timedelta(days=1)
    session = session or nb.nse_session(http)
    previous = (today.replace(day=1) - timedelta(days=1))
    actions = {f"{y}-{m:02d}": nb.fetch_corporate_actions(y, m, ca_dir, session)
               for y, m in ((previous.year, previous.month), (today.year, today.month))}
    refreshed = False
    if not changes.exists() or now.timestamp() - changes.stat().st_mtime > CHANGES_MAX_AGE.total_seconds():
        nb.fetch_symbol_changes(changes, http)
        refreshed = True
    return {"saved": saved, "absent": absent, "corporate_actions": actions, "symbol_changes": refreshed}


def rebuild(raw_dir: Path = RAW, ca_dir: Path = CA, changes: Path = CHANGES, out_dir: Path = PANEL) -> bool:
    """Round 8's frozen archive plus the new files, adjusted as in round 8, into out_dir (never round 8's panel). Only
    when an input changed since the last build (a new session, a corporate-action record, a symbol change): about five
    minutes of work. Returns whether it rebuilt."""
    changes = changes if changes.exists() else nb.SYMBOL_CHANGES
    files, actions = nb.raw_files([nb.RAW_DIR, raw_dir]), nb.ca_files([nb.CA_DIR, ca_dir])
    inputs = {"raw": sorted(f.name for f in files), "corporate_actions": {f.name: nb.sha256(f) for f in actions},
              "symbol_changes": nb.sha256(changes)}
    manifest = out_dir / "manifest.json"
    if manifest.exists():
        built = json.loads(manifest.read_text(encoding="utf-8"))
        if (sorted(Path(k).name for k in built["raw"]) == inputs["raw"]
                and built["corporate_actions_sha256"] == inputs["corporate_actions"]
                and built["symbol_changes_sha256"] == inputs["symbol_changes"]):
            return False
    nb.build([nb.RAW_DIR, raw_dir], out_dir, [nb.CA_DIR, ca_dir], changes)
    return True


def load_inputs(panel_dir: Path = PANEL):
    """As round8.load_inputs, from the forward panel (which grows, so it isn't pinned)."""
    panel = nb.load_panel(panel_dir, None, columns=round8.PANEL_COLUMNS)
    isins = round8.isins_by_sid(panel, nb.load_isins(panel_dir))
    sessions = round8.session_list(panel)
    signal_idx = month_ends_known(sessions)
    table = round8.features(sessions, round8.iter_securities(panel, sessions, isins), signal_idx)
    lo, hi = round8.TIERS[KEY]
    needed = set(table.loc[table["rank"] <= hi, "sid"])
    secs = {sec.sid: sec for sec in round8.iter_securities(panel, sessions, isins, keep=needed)}
    return sessions, secs, table


def nse_calendar():
    return load_calendars()["NSE"]


def month_ends_known(sessions: list[date], calendar=None) -> list[int]:
    """Indices of month-end sessions known to be the month's last: a later session of the next month is in the data,
    or the NSE calendar says the next trading day falls in a new month (for a year it covers)."""
    ends = round8.month_ends(sessions)
    if ends and ends[-1] == len(sessions) - 1:  # the newest session: only the calendar can say it ends the month
        day = sessions[-1]
        try:
            nxt = (calendar or nse_calendar()).next_trading_day(day)
            if (nxt.year, nxt.month) == (day.year, day.month):
                ends = ends[:-1]
        except (CalendarCoverageError, KeyError, ValueError):
            ends = ends[:-1]
    return ends


# ------------------------------------------------------------------------------------------------ trades
def trade(sec: round8.Security, e: int, x0: int, n: int) -> dict:
    """One paper position: "pending" (its entry session isn't in the data yet), "open", or closed by "stop", "time",
    "time, delayed" or "no further rows" (no row for WAIT_SESSIONS after its exit date), with its prices. Prices are
    reported as NSE printed them (raw); returns are computed in adjusted prices, as in round 8."""
    if e >= n:
        return {"outcome": "pending"}
    if not round8.enterable(sec, e):
        return {"outcome": "not bought", "entry_date_i": e}
    entry = float(sec.adj_open[e])
    level = entry * (1 - round8.STOP)
    base = {"entry_i": e, "entry_raw": float(sec.raw_open[e])}
    for j in range(e, min(x0, n)):
        if sec.present[j] and sec.adj_low[j] <= level:
            fill = min(level, float(sec.adj_open[j]))
            return {**base, "outcome": "stop", "exit_i": j, "gross": fill / entry - 1, "gapped": bool(sec.adj_open[j] < level),
                    "exit_raw": fill / (float(sec.adj_open[j]) / float(sec.raw_open[j]))}
    if x0 >= n:
        last = int(sec.last_row[n - 1])
        return {**base, "outcome": "open", "mark": float(sec.adj_close[last]) / entry - 1, "stop_raw": base["entry_raw"] * 0.9}
    j = x0
    while j < n and not sec.present[j]:
        j += 1
    if j < n:
        return {**base, "outcome": "time" if j == x0 else "time, delayed", "exit_i": j, "gapped": False,
                "gross": float(sec.adj_open[j]) / entry - 1, "exit_raw": float(sec.raw_open[j])}
    if n - 1 - x0 < WAIT_SESSIONS:
        return {**base, "outcome": "open", "mark": float(sec.adj_close[int(sec.last_row[n - 1])]) / entry - 1,
                "stop_raw": base["entry_raw"] * 0.9}
    last = int(sec.last_row[n - 1])
    return {**base, "outcome": "no further rows", "exit_i": last, "gapped": False,
            "gross": float(sec.adj_close[last]) / entry - 1, "exit_raw": float(sec.raw_close[last])}


def net_of_costs(t: dict) -> tuple[float, float]:
    cost = round8.ROUND_TRIP[KEY] + (round8.SLIPPAGE[KEY] if t["outcome"] == "stop" else 0.0)
    return t["gross"] - cost, cost


CLOSED = ("stop", "time", "time, delayed", "no further rows")


def month_picks(table: pd.DataFrame, i: int) -> list[dict]:
    """("Selection") the 5 highest 12-1 scores in N2's tier at signal index i, ties by symbol."""
    lo, hi = round8.TIERS[KEY]
    tier = table[(table["i"] == i) & (table["rank"] >= lo) & (table["rank"] <= hi)]
    ranked = tier.dropna(subset=["score_12-1"]).sort_values(["score_12-1", "sid"], ascending=[False, True]).head(round8.TOP)
    return [{"sid": s, "score": float(v), "tier_rank": int(r) - lo + 1} for s, v, r in
            zip(ranked["sid"], ranked["score_12-1"], ranked["rank"])]


def update(ledger: Ledger, sessions: list[date], secs: dict, table: pd.DataFrame, now: datetime) -> dict:
    """Record what has happened since the last update: new months' picks, closed positions, closed months' random-pick
    pools. Returns the events and the open positions."""
    n = len(sessions)
    ends = month_ends_known(sessions)
    signals = [i for i in ends if sessions[i] >= FIRST_SIGNAL]
    events = {"picks": [], "closed": [], "months": [], "open": [], "pending": [], "differences": []}
    for k, i in enumerate(signals):
        signal = sessions[i]
        chosen = month_picks(table, i)
        if not ledger.has_picks(signal):
            ledger.add_picks(signal, chosen, now)
            events["picks"].append((signal, chosen))
        elif ledger.picks_for(signal) != [p["sid"] for p in chosen]:
            events["differences"].append(f"{signal}: the data now picks {[p['sid'] for p in chosen]}, the ledger kept "
                                         f"{ledger.picks_for(signal)}")
        e = i + 1
        later = [j for j in ends if j > i]
        x0 = later[0] + 1 if later else n + 1  # the session after the next month-end, when it is known
        for sid in ledger.picks_for(signal):
            if ledger.has_trade(signal, sid):
                continue
            sec = secs.get(sid)
            t = trade(sec, e, x0, n) if sec is not None else {"outcome": "pending"}
            if t["outcome"] in CLOSED:
                t["net"], t["cost"] = net_of_costs(t)
                record = {"entry_date": sessions[t["entry_i"]], "entry_price": t["entry_raw"],
                          "exit_date": sessions[t["exit_i"]], "exit_price": t["exit_raw"], **t}
                ledger.add_trade(signal, sid, record, now)
                events["closed"].append((signal, sid, record))
            elif t["outcome"] == "not bought":
                ledger.add_trade(signal, sid, {"outcome": "not bought"}, now)
                events["closed"].append((signal, sid, {"outcome": "not bought"}))
            elif t["outcome"] == "open":
                events["open"].append((signal, sid, sessions[t["entry_i"]], t))
            else:
                events["pending"].append((signal, sid))
        if not ledger.has_month(signal) and x0 <= n - 1:
            lo, hi = round8.TIERS[KEY]
            tier = table[(table["i"] == i) & (table["rank"] >= lo) & (table["rank"] <= hi)]
            outcomes = [trade(secs[s], e, x0, n) for s in tier["sid"] if s in secs and round8.enterable(secs[s], e)]
            if all(o["outcome"] in CLOSED for o in outcomes):
                pool = [net_of_costs(o)[0] for o in outcomes]
                ledger.add_month(signal, len(tier), pool, now)
                events["months"].append((signal, len(pool)))
    return events


# -------------------------------------------------------------------------------------------- the look
def ledger_trades(ledger: Ledger, cutoff: date | None = None) -> pd.DataFrame:
    """The closed trades as round 8's criteria want them."""
    t = ledger.table("trades")
    t = t[t["outcome"].isin(CLOSED)].copy()
    if cutoff is not None:
        t = t[pd.to_datetime(t["signal_date"]).dt.date <= cutoff]
    if t.empty:
        return t
    t["signal_date"] = pd.to_datetime(t["signal_date"]).dt.date
    t["exit_date"] = pd.to_datetime(t["exit_date"]).dt.date
    t["signal_i"] = t["signal_date"].map(lambda d: d.toordinal())
    t["ticker"], t["R"] = t["sid"], t["net"] / round8.STOP
    t["stopped"], t["gapped"] = t["outcome"] == "stop", t["gapped"].astype(bool)
    return t.reset_index(drop=True)


def look_number(as_of: date) -> int:
    """L at the decision look in January (2028 is look 1, 2036 look 9); 0 for any other look."""
    return as_of.year - FIRST_DECISION_YEAR + 1 if as_of.month == 1 and FIRST_DECISION_YEAR <= as_of.year <= LAST_YEAR else 0


def cutoff(as_of: date) -> date:
    return date(as_of.year - 1, 12, 31) if as_of.month == 1 else as_of


def judge(ledger: Ledger, as_of: date) -> dict:
    """The forward trades, criteria and decision at a look on `as_of` ("Criteria at a decision look", "Decisions")."""
    look, end = look_number(as_of), cutoff(as_of)
    trades = ledger_trades(ledger, end)
    months = ledger.table("months")
    pools = {date.fromisoformat(s).toordinal(): np.asarray(json.loads(p)) for s, p in zip(months["signal_date"], months["pool"])}
    if trades.empty:
        return {"look": look, "cutoff": end, "trades": trades, "decision": "WAITING", "checks": [], "raw_p": np.nan}
    covered = trades[trades["signal_i"].isin(pools)]
    random_mean, raw_p, _ = round8.baseline(covered, pools) if len(covered) else (np.nan, 1.0, None)
    alpha = 0.05 / max(look, 1)
    checks, stats = round8.criteria(trades, (FIRST_SIGNAL, end), raw_p * max(look, 1), raw_p)
    checks = [c for c in checks if c.number != 12]
    checks = [Check(5, f"Beats the random baseline: p below 0.05/{max(look, 1)} = {alpha:.4f}", f"{raw_p:.5f}",
                    bool(raw_p < alpha)) if c.number == 5 else c for c in checks]
    depth = stats["max_drawdown_r"]
    if depth > 20.0:
        decision = "REJECTED"
    elif look == 0:
        decision = "INFORMATIONAL"
    elif all(c.passed for c in checks):
        decision = "PAPER"
    elif look >= LAST_YEAR - FIRST_DECISION_YEAR + 1 or (look >= RETIRE_FROM_YEAR - FIRST_DECISION_YEAR + 1
                                                        and not stats["mean_net"] > 0):
        decision = "REJECTED"
    else:
        decision = "CONTINUE"
    return {"look": look, "cutoff": end, "trades": trades, "checks": checks, "stats": stats, "raw_p": raw_p,
            "random_mean": random_mean, "decision": decision}


def evidence_for(r: dict, digest: str) -> Evidence:
    s = r["stats"]
    return Evidence(
        strategy_id="N2F", kind="research", decision=r["decision"], generated=date.today().isoformat(),
        source="docs/research/forward2-results.md (python -m trader.research.forward2 look)",
        checks=tuple(asdict(c) for c in r["checks"]),
        stats={"evaluation_span": f"{FIRST_SIGNAL} to {r['cutoff']}", "holdout_trades": s["trades"],
               "holdout_win_rate": s["win_rate"], "holdout_mean_net": s["mean_net"], "holdout_sd_net": s["sd_net"],
               "holdout_profit_factor": s["profit_factor"], "holdout_t": s["t"], "holdout_t_clustered": s["t_clustered"],
               "p_random_raw": r["raw_p"], "round_trip_cost": round8.ROUND_TRIP[KEY], "max_drawdown_r": s["max_drawdown_r"],
               "look": r["look"]},
        preregistration_sha256=digest)


# ---------------------------------------------------------------------------------------------- reports
def _pct(v, digits: int = 2) -> str:
    return f"{100 * v:+.{digits}f}%" if v is not None and not pd.isna(v) else "-"


def messages(events: dict) -> list[tuple[str, str]]:
    """(key, text) for each event worth a Telegram message; a key is sent once."""
    out = []
    for signal, picks in events["picks"]:
        names = ", ".join(html.escape(p["sid"]) for p in picks) or "none eligible"
        out.append((f"picks {signal}", f"<b>[FORWARD TEST 2 · paper only]</b> N2's picks at the {signal:%d %b %Y} close: "
                    f"{names}. Bought in paper at the next open with a 10% stop. Research, not a trading signal."))
    by_month: dict = {}
    for signal, sid, record in events["closed"]:
        by_month.setdefault(signal, []).append((sid, record))
    for signal, rows in by_month.items():
        parts = [f"{html.escape(sid)} {_pct(r['net'], 1)} ({r['outcome']})" if "net" in r else f"{html.escape(sid)} not bought"
                 for sid, r in rows]
        out.append((f"closed {signal} {'|'.join(s for s, _ in rows)}",
                    f"<b>[FORWARD TEST 2 · paper only]</b> Closed from the {signal:%b %Y} picks: " + "; ".join(parts) + "."))
    return out


def write_status(ledger: Ledger, events: dict | None, now: datetime) -> str:
    trades = ledger_trades(ledger)
    lines = ["# Forward test 2: status", "",
             f"Updated {now:%Y-%m-%d %H:%M} IST by `python -m trader.research.forward2`, against "
             "[the pre-registration](forward2-preregistration.md). Paper only: nothing here is a trade, and nothing here "
             "can place one. First picks: at the close of 30 Oct 2026.", ""]
    picks = ledger.table("picks")
    if picks.empty:
        lines.append("No picks yet.")
    else:
        lines += ["| Signal | Picks (tier rank) |", "|---|---|"]
        for signal, g in picks.groupby("signal_date", sort=True):
            lines.append(f"| {signal} | " + ", ".join(f"{s} ({r})" for s, r in zip(g["sid"], g["tier_rank"])) + " |")
    if events and events["open"]:
        lines += ["", "Open positions:", "", "| Signal | Stock | Entered | Mark | Stop |", "|---|---|---|---:|---:|"]
        lines += [f"| {s} | {sid} | {entered} | {_pct(t['mark'], 1)} | {t['stop_raw']:.2f} |"
                  for s, sid, entered, t in events["open"]]
    if not trades.empty:
        net = trades["net"]
        lines += ["", f"Closed trades: {len(trades)}, {100 * (net > 0).mean():.1f}% winners, {_pct(net.mean())} a trade "
                  f"net; drawdown {round8.drawdown_r(round8.r_in_exit_order(trades)):.1f}R (limit 20R).", "",
                  "| Signal | Stock | Entry | Exit | How | Net |", "|---|---|---|---|---|---:|"]
        lines += [f"| {t.signal_date} | {t.sid} | {t.entry_date} | {t.exit_date} | {t.outcome} | {_pct(t.net, 1)} |"
                  for t in trades.itertuples(index=False)]
    if events and events["differences"]:
        lines += ["", "Rebuilt data that would now pick differently (the ledger keeps the original picks):", ""]
        lines += [f"- {d}" for d in events["differences"]]
    text = "\n".join(lines) + "\n"
    STATUS.parent.mkdir(parents=True, exist_ok=True)
    STATUS.write_text(text, encoding="utf-8")
    return text


def write_look(r: dict, digest: str, as_of: date) -> None:
    lines = [f"# Forward test 2: look on {as_of}", "",
             f"Look {r['look'] or 'informational'}; trades signalled {FIRST_SIGNAL} to {r['cutoff']}; pre-registration "
             f"SHA-256 `{digest[:16]}...`.", "", f"**Decision: {r['decision']}.**", ""]
    if r["checks"]:
        lines += ["| # | Criterion | Value | Result |", "|---|---|---|---|"]
        lines += [f"| {c.number} | {c.criterion} | {c.value} | {'pass' if c.passed else '**fail**'} |" for c in r["checks"]]
    (LOOKS / f"forward2-look-{as_of}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


# ------------------------------------------------------------------------------------------------- main
def daily(now: datetime | None = None, notify: bool = True) -> int:
    from trader.notify.telegram import notifier_from_settings
    now = now or datetime.now(IST)
    ledger = Ledger()
    try:
        got = collect(now)
        rebuilt = rebuild()
        sessions, secs, table = load_inputs()
        events = update(ledger, sessions, secs, table, now)
        verdict = judge(ledger, now.date())
        notes = messages(events)
        if verdict.get("stats") and verdict["stats"]["max_drawdown_r"] > 20.0:  # "Any update: ... passes 20R"
            if not ledger.sent("rejected: drawdown"):
                save_evidence(evidence_for(verdict, check_preregistration()))
            notes.append(("rejected: drawdown", "<b>[FORWARD TEST 2]</b> N2's paper drawdown passed 20R "
                          f"({verdict['stats']['max_drawdown_r']:.1f}R): REJECTED, as pre-registered. The test ends."))
        write_status(ledger, events, now)
        if notify:
            notifier = notifier_from_settings(load_settings())
            for key, text in notes:
                if not ledger.sent(key):
                    ledger.add_notice(key, now, notifier.send(text))
        detail = (f"saved {len(got['saved'])} session(s) {[str(d) for d in got['saved']]}"
                  f"{', rebuilt' if rebuilt else ''}; picks {len(events['picks'])}, "
                  f"closed {len(events['closed'])}, open {len(events['open'])}, months {len(events['months'])}"
                  + (f"; differences: {events['differences']}" if events["differences"] else ""))
        ledger.add_run(now, "ok", detail)
        log.info("Forward test 2: %s", detail)
        return 0
    except (requests.RequestException, ValueError, OSError, KeyError) as exc:
        ledger.add_run(now, "failed", f"{type(exc).__name__}: {exc}")
        log.warning("Forward test 2 failed: %s: %s", type(exc).__name__, exc)
        return 1
    finally:
        ledger.close()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Forward test 2: N2 on new months, in paper mode (research only).")
    parser.add_argument("command", choices=["daily", "status", "look"])
    parser.add_argument("--no-notify", action="store_true", help="daily: don't send Telegram messages")
    args = parser.parse_args(argv)
    make_console_utf8()
    settings = load_settings()
    configure_logging(secrets=settings.secret_values(), filename="forward2.log")
    digest = check_preregistration()
    if args.command == "daily":
        raise SystemExit(daily(notify=not args.no_notify))
    ledger = Ledger()
    try:
        if args.command == "status":
            sessions, secs, table = load_inputs()
            now = datetime.now(IST)
            print(write_status(ledger, update(_ReadOnly(ledger), sessions, secs, table, now), now))
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
