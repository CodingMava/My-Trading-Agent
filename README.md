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

## Project layout

| Path | What it is |
|---|---|
| `signal_engine.py` | Live scanner (5-minute NSE bars). Only registry-approved strategies can emit signals. |
| `data_engine.py`, `ta_engine.py`, `universe.py` | Yahoo Finance fetcher, indicators, stock list |
| `alert_engine.py`, `ai_engine.py` | Telegram alerts; optional Gemini commentary (off by default) |
| `dashboard.py` | Streamlit dashboard |
| `config/settings.toml` | Non-secret settings (Telegram, AI) |
| `config/strategies.toml` | Strategy registry: the profitability gate's source of truth |
| `trader/` | Config, logging and registry code |
| `trader/research/` | Backtesting harness: simulator, costs, metrics, validation, audit reproduction |
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

## Research

Every strategy change must be measured with the harness in `trader/research/` before it can be
approved. Results are always net of costs, and each strategy is compared against random entries.

```bash
python -m trader.research.audit                                   # reproduce the audit (India 5-minute)
python -m trader.research.audit --dataset in_1h_730d --blocks --regimes
python -m trader.research.datasets fetch --name nse_daily_10y --interval 1d --period 10y --universe nifty
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
- AI never creates, sizes or approves trades.
- Secrets live only in `.env`. A test fails the build if a credential appears in the repository.
- US trades are placed manually. Indian order placement (Zerodha Kite Connect) comes later, and only
  after backtest, walk-forward and paper-trading evidence.

## Roadmap

| Phase | Goal | Status |
|---|---|---|
| 0 | Containment: secrets out of code, all rules disabled, honest docs, pinned dependencies | Done |
| 1 | Data: market calendars, validation, Zerodha Kite data for NSE | Next |
| 2 | Backtesting reliability: the harness in `trader/research/` | Foundation done |
| 3 | Evidence: pre-registered swing-trading hypotheses, tested on frozen data | |
| 4 | Profitability gate enforced from evidence reports | |
| 5-6 | Risk engine and portfolio limits | |
| 7 | Paper trading | |
| 8 | Zerodha Kite order placement (India) | |
| 9-12 | AI research layer, full Telegram monitoring, production monitoring, small live trading | |

## Data

Market data from Yahoo Finance is for personal research only. It lives in `data/`, which is
git-ignored: don't commit or redistribute it.
