"""Research round 10: drift after a strong results reaction (E2), promoter buying (Q) and the two in one account (M),
on round 8's survivorship-free NSE universe, judged against docs/research/round10-preregistration.md.

    python -m trader.research.round10 --stage 1    # development: writes docs/research/round10-stage1.md
    python -m trader.research.round10 --stage 2    # the decision, once: round10-results.md and the evidence for E2, Q, M

The universe, tiers, eligibility, exits and cost model are round 8's (round8.py is reused, not changed). New here: NSE's
board-meeting records (when each results meeting was notified) and insider-trading disclosures (when each promoter
purchase was published), a 15% stop, 40-session holds, and an account of at most 5 positions shared by every candidate.
"""
from __future__ import annotations

import argparse
import bisect
import gzip
import hashlib
import json
from dataclasses import asdict
from datetime import date, datetime, time
from pathlib import Path

import numpy as np
import pandas as pd

from trader.config import ROOT
from trader.gate import Check, Evidence, decide, save_evidence
from trader.logging_setup import make_console_utf8
from trader.research import round8
from trader.research.datasets import DATA_DIR, text_sha256

PREREGISTRATION = ROOT / "docs" / "research" / "round10-preregistration.md"
PREREGISTRATION_SHA256 = "c973d560263b7caac18022718d90fa468dfd2a153af1e7a11977dc702b89fc2b"  # pinned 2026-10-17 17:45 IST
STAGE1_RESULTS = ROOT / "docs" / "research" / "round10-stage1.md"
RESULTS = ROOT / "docs" / "research" / "round10-results.md"
BOARD_DIR = DATA_DIR / "round10" / "board_meetings"
BOARD_MANIFEST = DATA_DIR / "round10" / "board_meetings_manifest.json"
BOARD_MANIFEST_SHA256 = "1e7accb269c143491bfa80831f3e404e08cb0dc5e9091c3e7921c98e26c5b30c"
PIT_DIR = DATA_DIR / "round10" / "pit"
PIT_MANIFEST = DATA_DIR / "round10" / "pit_manifest.json"
PIT_MANIFEST_SHA256 = "4955502b6ef2b0a3026cb0df5bd6d2f07d4c711c2d6850fdfd18def64ec87b42"

TESTS_IN_PROJECT = 57  # 28 earlier hypotheses, 28 variants screened for this round, and M
CROSS_ROUND_ALPHA = 0.05 / TESTS_IN_PROJECT
UNIVERSE = 300
STOP, HOLD, CAP = 0.15, 40, 5
NOTIONAL = 0.005 * round8.EQUITY / STOP  # 0.5% of equity at risk with a 15% stop: Rs 33,333
ROUND_TRIP = {key: round8.COSTS.with_slippage(round8.SLIPPAGE[key]).round_trip(NOTIONAL) for key in round8.TIERS}
CUTOFF = time(18, 0)  # the daily run's decision time, IST
RESULTS_PURPOSE = r"result|(un-?)?audited accounts|annual accounts"
REACTION_PCT, REACTION_LOOKBACK, REACTION_MIN = 90, 250, 300
PIT_MIN_VALUE = 1_000_000
DRAWS, SEED, CHUNK = 20_000, 10, 500
NAMES = {"E2": "Drift after a strong results reaction (top 10%), 40 sessions, 15% stop, 5 positions",
         "Q": "Promoter open-market purchases of Rs 10 lakh+, 40 sessions, 15% stop, 5 positions",
         "M": "E2 and Q in one account sharing 5 positions (E2 first)"}
SPANS = {1: {"E2": (date(2009, 1, 2), date(2013, 3, 28)), "Q": (date(2015, 11, 19), date(2017, 10, 31))},
         2: {"E2": (date(2013, 6, 3), date(2026, 7, 31)), "Q": (date(2018, 1, 1), date(2026, 3, 31)),
             "M": (date(2018, 1, 1), date(2026, 3, 31))}}
PARTS = {"E2": ("E2",), "Q": ("Q",), "M": ("E2", "Q")}


# ------------------------------------------------------------------------------------------------- pins
def check_preregistration() -> str:
    digest = text_sha256(PREREGISTRATION)
    if digest != PREREGISTRATION_SHA256:
        raise SystemExit(f"{PREREGISTRATION.name} changed after it was pinned (sha256 {digest}); "
                         "pre-register a new hypothesis set instead of editing this one.")
    return digest


