"""Forward test 5: paper trial 1's trades (E2 x3 + V2 x2) hedged with short NIFTY futures, paper only, judged against
docs/research/forward5-preregistration.md.

    python -m trader.research.forward5 daily      # scheduled each evening after paper trial 1
    python -m trader.research.forward5 status     # hedged trades so far against the criteria (informational)
    python -m trader.research.forward5 look       # informational any time; a decision look each January

Each closed trade of paper trial 1 (read from state/trial1.db, never changed) is paired with a short NIFTY future of the
same notional, opened and closed with it and rolled at each expiry. NIFTY futures prices come from NSE's daily F&O files
(raw files kept outside OneDrive, see trader/research/nse_fo.py). Hedged trades, hedged random-pick pools and NIFTY
futures prices go into an append-only ledger (state/forward5.db). Research only: no order can be placed, F&O stays paper.
"""
from __future__ import annotations

import argparse
import html
import json
import logging
import sqlite3
import zipfile
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import requests

from trader.config import ROOT, load_settings
from trader.gate import Check, Evidence, save_evidence
from trader.logging_setup import configure_logging, make_console_utf8
from trader.research import forward2, forward3, nse_fo, round8, round10, trial
from trader.research.datasets import text_sha256

log = logging.getLogger(__name__)
IST = ZoneInfo("Asia/Kolkata")
PREREGISTRATION = ROOT / "docs" / "research" / "forward5-preregistration.md"
PREREGISTRATION_SHA256 = "56d316d8b0a81bbd213d6de342375da55008dfc9d1c21c05a65e16af773f7fef"  # pinned 2026-10-19 00:25 IST
LEDGER = ROOT / "state" / "forward5.db"
STATUS = ROOT / "state" / "forward5-status.md"
LOOKS = ROOT / "docs" / "research"
FIRST_DATA, FIRST_ENTRY = date(2026, 10, 19), date(2026, 10, 22)
FIRST_DECISION_YEAR, RETIRE_FROM_YEAR, LAST_YEAR = 2028, 2029, 2036
FUTURES_COST = 0.0012  # a futures round trip (each leg), share of notional
STOPS = {"E2": round10.STOP, "V2": round8.STOP}
KILL_R = 20.0
DRAWS, SEED = 20_000, 12
TAG = "<b>[FORWARD TEST 5 · paper only]</b>"
TABLES = ("futures", "hedged", "pools", "runs", "notices")
SCHEMA = """
CREATE TABLE IF NOT EXISTS futures (id INTEGER PRIMARY KEY, date TEXT NOT NULL, expiry TEXT NOT NULL, open REAL, high REAL,
    low REAL, close REAL, settle REAL, recorded_at TEXT NOT NULL, UNIQUE (date, expiry));
CREATE TABLE IF NOT EXISTS hedged (id INTEGER PRIMARY KEY, part TEXT NOT NULL, sid TEXT NOT NULL, signal_date TEXT NOT NULL,
    tier TEXT NOT NULL, entry_date TEXT NOT NULL, exit_date TEXT NOT NULL, outcome TEXT NOT NULL, gapped INTEGER NOT NULL,
    stock_gross REAL NOT NULL, stock_cost REAL NOT NULL, hedge REAL NOT NULL, hedge_cost REAL NOT NULL, legs INTEGER NOT NULL,
    gross REAL NOT NULL, cost REAL NOT NULL, net REAL NOT NULL, r REAL NOT NULL, recorded_at TEXT NOT NULL,
    UNIQUE (part, sid, signal_date));
CREATE TABLE IF NOT EXISTS pools (id INTEGER PRIMARY KEY, part TEXT NOT NULL, month_end TEXT NOT NULL, tier TEXT NOT NULL,
    entry_date TEXT NOT NULL, pool TEXT NOT NULL, recorded_at TEXT NOT NULL, UNIQUE (part, month_end, tier, entry_date));
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


class Ledger:
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

    def futures_dates(self) -> set[str]:
        return {r[0] for r in self.conn.execute("SELECT DISTINCT date FROM futures")}

    def add_futures(self, rows: list[dict], at: datetime) -> int:
        before = self.conn.total_changes
        for r in rows:
            self.conn.execute("INSERT OR IGNORE INTO futures (date, expiry, open, high, low, close, settle, recorded_at) "
                              "VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (r["date"], r["expiry"], r["open"], r["high"], r["low"],
                                                                 r["close"], r["settle"], at.isoformat()))
        return self.conn.total_changes - before

    def add_hedged(self, row: dict, at: datetime) -> None:
        cols = ["part", "sid", "signal_date", "tier", "entry_date", "exit_date", "outcome", "gapped", "stock_gross",
                "stock_cost", "hedge", "hedge_cost", "legs", "gross", "cost", "net", "r"]
        self.conn.execute(f"INSERT INTO hedged ({', '.join(cols)}, recorded_at) VALUES ({', '.join('?' * (len(cols) + 1))})",
                          [row[c] for c in cols] + [at.isoformat()])

    def has_pool(self, part: str, month_end: str, tier: str, entry: str) -> bool:
        return self.conn.execute("SELECT 1 FROM pools WHERE part = ? AND month_end = ? AND tier = ? AND entry_date = ?",
                                 (part, month_end, tier, entry)).fetchone() is not None

    def add_pool(self, part: str, month_end: str, tier: str, entry: str, pool: list[float], at: datetime) -> None:
        self.conn.execute("INSERT INTO pools (part, month_end, tier, entry_date, pool, recorded_at) VALUES (?, ?, ?, ?, ?, ?)",
                          (part, month_end, tier, entry, json.dumps([round(float(x), 8) for x in pool]), at.isoformat()))

    def add_run(self, at: datetime, status: str, detail: str) -> None:
        self.conn.execute("INSERT INTO runs (at, status, detail) VALUES (?, ?, ?)", (at.isoformat(), status, detail[:2000]))

    def sent(self, key: str) -> bool:
        return self.conn.execute("SELECT 1 FROM notices WHERE key = ? AND sent = 1", (key,)).fetchone() is not None

    def add_notice(self, key: str, at: datetime, sent: bool) -> None:
        self.conn.execute("INSERT INTO notices (key, at, sent) VALUES (?, ?, ?)", (key, at.isoformat(), int(sent)))


# ------------------------------------------------------------------------------------------ NIFTY futures
def nifty_futures(path: Path) -> list[dict]:
    """The NIFTY index futures rows of one NSE F&O file, old format or UDiFF."""
    with zipfile.ZipFile(path) as z:
        f = pd.read_csv(z.open(z.namelist()[0]), low_memory=False)
    f.columns = [c.strip() for c in f.columns]
    if "INSTRUMENT" in f:
        f = f[(f["INSTRUMENT"].astype(str).str.strip() == "FUTIDX") & (f["SYMBOL"].astype(str).str.strip() == "NIFTY")]
        out = pd.DataFrame({"date": pd.to_datetime(f["TIMESTAMP"], format="%d-%b-%Y"), "expiry": pd.to_datetime(f["EXPIRY_DT"], format="%d-%b-%Y"),
                            "open": f["OPEN"], "high": f["HIGH"], "low": f["LOW"], "close": f["CLOSE"], "settle": f["SETTLE_PR"]})
    else:
        f = f[(f["FinInstrmTp"].astype(str).str.strip() == "IDF") & (f["TckrSymb"].astype(str).str.strip() == "NIFTY")]
        out = pd.DataFrame({"date": pd.to_datetime(f["TradDt"]), "expiry": pd.to_datetime(f["XpryDt"]), "open": f["OpnPric"],
                            "high": f["HghPric"], "low": f["LwPric"], "close": f["ClsPric"], "settle": f["SttlmPric"]})
    out["date"], out["expiry"] = out["date"].dt.date.astype(str), out["expiry"].dt.date.astype(str)
    return out.to_dict("records")


def collect_futures(ledger: Ledger, sessions: list[date], now: datetime, http=requests) -> dict:
    """NIFTY futures for every session from 19 Oct 2026 not yet recorded (NSE's F&O file, saved unchanged outside
    OneDrive). A file NSE hasn't published yet is simply tried again next evening."""
    have, added, waiting = ledger.futures_dates(), 0, []
    for day in [d for d in sessions if d >= FIRST_DATA and d.isoformat() not in have]:
        if nse_fo.fetch(day, http) == "absent":
            waiting.append(day)
            continue
        added += ledger.add_futures(nifty_futures(nse_fo.raw_path(day)), now)
    return {"rows": added, "waiting": waiting}


