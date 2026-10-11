# My Trading Agent

A research-first trading system for Indian equities (NSE). Once a day it paper trades the strategies
that have earned it through the profitability gate and reports on Telegram; it **never places real
orders**. US stocks are researched with the same tools and traded manually.

> **Current mode: NO TRADE.** Nothing tested so far makes money after costs in a way that beats chance:
> not the original nine intraday rules (audit, 2026-10-08), and not the fourteen pre-registered swing
> hypotheses of five research rounds. The daily paper-trading run records NO TRADE until a strategy
> passes the profitability gate.

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

## Research round 2 (2026-10-09)

The H1 rules, unchanged, were [pre-registered](docs/research/round2-preregistration.md) on three markets
that no earlier test had touched and where trading is cheap, then judged on 2022 to Oct 2026
([results](docs/research/round2-results.md)):

| Hypothesis | Trades | Winners | Net per trade | Why it failed | Status |
|---|---:|---:|---:|---|---|
| H4: US large caps (82 S&P 100 stocks) | 2,607 | 62.0% | +0.16% | Random entry days in the same stocks made most of the profit; earnings gaps cost up to 3.4R | REJECTED |
| H5: Indian index ETFs (BANK, IT, PHARMA, NEXT 50) | 143 | 54.5% | -0.06% | The 2016-2021 edge (+0.31% per trade) vanished after 2021 | REJECTED |
| H6: US sector ETFs (the 11 SPDRs) | 431 | 65.2% | +0.24% | Consistently profitable, but not clearly better than random entry days (p = 0.07; 0.21 after correcting for three tests) | REJECTED |

This round added a stricter random baseline (trades entered on the same day in correlated instruments
count as one bet) and a cluster-robust t-statistic. H6 is the strongest lead so far, but it can only be
confirmed on data it hasn't seen, such as its signals recorded from now on, never by re-testing it here.

## Research round 3: confirming H6 (2026-10-09)

H6 was given one [pre-registered](docs/research/round3-preregistration.md) chance to confirm on data
nothing had examined, and had to pass both tests ([results](docs/research/round3-results.md)):

| Hypothesis | Trades | Winners | Net per trade | Result | Status |
|---|---:|---:|---:|---|---|
| H7: the 9 original US sector SPDRs, 2000-2015 | 1,085 | 71.1% | +0.32% | Beat random entry days (p = 0.012 after correction), but its average loss was 1.57x its average win (limit 1.5x) | REJECTED |
| H8: 15 iShares country ETFs, 2016-2026 | 1,154 | 61.6% | +0.07% | No better than random entry days (p = 0.19); 6 of 11 years positive | REJECTED |

H6 is not confirmed, so the pullback rules (H1, H2, H4-H8) are retired: as pre-registered, no variant of
them is tested again. The effect showed up strongly on US sector SPDRs before 2016 but did not carry over to other
ETFs in recent years. Eight hypotheses over three rounds, none passed: the system stays in NO TRADE.

## Research round 4: the turn of the month (2026-10-11)

A different kind of effect, with nothing to fit: holding the index over the turn of the month (the
month's last trading day and the next month's first three), documented for decades in many countries.
[Pre-registered](docs/research/round4-preregistration.md) and judged on each whole span
([results](docs/research/round4-results.md)):

| Hypothesis | Trades | Winners | Net per trade | Why it failed | Status |
|---|---:|---:|---:|---|---|
| H9: S&P 500 via SPY, 1993-2026 | 404 | 57.7% | +0.23% | Not clearly better than random 4-day holds (p = 0.067); 61% of years positive (needs 70%) | REJECTED |
| H10: NIFTY 50 via NIFTYBEES, 2008-2026 | 225 | 56.4% | +0.28% | Beat random 4-day holds (p = 0.033), but too few trades to be sure it is positive (t 1.65, needs 2.0); 61% of years positive; 2024-2026 slightly negative | REJECTED |

The effect points the right way in both markets and in both halves of each span, but not strongly or
steadily enough to trade. Ten hypotheses over four rounds, none passed.

## Research round 5: a batch of monthly effects (2026-10-11)

Four documented effects tested at once ([pre-registration](docs/research/round5-preregistration.md),
[results](docs/research/round5-results.md)), with a stability test fit for strategies that trade about
once a month (each third of the span must be profitable):

