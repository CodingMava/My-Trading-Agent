"""US paper trial 1 on synthetic data only: the same account as paper trial 1, the S&P 500 list, the SEC's results filings,
Yahoo's rows laid on NYSE's sessions, runs that must record nothing, the plain-words list for each US open, and messages that
survive a failed evening."""
import html
import sqlite3
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import pytest
import requests

from tests.research.test_trial import _cut, _e2, _security, _sessions, _v2
from trader.markets.calendar import load_calendars
from trader.ops import health
from trader.ops.health import ALERT, OK, WARN
from trader.research import forward2, round10, trial, ustrial

IST = ZoneInfo("Asia/Kolkata")
NYSE = load_calendars()["NYSE"]
NSE = load_calendars()["NSE"]
MONDAY = datetime(2026, 11, 2, 18, 15, tzinfo=IST)  # the US opens at 20:00 IST that evening (US winter time)
OCT30 = date(2026, 10, 30)


@pytest.fixture(autouse=True)
def _a_first_signal_for_the_test_dates(monkeypatch):
    monkeypatch.setattr(ustrial, "FIRST_SIGNAL", OCT30)


def _market(until=date(2027, 1, 29), names="ABCDEFGH", **special):
    sessions = NYSE.trading_days(date(2026, 8, 3), until)
    n = len(sessions)
    return sessions, {s: special.get(s) or _security(s, n) for s in names}


def _upto(sessions, secs, last):
    n = sessions.index(last) + 1
    return sessions[:n], {s: _cut(sec, n) for s, sec in secs.items()}


def test_the_definition_is_pinned():
    assert ustrial.check_definition() == ustrial.DEFINITION_SHA256


def test_the_definition_refuses_a_changed_file(tmp_path, monkeypatch):
    changed = tmp_path / "definition.md"
    changed.write_text("a new rule", encoding="utf-8")
    monkeypatch.setattr(ustrial, "DEFINITION", changed)
    with pytest.raises(SystemExit, match="changed after it was pinned"):
        ustrial.check_definition()


def test_the_trial_starts_at_the_first_close_it_can_act_on():
    source = ustrial.DEFINITION.read_text(encoding="utf-8")
    code = Path(ustrial.__file__).read_text(encoding="utf-8")
    assert "FIRST_SIGNAL = date(2026, 11, 2)" in code and "from the 2 Nov\n  2026 close" in source
    assert "from 30 Nov 2026" in source  # V2's first month-end after it


def test_positions_and_costs_are_as_defined():
    assert ustrial.VALUE["E2"] == pytest.approx(333.33, abs=0.01) and ustrial.VALUE["V2"] == 500.0
    assert ustrial.ROUND_TRIP["E2"] == pytest.approx(0.00288, abs=0.00001)  # the definition's "about 0.29%"
    assert ustrial.ROUND_TRIP["V2"] == pytest.approx(0.00288, abs=0.00001)


def test_the_ledger_is_append_only(tmp_path):
    ledger = ustrial.Ledger(tmp_path / "t.db")
    assert ledger.add_members([("AAA", "1", "A Co")], MONDAY) == 1 and ledger.add_members([("AAA", "1", "A Co")], MONDAY) == 0
    assert ledger.add_filings("AAA", [("0-1", "2026-10-29T12:00:00.000Z")], MONDAY) == 1
    assert ledger.add_filings("AAA", [("0-1", "2026-10-29T12:00:00.000Z")], MONDAY) == 0
    ledger.add_answers(OCT30, {"AAA"}, MONDAY)
    ledger.add_marks([("E2", "AAA", OCT30, {"entry_raw": 100.0, "mark": 0.1})], [OCT30], {"AAA": _security("AAA", 1)}, MONDAY)
    ledger.add_outbox([("k", "text")], MONDAY)
    for table in ustrial.EXTRA_TABLES:
        with pytest.raises(sqlite3.DatabaseError):
            ledger.conn.execute(f"DELETE FROM {table}")
    with pytest.raises(sqlite3.DatabaseError):
        ledger.conn.execute("UPDATE filings SET accepted = 'x'")
    assert len(ledger.table("filings")) == 1 and ledger.table("runs").empty
    ledger.close()


def test_a_transaction_records_all_or_nothing(tmp_path):
    ledger = ustrial.Ledger(tmp_path / "t.db")
    with pytest.raises(RuntimeError):
        with ledger.transaction():
            ledger.add_run(MONDAY, "ok", "x")
            raise RuntimeError("stop")
    assert ledger.table("runs").empty and not ledger.conn.in_transaction
    with ledger.transaction():
        ledger.add_run(MONDAY, "ok", "x")
    assert len(ledger.table("runs")) == 1
    ledger.close()


# ---------------------------------------------------------------------------------------------- the companies
PAGE = """<html><table class="other"><tr><th>Symbol</th><th>CIK</th></tr><tr><td>NOPE</td><td>9</td></tr></table>
<table class="wikitable" id="constituents"><tbody>
<tr><th>Symbol</th><th>Security</th><th>CIK</th></tr>
<tr><td><a href="x">GOOGL</a></td><td>Alphabet (Class A)</td><td>0001652044</td></tr>
<tr><td><a href="x">GOOG</a></td><td>Alphabet (Class C)</td><td>0001652044</td></tr>
<tr><td><a href="x">BRK.B</a></td><td>Berkshire Hathaway</td><td>0001067983</td></tr>
<tr><td>BAD</td><td>No CIK</td><td>n/a</td></tr>
</tbody></table><table><tr><td>AFTER</td><td>x</td><td>7</td></tr></table></html>"""


def test_the_list_keeps_one_share_class_per_company_with_yahoos_tickers(monkeypatch):
    monkeypatch.setattr(ustrial, "MIN_LIST", 2)
    assert ustrial.parse_constituents(PAGE) == [("GOOGL", "0001652044", "Alphabet (Class A)"), ("BRK-B", "0001067983", "Berkshire Hathaway")]
    assert ustrial.parse_constituents(PAGE, {"GOOG"})[0] == ("GOOG", "0001652044", "Alphabet (Class C)")  # the one on record
    unnamed = PAGE.replace("<th>Security</th>", "<th>Company</th>")
    assert ustrial.parse_constituents(unnamed)[0] == ("GOOGL", "0001652044", "")  # a name is a help, not a need


def test_a_page_without_the_table_or_with_too_few_companies_is_refused():
    with pytest.raises(ValueError, match="no constituents table"):
        ustrial.parse_constituents("<html><table><tr><td>x</td></tr></table></html>")
    with pytest.raises(ValueError, match="only 2 companies"):
        ustrial.parse_constituents(PAGE)


class Answer:
    def __init__(self, text="", payload=None, status=200):
        self.text, self.payload, self.status = text, payload, status

    def raise_for_status(self):
        if self.status != 200:
            raise requests.HTTPError(f"{self.status}")

    def json(self):
        if self.payload is None:
            raise ValueError("not JSON")
        return self.payload


class Web:
    """Answers by URL fragment; records what was asked and with which headers."""

    def __init__(self, answers):
        self.answers, self.asked = answers, []

    def get(self, url, headers=None, timeout=None):
        self.asked.append((url, headers))
        answer = next((a for fragment, a in self.answers.items() if fragment in url), Answer(status=404))
        if isinstance(answer, Exception):
            raise answer
        return answer


def test_the_list_grows_and_a_failed_look_keeps_it(tmp_path, monkeypatch):
    monkeypatch.setattr(ustrial, "MIN_LIST", 2)
    ledger = ustrial.Ledger(tmp_path / "t.db")

    def look(answer):
        members, read = ustrial.refresh_members(ledger, MONDAY, Web({"wikipedia": answer}))
        return list(members["ticker"]), read
    with pytest.raises(requests.ConnectionError):  # the first look must work
        look(requests.ConnectionError("down"))
    assert look(Answer(PAGE)) == (["GOOGL", "BRK-B"], True)
    assert look(Answer("<html></html>")) == (["GOOGL", "BRK-B"], False)
    grown = PAGE.replace("</tbody>", "<tr><td>NEW</td><td>New Co</td><td>5</td></tr></tbody>")
    assert look(Answer(grown)) == (["GOOGL", "BRK-B", "NEW"], True)
    ledger.close()


def test_a_resorted_page_adds_no_second_share_class_and_a_rename_gets_through(tmp_path, monkeypatch):
    monkeypatch.setattr(ustrial, "MIN_LIST", 2)
    ledger = ustrial.Ledger(tmp_path / "t.db")
    ustrial.refresh_members(ledger, MONDAY, Web({"wikipedia": Answer(PAGE)}))
    resorted = PAGE.replace(">GOOGL<", ">TEMP<").replace(">GOOG<", ">GOOGL<").replace(">TEMP<", ">GOOG<")
    assert list(ustrial.refresh_members(ledger, MONDAY, Web({"wikipedia": Answer(resorted)}))[0]["ticker"]) == ["GOOGL", "BRK-B"]
    renamed = PAGE.replace('<tr><td><a href="x">GOOGL</a></td><td>Alphabet (Class A)</td><td>0001652044</td></tr>', "")
    assert list(ustrial.refresh_members(ledger, MONDAY, Web({"wikipedia": Answer(renamed)}))[0]["ticker"]) == ["GOOGL", "BRK-B", "GOOG"]
    ledger.close()


# ---------------------------------------------------------------------------------------------------- filings
def _submissions(*rows):
    return {"filings": {"recent": {"form": [r[0] for r in rows], "items": [r[1] for r in rows],
                                   "accessionNumber": [r[2] for r in rows], "acceptanceDateTime": [r[3] for r in rows]}}}


def test_only_8ks_listing_item_2_02_are_results_filings():
    payload = _submissions(("8-K", "2.02,9.01", "a", "2026-10-29T20:30:00.000Z"), ("8-K", "5.02", "b", "x"),
                           ("10-Q", "", "c", "x"), ("8-K/A", "2.02", "d", "x"), ("8-K", "12.02", "e", "x"))
    assert ustrial.parse_filings(payload) == [("a", "2026-10-29T20:30:00.000Z")]


def _members(*rows):
    return pd.DataFrame(rows, columns=["ticker", "cik"])


