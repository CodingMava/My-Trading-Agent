"""The harness must keep reproducing the 2026-10-08 audit. Needs the frozen data in data/audit_2026-10-08
(git-ignored); run with `pytest -m slow`."""
import pytest

from trader.research import audit
from trader.research.costs import AUDIT_2026_10_08 as COSTS
from trader.research.datasets import load_dataset
from trader.research.metrics import summarize

pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(not (audit.AUDIT_DIR / "in_5m_60d" / "manifest.json").exists(),
                       reason="frozen audit data not present"),
]

# rule: (trades, win %, net % per trade, t-stat), India 5-minute, entry at the next bar's open
EXPECTED_RULES = {
    "R1": (604, 40.563, -0.102, -3.281), "R2": (152, 34.211, -0.201, -3.093),
    "R4": (454, 35.903, -0.175, -4.450), "R5": (661, 36.762, -0.191, -6.067),
    "R6": (356, 40.169, -0.117, -2.749), "R7": (374, 35.561, -0.188, -4.367),
    "R8L": (1234, 38.979, -0.152, -6.623), "R8S": (1274, 43.014, -0.106, -4.679),
}


def check(stats, trades, win=None, exp=None, t=None):
    assert stats["trades"] == trades
    if win is not None:
        assert stats["win_pct"] == pytest.approx(win, abs=6e-4)
    if exp is not None:
        assert stats["exp_net_pct"] == pytest.approx(exp, abs=6e-4)
    if t is not None:
        assert stats["t_stat"] == pytest.approx(t, abs=6e-3)


def prepared(name):
    raw = load_dataset(audit.AUDIT_DIR / name)
    result = audit.prepare(raw, audit.DATASETS[name]["drop_dates"])
    return result, audit.session_dates(result)


@pytest.fixture(scope="module")
def india_5m():
    return prepared("in_5m_60d")


def test_india_5m_each_rule(india_5m):
    data, dates = india_5m
    assert len(dates) == 56
    for rule, (trades, win, exp, t) in EXPECTED_RULES.items():
        check(summarize(audit.independent_trades(data, rule, "next_open"), COSTS["india_intraday"]["base"], dates),
              trades, win, exp, t)
    assert len(audit.independent_trades(data, "R3", "next_open")) == 0


def test_india_5m_as_deployed(india_5m):
    data, dates = india_5m
    check(summarize(audit.chain_trades(data, "signal_close"), COSTS["india_intraday"]["base"], dates), 1616, exp=-0.174, t=-7.953)
    check(summarize(audit.chain_trades(data, "next_open"), COSTS["india_intraday"]["base"], dates), 1620, exp=-0.170, t=-7.761)


def test_india_5m_random_entry_test(india_5m):
    data, dates = india_5m
    card = audit.scorecard(data, dates, COSTS["india_intraday"], entries=("next_open",))
    p_values = dict(zip(card["rule"], card["p_vs_random"]))
    assert p_values["R1"] == pytest.approx(0.194, abs=1e-3) and p_values["R5"] == pytest.approx(0.817, abs=1e-3)


def test_india_5m_multiday_sensitivity():
    raw = load_dataset(audit.AUDIT_DIR / "in_5m_60d")
    table = audit.multiday_table(raw, (), COSTS["india_delivery"]).set_index("rule")
    assert table.loc["R1", "trades"] == 465 and table.loc["R1", "exp_net_pct"] == pytest.approx(-0.419, abs=6e-4)


def test_us_5m_as_deployed():
    data, dates = prepared("us_5m_60d")
    assert len(dates) == 57
    check(summarize(audit.chain_trades(data, "next_open"), COSTS["us_intraday"]["base"], dates), 1692, exp=-0.064, t=-2.888)


def test_india_1h_as_deployed():
    data, dates = prepared("in_1h_730d")
    assert len(dates) == 695
    check(summarize(audit.chain_trades(data, "next_open"), COSTS["india_intraday"]["base"], dates), 10248, exp=-0.146, t=-18.025)
