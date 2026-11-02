"""US paper trial 1: paper trial 1's rules (E2 x3 + V2 x2) on S&P 500 stocks in one paper account, on Yahoo's prices and
the SEC's results filings, as defined in docs/research/ustrial1-definition.md.

    python -m trader.research.ustrial daily     # scheduled each evening, before the US open
    python -m trader.research.ustrial status    # the account: open positions and closed trades

Research only: nothing here can place an order or change a strategy's status, and the rules have never been tested on US
stocks. Its messages say what the rules buy and sell at each US open, for anyone who chooses to copy them by hand. The
account logic is paper trial 1's, kept in this file with US costs and NYSE's month-ends so that trader/research/trial.py,
which the real-money orders come from, stays untouched.
"""
from __future__ import annotations

import argparse
import bisect
import html
import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import date, datetime, time as clock_time, timedelta
from html.parser import HTMLParser
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import requests

from trader.config import ENV_FILE, ROOT, load_settings, parse_env_file
from trader.data.validate import DAILY_SETTLE
from trader.logging_setup import configure_logging, make_console_utf8
from trader.markets.calendar import MarketCalendar, load_calendars
from trader.notify.templates import money
from trader.research import forward2, forward3, round8, round9, round10, trial
from trader.research.costs import CostModel
from trader.research.datasets import text_sha256

log = logging.getLogger(__name__)
IST = ZoneInfo("Asia/Kolkata")
NEW_YORK = ZoneInfo("America/New_York")
DEFINITION = ROOT / "docs" / "research" / "ustrial1-definition.md"
DEFINITION_SHA256 = "cd6e3fca659f21dd15c2165e62f259b9378b6ba60198c11fa06a43becd27890d"  # pinned 2026-11-02 IST
LEDGER = ROOT / "state" / "ustrial1.db"
STATUS = ROOT / "state" / "ustrial1-status.md"
CAPITAL, RISK = 10_000, 0.005
VALUE = {part: CAPITAL * RISK / stop for part, stop in trial.STOPS.items()}  # E2 $333.33, V2 $500
FIRST_SIGNAL = date(2026, 11, 2)  # the first US close the trial can act on: the next open is the first it can tell in time
MARKET = "SPY"  # the session grid and the daily market check; never traded here
HISTORY = "4y"
FILED_BY = clock_time(16, 0)  # a filing accepted later, New York time, reaches the market in the next session
MIN_STOCKS, MIN_LIST, MAX_MISSING, MAX_FAILED = 400, 400, 0.02, 25
ALL_ANSWERS_UNTIL = clock_time(18, 15)  # India time: the task's earlier tries wait for every stock; later ones allow MAX_MISSING
HOLD_BACK = 3  # sessions behind the last good run that a run still waits for a held stock or a candidate
NO_ANSWER_LIMIT = 20  # sessions with no answer before a held stock closes at the last price on record
REACH = sum(trial.PLACES.values()) + trial.PLACES["V2"]  # how far down its list V2 can go: past every held stock, then its places
LIST_AT_RISK = timedelta(minutes=45)  # this close to the open, a failed run says so on Telegram at once
WORKERS, PAUSE = 6, 0.6  # SEC requests at once, and each one's seconds of rest: at most 10 a second, its fair-access limit
COSTS = CostModel(  # Kite's US charges: 0.10% brokerage + 18% GST, 0.005% IFSCA fee (kept in the stt fields: no GST on it), SEC fee
    name="US stocks on Kite", brokerage_rate=0.001, gst_rate=0.18, stt_buy=0.00005, stt_sell=0.00005,
    sell_fee_rate=0.0000206, slippage_per_side=0.0002, verified="2026-11-01")
ROUND_TRIP = {part: COSTS.round_trip(value) for part, value in VALUE.items()}
WIKIPEDIA_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
AGENT = "my_ai_agent personal research script"  # SEC_USER_AGENT in .env replaces it (the SEC asks tools to say who they are)
TAG = "<b>[US PAPER TRIAL · paper only]</b>"
TAG_OPEN = "<b>[US PAPER TRIAL · paper only] {title}</b>"
CLOSED_HOW = {"stop": "stop-loss hit", "time": "its time was up", "time, delayed": "its time was up", "no further rows": "it stopped trading"}
NOT_BOUGHT_WHY = {"not bought": "it didn't trade at that open", "no free place": "no free place", "already held": "already held",
                  "brake": "the trial has stopped buying"}
EXTRA_TABLES = ("members", "filings", "answers", "marks", "outbox")
EXTRA_SCHEMA = """
CREATE TABLE IF NOT EXISTS members (id INTEGER PRIMARY KEY, ticker TEXT NOT NULL, cik TEXT NOT NULL, name TEXT NOT NULL,
    first_seen TEXT NOT NULL, UNIQUE (ticker, cik));
CREATE TABLE IF NOT EXISTS filings (id INTEGER PRIMARY KEY, ticker TEXT NOT NULL, accession TEXT NOT NULL,
    accepted TEXT NOT NULL, first_seen TEXT NOT NULL, UNIQUE (ticker, accession));
CREATE TABLE IF NOT EXISTS answers (id INTEGER PRIMARY KEY, session TEXT UNIQUE NOT NULL, tickers TEXT NOT NULL,
    recorded_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS marks (id INTEGER PRIMARY KEY, part TEXT NOT NULL, sid TEXT NOT NULL, entry_date TEXT NOT NULL,
    session TEXT NOT NULL, entry_price REAL NOT NULL, close REAL NOT NULL, mark REAL NOT NULL, recorded_at TEXT NOT NULL,
    UNIQUE (part, sid, entry_date, session));
CREATE TABLE IF NOT EXISTS outbox (id INTEGER PRIMARY KEY, key TEXT UNIQUE NOT NULL, text TEXT NOT NULL,
    recorded_at TEXT NOT NULL);
"""
for _table in EXTRA_TABLES:
    EXTRA_SCHEMA += (f"CREATE TRIGGER IF NOT EXISTS {_table}_no_update BEFORE UPDATE ON {_table} BEGIN SELECT RAISE(ABORT, "
                     f"'the trial ledger is append-only'); END;\n"
                     f"CREATE TRIGGER IF NOT EXISTS {_table}_no_delete BEFORE DELETE ON {_table} BEGIN SELECT RAISE(ABORT, "
                     f"'the trial ledger is append-only'); END;\n")


class Refused(ValueError):
    """A run refused for a reason written here in plain words, fit to pass on to the reader."""


def check_definition() -> str:
    digest = text_sha256(DEFINITION)
    if digest != DEFINITION_SHA256:
        raise SystemExit(f"{DEFINITION.name} changed after it was pinned (sha256 {digest}); define a new trial instead.")
    return digest