def test_filings_go_in_once_and_the_sec_is_told_who_asks(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("SEC_USER_AGENT=Someone someone@example.com\n", encoding="utf-8")
    monkeypatch.setattr(ustrial, "ENV_FILE", tmp_path / "no-env-file")
    ledger = ustrial.Ledger(tmp_path / "t.db")
    web = Web({"CIK0000000001": Answer(payload=_submissions(("8-K", "2.02", "a", "2026-10-29T20:30:00.000Z")))})
    got = ustrial.fetch_filings(ledger, _members(("AAA", "0000000001")), MONDAY, web, sleep=lambda s: None)
    assert got == {"failed": [], "new": 1} and web.asked[0][1]["User-Agent"] == ustrial.AGENT
    assert web.asked[0][0] == "https://data.sec.gov/submissions/CIK0000000001.json"
    monkeypatch.setattr(ustrial, "ENV_FILE", env)
    got = ustrial.fetch_filings(ledger, _members(("AAA", "1")), MONDAY, web, sleep=lambda s: None)
    assert got == {"failed": [], "new": 0} and web.asked[1][1]["User-Agent"] == "Someone someone@example.com"
    assert len(ledger.table("filings")) == 1
    ledger.close()


def test_a_few_unread_companies_are_tolerated_and_too_many_fail_the_run(tmp_path, monkeypatch):
    monkeypatch.setattr(ustrial, "ENV_FILE", tmp_path / "no-env-file")
    monkeypatch.setattr(ustrial, "MAX_FAILED", 3)
    ledger = ustrial.Ledger(tmp_path / "t.db")
    good = Answer(payload=_submissions(("8-K", "2.02", "a", "2026-10-29T20:30:00.000Z")))
    web = Web({"CIK0000000001": good, "CIK0000000002": requests.Timeout("slow"), "CIK0000000003": Answer("not json"),
               "CIK0000000004": Answer(payload={"no": "filings"}),
               "CIK0000000005": Answer(payload={"filings": {"recent": {"form": None, "items": None, "accessionNumber": None,
                                                                        "acceptanceDateTime": None}}})})
    got = ustrial.fetch_filings(ledger, _members(("A", "1"), ("B", "2"), ("C", "3")), MONDAY, web, sleep=lambda s: None)
    assert got == {"failed": ["B", "C"], "new": 1}
    with pytest.raises(ValueError, match="couldn't be read for 3 companies"):
        ustrial.fetch_filings(ledger, _members(("B", "2"), ("C", "3"), ("D", "4"), ("E", "5")), MONDAY, web, sleep=lambda s: None)
    assert ustrial.fetch_filings(ledger, _members(("E", "5"),), MONDAY, web, sleep=lambda s: None)["failed"] == ["E"]  # a null in a record
    ledger.close()


def test_a_tickers_new_cik_is_read_as_well_as_the_old(tmp_path, monkeypatch):
    monkeypatch.setattr(ustrial, "ENV_FILE", tmp_path / "no-env-file")
    ledger = ustrial.Ledger(tmp_path / "t.db")
    assert ledger.add_members([("XOM", "34088", "Exxon")], MONDAY) == 1 and ledger.add_members([("XOM", "2115436", "Exxon")], MONDAY) == 1
    web = Web({"CIK0000034088": Answer(payload=_submissions(("8-K", "2.02", "old", "2026-04-29T20:30:00.000Z"))),
               "CIK0002115436": Answer(payload=_submissions(("8-K", "2.02", "new", "2026-07-29T20:30:00.000Z")))})
    assert ustrial.fetch_filings(ledger, ledger.table("members"), MONDAY, web, sleep=lambda s: None) == {"failed": [], "new": 2}
    assert list(ledger.table("filings")["accession"]) == ["old", "new"] and set(ledger.table("filings")["ticker"]) == {"XOM"}
    ledger.close()


def test_a_filing_reaches_the_market_in_its_session_if_before_the_close_else_the_next():
    sessions = NYSE.trading_days(date(2026, 10, 26), OCT30)  # New York is on summer time until 1 Nov
    filings = pd.DataFrame({"ticker": ["AAA", "AAA", "AAA", "BBB", "BBB", "ZZZ"],
                            "accepted": ["2026-10-26T12:00:00.000Z",   # 08:00 New York, before the open
                                         "2026-10-27T19:59:00.000Z",   # 15:59, before the close
                                         "2026-10-28T20:00:00.000Z",   # 16:00, at the close: the next session
                                         "2026-10-24T14:00:00.000Z",   # a Saturday: the next session
                                         "2026-10-30T20:30:00.000Z",   # after the last session's close: not yet
                                         "2026-10-27T12:00:00.000Z"]})  # a stock without prices
    notices = ustrial.results_notices(filings, sessions, {"AAA": object(), "BBB": object()})
    assert list(notices["AAA"][0]) == [0, 1, 3] and list(notices["AAA"][1]) == [sessions[0], sessions[1], sessions[3]]
    assert list(notices["BBB"][0]) == [0] and "ZZZ" not in notices
    only_late = pd.DataFrame({"ticker": ["AAA"], "accepted": ["2026-10-30T20:30:00.000Z"]})
    assert ustrial.results_notices(only_late, sessions, {"AAA": object()}) == {}


def test_e2_signals_start_at_the_first_signal_and_use_round_10s_rule(monkeypatch):
    monkeypatch.setattr(round10, "REACTION_MIN", 5)
    sessions = NYSE.trading_days(date(2026, 8, 3), date(2026, 11, 13))
    n = len(sessions)
    secs, rows = {}, []
    names = [f"S{k}" for k in range(8)]
    jumps = {"S0": OCT30, "S1": date(2026, 10, 29), "S2": date(2026, 11, 12)}  # S1's signal comes before the first one
    for k, sid in enumerate(names):
        closes = np.full(n, 100.0)
        if sid in jumps:
            closes[sessions.index(jumps[sid]):] = 130.0
        secs[sid] = _security(sid, n, closes=closes)
        for day in (date(2026, 9, 1 + k), date(2026, 9, 16 + k), date(2026, 10, 1 + k)):
            rows.append((sid, f"{day}T12:00:00.000Z"))
        if sid in jumps:  # the filing, one session before the reaction's last close
            filed = sessions[sessions.index(jumps[sid]) - 1]
            rows.append((sid, f"{filed}T12:00:00.000Z"))
    universe = round10.Universe(pd.DataFrame({"i": 0, "sid": names, "rank": range(1, 9)}))
    filings = pd.DataFrame(rows, columns=["ticker", "accepted"])
    signals = ustrial.e2_signals(filings, sessions, secs, universe)
    assert {(s, sessions[i]) for s, i in zip(signals["sid"], signals["signal"])} == {("S0", OCT30), ("S2", date(2026, 11, 12))}


def test_v2_lists_start_at_the_first_signal_on_nyse_month_ends(monkeypatch):
    sessions, secs = _market(until=OCT30)
    scored = pd.DataFrame({"i": [10, len(sessions) - 1, len(sessions) - 1, len(sessions) - 1], "sid": ["A", "B", "C", "D"],
                           "rank": [150, 150, 151, 50], "score_12-1": 0.1, "score_6-1": 0.1, "score_V": [9.0, 1.0, 2.0, 3.0]})
    monkeypatch.setattr(ustrial.round9, "add_scores", lambda table, secs: table)
    lists = ustrial.v2_lists(sessions, secs, scored, NYSE)
    assert list(lists) == [len(sessions) - 1]  # Oct 30: NYSE's next day is in November
    assert list(lists[len(sessions) - 1]["sid"]) == ["C", "B"]  # ranks 101-300 only, the best first
    mid_month = sessions[: sessions.index(date(2026, 10, 15)) + 1]
    assert ustrial.v2_lists(mid_month, secs, scored, NYSE) == {}


# ----------------------------------------------------------------------------------------------------- prices
def _yahoo(frames: dict) -> pd.DataFrame:
    return pd.concat(frames, axis=1)


def _rows(days, close=100.0, adj=None, volume=1000.0):
    index = pd.DatetimeIndex([pd.Timestamp(d) for d in days])
    close = np.full(len(days), close) if np.isscalar(close) else np.asarray(close, float)
    adj = close if adj is None else np.asarray(adj, float)
    return pd.DataFrame({"Open": close + 1, "High": close + 2, "Low": close - 1, "Close": close, "Adj Close": adj,
                         "Volume": volume}, index=index)


def test_yahoos_rows_become_a_security():
    days = NYSE.trading_days(date(2026, 10, 26), OCT30)
    rows = _rows(days, close=[100, 102, 104, 106, 108], adj=[50, 51, 52, 53, 54])
    rows.iloc[2] = np.nan  # no row that day
    sec = ustrial.security("AAA", rows)
    assert list(sec.present) == [True, True, False, True, True] and list(sec.eq) == list(sec.present)
    assert sec.raw_close[1] == 102 and np.isnan(sec.raw_close[2]) and sec.raw_open[0] == 101
    assert sec.adj_close[1] == 51 and sec.adj_open[1] == pytest.approx(103 / 2) and sec.adj_low[1] == pytest.approx(101 / 2)
    assert sec.raw_prev[3] == 102 and np.isnan(sec.raw_prev[0])  # the row before, across the gap
    assert sec.value[1] == 102_000 and sec.value[2] == 0.0
    assert list(sec.last_row) == [0, 1, 1, 3, 4]
    empty = _rows(days)
    empty["Volume"] = 0.0  # no trading: no good row
    assert ustrial.security("AAA", empty) is None


def _prices(days, tickers=("AAA", "BBB")):
    return _yahoo({**{t: _rows(days) for t in tickers}, "SPY": _rows(days, close=750.0)})


def test_a_session_still_trading_is_left_out(monkeypatch):
    monkeypatch.setattr(ustrial, "MIN_STOCKS", 2)
    days = NYSE.trading_days(date(2026, 10, 26), date(2026, 11, 2))
    during = datetime(2026, 11, 2, 22, 0, tzinfo=IST)  # Monday's session is open: Yahoo already has a partial row
    sessions, secs, spy = ustrial.load_prices(["AAA", "BBB"], during, NYSE, download=lambda tickers: _prices(days))
    assert sessions[-1] == OCT30 and len(secs["AAA"].present) == len(sessions) and spy == 750.0
    settled = datetime(2026, 11, 3, 3, 15, tzinfo=IST)  # closed at 02:30 IST, and 30 minutes have passed
    assert ustrial.load_prices(["AAA", "BBB"], settled, NYSE, download=lambda tickers: _prices(days))[0][-1] == date(2026, 11, 2)
    unsettled = datetime(2026, 11, 3, 2, 45, tzinfo=IST)  # closed 15 minutes ago: not yet
    assert ustrial.load_prices(["AAA", "BBB"], unsettled, NYSE, download=lambda tickers: _prices(days))[0][-1] == OCT30


def test_runs_on_bad_prices_are_refused(monkeypatch):
    monkeypatch.setattr(ustrial, "MIN_STOCKS", 2)
    days = NYSE.trading_days(date(2026, 10, 26), OCT30)
    with pytest.raises(ValueError, match="no SPY"):
        ustrial.load_prices(["AAA"], MONDAY, NYSE, download=lambda tickers: _yahoo({"AAA": _rows(days)}))
    with pytest.raises(ValueError, match="ends 2026-10-29"):
        ustrial.load_prices(["AAA", "BBB"], MONDAY, NYSE, download=lambda tickers: _prices(days[:-1]))
    with pytest.raises(ValueError, match="ends nowhere"):
        ustrial.load_prices(["AAA", "BBB"], MONDAY, NYSE, download=lambda tickers: _prices([date(2027, 1, 4)]))
    with pytest.raises(ValueError, match="only 1 of 3 stocks"):
        ustrial.load_prices(["AAA", "CCC", "DDD"], MONDAY, NYSE, download=lambda tickers: _prices(days, ("AAA",)))


def test_a_ticker_yahoo_left_blank_is_asked_for_once_more(monkeypatch):
    monkeypatch.setattr(ustrial, "MIN_STOCKS", 2)
    days = NYSE.trading_days(date(2026, 10, 26), OCT30)
    blank, short = _rows(days), _rows(days)
    blank.iloc[:] = np.nan  # how yfinance leaves a ticker it failed on
    short.iloc[-1] = np.nan
    asked = []

    def download(tickers):
        asked.append(list(tickers))
        if len(asked) == 1:
            return _yahoo({"AAA": blank, "BBB": short, "CCC": blank, "DDD": _rows(days), "SPY": _rows(days)})
        return _yahoo({"AAA": _rows(days, close=50.0), "BBB": short, "CCC": blank})
    sessions, secs, _ = ustrial.load_prices(["AAA", "BBB", "CCC", "DDD"], MONDAY, NYSE, download=download)
    assert asked[1:] == [["AAA", "BBB", "CCC"]] and sessions == days
    assert secs["AAA"].raw_close[-1] == 50.0 and secs["DDD"].present[-1]
    assert secs["BBB"].present[-2] and not secs["BBB"].present[-1] and "CCC" not in secs  # no better the second time: as they were

    asked.clear()
    blank_market = _yahoo({"AAA": _rows(days), "BBB": _rows(days), "SPY": blank})
    second = _yahoo({"SPY": _rows(days, close=700.0)})
    answers = iter([blank_market, second])
    assert ustrial.load_prices(["AAA", "BBB"], MONDAY, NYSE, download=lambda tickers: next(answers))[2] == 700.0


def test_a_session_missing_from_spys_rows_is_refused(monkeypatch):
    monkeypatch.setattr(ustrial, "MIN_STOCKS", 2)
    days = NYSE.trading_days(date(2026, 10, 26), OCT30)
    spy = _rows(days)
    spy.iloc[2] = np.nan  # without this check, the 28 Oct would leave the grid, and a signal would be recorded a second time
    frames = _yahoo({"AAA": _rows(days), "BBB": _rows(days), "SPY": spy})
    with pytest.raises(ustrial.Refused, match="don't match the US calendar this year: 2026-10-28"):
        ustrial.load_prices(["AAA", "BBB"], MONDAY, NYSE, download=lambda tickers: frames)


SEVERAL = [f"T{k}" for k in range(60)]
EARLY = MONDAY.replace(hour=17, minute=30)  # the task's first tries: until 18:15 every stock must answer


def _answering(names, no_last_row=()):
    secs = {sid: _security(sid, 5) for sid in names}
    for sid in no_last_row:
        secs[sid].present[-1] = False
    return secs


def test_a_partial_answer_from_yahoo_is_refused_before_anything_is_recorded():
    days = NYSE.trading_days(date(2026, 10, 26), OCT30)
    names = [*SEVERAL, "X", "Y"]
    everyone = _answering(names)
    ledger = ustrial.Ledger(":memory:")
    ustrial.check_answers(ledger, names, days, everyone, EARLY)  # the first run: every company on the list counts
    short = {sid: everyone[sid] for sid in names if sid != "X"}
    with pytest.raises(ValueError, match="no price for 1 of 62 stocks on 2026-10-30, e.g. X"):
        ustrial.check_answers(ledger, names, days, short, EARLY)
    ustrial.check_answers(ledger, names, days, short, MONDAY)  # from 18:15, up to 2% may have really stopped
    two_short = {sid: everyone[sid] for sid in SEVERAL}
    with pytest.raises(ValueError, match="no price for 2 of 62"):
        ustrial.check_answers(ledger, names, days, two_short, MONDAY)
    after_midnight = datetime(2026, 11, 3, 0, 30, tzinfo=IST)
    with pytest.raises(ValueError, match="no price for 1 of 62"):
        ustrial.check_answers(ledger, names, days, short, after_midnight)

    ledger.add_answers(date(2026, 10, 29), set(SEVERAL), MONDAY)  # later runs: the stocks with a row on the last good run
    ustrial.check_answers(ledger, names, days, _answering(SEVERAL), EARLY)  # X and Y had none then: they don't count
    with pytest.raises(ValueError, match="no price for 1 of 60 stocks on 2026-10-30, e.g. T0"):
        ustrial.check_answers(ledger, names, days, _answering(SEVERAL, no_last_row=["T0"]), EARLY)
    ledger.close()


def _holdings():
    """T0 held, T1 sold, T2 and T3 next up, and T4, T5 and T6 not going to come up."""
    ledger = ustrial.Ledger(":memory:")
    old = date(2026, 9, 30)
    ledger.add_answers(OCT30, set(SEVERAL), MONDAY)
    for sid in ("T0", "T1"):
        ledger.add_signal("E2", sid, date(2026, 10, 1), None, 0.2, "N1", False, MONDAY)
        ledger.add_decision("E2", sid, date(2026, 10, 1), date(2026, 10, 2), "bought", MONDAY)
    ledger.add_trade("E2", "T1", date(2026, 10, 1), "N1", {"entry_date": date(2026, 10, 2), "entry_price": 1.0, "exit_date": OCT30,
                     "exit_price": 1.0, "gross": 0.0, "net": 0.0, "cost": 0.0, "outcome": "stop", "gapped": False}, MONDAY)
    ledger.add_signal("E2", "T2", OCT30, None, 0.2, "N1", False, MONDAY)
    ledger.add_signal("V2", "T3", OCT30, ustrial.REACH, 1.0, "N2", False, MONDAY)
    ledger.add_signal("V2", "T4", OCT30, ustrial.REACH + 1, 1.0, "N2", False, MONDAY)
    ledger.add_signal("E2", "T5", OCT30, None, 0.2, "N1", True, MONDAY)
    ledger.add_signal("V2", "T6", old, 3, 1.0, "N2", False, MONDAY)
    return ledger


def test_the_stocks_a_run_cant_do_without():
    ledger = _holdings()
    assert ustrial.needed_stocks(ledger, OCT30) == {"T0", "T2", "T3"}
    ledger.close()


def test_a_held_stock_or_a_candidate_holds_the_run_back_for_three_sessions():
    ledger = _holdings()
    days = NYSE.trading_days(OCT30, date(2026, 11, 5))
    for sid in ("T0", "T2", "T3"):
        missing = _answering(SEVERAL, no_last_row=[sid])
        for last in (OCT30, date(2026, 11, 2), date(2026, 11, 4)):  # at most 3 sessions behind the last good run
            with pytest.raises(ValueError, match=f"no price for {sid}, which the trial holds or may buy"):
                ustrial.check_answers(ledger, SEVERAL, days[:days.index(last) + 1], missing, MONDAY)
        ustrial.check_answers(ledger, SEVERAL, days, missing, MONDAY)  # 4 sessions: it counts as gone
    for sid in ("T1", "T4", "T5", "T6"):  # these wait for nobody
        ustrial.check_answers(ledger, SEVERAL, days[:2], _answering(SEVERAL, no_last_row=[sid]), MONDAY)
    ledger.add_answers(date(2026, 11, 2), set(SEVERAL) - {"T0"}, MONDAY)  # gone by the last good run: it doesn't refuse again
    ustrial.check_answers(ledger, SEVERAL, days[:3], _answering(SEVERAL, no_last_row=["T0"]), EARLY)
    ledger.close()


def test_a_yahoo_failure_becomes_a_refused_run(monkeypatch):
    import yfinance

    def fails(*args, **kwargs):
        raise RuntimeError("rate limited")
    monkeypatch.setattr(yfinance, "download", fails)
    with pytest.raises(ValueError, match="Yahoo: RuntimeError: rate limited"):
        ustrial.yahoo_prices(["AAA"])
    monkeypatch.setattr(yfinance, "download", lambda *args, **kwargs: "the answer")
    assert ustrial.yahoo_prices(["AAA"]) == "the answer"


# ---------------------------------------------------------------------------------------------------- account
def test_the_account_decides_as_paper_trial_1_does(monkeypatch):
    """The same market through both: the same decisions and the same trades, at US costs."""
    monkeypatch.setattr(forward2, "nse_calendar", lambda: NSE)
    sessions = _sessions(160)
    n = len(sessions)
    lows = np.full(n, 100.0)
    lows[20] = 80.0  # A's stop
    secs = {s: _security(s, n) for s in "BCDEFGHIJ"}
    secs["A"] = _security("A", n, lows=lows)
    e2 = _e2([("A", 10, 0.30), ("B", 10, 0.25), ("C", 10, 0.20), ("D", 10, 0.15), ("E", 25, 0.5)])
    v2 = _v2(sessions, OCT30, ["A", "F", "G", "H"])
    india, us = trial.Ledger(":memory:"), ustrial.Ledger(":memory:")
    first, second = trial.update(india, sessions, secs, e2, v2, MONDAY), ustrial.update(us, sessions, secs, e2, v2, MONDAY, NSE)
    assert first["entries"] == second["entries"] and len(first["entries"]) == 7
    assert [e[:3] for e in first["closed"]] == [e[:3] for e in second["closed"]] and first["closed"]
    theirs, ours = india.table("trades"), us.table("trades")
    assert list(theirs["gross"]) == list(ours["gross"]) and list(theirs["outcome"]) == list(ours["outcome"])
    stopped = ours["outcome"] == "stop"
    assert stopped.any() and (~stopped).any()
    assert list(ours.loc[stopped, "cost"]) == pytest.approx(list(np.where(ours.loc[stopped, "part"] == "E2", ustrial.ROUND_TRIP["E2"],
                                                                         ustrial.ROUND_TRIP["V2"]) + ustrial.COSTS.slippage_per_side))
    assert list(ours.loc[~stopped, "cost"]) == pytest.approx(list(np.where(ours.loc[~stopped, "part"] == "E2", ustrial.ROUND_TRIP["E2"],
                                                                          ustrial.ROUND_TRIP["V2"])))
    assert list(ours["net"]) == pytest.approx(list(ours["gross"] - ours["cost"]))
    again = ustrial.update(us, sessions, secs, e2, v2, MONDAY, NSE)
    assert again["entries"] == [] and again["signals"] == [] and again["closed"] == []  # decided once
    us.close()
    india.close()


def test_a_v2_pick_without_a_row_keeps_its_place_in_cash_and_the_brakes_stop_entries():
    sessions, secs = _market()
    entry = sessions.index(OCT30) + 1
    hole = _security("E", len(sessions))
    hole.present[entry] = False
    secs["E"] = hole
    ledger = ustrial.Ledger(":memory:")
    events = ustrial.update(ledger, sessions, secs, _e2([]), _v2(sessions, OCT30, ["E", "F", "G"]), MONDAY, NYSE)
    assert {s: st for _, s, _, st in events["entries"]} == {"E": "not bought", "F": "bought"}
    ledger.close()

    ledger = ustrial.Ledger(":memory:")
    sessions, secs = _market()
    for j in range(25):  # a run of losses past 20R, recorded straight in the ledger
        ledger.add_trade("E2", "OLD", date.fromordinal(date(2020, 1, 1).toordinal() + j), "N1",
                         {"entry_date": date(2020, 1, 1), "entry_price": 1.0, "exit_date": date(2020, 1, 1), "exit_price": 1.0,
                          "gross": -0.15, "net": -0.15, "cost": 0.0, "outcome": "stop", "gapped": False}, MONDAY)
    e2 = _e2([("A", 10, 0.3)])
    events = ustrial.update(ledger, sessions, secs, e2, _v2(sessions, OCT30, ["B"]), MONDAY, NYSE)
    assert {(s, st) for _, s, _, st in events["entries"]} == {("A", "brake"), ("B", "brake")}
    assert {b[0] for b in events["brakes"]} == {"account", "E2"}
    told = ustrial.messages(events, ledger.table("trades"), sessions[-1])[2][1]
    assert "The US paper trial stops buying now, for good" in told and "SELLs still come" in told and "your Indian account" in told
    assert ustrial.update(ledger, sessions, secs, e2, _v2(sessions, OCT30, ["B"]), MONDAY, NYSE)["brakes"] == []  # recorded once
    ledger.close()


def test_a_brake_found_after_the_last_entry_is_still_recorded():
    sessions, secs = _market()
    ledger = ustrial.Ledger(":memory:")
    ledger.add_signal("E2", "A", sessions[10], None, 0.2, "N1", False, MONDAY)
    for j in range(25):
        ledger.add_trade("E2", "OLD", date.fromordinal(date(2020, 1, 1).toordinal() + j), "N1",
                         {"entry_date": date(2020, 1, 1), "entry_price": 1.0, "exit_date": date(2020, 1, 1), "exit_price": 1.0,
                          "gross": -0.15, "net": -0.15, "cost": 0.0, "outcome": "stop", "gapped": False}, MONDAY)
    ledger.add_decision("E2", "A", sessions[10], sessions[11], "not bought", MONDAY)  # nothing left to decide
    events = ustrial.update(ledger, sessions, secs, _e2([]), {}, MONDAY, NYSE)
    assert {b[0] for b in events["brakes"]} == {"account", "E2"} and events["entries"] == []
    ledger.close()


def test_a_held_stock_yahoo_stops_answering_for_keeps_its_place_and_says_so():
    sessions, secs = _market(until=date(2026, 11, 13))
    entry_signal = sessions.index(date(2026, 11, 2))
    e2 = _e2([("A", entry_signal, 0.3), ("B", entry_signal, 0.25), ("C", entry_signal, 0.2)])
    ledger = ustrial.Ledger(":memory:")
    assert {st for _, _, _, st in ustrial.update(ledger, sessions, secs, e2, {}, MONDAY, NYSE)["entries"]} == {"bought"}
    gone = {s: sec for s, sec in secs.items() if s != "A"}  # bought out: no rows at all now
    hole = _security("B", len(sessions))
    hole.present[entry_signal + 1] = False  # or the row of its entry session has vanished
    gone["B"] = hole
    events = ustrial.update(ledger, sessions, gone, e2, {}, MONDAY, NYSE)
    assert sorted(s for _, s, _ in events["no prices"]) == ["A", "B"] and [t[1] for t in events["open"]] == ["C"]
    notes = dict(ustrial.messages(events, ledger.table("trades"), sessions[-1]))
    assert any("Yahoo has stopped giving prices for A" in text and "check it in Kite yourself" in text for text in notes.values())
    assert "no prices E2 A never" in notes
    later = ustrial.update(ledger, sessions, gone, _e2([("A", entry_signal, 0.3), ("B", entry_signal, 0.25), ("C", entry_signal, 0.2),
                                                        ("D", entry_signal + 2, 0.5)]), {}, MONDAY, NYSE)
    assert later["entries"][-1][1:] == ("D", sessions[entry_signal + 3], "no free place")  # their places stay taken
    ledger.close()


def test_a_stock_yahoo_never_answers_for_again_closes_at_its_last_price_after_20_sessions(tmp_path, monkeypatch):
    monkeypatch.setattr(ustrial, "STATUS", tmp_path / "status.md")
    sessions, _ = _market()
    n, signal = len(sessions), sessions.index(OCT30)
    held_to = sessions.index(date(2026, 11, 6))
    closes = np.full(n, 100.0)
    closes[held_to:] = 110.0
    secs = {"A": _security("A", n, closes=closes), "B": _security("B", n), "C": _security("C", n), "D": _security("D", n)}
    e2 = _e2([("A", signal, 0.3), ("B", signal, 0.2), ("C", signal, 0.1)])
    ledger = ustrial.Ledger(":memory:")
    first, cut_secs = _upto(sessions, secs, sessions[held_to])
    events = ustrial.update(ledger, first, cut_secs, e2, {}, MONDAY, NYSE)
    ledger.add_marks(events["open"], first, cut_secs, MONDAY)
    last = ledger.last_mark("E2", "A", sessions[signal + 1])
    assert last == {"session": str(sessions[held_to]), "entry_price": 100.0, "close": 110.0, "mark": pytest.approx(0.1)}

    gone = {s: sec for s, sec in secs.items() if s != "A"}
    nearly = sessions[held_to + ustrial.NO_ANSWER_LIMIT - 1]
    days, secs_now = _upto(sessions, gone, nearly)
    events = ustrial.update(ledger, days, secs_now, e2, {}, MONDAY, NYSE)
    assert events["no prices"] == [("E2", "A", last)] and events["closed"] == []
    notes = dict(ustrial.messages(events, ledger.table("trades"), nearly))
    assert f"no prices E2 A {sessions[held_to]}" in notes  # one message for each time it goes missing
    summary = ustrial.summary_message(events, ledger.table("trades"), nearly, 700.0)[1]
    assert "A (no price)" in summary and "Account: $10,033.33" in summary  # its last mark, +10% over a 15% stop: +0.67R
    status = ustrial.write_status(ledger, events, MONDAY)
    assert f"| E2 | A | - | no price since {sessions[held_to]} | - |" in status

    ended = sessions[held_to + ustrial.NO_ANSWER_LIMIT]
    days, secs_now = _upto(sessions, gone, ended)
    events = ustrial.update(ledger, days, secs_now, e2, {}, MONDAY, NYSE)
    assert [c[1] for c in events["closed"]] == ["A"] and events["no prices"] == []
    trade = ledger.table("trades").iloc[-1]
    assert trade["outcome"] == "no further rows" and trade["exit_date"] == str(sessions[held_to]) and trade["exit_price"] == 110.0
    assert trade["net"] == pytest.approx(0.1 - ustrial.ROUND_TRIP["E2"]) and trade["entry_price"] == 100.0
    assert ustrial.sells_to_tell(ledger, ledger.table("trades")).empty  # it can't be sold: its "Closed" message says so
    later = _e2([("A", signal, 0.3), ("B", signal, 0.2), ("C", signal, 0.1), ("D", held_to + ustrial.NO_ANSWER_LIMIT, 0.5)])
    days, secs_now = _upto(sessions, gone, sessions[held_to + ustrial.NO_ANSWER_LIMIT + 1])
    assert ustrial.update(ledger, days, secs_now, later, {}, MONDAY, NYSE)["entries"][-1][1:] == ("D", days[-1], "bought")  # its place is free
    ledger.close()


def test_a_held_stock_whose_rows_stop_while_yahoo_still_answers_says_so_and_its_sale_is_told_once(tmp_path, monkeypatch):
    monkeypatch.setattr(ustrial, "STATUS", tmp_path / "status.md")
    sessions, _ = _market()
    n, signal = len(sessions), sessions.index(OCT30)
    stopped_after = signal + 5
    dead = _security("A", n)
    dead.present[stopped_after + 1:] = False
    dead.raw_close[stopped_after + 1:] = np.nan
    dead.last_row[stopped_after + 1:] = stopped_after
    secs = {"A": dead, "B": _security("B", n)}
    e2 = _e2([("A", signal, 0.3)])
    ledger = ustrial.Ledger(":memory:")
    days, now_secs = _upto(sessions, secs, sessions[stopped_after])
    events = ustrial.update(ledger, days, now_secs, e2, {}, MONDAY, NYSE)
    ledger.add_marks(events["open"], days, now_secs, MONDAY)
    days, now_secs = _upto(sessions, secs, sessions[stopped_after + ustrial.HOLD_BACK])
    assert [o[1] for o in ustrial.update(ledger, days, now_secs, e2, {}, MONDAY, NYSE)["open"]] == ["A"]  # a few evenings: not yet
    days, now_secs = _upto(sessions, secs, sessions[stopped_after + ustrial.HOLD_BACK + 1])
    events = ustrial.update(ledger, days, now_secs, e2, {}, MONDAY, NYSE)
    assert events["open"] == [] and [(p, s) for p, s, _ in events["no prices"]] == [("E2", "A")]
    summary = ustrial.summary_message(events, ledger.table("trades"), days[-1], 700.0)[1]
    assert "Holding: A (no price)" in summary
    assert any("Yahoo has stopped giving prices for A" in text for _, text in ustrial.messages(events, ledger.table("trades"), days[-1]))
    exit_i = signal + 1 + 40  # its 40 sessions end here, with no row to sell at: planned, and told once
    days, now_secs = _upto(sessions, secs, sessions[exit_i - 1])
    assert [x["sid"] for x in ustrial.next_open(ledger, days, now_secs, e2, {}, sessions[exit_i], MONDAY, NYSE)["exits"]] == ["A"]
    ledger.add_notice(f"sell told E2 A {OCT30}", MONDAY, True)
    assert ustrial.next_open(ledger, days, now_secs, e2, {}, sessions[exit_i], MONDAY, NYSE)["exits"] == []
    ledger.close()


def test_an_old_event_that_becomes_a_signal_is_on_record_as_late():
    sessions, secs = _market()
    at = sessions.index
    nov5, nov10, nov12, nov13 = date(2026, 11, 5), date(2026, 11, 10), date(2026, 11, 12), date(2026, 11, 13)
    e2 = _e2([("A", at(nov10), 0.3), ("B", at(nov12), 0.2), ("C", at(nov13), 0.1)])
    days, now_secs = _upto(sessions, secs, nov13)
    ledger = ustrial.Ledger(":memory:")
    ledger.add_answers(nov12, set(secs), MONDAY)  # a good run covered the 12th, so the list has changed since: hindsight
    events = ustrial.update(ledger, days, now_secs, e2, {}, MONDAY, NYSE)
    assert {s[1]: s[4] for s in events["signals"]} == {"A": True, "B": True, "C": False}
    assert events["entries"] == [] and events["waiting"] == [("E2", "C", str(nov13))]
    [(_, note)] = ustrial.messages(events, ledger.table("trades"), nov13)
    assert "US close: C (+10.0%) (results reaction" in note  # the late ones aren't announced
    assert ustrial.update(ledger, days, now_secs, e2, {}, MONDAY, NYSE)["signals"] == []  # on record once
    ledger.close()

    days, now_secs = _upto(sessions, secs, nov12)  # the newest session's signal, first seen on a second run that evening
    ledger = ustrial.Ledger(":memory:")
    ledger.add_answers(nov12, set(secs), MONDAY)
    assert [s[4] for s in ustrial.update(ledger, days, now_secs, _e2([("B", at(nov12), 0.2)]), {}, MONDAY, NYSE)["signals"]] == [False]
    ledger.close()

    ledger = ustrial.Ledger(":memory:")  # days with no good run: newer signals are still decided, as they always were
    ledger.add_answers(nov5, set(secs), MONDAY)
    events = ustrial.update(ledger, days, now_secs, _e2([("A", at(nov10), 0.3)]), {}, MONDAY, NYSE)
    assert events["entries"] == [("E2", "A", date(2026, 11, 11), "bought")]
    ledger.close()


def test_a_signal_with_no_stock_on_record_is_not_bought():
    sessions, secs = _market()
    ledger = ustrial.Ledger(":memory:")
    events = ustrial.update(ledger, sessions, secs, _e2([("ZZZ", 10, 0.3)]), _v2(sessions, OCT30, ["YYY"]), MONDAY, NYSE)
    assert {(s, st) for _, s, _, st in events["entries"]} == {("ZZZ", "not bought"), ("YYY", "not bought")}
    held = ustrial.update(ledger, sessions, secs, _e2([("A", 40, 0.3)]), {}, MONDAY, NYSE)
    assert held["entries"][0][1:] == ("A", sessions[41], "bought")
    ledger.close()


def test_stocks_held_are_skipped_and_full_places_end_the_months_list():
    sessions, secs = _market()
    signal = sessions.index(OCT30)
    e2 = _e2([("A", signal - 1, 0.5), ("B", signal, 0.4), ("C", signal, 0.3), ("D", signal, 0.2), ("A", signal, 0.1)])
    ledger = ustrial.Ledger(":memory:")
    events = ustrial.update(ledger, sessions, secs, e2, _v2(sessions, OCT30, ["A", "E"]), MONDAY, NYSE)
    status = {(p, s, e): st for p, s, e, st in events["entries"]}
    assert status[("E2", "A", sessions[signal])] == "bought"
    assert status[("E2", "B", sessions[signal + 1])] == status[("E2", "C", sessions[signal + 1])] == "bought"
    assert status[("E2", "D", sessions[signal + 1])] == "no free place"
    assert status[("E2", "A", sessions[signal + 1])] == "already held" and status[("V2", "A", sessions[signal + 1])] == "already held"
    assert status[("V2", "E", sessions[signal + 1])] == "bought"
    ledger.close()

    ledger = ustrial.Ledger(":memory:")
    jan29 = date(2027, 1, 29)  # the data ends on a month-end: January's picks wait for the next open
    november = _v2(sessions, date(2026, 11, 30), ["A", "B", "C", "D"])
    full = ustrial.update(ledger, sessions, secs, _e2([]), november, MONDAY, NYSE)
    assert [s for _, s, _, st in full["entries"] if st == "bought"] == ["A", "B"]
    january = _v2(sessions, jan29, ["E"])
    assert ustrial.update(ledger, sessions, secs, _e2([]), january, MONDAY, NYSE)["waiting"] == [("V2", "E", str(jan29))]
    ledger.close()

    ledger = ustrial.Ledger(":memory:")  # a pick with its places taken ends the month's list
    picks = {**_v2(sessions, OCT30, ["A", "B"]), **_v2(sessions, sessions[sessions.index(OCT30) + 2], ["C", "D"])}
    events = ustrial.update(ledger, sessions, secs, _e2([]), picks, MONDAY, NYSE)
    assert [(s, st) for _, s, _, st in events["entries"]] == [("A", "bought"), ("B", "bought"), ("C", "no free place")]
    ledger.close()


# ---------------------------------------------------------------------------------------------- plain messages
def _plan(**kwargs):
    return {"entries": [], "exits": [], **kwargs}


NO_SALES = pd.DataFrame(columns=["part", "sid", "signal_date", "entry_date", "exit_date", "outcome"])
OLD_EXIT = {"part": "E2", "sid": "OLD", "signal_date": "2026-08-25", "entry_date": "2026-08-26"}
NVDA = {"part": "E2", "sid": "NVDA", "strength": 0.103, "close": 185.2}
ABC = {"part": "V2", "sid": "ABC", "strength": 2.1, "close": 50.0}


def _sales(*rows):
    return pd.DataFrame(rows, columns=["part", "sid", "signal_date", "entry_date", "exit_date", "outcome"])


def test_the_list_for_an_open_says_what_to_do_in_plain_words():
    plan = _plan(entries=[NVDA, ABC], exits=[OLD_EXIT])
    stopped = _sales(("V2", "XYZ", "2026-09-30", "2026-10-01", "2026-10-30", "stop"))
    raw = ustrial.tonight(plan, stopped, NYSE, date(2026, 11, 2), MONDAY)
    text = html.unescape(raw)
    assert text.startswith("<b>[US PAPER TRIAL · paper only] Tonight's US open, Mon 2 Nov, 8:00 pm India time</b>\n\n")
    assert "BUY NVDA with about $333.33 (about 1.80 shares at the last close, $185.20)" in text
    assert "Why: after its results filing it beat the market by +10.3%" in text and "Stop-loss: 15% below tonight's open, about $157.42" in text
    assert "BUY ABC with about $500.00 (about 10.00 shares" in text and "Why: one of this month's top picks" in text
    assert "Stop-loss: 10% below tonight's open, about $45.00" in text
    assert "SELL OLD: all the shares you hold from these lists (its time is up). None from these lists? Do nothing." in text
    assert "SELL XYZ: all the shares you hold from these lists (it hit its stop-loss on 30 Oct). None from these lists? Do nothing." in text
    assert text.index("SELL OLD") < text.index("SELL XYZ") < text.index("BUY NVDA")  # the sales free the money for the buys
    assert "Pretend money" in text and "never tested on US stocks" in text and "no stop-loss" in text
    assert "a pretend $10,000 account: all 5 places take about $2,000" in text
    assert "To buy, only before 8:00 pm tonight (after that, skip it): Kite > Marketwatch search > International > the stock > Buy > Market, by amount." in text
    assert "To sell: Kite > Marketwatch search > International > the stock > Sell > Market, by quantity: the shares you hold from these lists." in text
    assert "&gt;" in raw  # Telegram's HTML mode needs it


def test_a_stock_sold_and_bought_again_at_one_open_gets_one_line():
    held = dict(OLD_EXIT, sid="ABC")
    text = html.unescape(ustrial.tonight(_plan(entries=[NVDA, ABC], exits=[held]), NO_SALES, NYSE, date(2026, 11, 2), MONDAY))
    assert "KEEP ABC: the rules buy it again at this open, so if you still hold it, do nothing." in text
    assert "Don't hold it? Buy with about $500.00 (about 10.00 shares at the last close, $50.00)" in text
    assert "Stop-loss from now: 10% below tonight's open, about $45.00" in text
    assert "SELL ABC" not in text and "BUY ABC" not in text and "BUY NVDA" in text
    assert "To sell" not in text  # no SELL line above it
    stopped = _sales(("V2", "ABC", "2026-09-30", "2026-10-01", "2026-10-30", "stop"))  # a stop and a new buy: the same
    text = html.unescape(ustrial.tonight(_plan(entries=[ABC]), stopped, NYSE, date(2026, 11, 2), MONDAY))
    assert "KEEP ABC" in text and "SELL ABC" not in text and "To sell" not in text


def test_a_list_after_the_open_says_not_to_buy_and_still_says_to_sell():
    late = datetime(2026, 11, 2, 23, 40, tzinfo=IST)
    held = dict(OLD_EXIT, sid="ABC")
    text = html.unescape(ustrial.tonight(_plan(entries=[NVDA, ABC], exits=[OLD_EXIT, held]), NO_SALES, NYSE, date(2026, 11, 2), late))
    assert "Tonight's US open was at 8:00 pm India time, Mon 2 Nov" in text
    assert "BUY" not in text and "To buy" not in text and "$10,000" not in text
    assert "SELL OLD: all the shares you hold from these lists" in text and "To sell" in text
    assert "Too late to copy: NVDA. The paper account bought at the open, and the price has moved." in text
    assert "KEEP ABC: the rules buy it again at this open, so if you still hold it, do nothing." in text and "Don't hold it?" not in text


def test_the_list_gives_the_opens_own_time_and_says_when_there_is_nothing_to_do():
    assert html.unescape(ustrial.tonight(_plan(), NO_SALES, NYSE, date(2026, 11, 2), MONDAY)).endswith(
        "Tonight's US open, Mon 2 Nov, 8:00 pm India time</b>\n\nNothing to buy or sell.")
    only_sale = _plan(exits=[OLD_EXIT])
    summer = datetime(2027, 4, 5, 18, 15, tzinfo=IST)
    assert "Tonight's US open, Mon 5 Apr, 7:00 pm India time" in ustrial.tonight(only_sale, NO_SALES, NYSE, date(2027, 4, 5), summer)
    text = html.unescape(ustrial.tonight(only_sale, NO_SALES, NYSE, date(2026, 11, 2), MONDAY))
    assert "Do nothing.\n\nPretend money" in text and "To sell" in text and "To buy" not in text and "$10,000" not in text
    assert "SELL OLD: all the shares you hold from these lists (its time is up)" in text


def test_a_sale_whose_evening_was_missed_comes_in_the_next_list():
    missed = _sales(("E2", "A", "2026-08-25", "2026-08-26", "2026-10-29", "time"), ("V2", "B", "2026-08-31", "2026-09-01", "2026-10-29", "time, delayed"))
    text = html.unescape(ustrial.tonight(_plan(), missed, NYSE, date(2026, 11, 2), MONDAY))
    assert "SELL A: all the shares you hold from these lists (its time was up on 29 Oct, and that evening's list didn't reach you)." in text
    assert "SELL B: all the shares you hold from these lists (its time was up on 29 Oct" in text


def test_the_list_spells_a_stock_as_the_exchange_does():
    brk = {"part": "E2", "sid": "BRK-B", "strength": 0.103, "close": 500.0}
    text = html.unescape(ustrial.tonight(_plan(entries=[brk]), NO_SALES, NYSE, date(2026, 11, 2), MONDAY))
    assert "BUY BRK.B with" in text and "BRK-B" not in text


def test_the_list_says_which_company_since_some_us_tickers_are_indian_symbols_too():
    carnival = {"part": "E2", "sid": "CCL", "strength": 0.103, "close": 25.0}
    sale = _plan(entries=[carnival], exits=[dict(OLD_EXIT, sid="HAL")])
    names = {"CCL": "Carnival", "HAL": "Halliburton"}
    text = html.unescape(ustrial.tonight(sale, NO_SALES, NYSE, date(2026, 11, 2), MONDAY, names))
    assert "BUY CCL (Carnival) with about" in text and "SELL HAL (Halliburton): all the shares" in text


def test_the_entries_message_gives_the_real_buy_price_and_stop():
    events = {"signals": [], "entries": [("E2", "X", OCT30, "bought"), ("V2", "Y", OCT30, "bought")], "brakes": [], "no prices": [],
              "open": [("E2", "X", OCT30, {"entry_raw": 100.0, "stop_raw": 85.0, "mark": 0.0})],
              "closed": [("V2", "Y", OCT30, {"entry_raw": 50.0, "net": 0.03, "outcome": "stop", "exit_date": date(2026, 11, 2)})]}
    [entries, _] = ustrial.messages(events, pd.DataFrame(columns=["exit_date", "r"]), OCT30)
    assert "Paper entries at the 30 Oct 2026 US open: E2 X: bought at $100.00, stop $85.00; V2 Y: bought at $50.00." in entries[1]


def test_messages_are_labelled_and_the_strongest_signal_comes_first():
    events = {"signals": [("E2", "LOW", OCT30, 0.09, False), ("E2", "TOP", OCT30, 0.2, False), ("E2", "LATE", OCT30, 0.3, True),
                          ("E2", "OLD", date(2026, 10, 29), 0.3, False), ("V2", "A, B", OCT30, np.nan, False),
                          ("V2", "C, D", date(2026, 9, 30), np.nan, False)],
              "entries": [("E2", "X", OCT30, "bought"), ("V2", "Y", OCT30, "no free place")],
              "closed": [("E2", "Z", OCT30, {"net": 0.03, "outcome": "time", "exit_date": date(2026, 12, 1)})],
              "brakes": [("E2", "paused", "2026-11-01", "x")], "no prices": []}
    notes = ustrial.messages(events, pd.DataFrame(columns=["exit_date", "r"]), OCT30)
    assert len(notes) == 5 and all(text.startswith("<b>[US PAPER TRIAL · paper only]</b>") for _, text in notes)
    assert "E2 signals at the 30 Oct 2026 US close: TOP (+20.0%), LOW (+9.0%) (results reaction" in notes[0][1]
    assert "Research, not a trading signal" in notes[0][1]
    assert "V2 signal at the 30 Oct 2026 US close: A, B" in notes[1][1]
    assert "Paper entries at the 30 Oct 2026 US open: E2 X: bought; V2 Y: no free place." in notes[2][1]
    assert "Closed E2 Z (bought 30 Oct 2026): +3.0% after costs (its time was up, 01 Dec 2026)." in notes[3][1]
    assert "The US paper trial stops buying E2 picks now, for good" in notes[4][1]


def test_each_month_gets_a_summary_in_its_first_week():
    events = {"signals": [], "entries": [], "closed": [], "brakes": [], "no prices": []}
    trades = pd.DataFrame({"exit_date": ["2026-11-10", "2026-10-10"], "r": [1.0, -0.5]})
    [(key, text)] = ustrial.messages(events, trades, date(2026, 12, 2))
    assert key == "month 2026-11" and "November 2026: 1 closed trade(s); the account +0.2% since the start" in text
    assert ustrial.messages(events, trades, date(2026, 12, 15)) == []
    assert ustrial.messages(events, trades, date(2027, 2, 2)) == []  # nothing closed in January


def test_the_summary_shows_the_account_holdings_and_the_market():
    events = {"open": [("E2", "NVDA", OCT30, {"mark": 0.06, "stop_raw": 85.0}), ("V2", "ABC", OCT30, {"outcome": "pending"})]}
    trades = pd.DataFrame({"r": [1.0]})
    key, text = ustrial.summary_message(events, trades, OCT30, 755.72)
    assert key == f"summary {OCT30}" and "DAILY SUMMARY 30 Oct 2026" in text
    assert "Account: $10,070.00 (+0.70% since the start)" in text  # closed +1R, and NVDA's +6% over its 15% stop: +0.4R
    assert "Holding: NVDA +6.0%" in text and "Market check: SPY closed at $755.72" in text
    assert "Holding: none" in ustrial.summary_message({"open": []}, pd.DataFrame({"r": []}), OCT30, 1.0)[1]
    gone = {"open": [], "no prices": [("E2", "OLD", None)]}  # no price, and no mark to go on
    assert "Holding: OLD (no price)" in ustrial.summary_message(gone, pd.DataFrame({"r": []}), OCT30, 1.0)[1]


def test_the_status_page(tmp_path, monkeypatch):
    monkeypatch.setattr(ustrial, "STATUS", tmp_path / "state" / "status.md")
    ledger = ustrial.Ledger(":memory:")
    t = {"entry_date": OCT30, "entry_price": 100.0, "exit_date": date(2026, 11, 3), "exit_price": 110.0, "gross": 0.1, "net": 0.097,
         "cost": 0.003, "outcome": "time", "gapped": False}
    ledger.add_trade("E2", "AAA", OCT30, "N1", t, MONDAY)
    ledger.add_brake("E2", "paused", OCT30, "too many losses", MONDAY)
    events = {"open": [("V2", "BBB", OCT30, {"mark": 0.02, "stop_raw": 90.0})]}
    text = ustrial.write_status(ledger, events, MONDAY)
    assert (tmp_path / "state" / "status.md").read_text(encoding="utf-8") == text
    assert "never tested on US stocks" in text and "Brakes: E2 paused" in text and "| V2 | BBB |" in text
    assert "| E2 | 1 | 100.0% | +9.70% | +0.65 |" in text and "| V2 | 0 | - | - | - |" in text and "| E2 | AAA |" in text
    text = ustrial.write_status(ledger, {"open": [], "no prices": [("V2", "CCC", None)]}, MONDAY)
    assert "| V2 | CCC | - | no price since it was bought | - |" in text
    ledger.close()


# ---------------------------------------------------------------------------------------------- the evening run
class Telegram:
    def __init__(self, works=True):
        self.sent, self.works = [], works

    def send(self, text):
        self.sent.append(html.unescape(text))
        return self.works


def _lists(telegram):
    return [text for text in telegram.sent if "Tonight's US open" in text and "isn't ready" not in text]


@pytest.fixture
def evening(tmp_path, monkeypatch):
    """`daily` on a synthetic market, a temporary ledger and a fake Telegram; returns the run, the world and the telegram."""
    real = ustrial.Ledger
    path = tmp_path / "ustrial1.db"
    monkeypatch.setattr(ustrial, "Ledger", lambda: real(path))
    monkeypatch.setattr(ustrial, "STATUS", tmp_path / "status.md")
    monkeypatch.setattr(ustrial, "load_settings", lambda: None)
    telegram = Telegram()
    monkeypatch.setattr("trader.notify.telegram.notifier_from_settings", lambda settings: telegram)
    all_sessions, all_secs = _market()
    world = {"e2": _e2([]), "v2": {}, "last": OCT30, "secs": all_secs, "error": None, "reads": 0}

    def refresh_members(ledger, now):
        world["reads"] += 1
        ledger.add_members([("A", "1", "Alpha Inc")], now)
        return ledger.table("members"), True
    monkeypatch.setattr(ustrial, "refresh_members", refresh_members)
    monkeypatch.setattr(ustrial, "fetch_filings", lambda ledger, members, now: {"failed": [], "new": 0})

    def inputs(ledger, now, calendar):
        if world["error"]:
            raise world["error"]
        sessions, secs = _upto(all_sessions, world["secs"], world["last"])
        return sessions, secs, 755.72, world["e2"], world["v2"]
    monkeypatch.setattr(ustrial, "inputs", inputs)

    def run(now, notify=True):
        return ustrial.daily(now, notify=notify)
    return run, world, telegram, all_sessions, path


def test_the_first_evening_says_what_to_buy_and_nothing_is_said_twice(evening):
    run, world, telegram, sessions, path = evening
    signal = sessions.index(OCT30)
    world["e2"], world["v2"] = _e2([("A", signal, 0.2), ("B", signal, 0.1)]), _v2(sessions, OCT30, ["C", "D"])
    assert run(MONDAY) == 0
    assert len(telegram.sent) == 4
    assert "E2 signals at the 30 Oct 2026 US close: A (+20.0%), B (+10.0%)" in telegram.sent[0] and "V2 signal" in telegram.sent[1]
    assert "DAILY SUMMARY 30 Oct 2026" in telegram.sent[2] and "Holding: none" in telegram.sent[2]
    plan = telegram.sent[3]
    assert "Tonight's US open, Mon 2 Nov, 8:00 pm India time" in plan
    assert "BUY A (Alpha Inc) with about $333.33" in plan and all(f"BUY {s} " in plan for s in "BCD")
    assert "SELL" not in plan.split("Pretend money")[0]
    assert world["reads"] == 1
    assert run(MONDAY.replace(minute=45)) == 0 and len(telegram.sent) == 4  # a repeat that evening: nothing new
    assert world["reads"] == 1  # and it doesn't ask the SEC or Yahoo again

    tuesday = datetime(2026, 11, 3, 18, 15, tzinfo=IST)
    world["last"] = date(2026, 11, 2)
    assert run(tuesday) == 0
    told = telegram.sent[4:]
    assert len(told) == 3
    assert ("Paper entries at the 02 Nov 2026 US open: E2 A: bought at $100.00, stop $85.00; E2 B: bought at $100.00, stop $85.00; "
            "V2 C: bought at $100.00, stop $90.00; V2 D: bought at $100.00, stop $90.00.") in told[0]
    assert "DAILY SUMMARY 02 Nov 2026" in told[1] and "Holding: A " in told[1]
    assert told[2].endswith("Nothing to buy or sell.")
    ledger = ustrial.Ledger()
    runs = ledger.table("runs")
    assert list(runs["status"]) == ["ok", "ok"] and "data to 2026-11-02" in runs["detail"].iat[-1]  # the repeat left no row
    assert ledger.last_answers() == (date(2026, 11, 2), set(world["secs"]))
    assert list(ledger.table("marks")["sid"]) == list("ABCD")
    ledger.close()


def test_the_list_waits_for_the_evening_of_the_open(evening):
    run, world, telegram, sessions, path = evening
    saturday = datetime(2026, 10, 31, 18, 15, tzinfo=IST)
    world["e2"] = _e2([("A", sessions.index(OCT30), 0.2)])
    assert run(saturday) == 0
    assert len(telegram.sent) == 2 and "E2 signals" in telegram.sent[0] and "DAILY SUMMARY" in telegram.sent[1]
    assert run(saturday.replace(minute=30)) == 0 and world["reads"] == 1  # a repeat with no list due does nothing
    sunday = saturday.replace(day=1, month=11)
    assert run(sunday) == 0 and len(telegram.sent) == 2 and world["reads"] == 2  # nothing new, but every evening is on record
    ledger = ustrial.Ledger()
    assert len(ledger.table("runs")) == 2
    ledger.close()
    assert run(MONDAY) == 0
    assert len(telegram.sent) == 3 and "BUY A (Alpha Inc) " in telegram.sent[2]


def test_a_stop_is_told_as_a_sell_once_in_the_next_list_and_time_exits_at_their_open(evening):
    run, world, telegram, sessions, path = evening
    signal = sessions.index(date(2026, 10, 29))
    n = len(sessions)
    lows = np.full(n, 100.0)
    stop_day = sessions.index(date(2026, 11, 5))
    lows[stop_day] = 80.0
    world["secs"] = {**world["secs"], "A": _security("A", n, lows=lows)}
    world["e2"] = _e2([("A", signal, 0.2), ("B", signal, 0.1)])
    assert run(MONDAY) == 0  # bought at Friday's open; Monday's list has nothing new to buy
    assert _lists(telegram)[-1].endswith("Nothing to buy or sell.")
    world["last"] = date(2026, 11, 5)
    friday = datetime(2026, 11, 6, 18, 15, tzinfo=IST)
    assert run(friday) == 0
    assert "SELL A (Alpha Inc): all the shares you hold from these lists (it hit its stop-loss on 05 Nov)" in _lists(telegram)[-1]
    assert any("Closed E2 A" in text and "(stop-loss hit, 05 Nov 2026)" in text for text in telegram.sent)
    world["last"] = date(2026, 11, 6)
    assert run(datetime(2026, 11, 9, 18, 15, tzinfo=IST)) == 0  # Monday's list: A's stop has been told
    assert "SELL A" not in _lists(telegram)[-1]

    world["last"] = sessions[signal + 1 + 39]  # B's 40 sessions end at the next open
    exit_day = sessions[signal + 1 + 40]
    assert run(datetime(exit_day.year, exit_day.month, exit_day.day, 18, 15, tzinfo=IST)) == 0
    assert "SELL B: all the shares you hold from these lists (its time is up)" in telegram.sent[-1] and "Tonight's" in telegram.sent[-1]
    count = len(_lists(telegram))
    world["last"] = exit_day  # closed at that open: it was told, so the next list says nothing about it
    next_day = NYSE.next_trading_day(exit_day)
    assert run(datetime(next_day.year, next_day.month, next_day.day, 18, 15, tzinfo=IST)) == 0
    assert len(_lists(telegram)) == count + 1 and "SELL B" not in _lists(telegram)[-1]


def _b_and_its_time_exit(world, sessions):
    signal = sessions.index(date(2026, 10, 29))
    world["e2"] = _e2([("B", signal, 0.1)])
    return sessions[signal + 1 + 40]


def _evening_of(day, hour=18, minute=15):
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=IST)


