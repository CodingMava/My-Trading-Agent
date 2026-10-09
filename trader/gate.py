"""The profitability gate: the only path from research to paper trading to real money.

* research_checks() scores backtest evidence against the criteria in config/gate.toml, and decide()
  turns the checks into a status.
* paper_checks() does the same for paper-trading results before any real money is used.
* Evidence is saved as JSON under docs/research/evidence/ and committed with the code.
* supported_status() is what the registry enforces when it loads: a strategy holds only the status its
  evidence supports. PAPER needs passing research evidence; LIVE_SMALL also needs passing paper
  evidence; LIVE also needs passing small-capital live evidence. Evidence expires.
* decay_check() watches paper or live trades and demotes a strategy whose results fall apart.
"""
from __future__ import annotations

import json
import math
import tomllib
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from trader.config import CONFIG_DIR, ROOT
from trader.research.metrics import summarize

GATE_FILE = CONFIG_DIR / "gate.toml"
EVIDENCE_DIR = ROOT / "docs" / "research" / "evidence"
LADDER = ("REJECTED", "DISABLED", "RESEARCH", "PAPER", "LIVE_SMALL", "LIVE")


@dataclass(frozen=True)
class ResearchThresholds:
    min_trades: int = 50
    min_win_rate: float = 0.50
    min_profit_factor: float = 1.3
    min_t_stat: float = 2.0
    max_p_value: float = 0.05
    cost_stress: float = 1.5
    max_loss_to_win: float = 1.5
    worst_trade_r: float = -3.0
    min_positive_years: float = 0.70
    min_trades_per_year: int = 10
    min_breadth: float = 0.60
    min_trades_per_stock: int = 5


@dataclass(frozen=True)
class PaperThresholds:
    min_weeks: int = 8
    min_trades: int = 40
    max_cost_ratio: float = 1.5


@dataclass(frozen=True)
class DecayThresholds:
    window: int = 50
    max_win_rate_drop: float = 0.15
    max_drawdown_r: float = 20.0


@dataclass(frozen=True)
class GateConfig:
    research: ResearchThresholds = ResearchThresholds()
    paper: PaperThresholds = PaperThresholds()
    decay: DecayThresholds = DecayThresholds()
    max_evidence_age_days: int = 365


def load_gate_config(path: Path = GATE_FILE) -> GateConfig:
    with open(path, "rb") as fh:
        raw = tomllib.load(fh)
    return GateConfig(ResearchThresholds(**raw.get("research", {})), PaperThresholds(**raw.get("paper", {})),
                      DecayThresholds(**raw.get("decay", {})), int(raw.get("evidence", {}).get("max_age_days", 365)))


@dataclass(frozen=True)
class Check:
    number: int
    criterion: str
    value: str
    passed: bool


def decide(checks: list[Check]) -> str:
    """All checks pass -> PAPER; only the sample-size check (#1) fails -> RESEARCH; otherwise REJECTED."""
    failed = [c.number for c in checks if not c.passed]
    return "PAPER" if not failed else ("RESEARCH" if failed == [1] else "REJECTED")


def yearly_table(trades: pd.DataFrame, cost: float) -> pd.DataFrame:
    years = pd.Series([d.year for d in trades["signal_date"]], index=trades.index)
    net = trades["gross"] - cost
    table = pd.DataFrame({"trades": net.groupby(years).size(), "win_pct": 100 * (net > 0).groupby(years).mean(),
                          "exp_net_pct": 100 * net.groupby(years).mean()})
    table.index.name = "year"
    return table


