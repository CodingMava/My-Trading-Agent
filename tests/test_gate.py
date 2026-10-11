from datetime import date

import numpy as np
import pandas as pd
import pytest

from trader.gate import (Check, Evidence, GateConfig, ResearchThresholds, decay_check, decide, decide_paper,
                         load_evidence, load_gate_config, paper_checks, research_checks, save_evidence,
                         supported_status)
from trader.registry import StrategyRegistry

HOLDOUT = date(2022, 1, 1)


def make_trades(n_per_year, win_rate, win, loss, years=range(2016, 2027), tickers=("A", "B", "C", "D"), risk=0.02):
    """Trades (zero costs) that win `win` or lose `loss`, in a repeating pattern of 10 with
    round(10 * win_rate) winners."""
    rows = []
    for year in years:
        for i in range(n_per_year):
            won = (i % 10) < round(10 * win_rate)
            day = date(year, 1 + i % 12, 1 + (i // 12) % 28)
            rows.append({"ticker": tickers[i % len(tickers)], "signal_date": day, "exit_date": day,
                         "signal_time": pd.Timestamp(day), "exit_time": pd.Timestamp(day) + pd.Timedelta(hours=i),
                         "gross": win if won else -loss, "reason": 0, "hold_bars": 3, "risk": risk})
    return pd.DataFrame(rows)


def score(trades, p_value=0.001, stocks=True, thresholds=ResearchThresholds()):
    days = sorted(set(trades["signal_date"]))
    sessions = {"design": [d for d in days if d < HOLDOUT], "holdout": [d for d in days if d >= HOLDOUT], "all": days}
    checks, details = research_checks(trades, 0.0, HOLDOUT, sessions, p_value, stocks, thresholds)
    return {c.number: c.passed for c in checks}, decide(checks), details


def test_a_strong_consistent_strategy_passes_every_criterion():
    passed, decision, details = score(make_trades(30, 0.6, 0.02, 0.01))
    assert all(passed.values()) and decision == "PAPER"
    assert details["stats"]["holdout"]["trades"] == 30 * 5 and details["worst_r"] == pytest.approx(-0.5)


def test_a_high_win_rate_with_big_losses_is_rejected():
    passed, decision, _ = score(make_trades(30, 0.7, 0.01, 0.03))  # 70% winners, but each loss is 3 wins
    assert passed[2] and not passed[3] and not passed[6] and not passed[7] and decision == "REJECTED"


def test_too_few_trades_alone_means_research():
    passed, decision, _ = score(make_trades(10, 0.6, 0.02, 0.01, years=range(2016, 2026)))  # 40 holdout trades
    assert [n for n, ok in passed.items() if not ok] == [1] and decision == "RESEARCH"


def test_not_beating_random_entries_is_rejected():
    passed, decision, _ = score(make_trades(30, 0.6, 0.02, 0.01), p_value=0.2)
    assert not passed[5] and decision == "REJECTED"


def test_thresholds_are_boundaries():
    lenient = ResearchThresholds(min_trades=150, min_win_rate=0.6, min_profit_factor=2.99)
    passed, _, _ = score(make_trades(30, 0.6, 0.02, 0.01), thresholds=lenient)
    assert passed[1] and passed[2] and passed[6]  # exactly 150 trades and 60% winners; PF 3.0
    strict = ResearchThresholds(min_trades=151, min_win_rate=0.61, min_profit_factor=3.01)
    passed, _, _ = score(make_trades(30, 0.6, 0.02, 0.01), thresholds=strict)
    assert not passed[1] and not passed[2] and not passed[6]


def test_repository_gate_config_matches_the_preregistered_defaults():
    assert load_gate_config() == GateConfig()


def research_evidence(decision="PAPER", generated="2026-10-01", kind="research"):
    return Evidence("X1", kind, decision, generated, "test", stats={"holdout_win_rate": 0.6})


def test_evidence_round_trip(tmp_path):
    save_evidence(research_evidence(), tmp_path)
    loaded = load_evidence("X1", "research", tmp_path)
    assert loaded.decision == "PAPER" and loaded.generated_date == date(2026, 10, 1)
    assert load_evidence("X1", "paper", tmp_path) is None


def test_status_is_limited_to_what_the_evidence_supports(tmp_path):
    today = date(2026, 10, 9)
    assert supported_status("REJECTED", "X1", today, directory=tmp_path) == ("REJECTED", None)
    assert supported_status("RESEARCH", "X1", today, directory=tmp_path) == ("RESEARCH", None)
    status, why = supported_status("PAPER", "X1", today, directory=tmp_path)
    assert status == "RESEARCH" and "none" in why
    save_evidence(research_evidence(), tmp_path)
    assert supported_status("PAPER", "X1", today, directory=tmp_path) == ("PAPER", None)
    status, why = supported_status("LIVE", "X1", today, directory=tmp_path)
    assert status == "PAPER" and "paper evidence" in why
    save_evidence(research_evidence("LIVE_SMALL", kind="paper"), tmp_path)
    assert supported_status("LIVE_SMALL", "X1", today, directory=tmp_path) == ("LIVE_SMALL", None)
    assert supported_status("LIVE", "X1", today, directory=tmp_path)[0] == "LIVE_SMALL"  # no live evidence yet


def test_stale_or_failing_evidence_does_not_count(tmp_path):
    save_evidence(research_evidence(generated="2025-01-01"), tmp_path)
    status, why = supported_status("PAPER", "X1", date(2026, 10, 9), directory=tmp_path)
    assert status == "RESEARCH" and "days old" in why
    save_evidence(research_evidence(decision="REJECTED"), tmp_path)
    status, why = supported_status("PAPER", "X1", date(2026, 10, 9), directory=tmp_path)
    assert status == "RESEARCH" and "REJECTED" in why


def test_the_registry_will_not_load_an_unproven_live_strategy(tmp_path):
    config = tmp_path / "strategies.toml"
    config.write_text('[X1]\nname = "Unproven"\nstatus = "LIVE"\n', encoding="utf-8")
    registry = StrategyRegistry.load(config, evidence_dir=tmp_path, today=date(2026, 10, 9))
    assert registry.live_strategies() == [] and registry.get("Unproven").status == "RESEARCH"
    assert "lowered from LIVE to RESEARCH" in registry.problems[0]


def test_every_registered_strategy_holds_its_status():
    assert StrategyRegistry.load().problems == []


def test_paper_checks_and_decision():
    good = pd.Series([0.012, -0.006] * 25)  # 50 trades averaging +0.3%
    research = dict(research_mean=0.003, research_sd=0.02, research_n=400, modelled_cost=0.003)
    ready = dict(clean_sessions=60, reviewed_trades=20)
    checks = paper_checks(good, weeks=13, realised_cost=0.0035, **research, **ready)
    assert all(c.passed for c in checks) and decide_paper(checks) == "LIVE_SMALL"
    early = paper_checks(good[:20], weeks=3, realised_cost=0.003, **research, clean_sessions=15)
    assert decide_paper(early) == "PAPER"  # promising but not enough time, trades, sessions or review yet
    off = paper_checks(-good, weeks=13, realised_cost=0.003, **research, **ready)
    assert decide_paper(off) == "RESEARCH"  # results contradict the research


def test_level_5_needs_three_months_a_clean_system_and_a_human_review():
    good = pd.Series([0.012, -0.006] * 25)
    research = dict(research_mean=0.003, research_sd=0.02, research_n=400, realised_cost=0.003, modelled_cost=0.003)
    failing = lambda checks: {c.number for c in checks if not c.passed}  # noqa: E731
    two_months = paper_checks(good, weeks=9, **research, clean_sessions=60, reviewed_trades=20)
    assert failing(two_months) == {1} and decide_paper(two_months) == "PAPER"
    crashed = paper_checks(good, weeks=13, **research, clean_sessions=59, reviewed_trades=20)
    assert failing(crashed) == {6} and decide_paper(crashed) == "PAPER"
    defect = paper_checks(good, weeks=13, **research, clean_sessions=60, duplicate_orders=1, reviewed_trades=20)
    assert failing(defect) == {7} and decide_paper(defect) == "PAPER"  # fix the system, not the strategy
    unreviewed = paper_checks(good, weeks=13, **research, clean_sessions=60, reconciliation_problems=0)
    assert failing(unreviewed) == {8} and decide_paper(unreviewed) == "PAPER"


def test_decay_monitor():
    assert decay_check(np.full(10, 0.5), 0.6)[0] == "keep"  # too few trades to judge
    steady = np.tile([1.0, 1.0, -1.0], 20)[:50]
    assert decay_check(steady, 0.6)[0] == "keep"
    rarely_wins = np.tile([2.0, -0.6, -0.6, -0.6, -0.6, -0.6, -0.6, 2.0, 2.0, -0.6], 5)  # profitable, 30% winners
    assert decay_check(rarely_wins, 0.6)[0] == "demote"
    assert decay_check(np.tile([0.5, 0.5, -1.5], 17)[:50], 0.6)[0] == "demote"  # wins 2 in 3 but loses money
    assert decay_check(np.full(30, -1.0), 0.6)[0] == "disable"  # 30R drawdown
    assert decide([Check(1, "", "", True)]) == "PAPER"
