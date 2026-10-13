"""Round 7's runner on synthetic bars only: the real frozen data is used once, by the run itself."""
from datetime import date, time

import numpy as np
import pandas as pd
import pytest

from trader.research import round7
from trader.research.datasets import save_dataset

IST = round7.IST


def flat_day(day: str, price: float, start="09:15", end="15:29", volume=1000) -> pd.DataFrame:
    stamps = pd.date_range(f"{day} {start}", f"{day} {end}", freq="min", tz=IST)
    return pd.DataFrame({"open": price, "high": price, "low": price, "close": price, "volume": volume}, index=stamps)


def set_bar(frame: pd.DataFrame, stamp: str, **values) -> None:
    for column, value in values.items():
        frame.loc[pd.Timestamp(stamp, tz=IST), column] = value


def test_the_preregistration_and_costs_are_the_pinned_ones():
    assert round7.check_preregistration() == round7.PREREGISTRATION_SHA256
    assert round7.ROUND_TRIP == pytest.approx(0.0011908, abs=1e-7) and round7.STOP_EXTRA == 0.0003
    assert round7.CROSS_ROUND_ALPHA == pytest.approx(0.05 / 23) and round7.DRAWS == 20_000


def test_r_first_uses_the_09_44_bar_and_the_previous_sessions_15_14_bar():
    day1 = flat_day("2026-03-02", 100.0)
    muhurat = flat_day("2026-03-03", 999.0, start="18:00", end="19:00")  # no 09:44 or 15:14 bar
    day3 = flat_day("2026-03-04", 100.0)
    set_bar(day1, "2026-03-02 15:14", close=100.0)
    set_bar(day1, "2026-03-02 15:29", close=150.0)  # after 15:14: not the "previous close"
    set_bar(day3, "2026-03-04 09:44", close=101.0)
    set_bar(day3, "2026-03-04 09:45", close=500.0)  # after the signal: never used
    index = pd.concat([day1, muhurat, day3]).assign(volume=0)
    etf = pd.concat([flat_day("2026-03-02", 1.0), flat_day("2026-03-04", 1.0)])
    table = round7.sessions({round7.INDEX: index, round7.ETF: etf})
    assert table.loc[date(2026, 3, 4), "r_first"] == pytest.approx(0.01) and table.loc[date(2026, 3, 4), "traded"]
    assert table.loc[date(2026, 3, 2), "reason"] == "no earlier session with an index 15:14 bar"
    assert table.loc[date(2026, 3, 3), "reason"] == "no index 09:44 bar"


def test_a_session_is_traded_only_if_niftybees_traded_at_14_45_and_nothing_later_drops_it():
    index = pd.concat([flat_day("2026-03-02", 100.0), flat_day("2026-03-03", 100.0), flat_day("2026-03-04", 100.0)])
    no_bar = flat_day("2026-03-03", 1.0).drop(pd.Timestamp("2026-03-03 14:45", tz=IST))
    silent = flat_day("2026-03-04", 1.0)
    set_bar(silent, "2026-03-04 14:45", volume=0)
    later = flat_day("2026-03-02", 1.0)
    set_bar(later, "2026-03-02 15:14", volume=0)  # known only after the entry: the session still counts
    etf = pd.concat([later, no_bar, silent])
    table = round7.sessions({round7.INDEX: index.assign(volume=0), round7.ETF: etf})
    assert table["reason"].tolist() == ["no earlier session with an index 15:14 bar", "no NIFTYBEES 14:45 bar",
                                        "NIFTYBEES 14:45 bar without trades"]
    index5 = pd.concat([index, flat_day("2026-03-05", 100.0)])
    later5 = flat_day("2026-03-05", 1.0)
    set_bar(later5, "2026-03-05 15:14", volume=0)
    table = round7.sessions({round7.INDEX: index5.assign(volume=0), round7.ETF: pd.concat([etf, later5])})
    assert table.loc[date(2026, 3, 5), "traded"]