def hedge_return(futures: pd.DataFrame, entry: date, exit_: date, at_close: bool) -> tuple[float, int] | None:
    """("The hedge") A short NIFTY future from the entry session's open to the exit (its open, or its close for a stop
    or a last close), rolled at each expiry inside the holding. (h, legs), or None while a needed price is missing."""
    rows = {(d, e): r for d, e, r in zip(futures["date"], futures["expiry"], futures.itertuples(index=False))}
    on = lambda d: sorted(e for (dd, e) in rows if dd == d)
    e_iso, x_iso = entry.isoformat(), exit_.isoformat()
    near = [e for e in on(e_iso) if e >= e_iso]
    if not near or x_iso not in {d for d, _ in rows}:
        return None
    current = near[0]
    first = rows[(e_iso, current)].open
    leg_in, legs = first, []
    while current < x_iso:  # the held contract expires inside the holding: roll at its settlement price that day
        if (current, current) not in rows:
            return None
        legs.append((leg_in, rows[(current, current)].settle))
        later = [e for e in on(current) if e > current]
        if not later:
            return None
        leg_in, current = rows[(current, later[0])].close, later[0]
    if (x_iso, current) not in rows:
        return None
    last = rows[(x_iso, current)]
    legs.append((leg_in, last.close if at_close else last.open))
    values = [v for leg in legs for v in leg]
    if not all(isinstance(v, (int, float)) and np.isfinite(v) and v > 0 for v in values):
        return None
    return float(sum(a - b for a, b in legs) / first), len(legs)