class Ledger(trial.Ledger):
    """Paper trial 1's ledger, apart from every other record, plus the companies, their results filings, the stocks answered
    on each session, open positions' latest prices, and the messages."""

    def __init__(self, path: Path | str = LEDGER):
        super().__init__(path)
        self.conn.execute("PRAGMA busy_timeout = 30000")  # the state folder is synced by OneDrive: wait out a short lock
        self.conn.executescript(EXTRA_SCHEMA)

    def table(self, name: str) -> pd.DataFrame:
        if name in EXTRA_TABLES:
            return pd.read_sql_query(f"SELECT * FROM {name} ORDER BY id", self.conn)
        return super().table(name)

    @contextmanager
    def transaction(self):
        """All of it recorded, or none of it."""
        self.conn.execute("BEGIN")
        try:
            yield
            self.conn.execute("COMMIT")
        except BaseException:
            if self.conn.in_transaction:
                self.conn.execute("ROLLBACK")
            raise

    def add_members(self, members: list[tuple[str, str, str]], at: datetime) -> int:
        return self._add("INSERT OR IGNORE INTO members (ticker, cik, name, first_seen) VALUES (?, ?, ?, ?)",
                         [(ticker, cik, name, at.isoformat()) for ticker, cik, name in members])

    def add_filings(self, ticker: str, filings: list[tuple[str, str]], at: datetime) -> int:
        return self._add("INSERT OR IGNORE INTO filings (ticker, accession, accepted, first_seen) VALUES (?, ?, ?, ?)",
                         [(ticker, accession, accepted, at.isoformat()) for accession, accepted in filings])

    def _add(self, query: str, rows: list[tuple]) -> int:
        """All the rows in one transaction, and how many were new."""
        before = self.conn.total_changes
        with self.transaction():
            self.conn.executemany(query, rows)
        return self.conn.total_changes - before

    def add_answers(self, session: date, tickers: set[str], at: datetime) -> None:
        self.conn.execute("INSERT OR IGNORE INTO answers (session, tickers, recorded_at) VALUES (?, ?, ?)",
                          (session.isoformat(), json.dumps(sorted(tickers)), at.isoformat()))

    def last_answers(self) -> tuple[date, set[str]] | None:
        """The newest session a good run covered, and the stocks with a row on it."""
        row = self.conn.execute("SELECT session, tickers FROM answers ORDER BY id DESC LIMIT 1").fetchone()
        return (date.fromisoformat(row[0]), set(json.loads(row[1]))) if row else None

    def add_marks(self, positions: list, sessions: list[date], secs: dict, at: datetime) -> None:
        """Each open position's latest price, which is all that is left of it if Yahoo stops answering for the stock."""
        self.conn.executemany(
            "INSERT OR IGNORE INTO marks (part, sid, entry_date, session, entry_price, close, mark, recorded_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [(part, sid, entry.isoformat(), sessions[int(secs[sid].last_row[-1])].isoformat(), t["entry_raw"],
              float(secs[sid].raw_close[int(secs[sid].last_row[-1])]), t["mark"], at.isoformat())
             for part, sid, entry, t in positions if "mark" in t])

    def last_mark(self, part: str, sid: str, entry: date) -> dict | None:
        row = self.conn.execute("SELECT session, entry_price, close, mark FROM marks WHERE part = ? AND sid = ? AND entry_date = ? "
                                "ORDER BY session DESC LIMIT 1", (part, sid, entry.isoformat())).fetchone()
        return dict(zip(("session", "entry_price", "close", "mark"), row)) if row else None

    def add_outbox(self, notes: list[tuple[str, str]], at: datetime) -> None:
        self.conn.executemany("INSERT OR IGNORE INTO outbox (key, text, recorded_at) VALUES (?, ?, ?)",
                              [(key, text, at.isoformat()) for key, text in notes])

    def unsent(self) -> list[tuple[str, str]]:
        """(key, text) of the messages not yet sent, oldest first."""
        return self.conn.execute("SELECT key, text FROM outbox AS o WHERE NOT EXISTS (SELECT 1 FROM notices AS n "
                                 "WHERE n.key = o.key AND n.sent = 1) ORDER BY id").fetchall()


# -------------------------------------------------------------------------------------------- the companies
class _Constituents(HTMLParser):
    """The rows of Wikipedia's table with the id "constituents" (cells as text; tables inside it are not expected)."""

    def __init__(self):
        super().__init__()
        self.inside, self.rows, self.row, self.cell = False, [], None, None

    def handle_starttag(self, tag, attrs):
        if tag == "table" and dict(attrs).get("id") == "constituents":
            self.inside = True
        elif self.inside and tag == "tr":
            self.row = []
        elif self.inside and tag in ("td", "th"):
            self.cell = []

    def handle_endtag(self, tag):
        if tag == "table":
            self.inside = False
        elif self.inside and tag == "tr" and self.row is not None:
            self.rows.append(self.row)
            self.row = None
        elif self.inside and tag in ("td", "th") and self.cell is not None and self.row is not None:
            self.row.append("".join(self.cell).strip())
            self.cell = None

    def handle_data(self, data):
        if self.cell is not None:
            self.cell.append(data)


def parse_constituents(page: str, on_record: set[str] | frozenset[str] = frozenset()) -> list[tuple[str, str, str]]:
    """(Yahoo's ticker, CIK, company name) for each company, one share class each: the one on record if the page still shows
    it, otherwise the first listed."""
    parser = _Constituents()
    parser.feed(page)
    if not parser.rows or not {"Symbol", "CIK"} <= set(parser.rows[0]):
        raise Refused("Wikipedia's S&P 500 page has no constituents table with Symbol and CIK")
    header = parser.rows[0]
    symbol, cik, name = header.index("Symbol"), header.index("CIK"), header.index("Security") if "Security" in header else None
    companies: dict[str, list[tuple[str, str]]] = {}
    for row in parser.rows[1:]:
        if len(row) > max(symbol, cik) and row[cik].isdigit():
            companies.setdefault(row[cik], []).append((row[symbol].replace(".", "-"), row[name] if name is not None else ""))
    if len(companies) < MIN_LIST:
        raise Refused(f"Wikipedia's S&P 500 table has only {len(companies)} companies")
    chosen = {company: next((c for c in classes if c[0] in on_record), classes[0]) for company, classes in companies.items()}
    return [(ticker, company, title) for company, (ticker, title) in chosen.items()]


def refresh_members(ledger: Ledger, now: datetime, http=requests) -> tuple[pd.DataFrame, bool]:
    """Every company seen so far, with any new ones added, and whether the page could be read. A failed look keeps the list
    (only a first look must work)."""
    try:
        answer = http.get(WIKIPEDIA_URL, headers={"User-Agent": AGENT}, timeout=30)
        answer.raise_for_status()
        added = ledger.add_members(parse_constituents(answer.text, set(ledger.table("members")["ticker"])), now)
        if added:
            log.info("US paper trial: %d new companies on the S&P 500 list", added)
        read = True
    except (requests.RequestException, ValueError) as exc:
        if ledger.table("members").empty:
            raise
        log.warning("US paper trial: the S&P 500 list stays as it was: %s: %s", type(exc).__name__, exc)
        read = False
    return ledger.table("members"), read


# ------------------------------------------------------------------------------------------- results filings
def parse_filings(payload: dict) -> list[tuple[str, str]]:
    """(accession number, when it was accepted) of each 8-K listing Item 2.02 in one company's SEC record."""
    recent = payload["filings"]["recent"]
    return [(accession, accepted) for form, items, accession, accepted in zip(
                recent["form"], recent["items"], recent["accessionNumber"], recent["acceptanceDateTime"])
            if form == "8-K" and "2.02" in str(items).split(",")]