def research_checks(trades: pd.DataFrame, cost: float, holdout_start: date, session_days: dict[str, list],
                    p_value: float, stocks: bool, t: ResearchThresholds = ResearchThresholds()):
    """Score a backtest. `trades` covers the whole evaluation span; the holdout is every trade signalled
    on or after `holdout_start`. `session_days` has the trading days of "design", "holdout" and "all"
    (for Sharpe). `p_value` is the holdout random-baseline p after multiple-testing correction.
    Returns (checks, details) where details has per-period stats, the yearly table, stress and worst R."""
    design = trades[trades["signal_date"] < holdout_start]
    holdout = trades[trades["signal_date"] >= holdout_start]
    stats = {"design": summarize(design, cost, session_days["design"]),
             "holdout": summarize(holdout, cost, session_days["holdout"]),
             "all": summarize(trades, cost, session_days["all"])}
    h, d = stats["holdout"], stats["design"]
    n = h.get("trades", 0)
    net = holdout["gross"] - cost
    stress = 100 * (holdout["gross"] - t.cost_stress * cost).mean() if n else np.nan
    worst_r = float((net / holdout["risk"]).min()) if n and holdout["risk"].notna().all() else np.nan
    by_year = yearly_table(trades, cost)
    counted = by_year[by_year["trades"] >= t.min_trades_per_year]
    share_years = (counted["exp_net_pct"] > 0).mean() if len(counted) else np.nan
    with_stop = not np.isnan(worst_r)
    checks = [
        Check(1, f"At least {t.min_trades} holdout trades", f"{n}", n >= t.min_trades),
        Check(2, f"Win rate at least {t.min_win_rate:.0%}", f"{h.get('win_pct', np.nan):.1f}%",
              n > 0 and h["win_pct"] >= 100 * t.min_win_rate),
        Check(3, f"Expectancy above 0 at base and {t.cost_stress}x costs",
              f"{h.get('exp_net_pct', np.nan):+.3f}% / {stress:+.3f}%", n > 0 and h["exp_net_pct"] > 0 and stress > 0),
        Check(4, f"t-statistic at least {t.min_t_stat}", f"{h.get('t_stat', np.nan):.2f}",
              n > 2 and h["t_stat"] >= t.min_t_stat),
        Check(5, f"Beats random entries (Holm-adjusted p < {t.max_p_value})", f"{p_value:.3f}", p_value < t.max_p_value),
        Check(6, f"Profit factor at least {t.min_profit_factor}", f"{h.get('profit_factor', np.nan):.2f}",
              n > 0 and h["profit_factor"] >= t.min_profit_factor),
        Check(7, f"Avg loss at most {t.max_loss_to_win}x avg win"
              + (f"; worst trade no worse than {t.worst_trade_r:g}R" if with_stop else ""),
              f"{h.get('avg_loss_pct', np.nan):+.2f}% vs {h.get('avg_win_pct', np.nan):+.2f}%"
              + (f"; worst {worst_r:+.1f}R" if with_stop else ""),
              n > 0 and abs(h["avg_loss_pct"]) <= t.max_loss_to_win * h["avg_win_pct"]
              and (not with_stop or worst_r >= t.worst_trade_r)),
        Check(8, "Design-period expectancy also above 0", f"{d.get('exp_net_pct', np.nan):+.3f}%",
              d.get("trades", 0) > 0 and d["exp_net_pct"] > 0),
        Check(9, f"At least {t.min_positive_years:.0%} of years ({t.min_trades_per_year}+ trades) positive",
              f"{share_years:.0%} of {len(counted)} years", bool(share_years >= t.min_positive_years)),
    ]
    if stocks:
        all_net = trades["gross"] - cost
        per_stock = all_net.groupby(trades["ticker"]).agg(["mean", "count", "sum"])
        counted_stocks = per_stock[per_stock["count"] >= t.min_trades_per_stock]
        breadth = (counted_stocks["mean"] > 0).mean() if len(counted_stocks) else np.nan
        top = per_stock["sum"].idxmax() if len(per_stock) else None
        without_top = 100 * all_net[trades["ticker"] != top].mean() if top else np.nan
        checks.append(Check(10, f"{t.min_breadth:.0%}+ of stocks profitable; still positive without the top stock",
                            f"{breadth:.0%} of {len(counted_stocks)} stocks; {without_top:+.3f}% without {top}",
                            bool(breadth >= t.min_breadth and without_top > 0)))
    return checks, {"stats": stats, "by_year": by_year, "stress": stress, "worst_r": worst_r}


def paper_checks(paper_net: pd.Series, weeks: float, research_mean: float, research_sd: float, research_n: int,
                 realised_cost: float, modelled_cost: float, t: PaperThresholds = PaperThresholds()) -> list[Check]:
    """Score paper-trading results (net return per trade) against the research holdout they should match
    (its mean, standard deviation and trade count, as stored in the research evidence)."""
    n = len(paper_net)
    mean = float(paper_net.mean()) if n else math.nan
    half_width = 1.96 * research_sd / math.sqrt(research_n) if research_n > 1 else math.inf
    low, high = research_mean - half_width, research_mean + half_width
    return [
        Check(1, f"At least {t.min_weeks} weeks of paper trading", f"{weeks:.1f} weeks", weeks >= t.min_weeks),
        Check(2, f"At least {t.min_trades} paper trades", f"{n}", n >= t.min_trades),
        Check(3, "Paper expectancy inside the research holdout's 95% interval",
              f"{100 * mean:+.3f}% vs [{100 * low:+.3f}%, {100 * high:+.3f}%]", n > 0 and low <= mean <= high),
        Check(4, "Paper expectancy above 0", f"{100 * mean:+.3f}%", n > 0 and mean > 0),
        Check(5, f"Realised costs at most {t.max_cost_ratio}x modelled",
              f"{100 * realised_cost:.3f}% vs {100 * modelled_cost:.3f}%", realised_cost <= t.max_cost_ratio * modelled_cost),
    ]