| Hypothesis | Trades | Winners | Net per trade | Result | Status |
|---|---:|---:|---:|---|---|
| H11: turn of the month, India's Bank, Next 50, IT and Pharma indices, 2008-2026 | 863 | 57.9% | +0.48% | Far better than random days (p < 0.001), but 2014-2020 was flat, and it lost money in each of 2024, 2025 and 2026 | REJECTED |
| H12: turn of the month, 15 country ETFs, 2001-2026 | 4,334 | 54.9% | +0.27% | Beat random days and was profitable in every country, but its profit factor was 1.27 (needs 1.3) | REJECTED |
| H13: momentum, top 3 US sector ETFs monthly | 960 | 59.0% | +0.86% | Three random sectors did nearly as well: market drift, not momentum | REJECTED |
| H14: momentum, top 3 country ETFs monthly | 924 | 57.8% | +0.80% | Three random countries did nearly as well | REJECTED |

The turn of the month is the strongest effect found so far: it beat random timing in every market
tested. But it isn't steady enough to trade, and in India it has lost money since the start of 2024.
Fourteen hypotheses over five rounds, none passed.

## Project layout

| Path | What it is |
|---|---|
| `dashboard.py` | Ops console (Streamlit, read-only): health, the paper account, decisions, strategies, runs |
| `scripts/register_tasks.ps1` | Creates the Windows scheduled tasks: the daily run, the health check, Telegram commands |
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
| `trader/ops/` | Health checks (alerts on failure and on silence) and the console's read-only views |
| `trader/notify/` | Telegram message formats, a sender that retries and never logs the token, and the commands |
| `trader/research/` | Backtesting harness: simulator, costs, metrics, validation; the research-round runners; the audit, with the original rules and indicator code kept so it can be reproduced |
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
python -m trader.execution.eod            # the daily run: paper trading after the NSE close
python -m trader.ops.health               # is it running, and is it safe? (exit code 1 if not)
streamlit run dashboard.py                # ops console, read-only
python -m trader.risk.killswitch status   # the kill switch
python -m trader.notify.telegram --test   # send a Telegram test message
```

Logs go to the console and to `logs/trader.log` and `logs/health.log` (UTF-8, rotated, secrets masked).
The original intraday scanner was retired on 2026-10-11, after every one of its rules was rejected; its
rules and indicator code live on in `trader/research/` so the audit can be reproduced.

## Market data

Before any rule sees a bar, the daily run drops the candle that is still forming, cleans the rest the
way research does (repeated timestamps, bars without prices, holiday placeholders) and checks it: no
broken prices, and no implausible jump on the latest bar, which blocks new entries but never a stop. An
instrument whose data fails is skipped and logged, which ends in NO TRADE for it; when a session's data
is broadly missing, the run stops and alerts.

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
(none of the fourteen swing hypotheses passed), so every run records NO TRADE. To run it every day, see
[Running unattended](#running-unattended).

## Running unattended

Three Windows scheduled tasks run the system. `scripts/register_tasks.ps1` creates them: review it, then
run it once with `powershell -ExecutionPolicy Bypass -File scripts\register_tasks.ps1`.

| Task | When | Runs |
|---|---|---|
| Daily run | 18:00 IST every day; if the PC was off then, as soon as it is back | `python -m trader.execution.eod` |
| Health check | 21:00 IST every day | `python -m trader.ops.health --notify` |
| Telegram commands | Always, from logon (no console window; restarted if it stops) | `python -m trader.notify.bot` |

From your Telegram chat with the bot: `/status` (health, mode, equity, positions), `/positions`,
`/trades` (the latest closed trades), and `/kill reason`, which stops all new trades at once while open
positions still exit as planned. Only your chat (`TELEGRAM_CHAT_ID`) is answered. No command can release
the kill switch, change a limit or place an order; releasing is only possible on the PC.

What sends you a Telegram alert:

- **The run fails** (a crash, a broken config, no Kite login): an alert straight away, with secrets masked.
  Every run is recorded, and a failure leaves no half-processed session behind.
- **Market data is missing**: when more than 20% of the instruments have no bar yet for a session, the
  run stops before that session instead of recording a day it couldn't see, and the next run retries it.
- **The run didn't happen**: the 21:00 health check alerts when the latest session isn't processed, the
  last run failed, halted or died, the kill switch is on, Telegram messages are stuck, or cash and
  holdings don't reconcile with the fills.
- **The PC is off**, so nothing on it can alert (optional): create a free check at healthchecks.io or a
  similar dead man's switch and put its ping URL in `.env` as `HEARTBEAT_URL`. Every clean run pings it,
  and the service alerts you when the pings stop.

The health check also counts clean sessions in a row since the last failure. The roadmap asks for 60
before broker integration (Phase 8).

After every run that didn't fail, the records are copied to `state/backups/paper-<date>.db` (inside
OneDrive here, so the copies leave the PC), and the record of what happened (fills, closed trades,
decisions, session snapshots) can't be edited or deleted: the database refuses. **What each alert means,
what to do about it, and the plan for losses decided in advance are in [docs/runbook.md](docs/runbook.md).**

## Market calendars

`config/market_calendars.toml` holds each exchange's holidays and hours, taken from the official lists.
**Update it every December** when NSE publishes the next year's holidays: for any year that isn't
listed, the daily run can't tell which days are sessions, so it stops and alerts rather than guess. The
health check warns throughout December if the next year is missing. Add NSE's Muhurat trading session there when it is announced.

## Research

Every strategy change must be measured with the harness in `trader/research/` before it can be
approved. Results are always net of costs, and each strategy is compared against random entries.

```bash
python -m trader.research.audit                                   # reproduce the audit (India 5-minute)
python -m trader.research.audit --dataset in_1h_730d --blocks --regimes
python -m trader.research.datasets fetch --name nse_daily_10y --interval 1d --period 10y --universe nifty50
python -m trader.research.datasets validate data/nse_daily_10y    # data-quality report
python -m trader.research.phase3                                  # re-run the Phase 3 evaluation
python -m trader.research.round2                                  # re-run research round 2
python -m trader.research.round3                                  # re-run research round 3
python -m trader.research.round4                                  # re-run research round 4
python -m trader.research.round5                                  # re-run research round 5
pytest                                                            # fast tests
pytest -m slow                                                    # research regressions (need the frozen data in data/)
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