def fetch_filings(ledger: Ledger, members: pd.DataFrame, now: datetime, http=requests, sleep=time.sleep) -> dict:
    """Each company's results filings from the SEC, new ones added to the ledger. A few failures keep what is on record;
    MAX_FAILED of them fail the run."""
    headers = {"User-Agent": parse_env_file(ENV_FILE).get("SEC_USER_AGENT") or AGENT}

    def ask(cik: str) -> list[tuple[str, str]] | Exception:
        try:
            answer = http.get(SUBMISSIONS_URL.format(cik=int(cik)), headers=headers, timeout=30)
            answer.raise_for_status()
            return parse_filings(answer.json())
        except (requests.RequestException, ValueError, KeyError, TypeError) as exc:
            return exc
        finally:
            sleep(PAUSE)

    failed, new = [], 0
    pool = ThreadPoolExecutor(WORKERS)
    try:
        for ticker, answer in zip(members["ticker"], pool.map(ask, members["cik"])):
            if not isinstance(answer, Exception):
                new += ledger.add_filings(ticker, answer, now)
                continue
            failed.append(ticker)
            log.warning("US paper trial: SEC filings of %s: %s: %s", ticker, type(answer).__name__, answer)
            if len(failed) >= MAX_FAILED:
                raise Refused(f"the SEC's filings couldn't be read for {len(failed)} companies, the last {ticker}: "
                              f"{type(answer).__name__}")
    finally:
        pool.shutdown(wait=False, cancel_futures=True)
    return {"failed": failed, "new": new}


def results_notices(filings: pd.DataFrame, sessions: list[date], secs: dict) -> dict[str, tuple[np.ndarray, np.ndarray]]:
    """Each stock's results filings in round 10's form: (session m, that session's date), in filing order. Filings after
    the last session of the data wait for a later run."""
    n, out = len(sessions), {}
    for ticker, rows in filings[filings["ticker"].isin(set(secs))].groupby("ticker"):
        accepted = sorted(datetime.fromisoformat(a.replace("Z", "+00:00")).astimezone(NEW_YORK) for a in rows["accepted"])
        found = []
        for at in accepted:
            m = bisect.bisect_left(sessions, at.date())
            if m < n and sessions[m] == at.date() and at.time() >= FILED_BY:
                m += 1
            if m < n:
                found.append(m)
        if found:
            out[ticker] = (np.asarray(found, int), np.asarray([sessions[m] for m in found], dtype=object))
    return out


# ------------------------------------------------------------------------------------------------- prices
def yahoo_prices(tickers: list[str]) -> pd.DataFrame:
    """Daily rows from Yahoo, columns (ticker, field)."""
    import yfinance as yf

    try:
        return yf.download(tickers, period=HISTORY, interval="1d", auto_adjust=False, actions=False, group_by="ticker",
                           threads=True, progress=False, timeout=30)  # slow ones get a second chance in load_prices
    except Exception as exc:  # whatever an unofficial source raises: this run records nothing, and the next one catches up
        raise ValueError(f"Yahoo: {type(exc).__name__}: {exc}") from exc


def security(sid: str, rows: pd.DataFrame) -> round8.Security | None:
    """One stock's Yahoo rows, already laid on the session grid, as the trial's rules read them: "raw" is Yahoo's Close
    (split-adjusted, as printed), and adjusted prices follow its Adj Close. None if it has no good row."""
    good = ((rows["Open"] > 0) & (rows["High"] > 0) & (rows["Low"] > 0) & (rows["Close"] > 0) & (rows["Adj Close"] > 0)
            & (rows["Volume"] > 0)).to_numpy(bool)
    if not good.any():
        return None

    def column(name: str) -> np.ndarray:
        return np.where(good, rows[name].to_numpy(float), np.nan)

    opened, high, low, close = column("Open"), column("High"), column("Low"), column("Close")
    factor = column("Adj Close") / close
    n = len(rows)
    return round8.Security(sid=sid, present=good, eq=good.copy(), raw_close=close, raw_open=opened, raw_high=high, raw_low=low,
                           raw_prev=pd.Series(close).ffill().shift(1).to_numpy(float),
                           value=np.nan_to_num(close * rows["Volume"].to_numpy(float)), adj_open=opened * factor,
                           adj_low=low * factor, adj_close=close * factor,
                           last_row=np.maximum.accumulate(np.where(good, np.arange(n), -1)).astype(np.int32))


def _with_a_close(prices: pd.DataFrame, last: date) -> set[str]:
    """The tickers with a close on the session `last`."""
    rows = prices.index[[stamp.date() == last for stamp in prices.index]]
    if not len(rows):
        return set()
    return {ticker for (ticker, field), value in prices.loc[rows[0]].items() if field == "Close" and value > 0}


def load_prices(tickers: list[str], now: datetime, calendar: MarketCalendar, download=None) -> tuple[list[date], dict, float]:
    """The completed sessions on SPY's rows, each stock on them, and SPY's latest close. yfinance swallows a ticker's failure
    and leaves it blank, so the tickers with no row for the last session are asked for once more. Raises ValueError if Yahoo's
    data doesn't reach the last completed session, skips one, or covers too few stocks: such a run must record nothing."""
    ask = download or yahoo_prices
    names = [*tickers, MARKET]
    last = calendar.last_completed_session(now - DAILY_SETTLE)
    prices = ask(names)
    blank = [name for name in names if name not in _with_a_close(prices, last)]
    if blank:
        again = ask(blank)
        found = sorted(_with_a_close(again, last) & set(blank))
        log.info("US paper trial: %d tickers had no row for %s, %d of them did when asked again", len(blank), last, len(found))
        if found:
            prices = pd.concat([prices.drop(columns=found, level=0, errors="ignore"), again[found]], axis=1).sort_index()
    answered = set(prices.columns.get_level_values(0))
    if MARKET not in answered:
        raise Refused(f"Yahoo's answer has no {MARKET}")
    market = prices[MARKET]["Close"].dropna()
    grid = market.index[[stamp.date() <= last for stamp in market.index]]
    if len(grid) < 2 or grid[-1].date() != last:
        raise Refused(f"Yahoo's data ends {grid[-1].date() if len(grid) else 'nowhere'}, but the last completed US "
                      f"session is {last}")
    sessions = [stamp.date() for stamp in grid]
    days = calendar.trading_days(max(sessions[0], date(last.year, 1, 1)), last)
    if days != sessions[-len(days):]:
        raise Refused(f"Yahoo's rows for {MARKET} don't match the US calendar this year: "
                      f"{', '.join(str(d) for d in sorted(set(days) ^ {d for d in sessions if d >= days[0]})[:3])}")
    secs = {}
    for sid in tickers:
        if sid in answered:
            sec = security(sid, prices[sid].reindex(grid))
            if sec is not None:
                secs[sid] = sec
    if len(secs) < MIN_STOCKS:
        raise Refused(f"Yahoo answered for only {len(secs)} of {len(tickers)} stocks")
    return sessions, secs, float(market.loc[grid[-1]])