def test_a_time_exit_whose_evening_was_lost_is_told_in_the_next_list(evening):
    run, world, telegram, sessions, path = evening
    exit_day = _b_and_its_time_exit(world, sessions)
    assert run(MONDAY) == 0
    world["last"] = sessions[sessions.index(exit_day) - 1]
    world["error"] = ValueError("Yahoo: down")  # that evening's run fails, every try
    assert run(_evening_of(exit_day)) == 1
    world["error"] = None
    world["last"] = exit_day
    next_day = NYSE.next_trading_day(exit_day)
    assert run(_evening_of(next_day)) == 0
    assert f"SELL B: all the shares you hold from these lists (its time was up on {exit_day:%d %b}" in _lists(telegram)[-1]
    world["last"] = next_day  # told once
    after = NYSE.next_trading_day(next_day)
    assert run(_evening_of(after)) == 0 and "SELL B" not in _lists(telegram)[-1]


def test_a_time_exit_with_no_row_at_its_open_is_told_once(evening):
    run, world, telegram, sessions, path = evening
    exit_day = _b_and_its_time_exit(world, sessions)
    gap = _security("B", len(sessions))
    gap.present[sessions.index(exit_day)] = False  # no row at its exit open: the same SELL is planned again the next evening
    world["secs"] = {**world["secs"], "B": gap}
    assert run(MONDAY) == 0
    world["last"] = sessions[sessions.index(exit_day) - 1]
    assert run(_evening_of(exit_day)) == 0
    assert "SELL B" in _lists(telegram)[-1]
    world["last"] = exit_day
    next_day = NYSE.next_trading_day(exit_day)
    assert run(_evening_of(next_day)) == 0
    assert "SELL B" not in _lists(telegram)[-1]  # told the evening before