def verify_manifest(directory: Path, manifest: Path, expected: str) -> None:
    """The manifest's own SHA-256, and every listed file's, must match what was frozen."""
    digest = hashlib.sha256(manifest.read_bytes()).hexdigest()
    if digest != expected:
        raise SystemExit(f"{manifest.name} changed (sha256 {digest})")
    for name, sha in json.loads(manifest.read_text(encoding="utf-8")).items():
        if hashlib.sha256((directory / name).read_bytes()).hexdigest() != sha:
            raise SystemExit(f"{directory.name}/{name} changed since it was frozen")


# ------------------------------------------------------------------------------------------------- data
def _rows(payload) -> list:
    return payload if isinstance(payload, list) else payload.get("data", [])


def load_board_meetings(directory: Path = BOARD_DIR) -> pd.DataFrame:
    rows = []
    for path in sorted(directory.glob("*.json")):
        rows += _rows(json.loads(path.read_bytes()))
    frame = pd.DataFrame(rows)
    return frame[["bm_symbol", "bm_date", "bm_purpose", "bm_timestamp"]] if len(frame) else frame


def load_pit(directory: Path = PIT_DIR) -> pd.DataFrame:
    rows = []
    for path in sorted(directory.glob("*.json.gz")):
        rows += _rows(json.loads(gzip.decompress(path.read_bytes())))
    return pd.DataFrame(rows)


def known_session(ts: datetime, sessions: list[date]) -> int:
    """("Known by session d") The first session whose decision (18:00 IST) comes at or after the filing time."""
    day = ts.date()
    k = bisect.bisect_left(sessions, day)
    if k < len(sessions) and sessions[k] == day and ts.time() > CUTOFF:
        k += 1
    return k


class Universe:
    """("The universe at session d") Round 8's ranks 1-300 at the latest month-end on or before d, with each tier."""

    def __init__(self, table: pd.DataFrame):
        top = table[table["rank"] <= UNIVERSE]
        self.month_ends = sorted(top["i"].unique())
        self.members = {int(i): dict(zip(g["sid"], np.where(g["rank"] <= round8.TIERS["N1"][1], "N1", "N2")))
                        for i, g in top.groupby("i")}

    def at(self, d: int) -> tuple[int | None, dict]:
        k = bisect.bisect_right(self.month_ends, d) - 1
        if k < 0:
            return None, {}
        i = int(self.month_ends[k])
        return i, self.members[i]


def results_notices(bm: pd.DataFrame, sessions: list[date], sids) -> dict[str, tuple[np.ndarray, np.ndarray]]:
    """Each company's results notices as (session known, meeting date), in filing order (ties: the later meeting last)."""
    sub = bm[bm["bm_purpose"].astype(str).str.contains(RESULTS_PURPOSE, case=False, regex=True, na=False)
             & bm["bm_symbol"].isin(set(sids))].copy()
    sub["mdate"] = pd.to_datetime(sub["bm_date"], format="%d-%b-%Y", errors="coerce").dt.date
    sub["ts"] = pd.to_datetime(sub["bm_timestamp"], format="%d-%b-%Y %H:%M:%S", errors="coerce")
    sub = sub.dropna(subset=["mdate", "ts"])
    sub["k"] = [known_session(t.to_pydatetime(), sessions) for t in sub["ts"]]
    sub = sub.sort_values(["bm_symbol", "ts", "mdate"])
    return {sid: (g["k"].to_numpy(int), g["mdate"].to_numpy(object)) for sid, g in sub.groupby("bm_symbol")}


def latest_meeting(notices: tuple[np.ndarray, np.ndarray], d: int):
    """The meeting date named by the company's latest results notice known by session d (None before any)."""
    ks, meetings = notices
    j = bisect.bisect_right(ks, d) - 1
    return meetings[j] if j >= 0 else None