def needed_stocks(ledger: Ledger, covered: date) -> set[str]:
    """The stocks a run must not decide without: those held, and the candidates for the next decisions (V2's only as far
    down its list as it can reach; the rest of its list never comes up)."""
    decisions, trades, signals = ledger.table("decisions"), ledger.table("trades"), ledger.table("signals")
    closed = set(zip(trades["part"], trades["sid"], trades["signal_date"]))
    decided = set(zip(decisions["part"], decisions["sid"], decisions["signal_date"]))
    held = {sid for part, sid, signal, status in zip(decisions["part"], decisions["sid"], decisions["signal_date"],
                                                     decisions["status"])
            if status == "bought" and (part, sid, signal) not in closed}
    waiting = {s.sid for s in signals.itertuples(index=False)
               if not s.late and (s.part, s.sid, s.signal_date) not in decided
               and s.signal_date >= covered.isoformat() and (s.part == "E2" or s.rank <= REACH)}
    return held | waiting


def check_answers(ledger: Ledger, tickers: list[str], sessions: list[date], secs: dict, now: datetime) -> None:
    """Refuses a run on a partial answer from Yahoo before anything is recorded: a stock missing tonight would change the
    ranks and signals for good, and could turn a BUY already told into "not bought". A stock counts only if it had a row on
    the last good run, so one that has really stopped holds up a single evening, or a few if it is held or a candidate."""
    answered = {sid for sid, sec in secs.items() if sec.present[-1]}
    last = ledger.last_answers()
    expected = last[1] if last else set(tickers)
    gone = sorted(expected - answered)
    allowed = MAX_MISSING * len(expected) if now.astimezone(IST).time() >= ALL_ANSWERS_UNTIL else 0
    if len(gone) > allowed:
        raise Refused(f"Yahoo has no price for {len(gone)} of {len(expected)} stocks on {sessions[-1]}, e.g. {', '.join(gone[:3])}")
    if last and sum(day > last[0] for day in sessions) <= HOLD_BACK:
        lacking = sorted(set(gone) & needed_stocks(ledger, last[0]))
        if lacking:
            raise Refused(f"Yahoo has no price for {', '.join(lacking)}, which the trial holds or may buy")


# ------------------------------------------------------------------------------------------------- signals
def e2_signals(filings: pd.DataFrame, sessions: list[date], secs: dict, universe: round10.Universe) -> pd.DataFrame:
    """E2's signals, as round 10 computes them, from FIRST_SIGNAL's close."""
    events = round10.flag_signals(round10.reaction_events(results_notices(filings, sessions, secs), sessions, secs, universe))
    first = bisect.bisect_left(sessions, FIRST_SIGNAL)
    return events[events["is_signal"] & (events["signal"] >= first)].reset_index(drop=True)


def v2_lists(sessions: list[date], secs: dict, table: pd.DataFrame, calendar: MarketCalendar) -> dict[int, pd.DataFrame]:
    """Each known month-end from FIRST_SIGNAL: the eligible stocks of ranks 101-300, highest volatility-adjusted momentum
    first (ties by symbol), the first 20 kept."""
    wanted = [i for i in forward2.month_ends_known(sessions, calendar) if sessions[i] >= FIRST_SIGNAL]
    if not wanted:
        return {}
    scored = round9.add_scores(table[table["i"].isin(wanted)], secs)
    lo, hi = round8.TIERS["N2"]
    out = {}
    for i in wanted:
        tier = scored[(scored["i"] == i) & scored["rank"].between(lo, hi)].dropna(subset=["score_V"])
        out[i] = tier.sort_values(["score_V", "sid"], ascending=[False, True]).head(trial.RANKED)[["sid", "score_V"]]
    return out


def record_old_signals_as_late(ledger, sessions: list[date], e2: pd.DataFrame, now: datetime, events: dict) -> None:
    """Ranks and thresholds are computed on tonight's list, so a list change can make an old event a signal, with hindsight
    in it. One dated on or before the last session a good run covered, whose entry session has passed, is on record as late:
    never a candidate. Catching up after days with no good run is unchanged: those sessions are newer than that."""
    last = ledger.last_answers()
    if last is None:
        return
    recorded = ledger.table("signals")
    known = set(zip(recorded["part"], recorded["sid"], recorded["signal_date"]))
    for row in e2.itertuples(index=False):
        signal = sessions[row.signal]
        if signal <= last[0] and row.signal + 1 < len(sessions) and ("E2", row.sid, signal.isoformat()) not in known:
            ledger.add_signal("E2", row.sid, signal, None, float(row.abnormal), row.tier, True, now)
            events["signals"].append(("E2", row.sid, signal, float(row.abnormal), True))


# ------------------------------------------------------------------------------------------------- account
def with_costs(t: dict, part: str) -> dict:
    cost = ROUND_TRIP[part] + (COSTS.slippage_per_side if t["outcome"] == "stop" else 0.0)
    return {**t, "cost": cost, "net": t["gross"] - cost}


def e2_position(sec: round8.Security, e: int, n: int) -> dict:
    t = forward3.position(sec, e, n)
    return with_costs(t, "E2") if t["outcome"] in forward3.CLOSED else t


def v2_position(sec: round8.Security, e: int, x0: int, n: int) -> dict:
    t = forward2.trade(sec, e, x0, n)
    return with_costs(t, "V2") if t["outcome"] in forward2.CLOSED else t