def hedged_row(part: str, sid: str, signal: str, tier: str, entry: str, exit_: str, outcome: str, gapped: int,
               stock_gross: float, stock_cost: float, h: float, legs: int) -> dict:
    hedge_cost = FUTURES_COST * legs
    gross, cost = stock_gross + h, stock_cost + hedge_cost
    net = gross - cost
    return {"part": part, "sid": sid, "signal_date": signal, "tier": tier, "entry_date": entry, "exit_date": exit_,
            "outcome": outcome, "gapped": int(gapped), "stock_gross": stock_gross, "stock_cost": stock_cost, "hedge": h,
            "hedge_cost": hedge_cost, "legs": legs, "gross": gross, "cost": cost, "net": net, "r": net / STOPS[part]}


def at_close(outcome: str) -> bool:
    return outcome in ("stop", "no further rows")


def trial_trades(path: Path = trial.LEDGER) -> pd.DataFrame:
    """Paper trial 1's closed trades, read-only."""
    if not Path(path).exists():
        return pd.DataFrame()
    conn = sqlite3.connect(f"{Path(path).as_uri()}?mode=ro", uri=True)
    try:
        return pd.read_sql_query("SELECT * FROM trades ORDER BY id", conn)
    finally:
        conn.close()


def record_hedged(ledger: Ledger, trades: pd.DataFrame, now: datetime, events: dict) -> None:
    if trades.empty:
        return
    futures = ledger.table("futures")
    done = set(zip(ledger.table("hedged")["part"], ledger.table("hedged")["sid"], ledger.table("hedged")["signal_date"]))
    for t in trades[trades["entry_date"] >= FIRST_ENTRY.isoformat()].itertuples(index=False):
        if (t.part, t.sid, t.signal_date) in done:
            continue
        hedge = hedge_return(futures, date.fromisoformat(t.entry_date), date.fromisoformat(t.exit_date), at_close(t.outcome))
        if hedge is None:
            events["waiting"].append((t.part, t.sid))
            continue
        row = hedged_row(t.part, t.sid, t.signal_date, t.tier, t.entry_date, t.exit_date, t.outcome, t.gapped,
                         float(t.gross), float(t.cost), *hedge)
        ledger.add_hedged(row, now)
        events["hedged"].append(row)