def test_messages_telegram_didnt_take_wait_for_the_next_run(evening):
    run, world, telegram, sessions, path = evening
    world["e2"] = _e2([("A", sessions.index(OCT30), 0.2)])
    telegram.works = False
    assert run(MONDAY) == 0
    assert len(telegram.sent) == 2 and "E2 signals" in telegram.sent[0]  # one refused, and then the list
    ledger = ustrial.Ledger()
    assert "2 messages waiting" in ledger.table("runs")["detail"].iat[-1] and len(ledger.unsent()) == 2
    ledger.close()
    telegram.works, telegram.sent = True, []
    assert run(MONDAY.replace(minute=30)) == 0
    assert [("E2 signals" in text, "DAILY SUMMARY" in text, "BUY A (Alpha Inc) " in text) for text in telegram.sent] == [
        (True, False, False), (False, True, False), (False, False, True)]  # in order, with the list after them
    assert run(MONDAY.replace(minute=45)) == 0 and len(telegram.sent) == 3
    ledger = ustrial.Ledger()
    assert ledger.unsent() == []
    ledger.close()


def test_a_repeat_after_the_list_went_out_sends_what_is_still_waiting_without_reading_anything(evening):
    run, world, telegram, sessions, path = evening
    assert run(MONDAY) == 0
    ledger = ustrial.Ledger()
    ledger.add_outbox([("late note", "a note still waiting")], MONDAY)
    ledger.close()
    assert run(MONDAY.replace(minute=30)) == 0 and telegram.sent[-1] == "a note still waiting" and world["reads"] == 1