# ------------------------------------------------------------------------------------------- E2 signals
def reaction_events(notices: dict, sessions: list[date], secs: dict, universe: Universe) -> pd.DataFrame:
    """Every results meeting held as scheduled for a universe member with rows on m-1 and m+1, with its abnormal
    reaction (close m-1 -> close m+1, minus the mean over the universe members with rows on both)."""
    n, rows, means = len(sessions), [], {}
    for sid, nt in notices.items():
        sec = secs[sid]
        for meeting in sorted(set(nt[1])):
            m = bisect.bisect_left(sessions, meeting)
            if m < 1 or m + 1 >= n or latest_meeting(nt, m + 1) != meeting:
                continue
            i_me, members = universe.at(m + 1)
            if sid not in members or not (sec.present[m - 1] and sec.present[m + 1]):
                continue
            if (i_me, m) not in means:
                values = [secs[x].adj_close[m + 1] / secs[x].adj_close[m - 1] - 1 for x in members
                          if x in secs and secs[x].present[m - 1] and secs[x].present[m + 1]]
                means[(i_me, m)] = float(np.mean(values))
            reaction = float(sec.adj_close[m + 1] / sec.adj_close[m - 1] - 1)
            rows.append({"sid": sid, "m": m, "signal": m + 1, "i_me": i_me, "tier": members[sid],
                         "reaction": reaction, "abnormal": reaction - means[(i_me, m)]})
    events = pd.DataFrame(rows, columns=["sid", "m", "signal", "i_me", "tier", "reaction", "abnormal"])
    return events.drop_duplicates(["sid", "m"]).sort_values(["signal", "sid"]).reset_index(drop=True)


def flag_signals(events: pd.DataFrame) -> pd.DataFrame:
    """("Signal") Abnormal reaction at least the 90th percentile of the events whose session m+1 lies in the 250 sessions
    before this event's (strictly before); at least 300 of them, otherwise no signal."""
    events = events.sort_values(["signal", "sid"]).reset_index(drop=True)
    sig, abn = events["signal"].to_numpy(int), events["abnormal"].to_numpy(float)
    threshold = np.full(len(events), np.nan)
    for j, s in enumerate(sig):
        lo, hi = bisect.bisect_left(sig, s - REACTION_LOOKBACK), bisect.bisect_left(sig, s)
        if hi - lo >= REACTION_MIN:
            threshold[j] = np.percentile(abn[lo:hi], REACTION_PCT)
    events["threshold"] = threshold
    events["is_signal"] = ~np.isnan(threshold) & (abn >= np.nan_to_num(threshold, nan=np.inf))
    return events


def e2_candidates(events: pd.DataFrame) -> pd.DataFrame:
    sig = events[events["is_signal"]]
    return pd.DataFrame({"part": "E2", "sid": sig["sid"], "entry": sig["signal"] + 1, "i_me": sig["i_me"],
                         "tier": sig["tier"], "priority": 0, "order": -sig["abnormal"], "strength": sig["abnormal"]})


# -------------------------------------------------------------------------------------------- Q signals
def promoter_purchases(pit: pd.DataFrame) -> pd.DataFrame:
    """("Q") Promoter or promoter-group open-market purchases of equity worth Rs 10 lakh or more, with publication time."""
    s = lambda col: pit[col].astype(str).str.strip()
    value = pd.to_numeric(pit["secVal"], errors="coerce")
    keep = (s("personCategory").isin(["Promoters", "Promoter Group"]) & s("acqMode").eq("Market Purchase")
            & s("tdpTransactionType").eq("Buy") & s("secType").str.lower().str.contains("equity") & (value >= PIT_MIN_VALUE))
    out = pit[keep].copy()
    out["ts"] = pd.to_datetime(out["date"].astype(str).str.strip(), format="%d-%b-%Y %H:%M", errors="coerce")
    out["sid"] = out["symbol"].astype(str).str.strip()
    out["value"] = value[keep]
    return out.dropna(subset=["ts"])


def q_candidates(purchases: pd.DataFrame, sessions: list[date], secs: dict, universe: Universe) -> pd.DataFrame:
    rows = []
    for sid, ts in zip(purchases["sid"], purchases["ts"]):
        if sid not in secs:
            continue
        d = known_session(ts.to_pydatetime(), sessions)
        i_me, members = universe.at(d)
        if sid in members:
            rows.append({"sid": sid, "d": d, "i_me": i_me, "tier": members[sid]})
    q = pd.DataFrame(rows, columns=["sid", "d", "i_me", "tier"]).drop_duplicates(["sid", "d"])
    entry = q["d"] + 1
    order = [hashlib.sha256(f"{sid}|{sessions[e] if e < len(sessions) else e}".encode()).hexdigest()
             for sid, e in zip(q["sid"], entry)]
    return pd.DataFrame({"part": "Q", "sid": q["sid"], "entry": entry, "i_me": q["i_me"], "tier": q["tier"],
                         "priority": 1, "order": order, "strength": np.nan})