def record_pools(ledger: Ledger, sessions: list[date], secs: dict, universe: round10.Universe, now: datetime,
                 events: dict) -> None:
    """("The random baseline") Each hedged trade's group: every member of its tier that could be bought at its entry
    open, traded by the part's rules and hedged by the same rules over its own holding, once all have closed."""
    hedged = ledger.table("hedged")
    if hedged.empty:
        return
    futures = ledger.table("futures")
    n = len(sessions)
    index = {d.isoformat(): i for i, d in enumerate(sessions)}
    ends = forward2.month_ends_known(sessions)
    for part, tier, signal, entry in hedged.drop_duplicates(["part", "tier", "entry_date"])[
            ["part", "tier", "signal_date", "entry_date"]].itertuples(index=False):
        if signal not in index or entry not in index:
            continue
        s_i, e = index[signal], index[entry]
        i_me, members = universe.at(s_i) if part == "E2" else (s_i, universe.members.get(s_i, {}))
        if i_me is None or ledger.has_pool(part, sessions[i_me].isoformat(), tier, entry):
            continue
        names = [s for s, t in members.items() if t == tier and s in secs and round8.enterable(secs[s], e)]
        if part == "E2":
            outcomes = [trial.e2_position(secs[s], e, n, tier) for s in names]
        else:
            later = [j for j in ends if j > s_i]
            if not later:
                continue
            outcomes = [trial.v2_position(secs[s], e, later[0] + 1, n) for s in names]
        if not outcomes or not all(o["outcome"] in forward3.CLOSED for o in outcomes):
            continue
        pool = []
        for o in outcomes:
            hedge = hedge_return(futures, sessions[e], sessions[o["exit_i"]], at_close(o["outcome"]))
            if hedge is None:
                break
            pool.append(o["net"] + hedge[0] - FUTURES_COST * hedge[1])
        if len(pool) == len(outcomes):
            ledger.add_pool(part, sessions[i_me].isoformat(), tier, entry, pool, now)
            events["pools"].append((part, tier, entry, len(pool)))


# ------------------------------------------------------------------------------------------------- looks
def judged(ledger: Ledger, end: date | None = None) -> pd.DataFrame:
    t = ledger.table("hedged")
    if len(t):
        keep = t["entry_date"] >= FIRST_ENTRY.isoformat()
        if end is not None:
            keep &= t["entry_date"] <= end.isoformat()
        t = t[keep]
    if t.empty:
        return t
    t = t.copy()
    t["entry_date"] = pd.to_datetime(t["entry_date"]).dt.date
    t["signal_date"] = t["entry_date"]
    t["exit_date"] = pd.to_datetime(t["exit_date"]).dt.date
    t["signal_i"] = [d.year * 12 + d.month for d in t["entry_date"]]
    t["ticker"], t["R"] = t["sid"], t["r"]
    t["stopped"], t["gapped"] = t["outcome"] == "stop", t["gapped"].astype(bool)
    return t.reset_index(drop=True)