def test_the_window_exits_at_15_14_or_at_the_last_traded_price():
    bars = flat_day("2026-03-04", 100.0)
    set_bar(bars, "2026-03-04 14:45", open=100.0)
    set_bar(bars, "2026-03-04 15:14", close=100.3)
    set_bar(bars, "2026-03-04 15:20", close=90.0)  # after the window: ignored
    long = round7.window(bars, "long")
    assert (long["entry"], long["exit"], long["stopped"]) == (100.0, 100.3, False)
    assert round7.gross(long, "long") == pytest.approx(0.003) and round7.gross(long, "short") == pytest.approx(-0.003)
    set_bar(bars, "2026-03-04 15:13", close=100.2)
    set_bar(bars, "2026-03-04 15:14", volume=0)
    assert round7.window(bars, "long")["exit"] == 100.2  # no trades at 15:14: the last traded price


def test_the_stop_fills_at_the_stop_or_at_a_gap_on_bars_that_traded():
    touched = flat_day("2026-03-04", 100.0)
    set_bar(touched, "2026-03-04 14:50", open=99.9, low=99.4, close=99.8)  # touches 99.5 within the minute
    trade = round7.window(touched, "long")
    assert (trade["exit"], trade["stopped"], trade["gapped"]) == (pytest.approx(99.5), True, False)
    gapped = flat_day("2026-03-04", 100.0)
    set_bar(gapped, "2026-03-04 14:50", open=99.0, low=98.8, close=99.1)  # jumped past the stop between minutes
    trade = round7.window(gapped, "long")
    assert (trade["exit"], trade["gapped"]) == (99.0, True)
    assert round7.window(gapped, "long", use_stop=False)["exit"] == 100.0
    entry_minute = flat_day("2026-03-04", 100.0)
    set_bar(entry_minute, "2026-03-04 14:45", low=99.0)  # the entry is the open; the low came after it
    assert round7.window(entry_minute, "long")["exit"] == pytest.approx(99.5)
    short = flat_day("2026-03-04", 100.0)
    set_bar(short, "2026-03-04 15:00", open=101.0, high=101.2, close=101.1)
    trade = round7.window(short, "short")
    assert (trade["exit"], trade["gapped"]) == (101.0, True) and round7.gross(trade, "short") == pytest.approx(-0.01)
    silent = flat_day("2026-03-04", 100.0)
    set_bar(silent, "2026-03-04 14:50", low=90.0, volume=0)  # a minute without trades offers no price
    assert round7.window(silent, "long")["stopped"] is False


def test_big_mornings_use_only_the_previous_250_sessions():
    days = pd.bdate_range("2025-01-01", periods=262)
    rng = np.random.default_rng(1)
    moves = rng.normal(0, 0.01, len(days))
    index_rows, etf_rows, close = [], [], 100.0
    for day, move in zip(days, moves):
        index_rows += [(pd.Timestamp(f"{day.date()} 09:44", tz=IST), close * (1 + move)),
                       (pd.Timestamp(f"{day.date()} 15:14", tz=IST), close * (1 + move))]
        etf_rows.append(pd.Timestamp(f"{day.date()} 14:45", tz=IST))
        close *= 1 + move
    index = pd.DataFrame(index_rows, columns=["stamp", "close"]).set_index("stamp").assign(open=1, high=1, low=1, volume=0)
    etf = pd.DataFrame(index=pd.DatetimeIndex(etf_rows)).assign(open=1.0, high=1.0, low=1.0, close=1.0, volume=5)
    table = round7.sessions({round7.INDEX: index, round7.ETF: etf})
    r = table["r_first"].dropna().abs()
    assert table["big_threshold"].notna().sum() == len(r) - 250  # 250 sessions of history first
    day = r.index[255]
    expected = np.percentile(r.iloc[5:255].to_numpy(), 80)  # the 250 before it, itself excluded
    assert table.loc[day, "big_threshold"] == pytest.approx(expected)
    assert table.loc[day, "big"] == (r.iloc[255] >= expected)