# ---------------------------------------------------------------------------------------------- account
def net_trade(sec: round8.Security, e: int, tier: str) -> dict:
    t = round8.simulate(sec, e, e + HOLD, STOP)
    t["cost"] = ROUND_TRIP[tier] + (round8.SLIPPAGE[tier] if t["reason"] == "stop" else 0.0)
    t["net"] = t["gross"] - t["cost"]
    return t


def release_at(t: dict) -> int:
    """("Positions") An exit at an open frees the place at that open; a stop or a last close, from the next session."""
    return t["exit_i"] + 1 if t["reason"] in ("stop", "no further rows") else t["exit_i"]


def run_account(candidates: pd.DataFrame, secs: dict, sessions: list[date], span: tuple[date, date],
                cap: int | None = CAP) -> pd.DataFrame:
    """The account: candidates in entry order, E2 before Q, each part in its own order; dropped when no place is free."""
    n = len(sessions)
    first, last = bisect.bisect_left(sessions, span[0]), bisect.bisect_right(sessions, span[1]) - 1
    cands = candidates[(candidates["entry"] >= first) & (candidates["entry"] <= last)]
    rows, free, held = [], [0] * (cap or 0), {}
    for part_rows in (cands.sort_values(["entry", "priority"]).groupby(["entry", "priority"], sort=True)):
        (e, _), group = part_rows
        group = group.sort_values(["order", "sid"]) if group["part"].iat[0] == "E2" else group.sort_values("order")
        for c in group.itertuples(index=False):
            if c.entry + HOLD >= n or held.get(c.sid, -1) > c.entry:
                continue
            sec = secs[c.sid]
            if not round8.enterable(sec, c.entry):
                continue
            if cap:
                k = int(np.argmin(free))
                if free[k] > c.entry:
                    continue
            t = net_trade(sec, c.entry, c.tier)
            if cap:
                free[k] = release_at(t)
            held[c.sid] = release_at(t)
            rows.append({"part": c.part, "ticker": c.sid, "tier": c.tier, "i_me": c.i_me, "entry_i": c.entry,
                         "exit_i": t["exit_i"], "signal_date": sessions[c.entry], "entry_date": sessions[c.entry],
                         "exit_date": sessions[t["exit_i"]], "gross": t["gross"], "cost": t["cost"], "net": t["net"],
                         "reason": t["reason"], "gapped": t["gapped"], "strength": c.strength})
    trades = pd.DataFrame(rows)
    if len(trades):
        trades["R"] = trades["net"] / STOP
        trades["stopped"] = trades["reason"] == "stop"
        trades["signal_i"] = [d.year * 12 + d.month for d in trades["entry_date"]]  # clusters: entry months
    return trades


# --------------------------------------------------------------------------------------------- baseline
def pools_for(trades: pd.DataFrame, secs: dict, universe: Universe) -> dict:
    """("The pools") Every member of the trade's tier at its month-end that could be bought at its entry open."""
    pools = {}
    for i_me, tier, e in trades[["i_me", "tier", "entry_i"]].drop_duplicates().itertuples(index=False):
        members = universe.members[int(i_me)]
        pools[(int(i_me), tier, int(e))] = np.array([net_trade(secs[s], int(e), tier)["net"] for s, t in members.items()
                                                    if t == tier and s in secs and round8.enterable(secs[s], int(e))])
    return pools


def baseline(trades: pd.DataFrame, pools: dict, draws: int = DRAWS, seed: int = SEED) -> tuple[float, float]:
    """For every (month-end, tier, entry session) with k trades, k distinct pool members in every draw. Returns the mean
    of the draws' statistics and p = (k + 1) / (draws + 1)."""
    rng = np.random.default_rng(seed)
    counts = trades.groupby(["i_me", "tier", "entry_i"]).size()
    total = np.zeros(draws)
    for (i_me, tier, e), k in counts.items():
        pool = pools[(int(i_me), tier, int(e))]
        for start in range(0, draws, CHUNK):
            size = min(CHUNK, draws - start)
            if k < len(pool):
                chosen = np.argpartition(rng.random((size, len(pool))), k - 1, axis=1)[:, :k]
            else:
                chosen = np.tile(np.arange(len(pool)), (size, 1))
            total[start:start + size] += pool[chosen].sum(axis=1)
    stats = total / int(counts.sum())
    observed = float(trades["net"].mean())
    return float(stats.mean()), (int((stats >= observed).sum()) + 1) / (draws + 1)