def judge(ledger: Ledger, as_of: date) -> dict:
    """At a look on `as_of`: the criteria and decision ("Criteria at a decision look", "Looks and decisions")."""
    look, end = forward3.look_number(as_of), forward3.cutoff(as_of)
    trades = judged(ledger, end)
    if trades.empty:
        return {"look": look, "cutoff": end, "trades": trades, "decision": "WAITING", "checks": [], "raw_p": np.nan}
    pt = ledger.table("pools")
    pools = {(0, f"{p}:{tier}", date.fromisoformat(e).toordinal()): np.asarray(json.loads(v))
             for p, tier, e, v in zip(pt["part"], pt["tier"], pt["entry_date"], pt["pool"])}
    base = pd.DataFrame({"i_me": 0, "tier": trades["part"] + ":" + trades["tier"], "net": trades["net"],
                         "entry_i": [d.toordinal() for d in trades["entry_date"]]})
    covered = base[[(0, k, e) in pools for k, e in zip(base["tier"], base["entry_i"])]]
    random_mean, raw_p = round10.baseline(covered, pools, DRAWS, SEED) if len(covered) else (np.nan, 1.0)
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
        strategy_id="B1HF", kind="research", decision=r["decision"], generated=date.today().isoformat(),
        source="docs/research/forward5-look-*.md (python -m trader.research.forward5 look)",
        checks=tuple({"number": c.number, "criterion": c.criterion, "value": c.value, "passed": c.passed} for c in r["checks"]),
        stats={"evaluation_span": f"{FIRST_ENTRY} to {r['cutoff']}", "holdout_trades": s["trades"],
               "holdout_win_rate": s["win_rate"], "holdout_mean_net": s["mean_net"], "holdout_sd_net": s["sd_net"],
               "holdout_profit_factor": s["profit_factor"], "holdout_t": s["t"], "holdout_t_clustered": s["t_clustered"],
               "p_random_raw": r["raw_p"], "round_trip_cost": round8.ROUND_TRIP["N2"] + FUTURES_COST,
               "max_drawdown_r": s["max_drawdown_r"], "look": r["look"]},
        preregistration_sha256=digest)


# ----------------------------------------------------------------------------------------------- reports
def _pct(v, digits: int = 2) -> str:
    return f"{100 * v:+.{digits}f}%" if v is not None and not pd.isna(v) else "-"


def messages(events: dict) -> list[tuple[str, str]]:
    return [(f"hedged {h['part']} {h['sid']} {h['signal_date']}",
             f"{TAG} Hedged result, {h['part']} {html.escape(h['sid'])} ({h['entry_date']} to {h['exit_date']}): stock "
             f"{_pct(h['stock_gross'] - h['stock_cost'])} after its costs, short NIFTY futures {_pct(h['hedge'])} over "
             f"{h['legs']} leg(s) less {_pct(h['hedge_cost'])} costs: hedged {_pct(h['net'])}, {h['r']:+.2f}R.")
            for h in events["hedged"]]


def write_status(ledger: Ledger, verdict: dict, now: datetime) -> str:
    hedged = ledger.table("hedged")
    lines = ["# Forward test 5: status (paper trial 1 hedged with short NIFTY futures)", "",
             f"Updated {now.astimezone(IST):%Y-%m-%d %H:%M} IST, against docs/research/forward5-preregistration.md. Paper only; "
             "F&O stays paper; nothing here can place an order. Decisions only at the January looks from 2028.", "",
             f"NIFTY futures sessions recorded: {len(ledger.futures_dates())}. Hedged trades: {len(hedged)}; now "
             f"{verdict['decision']}.", ""]
    if verdict.get("stats"):
        s = verdict["stats"]
        lines += ["| Hedged, so far (after costs) | Value |", "|---|---:|", f"| Trades | {s['trades']} |",
                  f"| Win rate | {100 * s['win_rate']:.1f}% |", f"| Net per trade | {_pct(s['mean_net'])} |",
                  f"| Average win / average loss | {_pct(s['avg_win'])} / {_pct(s['avg_loss'])} |",
                  f"| Profit factor | {s['profit_factor']:.2f} |", f"| Drawdown | {s['max_drawdown_r']:.1f}R |",
                  f"| Random picks, hedged the same way | {_pct(verdict['random_mean'])} ({verdict['covered']} compared) |",
                  f"| p against random | {verdict['raw_p']:.4f} |",
                  f"| Criteria passing (informational) | {sum(c.passed for c in verdict['checks'])} of {len(verdict['checks'])} |", ""]
    if len(hedged):
        lines += ["| Part | Stock | Entry | Exit | Stock net | Hedge | Hedged net | R |", "|---|---|---|---|---:|---:|---:|---:|"]
        lines += [f"| {h.part} | {h.sid} | {h.entry_date} | {h.exit_date} | {_pct(h.stock_gross - h.stock_cost)} | "
                  f"{_pct(h.hedge - h.hedge_cost)} | {_pct(h.net)} | {h.r:+.2f} |" for h in hedged.itertuples(index=False)]
    text = "\n".join(lines) + "\n"
    STATUS.parent.mkdir(parents=True, exist_ok=True)
    STATUS.write_text(text, encoding="utf-8")
    return text