def test_the_random_baseline_counts_draws_at_least_as_high():
    assert round7.baseline({"long": np.zeros(10)}, {"long": 5}, 0.0, draws=100)[1] == 1.0  # every draw ties
    assert round7.baseline({"long": np.zeros(10)}, {"long": 5}, 1.0, draws=100)[1] == pytest.approx(1 / 101)
    mixed = round7.baseline({"long": np.ones(4), "short": -np.ones(4)}, {"long": 1, "short": 1}, 0.0, draws=100)
    assert mixed == (0.0, 1.0)
    first = round7.baseline({"long": np.arange(50.0)}, {"long": 3}, 30.0)
    assert first == round7.baseline({"long": np.arange(50.0)}, {"long": 3}, 30.0)  # seeded: the same every time


def test_drawdown_in_r_starts_from_zero():
    assert round7.drawdown_r(np.array([1.0, -2.0, -3.0, 1.0])) == 5.0
    assert round7.drawdown_r(np.array([-1.0, -1.0])) == 2.0 and round7.drawdown_r(np.array([])) == 0.0


def synthetic(days=300, seed=3) -> dict[str, pd.DataFrame]:
    """Regular sessions with random minute moves: the index near 20,000, NIFTYBEES following it at 1/100."""
    rng, frames, price = np.random.default_rng(seed), [], 20_000.0
    for day in pd.bdate_range("2025-01-01", periods=days):
        stamps = pd.date_range(f"{day.date()} 09:15", f"{day.date()} 15:29", freq="min", tz=IST)
        price *= 1 + rng.normal(0, 0.004)  # overnight
        close = price * np.cumprod(1 + rng.normal(0, 0.0004, len(stamps)))
        open_ = np.r_[price, close[:-1]]
        frames.append(pd.DataFrame({"open": open_, "high": np.maximum(open_, close) * 1.0002,
                                    "low": np.minimum(open_, close) * 0.9998, "close": close}, index=stamps))
        price = close[-1]
    index = pd.concat(frames)
    return {round7.INDEX: index.assign(volume=0), round7.ETF: (index / 100).assign(volume=1000)}


def test_a_full_run_on_synthetic_bars(tmp_path, monkeypatch):
    save_dataset(synthetic(), tmp_path / "minutes", source="test", interval="1m")
    with pytest.raises(SystemExit, match="isn't the pinned data"):
        round7.run(tmp_path / "minutes")
    report = round7.run(tmp_path / "minutes", verify_pins=False)
    results = report["results"]
    assert list(results) == ["I1", "I2", "I3"] and report["traded_sessions"] == 299  # the first has no previous close
    for key, r in results.items():
        assert r["decision"] in ("PAPER", "RESEARCH", "REJECTED"), key
        assert [c.number for c in r["checks"]] == [1, 2, 3, 4, 5, 6, 7, 8, 9, 11, 12, 13]
        assert set(r["trades"]["cost"].round(7)) <= {round(round7.ROUND_TRIP, 7), round(round7.ROUND_TRIP + 0.0003, 7)}
        assert 0 < r["raw_p"] <= 1 and r["holm_p"] >= r["raw_p"]
    i1, i2, i3 = (set(results[k]["trades"]["session"]) for k in ("I1", "I2", "I3"))
    assert not i1 & i2 and i3 <= i1 | i2 and len(i3) > 0  # separate tests; I3's trades are among I1's and I2's
    monkeypatch.setattr(round7, "RESULTS", tmp_path / "round7-results.md")
    round7.write_report(report, "abc123")
    text = (tmp_path / "round7-results.md").read_text(encoding="utf-8")
    assert "## Verdict" in text and all(f"## {key}:" in text for key in results)


def test_it_runs_once_and_only_from_committed_code(tmp_path, monkeypatch):
    done = tmp_path / "round7-results.md"
    done.write_text("already run", encoding="utf-8")
    monkeypatch.setattr(round7, "RESULTS", done)
    with pytest.raises(SystemExit, match="runs once"):
        round7.main([])
    monkeypatch.setattr(round7, "RESULTS", tmp_path / "not-yet.md")
    monkeypatch.setattr(round7, "git_commit", lambda: ("abc", True))
    monkeypatch.setattr(round7, "run", lambda *a, **k: pytest.fail("must not run with uncommitted changes"))
    with pytest.raises(SystemExit, match="uncommitted changes"):
        round7.main([])