- Only a strategy whose status in `config/strategies.toml` is `PAPER` is paper traded, and only
  `LIVE_SMALL` or `LIVE` could ever trade real money (Phase 11). A strategy missing from the registry is
  blocked (fail closed).
- A status must be earned, not typed: when the registry loads, `PAPER` needs passing research evidence
  in `docs/research/evidence/`, `LIVE_SMALL` also needs passing paper-trading evidence, and `LIVE` also
  needs small-capital live evidence, none older than a year (`config/gate.toml`). Anything else is
  lowered automatically and the daily run logs why. Paper-trading evidence (the audit's Level 5,
  `python -m trader.execution.report`) needs three months and 40+ trades in line with the research,
  60 unattended sessions in a row without a failed run, no duplicate order, records that reconcile, and
  your review of 20+ of the paper trades (`--reviewed N`).
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
| 3b | Research round 2: the same rules on US stocks, US sector ETFs and Indian index ETFs | Done: 0 of 3 passed |
| 3c | Research round 3: confirm or retire H6 on unseen data | Done: not confirmed; pullback rules retired |
| 3d | Research round 4: the turn-of-the-month effect, US and India | Done: 0 of 2 passed |
| 3e | Research round 5: four monthly effects at once | Done: 0 of 4 passed |
| 4 | Profitability gate enforced from evidence reports | Done |
| 5-6 | Risk engine and portfolio limits | Done |
| 7 | Paper trading (end-of-day, for swing strategies) | Done: no strategy is eligible yet. Its 60 unattended sessions start once the tasks are scheduled |
| 8 | Broker integration: Zerodha Kite orders, still on paper capital | Waits for those 60 sessions and a strategy that qualifies |
| 9 | AI research layer: news to structured tags, advisory only | Waits for a strategy it could measurably improve |
| 10 | Observability: run records, alerts on failure and on silence, health checks, ops console | Done |
| 11 | Controlled live trading | Needs paper-trading evidence first |

## Data

Market data from Yahoo Finance is for personal research only. It lives in `data/`, which is
git-ignored: don't commit or redistribute it.