def test_a_list_that_comes_after_the_open_tells_no_buy(evening):
    run, world, telegram, sessions, path = evening
    world["e2"] = _e2([("A", sessions.index(OCT30), 0.2)])
    assert run(MONDAY.replace(hour=21)) == 0
    assert "Too late to copy: A (Alpha Inc)." in _lists(telegram)[-1] and "BUY" not in _lists(telegram)[-1]
    world["last"] = date(2026, 11, 2)
    assert run(datetime(2026, 11, 3, 18, 15, tzinfo=IST)) == 0
    assert any("The paper account bought A at the 02 Nov open, but no list told you in time" in text for text in telegram.sent)


def test_a_buy_the_paper_account_didnt_make_is_said_plainly(evening):
    run, world, telegram, sessions, path = evening
    world["e2"] = _e2([("A", sessions.index(OCT30), 0.2)])
    assert run(MONDAY) == 0
    hole = _security("A", len(sessions))
    hole.present[sessions.index(date(2026, 11, 2))] = False  # it didn't trade at that open
    world["secs"], world["last"] = {**world["secs"], "A": hole}, date(2026, 11, 2)
    assert run(datetime(2026, 11, 3, 18, 15, tzinfo=IST)) == 0
    assert any("The list said BUY A for the 02 Nov open, but the paper account didn't buy it (it didn't trade at that open). If you bought it, the bot "
               "won't follow it" in text for text in telegram.sent)