def decide_paper(checks: list[Check]) -> str:
    """All pass -> LIVE_SMALL; only time or trade count short -> PAPER (keep going); otherwise RESEARCH."""
    failed = {c.number for c in checks if not c.passed}
    return "LIVE_SMALL" if not failed else ("PAPER" if failed <= {1, 2} else "RESEARCH")


@dataclass(frozen=True)
class Evidence:
    strategy_id: str
    kind: str  # "research", "paper" or "live"
    decision: str  # the status this evidence supports
    generated: str  # ISO date
    source: str  # the report or command that produced it
    checks: tuple = ()
    stats: dict | None = None
    preregistration_sha256: str = ""

    @property
    def generated_date(self) -> date:
        return date.fromisoformat(self.generated[:10])


def _jsonable(value):
    if isinstance(value, (np.floating, np.integer)):
        return value.item()
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def evidence_path(strategy_id: str, kind: str, directory: Path = EVIDENCE_DIR) -> Path:
    return Path(directory) / f"{strategy_id}.{kind}.json"


def save_evidence(evidence: Evidence, directory: Path = EVIDENCE_DIR) -> Path:
    path = evidence_path(evidence.strategy_id, evidence.kind, directory)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(evidence), indent=2, default=_jsonable) + "\n", encoding="utf-8")
    return path


def load_evidence(strategy_id: str, kind: str, directory: Path = EVIDENCE_DIR) -> Evidence | None:
    path = evidence_path(strategy_id, kind, directory)
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    data["checks"] = tuple(data.get("checks", ()))
    return Evidence(**data)


# What each status needs, beyond the one below it: (evidence kind, decisions that support it).
REQUIREMENTS = {"PAPER": ("research", {"PAPER", "LIVE_SMALL", "LIVE"}),
                "LIVE_SMALL": ("paper", {"LIVE_SMALL", "LIVE"}),
                "LIVE": ("live", {"LIVE"})}


def supported_status(claimed: str, strategy_id: str, today: date, cfg: GateConfig = GateConfig(),
                     directory: Path = EVIDENCE_DIR) -> tuple[str, str | None]:
    """The highest status, up to `claimed`, that the evidence on file supports; plus why it was lowered."""
    if claimed not in LADDER:
        raise ValueError(f"unknown status {claimed!r}")
    status = "RESEARCH" if LADDER.index(claimed) >= LADDER.index("RESEARCH") else claimed
    for step in ("PAPER", "LIVE_SMALL", "LIVE"):
        if LADDER.index(claimed) < LADDER.index(step):
            break
        kind, accepted = REQUIREMENTS[step]
        evidence = load_evidence(strategy_id, kind, directory)
        if evidence is None:
            return status, f"needs {kind} evidence for {step}, but there is none"
        age = (today - evidence.generated_date).days
        if age > cfg.max_evidence_age_days:
            return status, f"its {kind} evidence is {age} days old (limit {cfg.max_evidence_age_days})"
        if evidence.decision not in accepted:
            return status, f"its {kind} evidence decided {evidence.decision}, which doesn't support {step}"
        status = step
    return status, None


def decay_check(net_r, research_win_rate: float, cfg: DecayThresholds = DecayThresholds()) -> tuple[str, str]:
    """Watch paper or live trades (net results in R, oldest first). Returns ("keep" | "demote" | "disable",
    reason): disable on a drawdown beyond the limit; demote when the latest `window` trades win clearly
    less often than research said, or lose money on average."""
    values = np.asarray(net_r, dtype=float)
    if len(values):
        equity = np.cumsum(values)
        drawdown = float((equity - np.maximum.accumulate(np.r_[0.0, equity])[1:]).min())
        if drawdown <= -cfg.max_drawdown_r:
            return "disable", f"drawdown of {drawdown:.1f}R exceeds the {cfg.max_drawdown_r:g}R limit"
    recent = values[-cfg.window:]
    if len(recent) < cfg.window:
        return "keep", f"{len(recent)} of {cfg.window} trades so far"
    win_rate = float((recent > 0).mean())
    if win_rate < research_win_rate - cfg.max_win_rate_drop:
        return "demote", f"won {win_rate:.0%} of the last {cfg.window} trades vs {research_win_rate:.0%} in research"
    if recent.mean() <= 0:
        return "demote", f"averaged {recent.mean():+.2f}R over the last {cfg.window} trades"
    return "keep", "in line with research"
