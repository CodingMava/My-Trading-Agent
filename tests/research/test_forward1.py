from datetime import date

import numpy as np
import pandas as pd
import pytest

from trader.gate import load_evidence
from trader.research import forward1


def tom_bars(end, tz, bump=0.012, down_every=4):
    """Bars from 1 Jun 2026 to `end` that move +-0.4% on alternate days, plus `bump` on each turn of the
    month (a month's last trading day and the next three); every `down_every`th turn falls by half as much."""
    days = pd.bdate_range("2026-06-01", end, tz=tz)
    months = days.year * 12 + days.month
    last = np.r_[months[1:] != months[:-1], False]
    turn, turn_no = np.zeros(len(days)), np.cumsum(last)
    for i in np.flatnonzero(last):
        sign = -0.5 if turn_no[i] % down_every == 0 else 1.0
        turn[i:i + 4] = sign * bump / 4
    returns = np.where(np.arange(len(days)) % 2 == 0, 0.004, -0.004) + turn
    close = 100 * np.cumprod(1 + returns)
    open_ = np.r_[100.0, close[:-1]]
    return pd.DataFrame({"open": open_, "high": np.maximum(open_, close) * 1.001, "low": np.minimum(open_, close) * 0.999,
                         "close": close, "volume": 1_000_000}, index=days)


def pieces(end, **kwargs):
    return {"H11": {s: tom_bars(end, "Asia/Kolkata", **kwargs) for s in forward1.TESTS["H11"][2]},
            "H12": {s: tom_bars(end, "America/New_York", **kwargs) for s in forward1.TESTS["H12"][2]}}


def test_the_preregistration_is_unchanged():
    assert forward1.check_preregistration().startswith("c30df70e")


def test_only_januarys_from_2028_decide_and_the_last_is_2036():
    assert [forward1.look_number(date(y, 1, 5)) for y in (2027, 2028, 2029, 2036, 2037)] == [0, 1, 2, 9, 0]
    assert forward1.look_number(date(2028, 6, 5)) == 0  # outside January: informational
    assert forward1.cutoff(date(2028, 1, 5)) == date(2027, 12, 31) and forward1.cutoff(date(2027, 6, 5)) == date(2027, 6, 4)
    passed, failed = [forward1.Check(1, "c", "v", True)], [forward1.Check(1, "c", "v", False)]
    assert forward1.decision(0, passed, 0.01) == "INFORMATIONAL"
    assert forward1.decision(1, passed, 0.01) == "PAPER"
    assert forward1.decision(1, failed, -0.01) == "CONTINUE"  # no retirement at the first decision look
    assert forward1.decision(2, failed, 0.0) == "REJECTED" and forward1.decision(2, failed, 0.001) == "CONTINUE"
    assert forward1.decision(9, failed, 0.01) == "REJECTED"  # the test ends


def test_an_effect_that_keeps_working_becomes_a_candidate_for_paper():
    results = forward1.results_for(pieces("2027-12-31"), date(2028, 1, 5))
    for key, r in results.items():
        assert r["trades"]["signal_date"].min() >= forward1.FIRST_SIGNAL  # nothing from before the pin
        assert r["trades"]["signal_date"].max() <= date(2027, 11, 30)  # December's turn ends in January: not yet
        assert r["decision"] == "PAPER", [c for c in r["checks"] if not c.passed]
    assert len(results["H11"]["trades"]) == 4 * 14  # four indices, October 2026 to November 2027


def test_an_effect_that_stopped_working_is_retired_from_the_second_decision_look():
    faded = pieces("2028-12-29", bump=-0.012)
    assert {r["decision"] for r in forward1.results_for(faded, date(2029, 1, 5)).values()} == {"REJECTED"}
    early = forward1.results_for(pieces("2027-12-31", bump=-0.012), date(2028, 1, 5))
    assert {r["decision"] for r in early.values()} == {"CONTINUE"}


def test_each_decision_look_raises_the_bar_for_beating_random_entries(monkeypatch):
    monkeypatch.setattr(forward1, "same_day_random_test", lambda pools, trades: (0.0, 0.02))

    def criterion_5(end, as_of):
        return next(c for c in forward1.results_for(pieces(end), as_of)["H11"]["checks"] if c.number == 5)

    first, second = criterion_5("2027-12-31", date(2028, 1, 5)), criterion_5("2028-12-29", date(2029, 1, 5))
    assert (first.value, first.passed) == ("0.040", True)  # Holm across the two makes 0.04: under 0.05 at look 1
    assert (second.value, second.passed) == ("0.080", False)  # the same evidence needs 0.025 at look 2


class FakeYahoo:
    name = "fake"

    def __init__(self, frames):
        self.frames = frames

    def history(self, symbol, interval, start, end):
        frame = self.frames[symbol]
        return frame[(frame.index >= start) & (frame.index < end)]


def test_a_look_freezes_its_data_reports_and_records_a_decision(tmp_path, monkeypatch):
    monkeypatch.setattr(forward1, "DATA", tmp_path / "data")
    monkeypatch.setattr(forward1, "RESULTS", tmp_path / "forward1-results.md")
    monkeypatch.setattr(forward1, "EVIDENCE", tmp_path / "evidence")
    frames = {s: f for group in pieces("2027-12-31").values() for s, f in group.items()}
    assert forward1.fetch(date(2028, 1, 5), FakeYahoo(frames)) == tmp_path / "data" / "2028-01-05"
    forward1.main(["--as-of", "2028-01-05", "--no-fetch"])
    report = (tmp_path / "forward1-results.md").read_text(encoding="utf-8")
    assert "decision look 1" in report and "| PAPER |" in report
    assert sorted(p.name for p in (tmp_path / "evidence").iterdir()) == ["H11F.research.json", "H12F.research.json"]
    recorded = load_evidence("H11F", "research", tmp_path / "evidence").stats["max_drawdown_r"]
    assert 0 <= recorded <= 20  # the gate's drawdown limit can be checked on it
    with pytest.raises(SystemExit, match="no data"):
        forward1.fetch(date(2028, 1, 5), FakeYahoo({}))


def test_before_the_first_forward_trade_it_waits(tmp_path, monkeypatch):
    results = forward1.results_for(pieces("2026-10-20"), date(2026, 10, 21))
    assert {r["decision"] for r in results.values()} == {"WAITING"}
    monkeypatch.setattr(forward1, "RESULTS", tmp_path / "forward1-results.md")
    forward1.write_report(date(2026, 10, 21), results, "c30df70e" * 8)
    assert "informational; nothing is decided" in (tmp_path / "forward1-results.md").read_text(encoding="utf-8")