def test_a_run_that_fails_near_the_open_says_so_once(evening):
    run, world, telegram, sessions, path = evening
    world["e2"] = _e2([("A", sessions.index(OCT30), 0.2)])
    world["error"] = ustrial.Refused("Yahoo's data ends 2026-10-29 <soon>")
    assert run(MONDAY) == 1 and telegram.sent == []  # 18:15: over an hour and a half to go
    at_risk = MONDAY.replace(hour=19, minute=15)
    assert run(at_risk) == 1
    assert len(telegram.sent) == 1 and "Tonight's US list isn't ready: Yahoo's data ends 2026-10-29 <soon>. If none comes before the open" in telegram.sent[0]
    assert run(at_risk.replace(minute=30)) == 1 and len(telegram.sent) == 1
    world["error"] = None
    assert run(at_risk.replace(minute=45)) == 0
    assert "BUY A (Alpha Inc) " in _lists(telegram)[-1]
    assert list(ustrial.Ledger().table("runs")["status"]) == ["failed", "failed", "failed", "ok"]


def test_a_computer_error_isnt_passed_on_and_after_the_open_it_doesnt_mention_the_open(evening):
    run, world, telegram, sessions, path = evening
    world["error"] = requests.ConnectionError("HTTPSConnectionPool(host='en.wikipedia.org', port=443)")
    assert run(MONDAY.replace(hour=20, minute=30)) == 1
    assert "Tonight's US list isn't ready: the prices or filings couldn't be read yet. There is nothing to copy tonight" in telegram.sent[0]
    assert "HTTPSConnectionPool" not in telegram.sent[0]
    assert "HTTPSConnectionPool" in ustrial.Ledger().table("runs")["detail"].iat[-1]  # it stays on record