def write_look(r: dict, digest: str, as_of: date) -> None:
    lines = [f"# Forward test 5: look on {as_of}", "",
             f"Look {r['look'] or 'informational'}; hedged trades entered {FIRST_ENTRY} to {r['cutoff']}; pre-registration "
             f"SHA-256 `{digest[:16]}...`.", "", f"**Decision: {r['decision']}.**", ""]
    if r["checks"]:
        lines += ["| # | Criterion | Value | Result |", "|---|---|---|---|"]
        lines += [f"| {c.number} | {c.criterion} | {c.value} | {'pass' if c.passed else '**fail**'} |" for c in r["checks"]]
    (LOOKS / f"forward5-look-{as_of}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


# ------------------------------------------------------------------------------------------------- main
def daily(now: datetime | None = None, notify: bool = True) -> int:
    from trader.notify.telegram import notifier_from_settings
    now = now or datetime.now(IST)
    ledger = Ledger()
    try:
        sessions, secs, table = forward2.load_inputs()
        got = collect_futures(ledger, sessions, now)
        events = {"hedged": [], "pools": [], "waiting": []}
        record_hedged(ledger, trial_trades(), now, events)
        record_pools(ledger, sessions, secs, round10.Universe(table), now, events)
        verdict = judge(ledger, now.astimezone(IST).date())
        notes = messages(events)
        if verdict.get("stats") and verdict["stats"]["max_drawdown_r"] > KILL_R:
            if not ledger.sent("rejected: drawdown"):
                save_evidence(evidence_for(verdict, check_preregistration()))
            notes.append(("rejected: drawdown", f"{TAG} The hedged trades' drawdown passed 20R "
                          f"({verdict['stats']['max_drawdown_r']:.1f}R): REJECTED, as pre-registered."))
        write_status(ledger, verdict, now)
        if notify:
            notifier = notifier_from_settings(load_settings())
            for key, text in notes:
                if not ledger.sent(key):
                    ledger.add_notice(key, now, notifier.send(text))
        detail = (f"futures rows {got['rows']} (waiting {[str(d) for d in got['waiting']]}); hedged {len(events['hedged'])}, "
                  f"pools {len(events['pools'])}, waiting for prices {len(events['waiting'])}; {verdict['decision']}")
        ledger.add_run(now, "ok", detail)
        log.info("Forward test 5: %s", detail)
        return 0
    except (requests.RequestException, ValueError, OSError, KeyError, zipfile.BadZipFile) as exc:
        ledger.add_run(now, "failed", f"{type(exc).__name__}: {exc}")
        log.warning("Forward test 5 failed: %s: %s", type(exc).__name__, exc)
        return 1
    finally:
        ledger.close()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Forward test 5: paper trial 1 hedged with short NIFTY futures (paper only).")
    parser.add_argument("command", choices=["daily", "status", "look"])
    parser.add_argument("--no-notify", action="store_true", help="daily: don't send Telegram messages")
    args = parser.parse_args(argv)
    make_console_utf8()
    settings = load_settings()
    configure_logging(secrets=settings.secret_values(), filename="forward5.log")
    digest = check_preregistration()
    if args.command == "daily":
        raise SystemExit(daily(notify=not args.no_notify))
    ledger = Ledger()
    try:
        as_of = datetime.now(IST).date()
        r = judge(ledger, as_of)
        if args.command == "status":
            print(write_status(ledger, r, datetime.now(IST)))
            return
        write_look(r, digest, as_of)
        if r["look"] and r["decision"] in ("PAPER", "REJECTED"):
            save_evidence(evidence_for(r, digest))
        print(f"Forward test 5, look {r['look'] or 'informational'}: {r['decision']}")
        for c in r["checks"]:
            print(f"   [{'x' if c.passed else ' '}] {c.number}. {c.criterion}: {c.value}")
    finally:
        ledger.close()


if __name__ == "__main__":
    main()
