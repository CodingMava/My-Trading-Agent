# My Trading Agent

A research-first trading assistant for Indian equities (NSE). It scans stocks and can send Telegram
alerts, but it **never places orders**. US stocks are researched with the same tools and traded manually.

> **Current mode: NO TRADE.** An audit on 2026-10-08 found that none of the original eight strategies
> makes money after costs, so all of them are switched off in `config/strategies.toml`. The scanner
> still runs and logs every blocked signal, but it sends nothing until a strategy passes the
> profitability gate.

## Audit results (2026-10-08)

Each rule was replayed with the project's own indicator code, its 1% stop / 2% target, and realistic
Zerodha intraday costs (0.14% round trip), on 56 sessions of 5-minute bars for 21 NSE stocks. Entries
fill at the next bar's open.

| Rule | Trades | Winners | Net per trade | Status |
|---|---:|---:|---:|---|
| Volume Breakout | 604 | 40.6% | -0.10% | DISABLED |
| Oversold Reversal | 152 | 34.2% | -0.20% | REJECTED |
| Overbought Breakdown | 0 | - | never fires | REJECTED |
| Turtle Trend Breakout | 454 | 35.9% | -0.18% | REJECTED |
| Tudor Jones Macro Filter | 661 | 36.8% | -0.19% | REJECTED |
| Minervini Momentum Stacking | 356 | 40.2% | -0.12% | REJECTED |
| Stat-Arb Mean Reversion | 374 | 35.6% | -0.19% | DISABLED |
| Crabel Intraday Expansion | 1,234 | 39.0% | -0.15% | REJECTED |
| Crabel Intraday Breakdown | 1,274 | 43.0% | -0.11% | REJECTED |
| **All rules, as deployed** | **1,620** | **38.3%** | **-0.17%** | |