def test_whether_a_list_is_too_late_is_judged_when_it_goes_not_when_the_run_began(evening, monkeypatch):
    run, world, telegram, sessions, path = evening
    world["e2"] = _e2([("A", sessions.index(OCT30), 0.2)])
    clock = {"calls": 0}

    def monotonic():
        clock["calls"] += 1
        return 0.0 if clock["calls"] == 1 else 3600.0  # the run took an hour
    monkeypatch.setattr(ustrial.time, "monotonic", monotonic)
    assert run(MONDAY.replace(hour=19, minute=30)) == 0
    assert "Too late to copy: A (Alpha Inc)." in _lists(telegram)[-1] and "BUY" not in _lists(telegram)[-1]


def test_no_warning_on_an_evening_with_no_open(evening):
    run, world, telegram, sessions, path = evening
    world["error"] = ValueError("Yahoo: down")
    assert run(datetime(2026, 10, 31, 19, 45, tzinfo=IST)) == 1 and telegram.sent == []


def test_a_failure_after_the_records_loses_no_message(evening, monkeypatch):
    run, world, telegram, sessions, path = evening
    world["e2"] = _e2([("A", sessions.index(OCT30), 0.2)])
    real = ustrial.next_open

    def broken(*args):
        raise TypeError("an unexpected answer")
    monkeypatch.setattr(ustrial, "next_open", broken)
    assert run(MONDAY) == 1
    assert len(telegram.sent) == 2 and "E2 signals" in telegram.sent[0]  # the messages went out before it
    ledger = ustrial.Ledger()
    assert ledger.table("runs")["status"].iat[-1] == "failed" and "TypeError: an unexpected answer" in ledger.table("runs")["detail"].iat[-1]
    ledger.close()
    monkeypatch.setattr(ustrial, "next_open", real)
    assert run(MONDAY.replace(minute=30)) == 0
    assert len(telegram.sent) == 3 and "BUY A (Alpha Inc) " in telegram.sent[-1]


def test_a_failure_while_recording_records_nothing_and_a_later_run_does_it_all(evening, monkeypatch):
    run, world, telegram, sessions, path = evening
    world["e2"] = _e2([("A", sessions.index(OCT30), 0.2)])
    real = ustrial.summary_message

    def broken(*args):
        raise KeyError("no such column")
    monkeypatch.setattr(ustrial, "summary_message", broken)
    assert run(MONDAY) == 1 and telegram.sent == []
    ledger = ustrial.Ledger()
    assert ledger.table("signals").empty and ledger.table("outbox").empty and ledger.last_answers() is None
    ledger.close()
    monkeypatch.setattr(ustrial, "summary_message", real)
    assert run(MONDAY.replace(minute=30)) == 0
    assert "E2 signals" in telegram.sent[0] and "BUY A (Alpha Inc) " in telegram.sent[-1]


