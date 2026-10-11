from datetime import date

import pandas as pd

from trader.research import round5


def test_the_preregistration_is_unchanged():
    assert round5.check_preregistration().startswith("a78ed4f2")


def test_each_third_of_the_span_must_be_profitable():
    start, end = date(2001, 1, 1), date(2025, 12, 31)  # thirds: to Apr 2009, to Aug 2017, to the end
    trades = pd.DataFrame({"signal_date": [date(2003, 1, 1), date(2012, 1, 1), date(2020, 1, 1), date(2025, 12, 31)],
                           "gross": [0.01, 0.01, -0.02, 0.03]})
    check = round5.thirds_check(trades, 0.001, start, end)
    assert check.number == 9 and check.passed and check.value == "+0.900% / +0.900% / +0.400%"
    assert not round5.thirds_check(trades.iloc[:3], 0.001, start, end).passed  # the last third lost money
    assert not round5.thirds_check(trades.iloc[1:], 0.001, start, end).passed  # no trades in the first third


def test_every_flagged_move_is_classified():
    assert round5.classify("EWY", date(2008, 10, 30)).startswith("Genuine")
    assert round5.classify("EWY", date(2008, 10, 31)) is None