The same rules also lost money on 20 US large caps and on about 2.8 years of hourly NSE data, in every
market regime tested. None beat randomly timed entries with the same exits. To reproduce the numbers,
see [Research](#research).

## Swing research (Phase 3, 2026-10-09)

Three swing hypotheses were [pre-registered](docs/research/phase3-preregistration.md) before any test,
then judged on daily data, 2022 to Oct 2026, net of Zerodha costs ([results](docs/research/phase3-results.md)):

| Hypothesis | Trades | Winners | Net per trade | Why it failed | Status |
|---|---:|---:|---:|---|---|
| H1: oversold pullback in an uptrend, NIFTY 50 stocks | 1,771 | 60.2% | -0.05% | Losses 1.6x the size of wins; the small edge before costs is smaller than the 0.30% delivery cost | REJECTED |
| H2: the same on the NIFTY 50 index via an ETF | 46 | 63.0% | +0.12% | Too few trades, not significant, lost money in 2016-2021 | REJECTED |
| H3: 12-1 month momentum, top 5 NIFTY 50 stocks | 280 | 55.7% | +1.18% | Random picks from the same list did nearly as well: the profit is market drift and survivorship bias | REJECTED |

Lessons: a high win rate means nothing without the size of wins and losses (H1); Indian delivery
costs (0.1% STT on each side) swamp short-horizon edges in single stocks, while equity ETFs pay
almost no STT; and any long-only test on today's index members needs a random-pick baseline (H3).

## Project layout

| Path | What it is |
|---|---|
| `signal_engine.py` | Live scanner (5-minute NSE bars). Only registry-approved strategies can emit signals. |
| `data_engine.py`, `ta_engine.py`, `universe.py` | Yahoo Finance fetcher, indicators, stock list |
| `alert_engine.py`, `ai_engine.py` | Telegram alerts; optional Gemini commentary (off by default) |
| `dashboard.py` | Streamlit dashboard |
| `config/settings.toml` | Non-secret settings (data source, Telegram, AI) |
| `config/strategies.toml` | Strategy registry: each strategy's status |
| `config/gate.toml` | The profitability gate: the evidence each status requires |
| `config/risk.toml`, `config/sectors.toml` | Hard risk limits; each stock's sector |
| `config/market_calendars.toml` | NSE and NYSE holidays and session hours (update every December) |
| `config/universes.toml` | The stock lists strategies trade (NIFTY 50, the NIFTY ETF) |
| `trader/` | Config, logging and registry code |
| `trader/markets/` | Exchange calendars |
| `trader/core/` | Shared domain objects (trade intents, positions, portfolio state) |
| `trader/risk/`, `trader/portfolio/` | Risk engine, kill switch, position sizing, sector and correlation exposure |
| `trader/data/` | Data providers (Yahoo, Zerodha Kite) and the checks every bar must pass |
| `trader/features/` | Tested, look-ahead-free indicators (SMA, Wilder RSI, ATR) |
| `trader/strategies/` | Strategy rules (the Phase 3 swing hypotheses) and the catalog the paper trader runs |
| `trader/execution/` | End-of-day paper trading and its SQLite store; paper evidence for the gate |
| `trader/notify/` | Telegram message formats and a sender that retries and never logs the token |
| `trader/research/` | Backtesting harness: simulator, costs, metrics, validation, audit and Phase 3 runners |
| `docs/research/` | Pre-registrations, evidence reports, and machine-readable verdicts (`evidence/`) |
| `tests/` | Test suite (`pytest`) |
| `data/` | Frozen market data for research (git-ignored) |

## Setup (Windows)

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements-dev.txt
copy .env.example .env
```

Then fill in your credentials in `.env`. It is git-ignored; never commit it.

## Usage

```bash
python signal_engine.py          # scan every 5 minutes during NSE hours (09:15-15:30 IST)
python signal_engine.py --once   # one scan now, then exit
python alert_engine.py           # send a Telegram test message
streamlit run dashboard.py       # dashboard
```

Logs go to the console and to `logs/trader.log` (UTF-8, rotated, secrets masked).

## Market data

Before any rule sees a bar, the scanner drops the candle that is still forming and checks the rest:
fresh enough (`[data] max_delay_minutes`), no duplicates or broken prices, no implausible jump on the
latest bar. Anything that fails is skipped and logged, which ends in NO TRADE for that stock.

The default source is Yahoo Finance, which is free but unofficial. To use Zerodha Kite Connect instead:

1. Create a Kite Connect app at developers.kite.trade and note its API key and secret.
2. Add `KITE_API_KEY` and `KITE_API_SECRET` to `.env`, and set `provider = "kite"` under `[data]` in
   `config/settings.toml`.
3. Log in once per trading day (Kite sessions expire at 06:00 IST):

```bash
python -m trader.data.kite login
```

```bash
python -m trader.data.kite check RELIANCE.NS
```

The session token is stored in `.kite_session.json` (git-ignored) and is never printed or logged.

## Paper trading

Swing strategies are paper traded once a day, after the NSE close. No real order is ever placed.

```bash
python -m trader.execution.eod                       # process every completed session not yet done
python -m trader.execution.eod --start 2026-10-01    # first run only: replay from this session
python -m trader.execution.report                    # score each strategy's paper trades against the gate
```

Each run uses the same fill rules as the backtester: orders decided at a close fill at the next open,
stops are checked against the day's range (a gap through the stop fills at the open), time exits happen
at the close, and costs come from the same Zerodha cost model. Every trade passes the risk engine, and
the kill switch blocks new entries but never stops an open position from exiting. Each session is one
database transaction in `state/paper.db` (git-ignored), so a crash or a second run can't duplicate
anything, and a missed day is caught up on the next run.

Telegram gets `[PAPER]` BUY SIGNAL, BUY EXECUTED, SELL EXECUTED and RISK ALERT messages and a daily
summary; with no approved strategy the summary says NO TRADE. A message that can't be sent is retried on
the next run. A strategy whose paper results drift from its research (`[decay]` in `config/gate.toml`) is
suspended automatically.

Only strategies whose status `PAPER` is backed by research evidence are traded. **Today there are none**
(all three swing hypotheses were rejected), so every run records NO TRADE. To run it daily, add a Windows
Task Scheduler task for weekdays at 18:00 IST that runs `venv\Scripts\python.exe -m trader.execution.eod`
with "Start in" set to this folder.

## Market calendars

`config/market_calendars.toml` holds each exchange's holidays and hours, taken from the official lists.
**Update it every December** when NSE publishes the next year's holidays: for any year that isn't
listed, the scanner can't tell whether the market is open, so it refuses to trade. It warns throughout
December if the next year is missing. Add NSE's Muhurat trading session there when it is announced.

## Research

Every strategy change must be measured with the harness in `trader/research/` before it can be
approved. Results are always net of costs, and each strategy is compared against random entries.

```bash
python -m trader.research.audit                                   # reproduce the audit (India 5-minute)
python -m trader.research.audit --dataset in_1h_730d --blocks --regimes
python -m trader.research.datasets fetch --name nse_daily_10y --interval 1d --period 10y --universe nifty
python -m trader.research.datasets validate data/nse_daily_10y    # data-quality report
python -m trader.research.phase3                                  # re-run the Phase 3 evaluation
pytest                                                            # fast tests
pytest -m slow                                                    # audit regression (needs data/audit_2026-10-08)
```

Swing trading (the next research focus) uses the same simulator with multi-day holding, per-signal
stops, and Zerodha delivery costs:

```python
from trader.research.costs import ZERODHA_DELIVERY
from trader.research.metrics import summarize
from trader.research.simulator import ExitRules, run_backtest

rules = ExitRules(max_hold_bars=10)  # time exit after 10 sessions
trades = run_backtest(daily_bars, signals, "long", rules, stops=atr_stops, targets=atr_targets, rule="my_idea")
summarize(trades, ZERODHA_DELIVERY.round_trip(100_000), session_dates)
```

## Safety rules

- Only strategies with status `LIVE_SMALL` or `LIVE` in `config/strategies.toml` can emit live
  signals. Unknown strategies are blocked (fail closed).
- A status must be earned, not typed: when the registry loads, `PAPER` needs passing research evidence
  in `docs/research/evidence/`, `LIVE_SMALL` also needs passing paper-trading evidence, and `LIVE` also
  needs small-capital live evidence, none older than a year (`config/gate.toml`). Anything else is
  lowered automatically and the scanner logs why.
- No decision on incomplete, stale or implausible data, and none on a day the calendar can't vouch for.
- Every trade passes the risk engine (`config/risk.toml`): it risks at most 0.5% of equity, stays within
  position, cash, liquidity, sector, gross-exposure and correlation limits, and is refused after a 2% daily
  loss. A 10% drawdown engages the kill switch, which only a person can release:

```bash
python -m trader.risk.killswitch status
```
- AI never creates, sizes or approves trades.
- Secrets live only in `.env`. A test fails the build if a credential appears in the repository.
- US trades are placed manually. Indian order placement (Zerodha Kite Connect) comes later, and only
  after backtest, walk-forward and paper-trading evidence.

## Roadmap

| Phase | Goal | Status |
|---|---|---|
| 0 | Containment: secrets out of code, all rules disabled, honest docs, pinned dependencies | Done |
| 1 | Data: market calendars, validation, Zerodha Kite data for NSE | Done (Kite awaiting a live check) |
| 2 | Backtesting reliability: the harness in `trader/research/` | Done |
| 3 | Evidence: pre-registered swing-trading hypotheses, tested on frozen data | Done: 0 of 3 passed |
| 4 | Profitability gate enforced from evidence reports | Done |
| 5-6 | Risk engine and portfolio limits | Done |
| 7 | Paper trading (end-of-day, for swing strategies) | Done: no strategy is eligible yet |
| 8 | Zerodha Kite order placement (India) | |
| 9-12 | AI research layer, full Telegram monitoring, production monitoring, small live trading | |

## Data

Market data from Yahoo Finance is for personal research only. It lives in `data/`, which is
git-ignored: don't commit or redistribute it.