def test_a_status_page_that_cant_be_written_costs_nothing_else(evening, monkeypatch):
    run, world, telegram, sessions, path = evening
    world["e2"] = _e2([("A", sessions.index(OCT30), 0.2)])

    def locked(*args):
        raise PermissionError("OneDrive has it")
    monkeypatch.setattr(ustrial, "write_status", locked)
    assert run(MONDAY) == 0 and "BUY A (Alpha Inc) " in telegram.sent[-1]
    assert ustrial.Ledger().table("runs")["status"].iat[-1] == "ok"


def test_any_error_at_all_is_a_failed_run_on_record(evening, monkeypatch):
    run, world, telegram, sessions, path = evening
    world["error"] = sqlite3.OperationalError("database is locked")
    assert run(MONDAY) == 1
    assert "OperationalError: database is locked" in ustrial.Ledger().table("runs")["detail"].iat[-1]


def test_a_ledger_that_wont_open_or_record_doesnt_escape_the_run(evening, monkeypatch):
    run, world, telegram, sessions, path = evening
    real = ustrial.Ledger

    def cant_open():
        raise sqlite3.OperationalError("database is locked")
    monkeypatch.setattr(ustrial, "Ledger", cant_open)
    assert run(MONDAY) == 1 and telegram.sent == []

    def opened():
        ledger = real(path)
        ledger.add_run = lambda *args: (_ for _ in ()).throw(sqlite3.OperationalError("database is locked"))
        return ledger
    monkeypatch.setattr(ustrial, "Ledger", opened)
    world["error"] = ValueError("Yahoo: down")
    assert run(MONDAY) == 1


def test_no_notify_sends_nothing_and_a_refused_run_records_nothing_but_the_failure(evening):
    run, world, telegram, sessions, path = evening
    world["e2"] = _e2([("A", sessions.index(OCT30), 0.2)])
    world["error"] = ValueError("Yahoo's data ends 2026-10-29, but the last completed US session is 2026-10-30")
    assert run(MONDAY) == 1 and telegram.sent == []
    ledger = ustrial.Ledger()
    assert ledger.table("signals").empty and ledger.table("runs")["status"].iat[-1] == "failed"
    assert "Yahoo's data ends" in ledger.table("runs")["detail"].iat[-1]
    ledger.close()
    world["error"] = None
    assert run(MONDAY, notify=False) == 0 and telegram.sent == []
    ledger = ustrial.Ledger()
    assert len(ledger.table("signals")) == 1 and ledger.table("notices").empty and len(ledger.unsent()) == 2
    ledger.close()
    assert run(MONDAY.replace(minute=30), notify=False) == 0 and telegram.sent == []  # still nothing, and the list stays due
    assert run(MONDAY.replace(minute=45)) == 0 and "BUY A (Alpha Inc) " in telegram.sent[-1]  # the next run with Telegram sends it all


def test_unread_filings_and_an_unread_list_show_in_the_runs_record(evening, monkeypatch):
    run, world, telegram, sessions, path = evening
    monkeypatch.setattr(ustrial, "fetch_filings", lambda ledger, members, now: {"failed": ["A", "B"], "new": 3})
    monkeypatch.setattr(ustrial, "refresh_members", lambda ledger, now: (ledger.table("members"), False))
    assert run(MONDAY) == 0
    ledger = ustrial.Ledger()
    assert "3 new filings (2 companies unread), list unread" in ledger.table("runs")["detail"].iat[-1]
    ledger.close()


def test_inputs_join_the_prices_filings_and_lists(tmp_path, monkeypatch):
    sessions, secs = _market(until=OCT30)
    asked = []

    def load_prices(tickers, now, calendar):
        asked.append(tickers)
        return sessions, secs, 700.0
    monkeypatch.setattr(ustrial, "load_prices", load_prices)
    seen = {}

    def features(sessions_, secs_, idx):
        seen["month-ends"] = [sessions_[i] for i in idx]
        return pd.DataFrame({"i": [idx[-1]], "sid": ["A"], "rank": [1]})
    monkeypatch.setattr(ustrial.round8, "features", features)
    monkeypatch.setattr(ustrial, "e2_signals", lambda filings, s, c, universe: ("E2 from", len(filings), universe.members))
    monkeypatch.setattr(ustrial, "v2_lists", lambda s, c, table, calendar: "V2 lists")
    ledger = ustrial.Ledger(tmp_path / "t.db")
    ledger.add_members([("A", "1", "A Co"), ("A", "2", "A Co")], MONDAY)  # a new CIK: one stock
    ledger.add_filings("A", [("a", "2026-10-29T12:00:00.000Z")], MONDAY)
    got = ustrial.inputs(ledger, MONDAY, NYSE)
    assert asked == [["A"]]
    assert got[:3] == (sessions, secs, 700.0) and got[4] == "V2 lists" and got[3][:2] == ("E2 from", 1)
    assert seen["month-ends"][-1] == OCT30 and seen["month-ends"][0] == date(2026, 8, 31)
    secs_without_a = {s: sec for s, sec in secs.items() if s != "A"}
    monkeypatch.setattr(ustrial, "load_prices", lambda tickers, now, calendar: (sessions, secs_without_a, 700.0))
    with pytest.raises(ValueError, match="no price for 1 of 1 stocks"):  # refused before anything is worked out
        ustrial.inputs(ledger, MONDAY, NYSE)
    ledger.close()


def test_the_command_line(tmp_path, monkeypatch, capsys):
    real = ustrial.Ledger
    monkeypatch.setattr(ustrial, "Ledger", lambda: real(tmp_path / "t.db"))
    monkeypatch.setattr(ustrial, "STATUS", tmp_path / "status.md")
    monkeypatch.setattr(ustrial, "configure_logging", lambda **kwargs: None)
    monkeypatch.setattr(ustrial, "load_settings", lambda: type("S", (), {"secret_values": lambda self: []})())
    calls = []
    monkeypatch.setattr(ustrial, "daily", lambda notify=True: calls.append(notify) or 7)
    with pytest.raises(SystemExit) as finished:
        ustrial.main(["daily", "--no-notify"])
    assert finished.value.code == 7 and calls == [False]
    sessions, secs = _market(until=OCT30)
    monkeypatch.setattr(ustrial, "inputs", lambda ledger, now, calendar: (sessions, secs, 700.0, _e2([("A", 10, 0.2)]), {}))
    ustrial.main(["status"])
    assert "US paper trial 1: status" in capsys.readouterr().out
    ledger = real(tmp_path / "t.db")
    assert ledger.table("signals").empty and ledger.table("trades").empty  # looking records nothing
    ledger.close()


# ---------------------------------------------------------------------------------------------- the health check
def test_the_health_check_alerts_when_the_trial_fails_or_stops(tmp_path, monkeypatch):
    monkeypatch.setattr(health, "ROOT", tmp_path)
    assert health.ustrial_check(MONDAY) == []  # not started
    ledger = ustrial.Ledger(tmp_path / health.USTRIAL_LEDGER)
    ledger.add_run(MONDAY, "ok", "data to 2026-10-30")
    [check] = health.ustrial_check(MONDAY)
    assert check.level == OK and "0 closed paper trade(s), +0.00R" in check.detail
    ledger.add_brake("account", "kill switch", OCT30, "x", MONDAY)
    assert "brakes: account kill switch" in health.ustrial_check(MONDAY)[0].detail
    [stale] = health.ustrial_check(datetime(2026, 11, 3, 21, 0, tzinfo=IST))  # it runs every evening: a day without is enough
    assert stale.level == ALERT and "no good update" in stale.detail and "ustrial1.log" in stale.detail
    assert health.ustrial_check(datetime(2026, 11, 3, 18, 0, tzinfo=IST))[0].level == OK  # tonight's first try may be failing still
    ledger.add_run(MONDAY, "failed", "ValueError: Yahoo")
    [failed] = health.ustrial_check(MONDAY)
    assert failed.level == ALERT and failed.name == "US paper trial" and "Yahoo" in failed.detail
    ledger.close()


def test_the_health_check_alerts_when_messages_cant_be_sent(tmp_path, monkeypatch):
    monkeypatch.setattr(health, "ROOT", tmp_path)
    ledger = ustrial.Ledger(tmp_path / health.USTRIAL_LEDGER)
    ledger.add_run(MONDAY, "ok", "data to 2026-10-30")
    ledger.add_outbox([("a", "text"), ("b", "text")], MONDAY)
    ledger.add_notice("a", MONDAY, True)
    [check] = health.ustrial_check(MONDAY)
    assert check.level == ALERT and "1 message(s) couldn't be sent" in check.detail
    ledger.add_notice("b", MONDAY, False)
    ledger.add_notice("b", MONDAY, True)
    assert health.ustrial_check(MONDAY)[0].level == OK
    ledger.add_notice(f"plan {MONDAY.date()}", MONDAY, False)
    [lost] = health.ustrial_check(MONDAY)
    assert lost.level == ALERT and "tonight's list couldn't be sent" in lost.detail
    assert health.ustrial_check(datetime(2026, 11, 3, 8, 0, tzinfo=IST))[0].level == OK  # only that evening's
    ledger.add_notice(f"plan {MONDAY.date()}", MONDAY, True)
    assert health.ustrial_check(MONDAY)[0].level == OK
    ledger.close()


def test_the_health_check_warns_when_the_list_stops_updating(tmp_path, monkeypatch):
    monkeypatch.setattr(health, "ROOT", tmp_path)
    ledger = ustrial.Ledger(tmp_path / health.USTRIAL_LEDGER)
    for _ in range(health.USTRIAL_LIST_UNREAD - 1):
        ledger.add_run(MONDAY, "ok", "data to 2026-10-30; 500 stocks, 0 new filings, list unread; signals 0")
    assert health.ustrial_check(MONDAY)[0].level == OK
    ledger.add_run(MONDAY, "ok", "data to 2026-10-30; 500 stocks, 0 new filings, list unread; signals 0")
    [check] = health.ustrial_check(MONDAY)
    assert check.level == WARN and "hasn't been read" in check.detail
    ledger.add_run(MONDAY, "ok", "data to 2026-10-30; 500 stocks, 0 new filings; signals 0")
    assert health.ustrial_check(MONDAY)[0].level == OK
    ledger.close()


def test_a_research_ledger_that_cant_be_read_doesnt_stop_the_other_checks(tmp_path, monkeypatch):
    monkeypatch.setattr(health, "ROOT", tmp_path)
    (tmp_path / health.USTRIAL_LEDGER).parent.mkdir(parents=True)
    (tmp_path / health.USTRIAL_LEDGER).write_bytes(b"this is not a database, but it is long enough to be read as a file")
    with pytest.raises(sqlite3.DatabaseError):
        health.ustrial_check(MONDAY)
    [check] = health.research_check(health.ustrial_check, MONDAY)
    assert check.level == ALERT and check.name == "ustrial" and "can't be read" in check.detail
