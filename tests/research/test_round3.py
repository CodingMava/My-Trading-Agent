from datetime import date

import pandas as pd

from trader.gate import Check
from trader.research import round3


def test_the_preregistration_is_unchanged():
    assert round3.check_preregistration().startswith("78c1275b")


def test_each_half_of_the_span_must_be_profitable():
    trades = pd.DataFrame({"signal_date": [date(2001, 5, 1), date(2005, 5, 1), date(2009, 5, 1), date(2014, 5, 1)],
                           "gross": [0.02, 0.01, 0.004, -0.010]})
    split = date(2008, 1, 1)
    assert round3.halves_check(trades, 0.0005, split).passed is False  # 2008-2015 lost money
    assert round3.halves_check(trades.assign(gross=[0.02, 0.01, 0.004, 0.001]), 0.0005, split).passed
    assert not round3.halves_check(trades.iloc[:2], 0.0005, split).passed  # no trades at all in one half


def _result(*failed):
    return {"checks": [Check(n, "", "", n not in failed) for n in range(1, 12)]}


def test_the_round_passes_only_if_both_hypotheses_do():
    both = {"H7": _result(), "H8": _result()}
    round3.join_verdicts(both)
    assert [r["decision"] for r in both.values()] == ["PAPER", "PAPER"]
    one = {"H7": _result(), "H8": _result(5)}
    round3.join_verdicts(one)
    assert [r["decision"] for r in one.values()] == ["REJECTED", "REJECTED"]  # H7 passed 1-11 alone: not enough
    assert one["H7"]["checks"][-1].value == "H8 fails"


def test_every_flagged_move_has_a_classification():
    assert round3.classify("XLF", date(2008, 9, 19)).startswith("Genuine")
    assert round3.classify("XLF", date(2008, 9, 22)) is None