def update(ledger, sessions: list[date], secs: dict, e2: pd.DataFrame, v2: dict[int, pd.DataFrame], now: datetime,
           calendar: MarketCalendar) -> dict:
    """Record what has happened since the last update: new signals, entry decisions, closed positions, brakes. Recorded
    rows are never recomputed. As trial.update, with US costs and NYSE's month-ends, old signals recorded as late, and an end
    for a held stock Yahoo no longer answers for."""
    n = len(sessions)
    index = {d.isoformat(): i for i, d in enumerate(sessions)}
    events = {"signals": [], "entries": [], "closed": [], "open": [], "brakes": [], "waiting": [], "no prices": []}
    record_old_signals_as_late(ledger, sessions, e2, now, events)
    trial.record_signals(ledger, sessions, e2, v2, now, events)
    sig = ledger.table("signals")
    if sig.empty:
        return events
    sig = sig[sig["late"] == 0].assign(entry_i=lambda f: [index[d] + 1 if d in index else n for d in f["signal_date"]])
    decisions = ledger.table("decisions")
    status_of = {(p, s, d): st for p, s, d, st in zip(decisions["part"], decisions["sid"], decisions["signal_date"],
                                                       decisions["status"])}
    closed = ledger.table("trades")
    closed_of = {(p, s, d): (o, ed) for p, s, d, o, ed in zip(closed["part"], closed["sid"], closed["signal_date"],
                                                              closed["outcome"], closed["exit_date"])}
    brakes_seen = set(ledger.table("brakes")["scope"])
    ends = forward2.month_ends_known(sessions, calendar)
    places = {part: [0] * k for part, k in trial.PLACES.items()}
    held: dict[str, int] = {}

    def exit_session(signal_i: int) -> int:
        later = [j for j in ends if j > signal_i]
        return later[0] + 1 if later else n + 1

    def blocked(part: str, entry: date) -> bool:
        states = trial.brake_states(ledger.table("trades"))
        for scope in ("account", part):
            if scope in states:
                kind, when, reason = states[scope]
                if scope not in brakes_seen:
                    ledger.add_brake(scope, kind, date.fromisoformat(when), reason, now)
                    brakes_seen.add(scope)
                    events["brakes"].append((scope, kind, when, reason))
                if when < entry.isoformat():
                    return True
        return False

    def no_answer(part: str, c, entry_i: int) -> int:
        """Yahoo has no prices for a held stock (renamed, or bought out): it keeps its place until NO_ANSWER_LIMIT sessions
        have passed, then closes at the last price on record. When its place is free."""
        last = ledger.last_mark(part, c.sid, sessions[entry_i])
        i = index.get(last["session"]) if last else None
        if i is None or n - 1 - i < NO_ANSWER_LIMIT:
            events["no prices"].append((part, c.sid, last))
            return n
        record = with_costs({"outcome": "no further rows", "gross": last["mark"], "gapped": False, "entry_date": sessions[entry_i],
                             "entry_price": last["entry_price"], "exit_date": sessions[i], "exit_price": last["close"]}, part)
        ledger.add_trade(part, c.sid, date.fromisoformat(c.signal_date), c.tier, record, now)
        events["closed"].append((part, c.sid, sessions[entry_i], record))
        return trial.free_from("no further rows", i)

    def take(part: str, c, entry_i: int) -> None:
        key = (part, c.sid, c.signal_date)
        k = int(np.argmin(places[part]))
        sec = secs.get(c.sid)
        if key in closed_of:
            outcome, exit_date = closed_of[key]
            free = trial.free_from(outcome, index[exit_date]) if exit_date in index else n
        elif sec is None or not sec.present[entry_i]:
            free = no_answer(part, c, entry_i)
        else:
            t = (e2_position(sec, entry_i, n) if part == "E2" else v2_position(sec, entry_i, exit_session(entry_i - 1), n))
            if t["outcome"] in forward3.CLOSED:
                record = {**t, "entry_date": sessions[entry_i], "entry_price": t["entry_raw"],
                          "exit_date": sessions[t["exit_i"]], "exit_price": t["exit_raw"]}
                ledger.add_trade(part, c.sid, date.fromisoformat(c.signal_date), c.tier, record, now)
                events["closed"].append((part, c.sid, sessions[entry_i], record))
                free = trial.free_from(t["outcome"], t["exit_i"])
            else:
                if n - 1 - int(sec.last_row[n - 1]) > HOLD_BACK:  # Yahoo still has its old rows, but they have stopped
                    events["no prices"].append((part, c.sid, ledger.last_mark(part, c.sid, sessions[entry_i])))
                else:
                    events["open"].append((part, c.sid, sessions[entry_i], t))
                free = n
        places[part][k] = max(places[part][k], free)
        held[c.sid] = free

    for entry_i in sorted(sig["entry_i"].unique()):
        if entry_i >= n:
            events["waiting"] += [(r.part, r.sid, r.signal_date) for r in sig[sig["entry_i"] == entry_i].itertuples(index=False)]
            continue
        entry = sessions[entry_i]
        group = sig[sig["entry_i"] == entry_i]
        # E2 first: strongest abnormal reaction first, ties by symbol.
        for c in group[group["part"] == "E2"].sort_values(["strength", "sid"], ascending=[False, True]).itertuples(index=False):
            key = ("E2", c.sid, c.signal_date)
            status = status_of.get(key)
            if status is None:
                sec = secs.get(c.sid)
                if held.get(c.sid, -1) > entry_i:
                    status = "already held"
                elif sec is None or not round8.enterable(sec, entry_i):
                    status = "not bought"
                elif min(places["E2"]) > entry_i:
                    status = "no free place"
                elif blocked("E2", entry):
                    status = "brake"
                else:
                    status = "bought"
                ledger.add_decision("E2", c.sid, date.fromisoformat(c.signal_date), entry, status, now)
                events["entries"].append(("E2", c.sid, entry, status))
            if status == "bought":
                take("E2", c, entry_i)
        # V2: down the month's ranked list until its places are used; a pick that can't be bought keeps its place in cash.
        used = 0
        for c in group[group["part"] == "V2"].sort_values("rank").itertuples(index=False):
            key = ("V2", c.sid, c.signal_date)
            status = status_of.get(key)
            if status is None:
                if used >= trial.PLACES["V2"]:
                    break
                sec = secs.get(c.sid)
                if held.get(c.sid, -1) > entry_i:
                    status = "already held"
                elif min(places["V2"]) > entry_i:
                    status = "no free place"
                elif blocked("V2", entry):
                    status = "brake"
                elif sec is None or not round8.enterable(sec, entry_i):
                    status = "not bought"
                else:
                    status = "bought"
                ledger.add_decision("V2", c.sid, date.fromisoformat(c.signal_date), entry, status, now)
                events["entries"].append(("V2", c.sid, entry, status))
            if status in ("no free place", "brake"):
                break  # the month's later picks are not candidates
            if status in ("bought", "not bought"):
                used += 1
                if status == "bought":
                    take("V2", c, entry_i)
                else:  # "Not bought": the place stays in cash until the month's exit
                    k = int(np.argmin(places["V2"]))
                    places["V2"][k] = max(places["V2"][k], exit_session(entry_i - 1))
    blocked_now = trial.brake_states(ledger.table("trades"))
    for scope, (kind, when, reason) in blocked_now.items():
        if scope not in brakes_seen:
            ledger.add_brake(scope, kind, date.fromisoformat(when), reason, now)
            events["brakes"].append((scope, kind, when, reason))
    return events


def next_open(ledger, sessions: list[date], secs: dict, e2: pd.DataFrame, v2: dict[int, pd.DataFrame], next_session: date,
              now: datetime, calendar: MarketCalendar) -> dict:
    """What the trial will do at the open of `next_session`, planned from the ledger as recorded: as trial.next_open, it
    runs the update on a stand-in session and records nothing."""
    view = trial._ReadOnly(ledger)
    update(view, [*sessions, next_session], trial._NextSession(secs), e2, v2, now, calendar)
    day = next_session.isoformat()
    signals = view.table("signals")
    strength = {(p, s, d): v for p, s, d, v in zip(signals["part"], signals["sid"], signals["signal_date"], signals["strength"])}
    decisions, trades = view.table("decisions"), view.table("trades")
    entries = [{"part": row.part, "sid": row.sid, "strength": strength[(row.part, row.sid, row.signal_date)],
                "close": float(secs[row.sid].raw_close[secs[row.sid].last_row[-1]])}
               for row in decisions[decisions["entry_date"] == day].itertuples(index=False) if row.status == "bought"]
    exits = [{"part": t.part, "sid": t.sid, "signal_date": t.signal_date}  # one with no row at its open is told once
             for t in trades[trades["exit_date"] == day].itertuples(index=False)
             if not ledger.sent(f"sell told {t.part} {t.sid} {t.signal_date}")]
    return {"entries": entries, "exits": exits}