def excess(trades: pd.DataFrame, pools: dict) -> pd.Series:
    return trades["net"] - [pools[(int(i), t, int(e))].mean() for i, t, e in zip(trades["i_me"], trades["tier"], trades["entry_i"])]


# --------------------------------------------------------------------------------------------- criteria
def criteria(trades: pd.DataFrame, span: tuple[date, date], p_holm: float, p_raw: float):
    """Round 8's criteria; clusters are entry months; criterion 12's bar is 0.05 / 57."""
    checks, stats = round8.criteria(trades, span, p_holm, p_raw)
    out = []
    for c in checks:
        if c.number == 11:
            c = Check(11, "Cluster-robust t-statistic (entry months as clusters) at least 2.0", c.value, c.passed)
        elif c.number == 12:
            c = Check(12, f"Raw random-baseline p below 0.05/{TESTS_IN_PROJECT} = {CROSS_ROUND_ALPHA:.6f}", f"{p_raw:.6f}",
                      bool(not pd.isna(p_raw) and p_raw < CROSS_ROUND_ALPHA))
        out.append(c)
    return out, stats


def load_everything(verify: bool = True):
    if verify:
        verify_manifest(BOARD_DIR, BOARD_MANIFEST, BOARD_MANIFEST_SHA256)
        verify_manifest(PIT_DIR, PIT_MANIFEST, PIT_MANIFEST_SHA256)
    sessions, secs, table = round8.load_inputs(verify_pins=verify)
    universe = Universe(table)
    notices = results_notices(load_board_meetings(), sessions, secs)
    events = flag_signals(reaction_events(notices, sessions, secs, universe))
    candidates = {"E2": e2_candidates(events), "Q": q_candidates(promoter_purchases(load_pit()), sessions, secs, universe)}
    return sessions, secs, universe, events, candidates


def evaluate(stage: int, sessions, secs, universe, candidates, with_informational: bool = True) -> dict:
    results, raw_p = {}, {}
    for key, span in SPANS[stage].items():
        cands = pd.concat([candidates[p] for p in PARTS[key]], ignore_index=True)
        trades = run_account(cands, secs, sessions, span)
        pools = pools_for(trades, secs, universe) if len(trades) else {}
        random_mean, raw_p[key] = baseline(trades, pools) if len(trades) else (np.nan, 1.0)
        results[key] = {"name": NAMES[key], "span": span, "trades": trades, "pools": pools, "random_mean": random_mean}
    adjusted = round8.holm(raw_p)
    for key, r in results.items():
        checks, stats = criteria(r["trades"], r["span"], adjusted[key], raw_p[key])
        r.update(checks=checks, stats=stats, decision=decide(checks), raw_p=raw_p[key], holm_p=adjusted[key])
        if with_informational and len(r["trades"]):
            r["info"] = informational(key, r, candidates, secs, sessions, universe)
    return {"stage": stage, "results": results}


def informational(key: str, r: dict, candidates: dict, secs, sessions, universe) -> dict:
    trades, info = r["trades"], {}
    trades = trades.assign(excess=excess(trades, r["pools"]))
    info["excess_mean"] = float(trades["excess"].mean())
    info["excess_t"] = round8.clustered_t(trades["excess"], trades["signal_i"])
    info["costs"] = {f"{x}x": float((trades["gross"] - x * trades["cost"]).mean()) for x in (0, 1, 1.5, 2, 3)}
    info["by_year"] = trades.groupby(trades["entry_date"].map(lambda d: d.year))["net"].agg(["count", "mean"])
    info["by_part"] = {p: (len(g), float(g["net"].mean()), float(g["excess"].mean()), float((g["net"] > 0).mean()))
                       for p, g in trades.groupby("part")}
    info["by_tier"] = {t: (len(g), float(g["net"].mean()), float(g["excess"].mean())) for t, g in trades.groupby("tier")}
    info["stops"] = (int(trades["stopped"].sum()), int(trades["gapped"].sum()))
    info["largest"] = trades.reindex(trades["net"].abs().sort_values(ascending=False).index).head(10)[
        ["part", "ticker", "entry_date", "exit_date", "reason", "net"]]
    every = {}
    for part in PARTS[key]:
        all_trades = run_account(candidates[part], secs, sessions, r["span"], cap=None)
        if len(all_trades):
            pools = pools_for(all_trades, secs, universe)
            every[part] = {"trades": len(all_trades), "net": float(all_trades["net"].mean()),
                           "win": float((all_trades["net"] > 0).mean()), "excess": float(excess(all_trades, pools).mean()),
                           "by_year": all_trades.groupby(all_trades["entry_date"].map(lambda d: d.year))["net"].mean()}
    info["every_event"] = every
    return info