# ------------------------------------------------------------------------------------------------- reports
def account(trades: pd.DataFrame, events: dict | None = None) -> dict:
    closed_r = float(trades["r"].sum()) if len(trades) else 0.0
    open_r = sum(t["mark"] / trial.STOPS[p] for p, _, _, t in (events or {}).get("open", []) if "mark" in t)
    open_r += sum(last["mark"] / trial.STOPS[p] for p, _, last in (events or {}).get("no prices", []) if last)
    return {"closed_r": closed_r, "open_r": open_r, "equity": CAPITAL * (1 + RISK * (closed_r + open_r))}


def messages(events: dict, trades: pd.DataFrame, latest: date) -> list[tuple[str, str]]:
    """Signals, paper entries, closed positions, brakes and each month's summary, in paper trial 1's words."""
    out = []
    e2_now = sorted(((sid, strength) for part, sid, signal, strength, late in events["signals"]
                     if part == "E2" and not late and signal == latest), key=lambda found: -found[1])
    if e2_now:
        names = ", ".join(f"{html.escape(sid)} ({trial._pct(strength)})" for sid, strength in e2_now)
        out.append((f"signal E2 {latest} {names}", f"{TAG} E2 signals at the {latest:%d %b %Y} US close: {names} (results reaction "
                    "vs the market). Bought in paper at the next US open if a place is free. Research, not a trading signal."))
    for part, sid, signal, _, late in events["signals"]:
        if part == "V2" and not late and signal == latest:
            out.append((f"signal V2 {latest}", f"{TAG} V2 signal at the {latest:%d %b %Y} US close: {html.escape(sid)} (this month's "
                        "top picks). Bought in paper at the next US open if a place is free. Research, not a trading signal."))
    prices = {(p, s, e): t for p, s, e, t in [*events.get("open", []), *events["closed"]]}
    by_entry: dict = {}
    for part, sid, entry, status in events["entries"]:
        row = f"{part} {html.escape(sid)}: {status}"
        t = prices.get((part, sid, entry), {})
        if status == "bought" and "entry_raw" in t:
            row += f" at {money(t['entry_raw'], '$')}" + (f", stop {money(t['stop_raw'], '$')}" if "stop_raw" in t else "")
        by_entry.setdefault(entry, []).append(row)
    for entry, rows in by_entry.items():
        out.append((f"entries {entry} {'|'.join(rows)}", f"{TAG} Paper entries at the {entry:%d %b %Y} US open: " + "; ".join(rows) + "."))
    for part, sid, entry, record in events["closed"]:
        out.append((f"closed {part} {sid} {entry}", f"{TAG} Closed {part} {html.escape(sid)} (bought {entry:%d %b %Y}): "
                    f"{trial._pct(record['net'])} after costs ({CLOSED_HOW[record['outcome']]}, {record['exit_date']:%d %b %Y})."))
    for scope, kind, when, reason in events["brakes"]:
        what = "stops buying" if scope == "account" else f"stops buying {scope} picks"
        out.append((f"brake {scope}", f"{TAG} The US paper trial {what} now, for good: too many losses. SELLs still come. This is only "
                    "the paper trial, nothing to do with your Indian account."))
    for part, sid, last in events["no prices"]:
        out.append((f"no prices {part} {sid} {last['session'] if last else 'never'}", f"{TAG} Yahoo has stopped giving prices for "
                    f"{html.escape(sid)} (renamed or bought out?). Its paper position ({part}) stays open and keeps its place for now. If "
                    "you copied it, check it in Kite yourself: no SELL comes from here unless the prices return."))
    if len(trades) and latest.day <= 7:
        month = latest.replace(day=1) - pd.Timedelta(days=1)
        done = trades[[d[:7] == f"{month:%Y-%m}" for d in trades["exit_date"]]]
        if len(done):
            out.append((f"month {month:%Y-%m}", f"{TAG} {month:%B %Y}: {len(done)} closed trade(s); the account "
                        f"{trial._pct(RISK * trades['r'].sum())} since the start on closed trades."))
    return out


def out_of_step(ledger, events: dict) -> list[tuple[str, str]]:
    """When the paper account and what the lists said differ, so that anyone copying isn't left guessing."""
    out = []
    for part, sid, entry, status in events["entries"]:
        told, name = ledger.sent(f"buy told {part} {sid} {entry}"), html.escape(sid)
        if told and status != "bought":
            out.append((f"out of step {part} {sid} {entry}", f"{TAG} The list said BUY {name} for the {entry:%d %b} open, but the "
                        f"paper account didn't buy it ({NOT_BOUGHT_WHY[status]}). If you bought it, the bot won't follow it and no "
                        "SELL will come for it: decide yourself."))
        elif status == "bought" and not told:
            out.append((f"out of step {part} {sid} {entry}", f"{TAG} The paper account bought {name} at the {entry:%d %b} open, but "
                        "no list told you in time. Don't buy it now. If you don't hold it, ignore its SELL later."))
    return out


def summary_message(events: dict, trades: pd.DataFrame, latest: date, market_close: float) -> tuple[str, str]:
    """One message for each new US session, so a quiet day still shows the trial ran."""
    equity = account(trades, events)["equity"]
    holding = [*(f"{html.escape(sid)} {trial._pct(t['mark'])}" for _, sid, _, t in events["open"] if "mark" in t),
               *(f"{html.escape(sid)} (no price)" for _, sid, _ in events.get("no prices", []))]
    return (f"summary {latest}", "\n".join([
        TAG_OPEN.format(title=f"DAILY SUMMARY {latest:%d %b %Y}"), "",
        f"Account: {money(equity, '$')} ({trial._pct(equity / CAPITAL - 1, 2)} since the start)",
        f"Holding: {', '.join(holding) or 'none'}", f"Market check: {MARKET} closed at {money(market_close, '$')}"]))


def _in_kite(sid: str, names: dict[str, str]) -> str:
    """As the exchange spells it (Yahoo's BRK-B is BRK.B), with the company's name: CCL, HAL and IEX are Indian stocks' symbols too."""
    return f"{sid.replace('-', '.')} ({names[sid]})" if names.get(sid) else sid.replace("-", ".")


def tonight(plan: dict, told: pd.DataFrame, calendar: MarketCalendar, next_session: date, now: datetime,
            names: dict[str, str] | None = None) -> str:
    """What the rules buy and sell at the next US open, in plain words, with what copying it by hand takes. A stock they sell
    and buy again at one open gets one line. Once the open has passed it no longer says to buy."""
    names = names or {}
    opens = calendar.session(next_session)[0].astimezone(IST)
    day, when = f"{opens:%a} {opens.day} {opens:%b}", f"{opens:%I:%M %p}".lstrip("0").lower()
    late = now.astimezone(IST) >= opens
    title = f"Tonight's US open was at {when} India time, {day}" if late else f"Tonight's US open, {day}, {when} India time"
    if not plan["entries"] and not plan["exits"] and told.empty:
        return TAG_OPEN.format(title=title) + "\n\nNothing to buy or sell."
    keep = {e["sid"] for e in plan["entries"]} & ({x["sid"] for x in plan["exits"]} | set(told["sid"]))
    sells = [(x["sid"], "its time is up") for x in plan["exits"]]
    for t in told.itertuples(index=False):
        end = f"{date.fromisoformat(t.exit_date):%d %b}"
        sells.append((t.sid, f"it hit its stop-loss on {end}" if t.outcome == "stop"
                      else f"its time was up on {end}, and that evening's list didn't reach you"))
    sells = [(sid, why) for sid, why in sells if sid not in keep]
    lines = [f"SELL {_in_kite(sid, names)}: all the shares you hold from these lists ({why}). None from these lists? Do nothing."
             for sid, why in sells]
    if lines:
        lines.append("")
    too_late = []
    for e in plan["entries"]:
        name, value, stop = _in_kite(e["sid"], names), VALUE[e["part"]], trial.STOPS[e["part"]]
        size = f"with about {money(value, '$')} (about {value / e['close']:.2f} shares at the last close, {money(e['close'], '$')})"
        below = f"below tonight's open, about {money(e['close'] * (1 - stop), '$')}"
        if e["sid"] in keep:
            lines.append(f"KEEP {name}: the rules buy it again at this open, so if you still hold it, do nothing.")
            lines += [] if late else [f"Don't hold it? Buy {size}"]
            lines += [f"Stop-loss from now: {stop:.0%} {below}", ""]
        elif late:
            too_late.append(name)
        else:
            why = (f"after its results filing it beat the market by {trial._pct(e['strength'])}" if e["part"] == "E2"
                   else "one of this month's top picks")
            lines += [f"BUY {name} {size}", f"Why: {why}", f"Stop-loss: {stop:.0%} {below}", ""]
    if too_late:
        lines += [f"Too late to copy: {', '.join(too_late)}. The paper account bought at the open, and the price has moved. "
                  "Skip it, or decide yourself.", ""]
    lines.append("Pretend money: the bot buys and sells nothing, and these rules were never tested on US stocks. Copying is your "
                 "choice.")
    if plan["entries"] and not late:
        lines += ["The amounts are for a pretend $10,000 account: all 5 places take about $2,000. Use less if you like.",
                  f"To buy, only before {when} tonight (after that, skip it): Kite > Marketwatch search > International > the stock > "
                  "Buy > Market, by amount."]
    if sells:
        lines.append("To sell: Kite > Marketwatch search > International > the stock > Sell > Market, by quantity: the shares you "
                     "hold from these lists.")
    lines.append("Kite has no stop-loss for US stocks yet. I look once a day after the US close. A stop that was hit comes here as "
                 "a SELL for the next open, when the price can be well below it (once 26% below the buy price, not 15%).")
    return TAG_OPEN.format(title=title) + "\n\n" + html.escape("\n".join(lines), quote=False)


def sells_to_tell(ledger, trades: pd.DataFrame) -> pd.DataFrame:
    """Closed positions with no list yet told to sell: stops, and time exits whose own evening's list didn't get through. A
    stock with no further rows can't be sold: its "Closed" message says so."""
    if trades.empty:
        return trades
    return trades[[o != "no further rows" and not ledger.sent(f"sell told {p} {s} {d}")
                   for o, p, s, d in zip(trades["outcome"], trades["part"], trades["sid"], trades["signal_date"])]]


def write_status(ledger, events: dict | None, now: datetime) -> str:
    trades, brakes = ledger.table("trades"), ledger.table("brakes")
    acct = account(trades, events)
    lines = ["# US paper trial 1: status (E2 x3 + V2 x2 on S&P 500 stocks)", "",
             f"Updated {now.astimezone(IST):%Y-%m-%d %H:%M} IST by `python -m trader.research.ustrial`, as defined in "
             "docs/research/ustrial1-definition.md. Paper only and not evidence: these rules were never tested on US stocks, "
             "nothing here is a trade or can place one, and no strategy's status changes because of it.", "",
             f"Account: {money(acct['equity'], '$')} (closed trades {acct['closed_r']:+.2f}R, open positions "
             f"{acct['open_r']:+.2f}R; 0.5% of $10,000 at risk per position).", ""]
    if len(brakes):
        lines += ["Brakes: " + "; ".join(f"{b.scope} {b.kind} from after {b.effective_date} ({b.reason})"
                                         for b in brakes.itertuples(index=False)), ""]
    missing = (events or {}).get("no prices", [])
    if events and (events["open"] or missing):
        lines += ["Open positions:", "", "| Part | Stock | Entered | Mark | Stop |", "|---|---|---|---:|---:|"]
        lines += [f"| {p} | {sid} | {entry} | {trial._pct(t['mark'])} | {t['stop_raw']:.2f} |"
                  for p, sid, entry, t in events["open"] if "mark" in t]
        lines += [f"| {p} | {sid} | - | no price since {last['session'] if last else 'it was bought'} | - |" for p, sid, last in missing]
        lines.append("")
    lines += ["| Part | Closed trades | Win rate | Net per trade | R |", "|---|---:|---:|---:|---:|"]
    for part in trial.PLACES:
        own = trades[trades["part"] == part]
        lines.append(f"| {part} | {len(own)} | {(100 * (own['net'] > 0).mean()):.1f}% | {trial._pct(own['net'].mean(), 2)} | "
                     f"{own['r'].sum():+.2f} |" if len(own) else f"| {part} | 0 | - | - | - |")
    if len(trades):
        lines += ["", "| Part | Stock | Entry | Exit | How | Net | R |", "|---|---|---|---|---|---:|---:|"]
        lines += [f"| {t.part} | {t.sid} | {t.entry_date} | {t.exit_date} | {t.outcome} | {trial._pct(t.net)} | {t.r:+.2f} |"
                  for t in trades.itertuples(index=False)]
    text = "\n".join(lines) + "\n"
    STATUS.parent.mkdir(parents=True, exist_ok=True)
    STATUS.write_text(text, encoding="utf-8")
    return text


# ---------------------------------------------------------------------------------------------------- main
def inputs(ledger: Ledger, now: datetime, calendar: MarketCalendar) -> tuple:
    """The sessions and stocks on Yahoo's latest prices, SPY's close, and E2's and V2's signals from the filings on record."""
    tickers = list(ledger.table("members")["ticker"].unique())
    sessions, secs, market_close = load_prices(tickers, now, calendar)
    check_answers(ledger, tickers, sessions, secs, now)
    table = round8.features(sessions, secs, forward2.month_ends_known(sessions, calendar))
    return (sessions, secs, market_close, e2_signals(ledger.table("filings"), sessions, secs, round10.Universe(table)),
            v2_lists(sessions, secs, table, calendar))