# ----------------------------------------------------------------------------------------------- report
_pct, _num = round8._pct, round8._num


def write_report(report: dict, digest: str, code_sha: str, path: Path) -> None:
    stage, results = report["stage"], report["results"]
    title = ("Research round 10, stage 1 (development; decides nothing)" if stage == 1
             else "Research round 10 results: results drift, promoter buying, and the two combined")
    lines = [f"# {title}", "",
             f"Run on {datetime.now(round8.IST):%Y-%m-%d %H:%M} IST by `python -m trader.research.round10 --stage {stage}` "
             f"(runner SHA-256 `{code_sha[:16]}...`), against [the pre-registration](round10-preregistration.md) (SHA-256 "
             f"`{digest[:16]}...`), the board-meeting and insider manifests (`{BOARD_MANIFEST_SHA256[:8]}...`, "
             f"`{PIT_MANIFEST_SHA256[:8]}...`) and round 8's frozen panel (`{round8.PANEL_SHA256[:8]}...`). Every hypothesis "
             "is reported. Returns are per trade, net of costs (Rs 33,333 positions, 15% stop, R = 15%).", "",
             "## Summary", "",
             "| Hypothesis | Entries | Trades | Win rate | Net per trade | Avg win / avg loss | PF | t | Cluster t | "
             "Random picks | p raw / Holm | Drawdown | " + ("Decision |" if stage == 2 else "|"),
             "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|"]
    for key, r in results.items():
        s = r["stats"]
        if not s["trades"]:
            lines.append(f"| {key}: {r['name']} | {r['span'][0]} to {r['span'][1]} | 0 | - | - | - | - | - | - | - | - | - | "
                         f"{r['decision']} |")
            continue
        lines.append(f"| {key}: {r['name']} | {r['span'][0]} to {r['span'][1]} | {s['trades']} | {100 * s['win_rate']:.1f}% | "
                     f"{_pct(s['mean_net'])} | {_pct(s['avg_win'], 2)} / {_pct(s['avg_loss'], 2)} | {_num(s['profit_factor'])} | "
                     f"{_num(s['t'])} | {_num(s['t_clustered'])} | {_pct(r['random_mean'])} | {r['raw_p']:.6f} / "
                     f"{r['holm_p']:.6f} | {s['max_drawdown_r']:.1f}R | " + (f"**{r['decision']}** |" if stage == 2 else "(stage 1) |"))
    lines += ["", "## The criteria" + (" (stage 1: reported, not applied)" if stage == 1 else ""), "",
              "| # | Criterion | " + " | ".join(results) + " |", "|---|---|" + "---|" * len(results)]
    first = next(iter(results.values()))["checks"]
    for i, check in enumerate(first):
        cells = [f"{r['checks'][i].value} ({'pass' if r['checks'][i].passed else '**fail**'})" for r in results.values()]
        lines.append(f"| {check.number} | {check.criterion} | " + " | ".join(cells) + " |")
    for key, r in results.items():
        info = r.get("info", {})
        lines += ["", f"## {key}: {r['name']}", ""]
        if stage == 2:
            lines += [f"**Decision: {r['decision']}.**", ""]
            if [c.number for c in r["checks"] if not c.passed] == [2]:
                lines += ["INELIGIBLE UNDER CURRENT POLICY: every criterion passes except the 50% win-rate floor.", ""]
        if not info:
            continue
        lines += ["Informational (not part of any decision):", "",
                  f"- Edge over random picks: {_pct(info['excess_mean'])} a trade (month-clustered t {_num(info['excess_t'])}).",
                  f"- Stops: {info['stops'][0]}, of which {info['stops'][1]} filled at a gap.",
                  "- Net per trade at 0x / 1x / 1.5x / 2x / 3x costs: " + " / ".join(_pct(v) for v in info["costs"].values()) + ".",
                  "- By part: " + "; ".join(f"{p}: {n} trades, net {_pct(m)}, edge {_pct(x)}, win {100 * w:.1f}%"
                                           for p, (n, m, x, w) in info["by_part"].items()) + ".",
                  "- By tier: " + "; ".join(f"{t}: {n} trades, net {_pct(m)}, edge {_pct(x)}" for t, (n, m, x) in info["by_tier"].items()) + "."]
        for part, ev in info["every_event"].items():
            lines.append(f"- {part} with every qualifying event (no position cap): {ev['trades']} trades, net {_pct(ev['net'])}, "
                         f"win {100 * ev['win']:.1f}%, edge over random {_pct(ev['excess'])}.")
        lines += ["", "| Year | Trades | Net per trade |" + "".join(f" {p} every event |" for p in info["every_event"]),
                  "|---|---:|---:|" + "---:|" * len(info["every_event"])]
        for year, row in info["by_year"].iterrows():
            extra = "".join(f" {_pct(ev['by_year'].get(year, np.nan))} |" for ev in info["every_event"].values())
            lines.append(f"| {year} | {int(row['count'])} | {_pct(row['mean'])} |{extra}")
        lines += ["", "Largest trades:", "", "| Part | Stock | Entry | Exit | How | Net |", "|---|---|---|---|---|---:|"]
        lines += [f"| {t.part} | {t.ticker} | {t.entry_date} | {t.exit_date} | {t.reason} | {_pct(t.net, 1)} |"
                  for t in info["largest"].itertuples(index=False)]
    lines += ["", "Patterns in the informational sections are hypotheses for future data, not findings."]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def evidence_for(key: str, r: dict, digest: str, code_sha: str) -> Evidence:
    s = r["stats"]
    return Evidence(
        strategy_id=key, kind="research", decision=r["decision"], generated=date.today().isoformat(),
        source="docs/research/round10-results.md (python -m trader.research.round10 --stage 2)",
        checks=tuple(asdict(c) for c in r["checks"]),
        stats={"evaluation_span": f"{r['span'][0]} to {r['span'][1]}", "holdout_trades": s["trades"],
               "holdout_win_rate": s["win_rate"], "holdout_mean_net": s["mean_net"], "holdout_sd_net": s["sd_net"],
               "holdout_profit_factor": s["profit_factor"], "holdout_t": s["t"], "holdout_t_clustered": s["t_clustered"],
               "p_random_raw": r["raw_p"], "p_random_holm": r["holm_p"], "round_trip_cost": ROUND_TRIP["N2"],
               "max_drawdown_r": s["max_drawdown_r"], "runner_sha256": code_sha},
        preregistration_sha256=digest)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Round 10: stage 1 (development), then stage 2 (the decision, once).")
    parser.add_argument("--stage", type=int, choices=[1, 2], required=True)
    args = parser.parse_args(argv)
    make_console_utf8()
    digest = check_preregistration()
    code_sha = round8.file_sha(Path(__file__))
    if args.stage == 2:
        if not STAGE1_RESULTS.exists():
            raise SystemExit("stage 1 has not run: run --stage 1 first")
        if RESULTS.exists():
            raise SystemExit(f"{RESULTS.name} already exists: stage 2 runs once")
    sessions, secs, universe, events, candidates = load_everything()
    report = evaluate(args.stage, sessions, secs, universe, candidates)
    path = STAGE1_RESULTS if args.stage == 1 else RESULTS
    write_report(report, digest, code_sha, path)
    for key, r in report["results"].items():
        s = r["stats"]
        print(f"{key}: {s['trades']} trades, win {100 * s.get('win_rate', np.nan):.1f}%, net {_pct(s.get('mean_net'))} a trade, "
              f"random {_pct(r['random_mean'])}, p {r['raw_p']:.6f} (Holm {r['holm_p']:.6f}), drawdown "
              f"{s.get('max_drawdown_r', np.nan):.1f}R" + (f" -> {r['decision']}" if args.stage == 2 else ""))
        for c in r["checks"]:
            print(f"   [{'x' if c.passed else ' '}] {c.number}. {c.criterion}: {c.value}")
        if args.stage == 2:
            save_evidence(evidence_for(key, r, digest, code_sha))
    print(f"Report written to {path}")


if __name__ == "__main__":
    main()