def evening_done(ledger: Ledger, calendar: MarketCalendar, now: datetime) -> bool:
    """Has a good run tonight covered the last session and settled tonight's list? Then a repeat of the task needn't ask the
    SEC or Yahoo. The first run of each evening always runs, so every evening is on record."""
    today = now.astimezone(IST).date()
    good = ledger.conn.execute("SELECT at FROM runs WHERE status = 'ok' ORDER BY id DESC LIMIT 1").fetchone()
    if good is None or datetime.fromisoformat(good[0]).astimezone(IST).date() != today:
        return False
    last, covered = calendar.last_completed_session(now - DAILY_SETTLE), ledger.last_answers()
    if covered is None or covered[0] != last:
        return False
    next_session = calendar.next_trading_day(last)
    return next_session != today or ledger.sent(f"plan {next_session}")


def send_notes(ledger: Ledger, notifier, now: datetime) -> None:
    """Every message not yet sent, oldest first. It stops at one Telegram doesn't take; the next run goes on from there."""
    for key, text in ledger.unsent():
        sent = notifier.send(text)
        ledger.add_notice(key, now, sent)
        if not sent:
            break


def send_list(ledger: Ledger, notifier, plan: dict, told: pd.DataFrame, calendar: MarketCalendar, next_session: date,
              now: datetime) -> None:
    """Tonight's list, and which BUYs and SELLs it told. A list that comes after the open tells no BUY."""
    members = ledger.table("members")
    sent = notifier.send(tonight(plan, told, calendar, next_session, now, dict(zip(members["ticker"], members["name"]))))
    ledger.add_notice(f"plan {next_session}", now, sent)
    if not sent:
        return
    keys = [f"sell told {x['part']} {x['sid']} {x['signal_date']}" for x in plan["exits"]]
    keys += [f"sell told {t.part} {t.sid} {t.signal_date}" for t in told.itertuples(index=False)]
    if now < calendar.session(next_session)[0]:
        keys += [f"buy told {e['part']} {e['sid']} {next_session}" for e in plan["entries"]]
    for key in dict.fromkeys(keys):
        if not ledger.sent(key):
            ledger.add_notice(key, now, True)


def tell_list_at_risk(ledger: Ledger, notifier, calendar: MarketCalendar, exc: Exception, now: datetime) -> None:
    """A run failed close to the open: say so now, once an evening, rather than in the 21:00 check, after the open."""
    today = now.astimezone(IST).date()
    session = calendar.session(today)
    key = f"no list {today}"
    if session is None or now < session[0] - LIST_AT_RISK or ledger.sent(f"plan {today}") or ledger.sent(key):
        return
    reason = str(exc)[:300] if isinstance(exc, Refused) else "the prices or filings couldn't be read yet"
    ledger.add_notice(key, now, notifier.send(
        f"{TAG} Tonight's US list isn't ready: {html.escape(reason, quote=False)}. "
        + ("If none comes before the open, there is nothing to copy tonight" if now < session[0] else "There is nothing to copy tonight")
        + ", and any SELL comes in the next list."))


def record_failure(ledger: Ledger | None, notifier, calendar: MarketCalendar | None, exc: Exception, now: datetime) -> None:
    """A failed run on record and, near the open, on Telegram. If even that fails, the health check sees no good run."""
    try:
        if ledger is not None:
            ledger.add_run(now, "failed", f"{type(exc).__name__}: {exc}")
            if notifier is not None and calendar is not None:
                tell_list_at_risk(ledger, notifier, calendar, exc, now)
    except Exception:
        log.exception("US paper trial: the failure couldn't be recorded")


def daily(now: datetime | None = None, notify: bool = True) -> int:
    from trader.notify.telegram import notifier_from_settings
    now = now or datetime.now(IST)
    started = time.monotonic()
    ledger = notifier = calendar = None
    try:
        ledger = Ledger()
        calendar = load_calendars()["NYSE"]
        notifier = notifier_from_settings(load_settings()) if notify else None
        if evening_done(ledger, calendar, now):
            if notifier is not None:
                send_notes(ledger, notifier, now)
            return 0
        members, list_read = refresh_members(ledger, now)
        got = fetch_filings(ledger, members, now)
        sessions, secs, market_close, e2, v2 = inputs(ledger, now, calendar)
        with ledger.transaction():  # the records and their messages together: no message is lost to a failure after this
            events = update(ledger, sessions, secs, e2, v2, now, calendar)
            trades = ledger.table("trades")
            ledger.add_outbox([*messages(events, trades, sessions[-1]), *out_of_step(ledger, events),
                               summary_message(events, trades, sessions[-1], market_close)], now)
            ledger.add_marks(events["open"], sessions, secs, now)
            ledger.add_answers(sessions[-1], {sid for sid, sec in secs.items() if sec.present[-1]}, now)
        if notifier is not None:
            send_notes(ledger, notifier, now)
            next_session = calendar.next_trading_day(sessions[-1])
            if next_session == now.astimezone(IST).date() and not ledger.sent(f"plan {next_session}"):  # not two days early
                plan = next_open(ledger, sessions, secs, e2, v2, next_session, now, calendar)
                send_list(ledger, notifier, plan, sells_to_tell(ledger, trades), calendar, next_session,  # as of now, not the start
                          now + timedelta(seconds=time.monotonic() - started))
        acct, waiting = account(trades, events), len(ledger.unsent())
        detail = (f"data to {sessions[-1]}; {len(secs)} stocks, {got['new']} new filings"
                  + (f" ({len(got['failed'])} companies unread)" if got["failed"] else "") + ("" if list_read else ", list unread")
                  + f"; signals {len(events['signals'])}, entries {len(events['entries'])}, closed {len(events['closed'])}, "
                  f"open {len(events['open'])}, brakes {len(events['brakes'])}; account {money(acct['equity'], '$')}"
                  + (f"; {waiting} messages waiting" if waiting else ""))
        ledger.add_run(now, "ok", detail)
        log.info("US paper trial: %s", detail)
        try:
            write_status(ledger, events, now)
        except OSError as exc:  # a convenience: a file locked by OneDrive mustn't cost anything else
            log.warning("US paper trial: the status page wasn't written: %s", exc)
        return 0
    except Exception as exc:  # whatever the cause, it must be on record: the health check and the next try rely on it
        log.exception("US paper trial failed: %s: %s", type(exc).__name__, exc)
        record_failure(ledger, notifier, calendar, exc, now)
        return 1
    finally:
        if ledger is not None:
            ledger.close()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="US paper trial 1: paper trial 1's rules on S&P 500 stocks (research only).")
    parser.add_argument("command", choices=["daily", "status"])
    parser.add_argument("--no-notify", action="store_true", help="daily: don't send Telegram messages")
    args = parser.parse_args(argv)
    make_console_utf8()
    settings = load_settings()
    configure_logging(secrets=settings.secret_values(), filename="ustrial1.log")
    check_definition()
    if args.command == "daily":
        raise SystemExit(daily(notify=not args.no_notify))
    ledger = Ledger()
    try:
        now = datetime.now(IST)
        calendar = load_calendars()["NYSE"]
        sessions, secs, _, e2, v2 = inputs(ledger, now, calendar)
        view = trial._ReadOnly(ledger)
        print(write_status(view, update(view, sessions, secs, e2, v2, now, calendar), now))
    finally:
        ledger.close()


if __name__ == "__main__":
    main()
