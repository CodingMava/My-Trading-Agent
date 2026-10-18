# My Trading Agent

A research-first trading system for Indian equities (NSE), with a US paper account alongside. Once a
day it paper trades the strategies that have earned it through the profitability gate and reports on
Telegram; it **never places real orders**. US stocks are researched with the same tools, and their
signals come to you to place by hand.

> **Current mode: NO TRADE.** Nothing tested so far makes money after costs in a way that beats chance:
> not the original nine intraday rules (audit, 2026-10-08), and not the thirty-one pre-registered
> hypotheses of ten research rounds (plus 28 variants screened on development years). The daily paper-trading
> run records NO TRADE until a strategy passes the profitability gate. The closest so far is round 10's E2, drift
> after a strong results reaction: profitable, 55% winners, steady years and a 17R drawdown, but its edge over
> random picks was not significant enough (p 0.03 against a bar of 0.00088)
> ([round 10](#research-round-10-results-drift-promoter-buying-and-the-two-combined-2026-10-17)). Mid-cap
> momentum (rounds 8 and 9) beat random picks but failed the win-rate, stability and drawdown rules.

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

## Research round 6: Ernest Chan's strategies (2026-10-12)

Six strategies from Ernest Chan's *Algorithmic Trading* (2013), judged with the method of Aronson's
*Evidence-Based Technical Analysis* on the years after the book appeared, data its rules were never
designed on ([pre-registration](docs/research/round6-preregistration.md),
[results](docs/research/round6-results.md)). The book's text wasn't available, so the rules are as
described by secondary sources: a test of those rules, not a verdict on the book. A new criterion
allows for the number of hypotheses now tested: the raw p-value against random entries must be below
0.05 / 20.

| Hypothesis | Trades | Winners | Net per trade | Result | Status |
|---|---:|---:|---:|---|---|
| C1: buy-on-gap, NIFTY 50 stocks, intraday | 111 | 54.1% | +0.15% | Weak (t 0.73); beat random days only before correcting for six tests; lost money in 2024 and 2025 | REJECTED |
| C2: buy-on-gap, 82 S&P 100 stocks, intraday | 355 | 51.0% | +0.01% | Flat, and no better than random days | REJECTED |
| C3: opening-gap momentum, NIFTY 50 index, intraday | 1,055 | 40.9% | -0.16% | Loses before costs too: NIFTY's gaps faded during the day | REJECTED |
| C4: opening-gap momentum, SPY, intraday | 1,066 | 47.9% | -0.06% | Loses before costs too | REJECTED |
| C5: time-series momentum, NIFTY 50 or cash, monthly | 127 | 55.1% | +0.50% | Its months did worse than random months; CAGR 5.2% against 10.9% bought and held | REJECTED |
| C6: time-series momentum, SPY or T-bills, monthly | 141 | 70.2% | +1.00% | Profitable (t 3.01) but no better than random months: market drift. CAGR 10.6% against 14.0% bought and held | REJECTED |

Twenty hypotheses over six rounds, none passed.

## Research round 7: intraday momentum on minute data (2026-10-13)

The first test on Kite's 1-minute bars ([pre-registration](docs/research/round7-preregistration.md),
pinned and pushed before any test code existed; [results](docs/research/round7-results.md), from one
run). Market intraday momentum (Gao, Han, Li and Zhou, 2018): the morning's direction, from the
previous 15:14 to 09:44, traded in NIFTYBEES from 14:45 to 15:14, at Zerodha's intraday costs (0.12% a
round trip with slippage).

| Hypothesis | Trades | Winners | Gross per trade | Net per trade | p vs random | Status |
|---|---:|---:|---:|---:|---:|---|
| I1: buy after a rising morning | 959 | 24.4% | +0.010% | -0.111% | 0.42 | REJECTED |
| I2: short after a falling morning | 714 | 23.5% | -0.008% | -0.128% | 0.56 | REJECTED |
| I3: either way after a big morning | 279 | 26.9% | -0.002% | -0.123% | 0.60 | REJECTED |

The morning's direction carried no information about the last half hour of continuous trading: before
costs, each window earned what the same window earned on random days, about zero. Costs then made every
variant lose. Twenty-three hypotheses over seven rounds, none passed.

## Research round 8: stock momentum on a survivorship-free NSE universe (2026-10-14)

New data first: NSE's own daily files (bhavcopies) for every security from 2005 to October 2026, delisted companies
included, adjusted for splits, bonuses, rights, special dividends and demergers from NSE's corporate-action records
(`python -m trader.research.nse_bhavcopy build`). At each month-end the eligible stocks were ranked by liquidity;
each hypothesis bought the 5 with the best 12-1 month return, at the next open, with a 10% stop, at Zerodha's delivery
costs and the risk engine's size, and was compared with 5 random stocks from the same tier
([pre-registration](docs/research/round8-preregistration.md), pinned before any test; a development stage on 2006-2013,
[stage 1](docs/research/round8-stage1.md), then one decision run on 2013-2026, [results](docs/research/round8-results.md)).

| Hypothesis | Trades | Winners | Net per trade | Random picks | p vs random | Result | Status |
|---|---:|---:|---:|---:|---:|---|---|
| N1: the 100 most liquid stocks | 795 | 48.6% | +0.41% | +0.52% | 0.64 | No better than random picks; lost money in the first half | REJECTED |
| N2: liquidity ranks 101-300 | 792 | 43.9% | +1.75% | +0.67% | 0.0019 | Beat random picks, but 44% winners (floor 50%), 64% of years profitable (70%), drawdown 34R (20R) | REJECTED |

Mid-cap momentum is the second effect, after the turn of the month in India's sector indices (H11), to beat random
entries at the project's multiple-testing bar (p below 0.05 / 25). It fails three rules where H11 failed one, and after
the fact its edge leans on a few very large winners and on the years since 2020. The 10% stop hurt: without it, the same picks won 51-54% of their trades and beat random picks
by more. Twenty-five hypotheses over eight rounds, none passed. What this suggests next, and what it would take, is in
[the research review](docs/research/round8-research-review.md).

## Research round 11: new return sources: value, dividend flows, option-implied information (2026-10-18)

To find parts that could complement E2 and V2 (both buy strength; both lost in 2016 and 2018), ten variants from three
families never tested here were screened on development years only (2006 or 2008 to May 2013), with total returns
(dividends added for the strategy and the random picks alike): dividend yield (Y1a-c), long-term reversal (R1a-b), the
dividend-month premium (DM1a-b), and option-implied signals from NSE's F&O files (O1-O3; data kept outside OneDrive, see
`trader/research/nse_fo.py`). Only O2 (stocks whose options are cheap relative to their realized volatility) beat
random picks, by +1.0% a trade (t 1.3). It was pre-registered unchanged ([pre-registration](docs/research/round11-preregistration.md),
pinned 18 Oct 2026 23:45 IST; the bar is now 0.05 / 67), reproduced in [stage 1](docs/research/round11-stage1.md), and
decided once ([results](docs/research/round11-results.md)):

| Hypothesis | Span | Trades | Winners | Net per trade | Random picks | p vs random | Status |
|---|---|---:|---:|---:|---:|---:|---|
| O2: options cheapest relative to realized volatility | 2013-2026 | 795 | 49.6% | +0.72% | +0.81% | 0.61 | REJECTED |

No edge on the decision years: the screening edge was the winner's curse (the best of ten). Dividend yield, the
dividend month and long-term reversal showed no edge even on the development years (long-term losers kept losing).
Thirty-two hypotheses decided and 38 variants screened; none passed.

## Research round 10: results drift, promoter buying, and the two combined (2026-10-17)

Two kinds of new data: NSE's board-meeting notices (2009-2026, with the time each was filed) and SEBI insider-trading
disclosures (from November 2015, with the time each was published). Following your suggestion of a mix of strategies
whose losses offset, 28 rule variants were first screened only on development years (2009 to May 2013 for
board-meeting rules; November 2015 to December 2017 for insider rules); every one is listed with its numbers in the
[pre-registration](docs/research/round10-preregistration.md), pinned 17 Oct 2026 17:45 IST, and counts toward the
multiple-testing bar (0.05 / 57). Two survived and were tested alone and combined: a development stage
([stage 1](docs/research/round10-stage1.md)), then one decision run on later years ([results](docs/research/round10-results.md)).

| Hypothesis | Span | Trades | Winners | Net per trade | Random picks | p vs random (raw / Holm) | Result | Status |
|---|---|---:|---:|---:|---:|---:|---|---|
| E2: drift after a top-10% results reaction, 300 most liquid stocks, 40 sessions, 15% stop, 5 positions | 2013-2026 | 313 | 55.0% | +2.33% | +0.83% | 0.030 / 0.089 | Passed 11 of 13 criteria (profit factor 1.47, 71% of years profitable, drawdown 17.3R); failed only the two tests of beating random picks | REJECTED |
| Q: promoter open-market purchases of Rs 10 lakh or more | 2018-2026 | 230 | 50.0% | +1.33% | +0.89% | 0.31 / 0.36 | No edge over random picks in the decision years | REJECTED |
| M: E2 and Q sharing the 5 positions | 2018-2026 | 288 | 53.8% | +1.88% | +1.15% | 0.18 / 0.36 | Passed 10 of 13; Q diluted E2 | REJECTED |

E2 is the closest the project has come: a profitable rule with the payoff and stability the rules ask for, ahead of
random picks from the same stocks by about 1.5% a trade (1.8% with every event taken, 1,597 trades), but not by enough
to rule out luck at the bar this many tests require. The mix did not help, because promoter buying, which looked
promising on 2016-2017, had no edge in 2018-2026. What did not survive screening: holding through the results day (the
rise comes before it), bonus, split and buyback meetings (too few), the high-volume premium (high-volume stocks did
worse than random in India), same-month seasonality, and promoter pledge releases. NSE's insider-trading API returns
nothing published after 2 May 2026, so any insider-based rule would need another source.

**Forward test 3** (your decision, 17 Oct 2026): E2's rules, frozen, judged only on results meetings from 19 Oct 2026, in
paper mode ([pre-registration](docs/research/forward3-preregistration.md), pinned 17 Oct 2026 19:02 IST). Each evening,
after forward test 2's update, `python -m trader.research.forward3 daily` fetches NSE's board-meeting notices, records new
signals, paper entries and exits and the random-pick pools in an append-only ledger (`state/forward3.db`), and sends
`[FORWARD TEST 3 · paper only]` messages. Decisions each January from 2028 (evidence id E2F); it is slow: about 20-25
trades a year, so it can show an edge has gone long before it can confirm one.

**Paper trial 1** (your decision, 17 Oct 2026): instead of searching for one strategy that passes everything, the best
bunch of near-misses runs together in one paper account ([definition](docs/research/trial1-definition.md), pinned
17 Oct 2026 21:00 IST): E2 with 3 of the 5 positions and V2 (volatility-adjusted mid-cap momentum, round 9) with 2. A
backtest of every reasonable split on 2013-2026 (chosen after seeing those years, so not evidence) gave this one the
best return for its drawdown: +6.9R a year (+3.4% at 0.5% risk a position), 10 of 14 years profitable, worst year
-10.4R, drawdown 18.4R; E2 and V2's yearly results were only loosely related (0.39). The account uses the risk engine's
sizes, the 20R kill switch and the gate's decay rule per part, records everything in `state/trial1.db`, and sends
`[PAPER TRIAL 1 · paper only]` messages. It changes no strategy's status and cannot reach real money.

**Forward test 4** (your decision, 18 Oct 2026): the trial's future trades are judged against the project's mandatory
criteria ([pre-registration](docs/research/forward4-preregistration.md), pinned 18 Oct 2026 12:24 IST, before its first
trade): realistic costs, the random baseline (pools recorded for every closed trade), drawdown, stable years and
significance at 0.05 / L, each January from 2028. Fail any criterion: real money stays NO TRADE. Pass every one: a
candidate (B1F) for the existing approval stages, nothing automatic. Most likely obstacle: the 50% win-rate floor
(the bunch won 48.7% in the backtest), which stays. Between looks, `state/trial1-status.md` and the monthly Telegram
summary show its figures after costs (win rate, average win and loss, profit factor, drawdown, p against random), and
every random-pick comparison is sent on Telegram; each January the health check warns until the looks are written.

## Research round 9: low volatility and volatility-adjusted momentum (2026-10-14)

Round 8's universe, tiers, trade, 10% stop, costs, random baseline and criteria, with two other ways of choosing the 5
stocks: the least volatile (L1 among the 100 most liquid, L2 among ranks 101-300), and momentum divided by volatility,
like NSE's Nifty200 Momentum 30 (V2, ranks 101-300). Pinned before any code computed them
([pre-registration](docs/research/round9-preregistration.md)); a development stage on 2006-2013
([stage 1](docs/research/round9-stage1.md)), then one decision run on 2013-2026 ([results](docs/research/round9-results.md)).

| Hypothesis | Trades | Winners | Net per trade | Random picks | p vs random | Result | Status |
|---|---:|---:|---:|---:|---:|---|---|
| L1: least volatile of the 100 most liquid | 795 | 51.4% | +0.58% | +0.52% | 0.43 | No better than random picks; profit factor 1.24, 57% of years profitable | REJECTED |
| L2: least volatile of ranks 101-300 | 795 | 52.7% | +0.67% | +0.68% | 0.50 | Passed 11 of 13 criteria (drawdown 12.9R, 71% of years) but no edge over random picks | REJECTED |
| V2: volatility-adjusted momentum, ranks 101-300 | 791 | 45.9% | +2.07% | +0.67% | 0.0002 | The project's strongest edge over random picks, but 46% winners, 64% of years profitable, drawdown 30R | REJECTED |

The two halves of the problem showed up in different rules. Low-volatility mid caps (L2) had the payoff the rules ask
for (more winners than losers, small drawdowns, steady years) but earned exactly what random picks from the same tier
earned. Volatility-adjusted momentum (V2) beat random picks by far more than chance allows (p 0.0002 against a bar of
0.0018) but failed the same three rules as N2, with which it shares many picks. Twenty-eight hypotheses over nine
rounds, none passed. Two notes on stage 1 (decides nothing): two months held 4 picks because the top stock could not be
bought (round 8's rule, as in round 8), and one closed-end fund (MORGANSTAN, until 2008) was counted as a company by
round 8's data audit; neither touches the 2013-2026 decision.

## Research status: a forward test instead of more rounds (2026-10-13)

Seven rounds have tested the well-documented ideas that fit the hard rule (most trades must win, and the
profit must survive costs and beat random entries): pullbacks, the turn of the month, momentum, gaps, and
intraday momentum on minute data. None passed. Each further test on the same data makes a lucky pass more
likely, so there are no more rounds on the daily data. The minute data has had one test (round 7), and
every further idea on it adds to the count too, so it needs strong published evidence and costs it can
plausibly beat before it is tried. Otherwise research restarts only with something genuinely new: a NIFTY
universe as it was at each date, instead of today's members, or a deliberate change to the rules. (Round 8,
on 14 Oct 2026, used exactly that: a universe built from NSE's own daily files as it was at each month-end.)

The only data no one has seen is the future. The two strongest near-misses, H11 and H12 (the turn of
the month), are judged only on sessions after their rules were pinned on 13 Oct 2026: [forward test
1](docs/research/forward1-preregistration.md), `python -m trader.research.forward1`, status in
[docs/research/forward1-results.md](docs/research/forward1-results.md). Its first trade can only come
at the end of October 2026. A look each January decides from 2028 to 2036: every criterion passed makes
a candidate for paper trading (with your approval), and from 2029 a forward loss retires it. A strategy
that trades once a month needs years of new data to prove itself, so this test can show an effect has
stopped working long before it can show one still works: nothing from it is expected to trade before
2030.

New data: Kite's minute history comes with this account's plan at no extra cost, from February 2015 and
adjusted for corporate actions. Its limits matter as much: delisted stocks are missing (survivorship), and
since 3 Aug 2026 NSE closes F&O stocks with an auction from 15:15. What it allows, and what an honest
intraday test needs, is in [docs/research/kite-minute-data.md](docs/research/kite-minute-data.md).

The standards, confirmed on 13 Oct 2026 before any new data was looked at, and not to be relaxed after
seeing results: a strategy must show at least a 50% win rate, positive expectancy after all trading costs
(also at 1.5x costs), an acceptable drawdown, and robust out-of-sample performance, better than random
entries after correcting for every hypothesis tested. A 50% win rate alone is not enough. If nothing
passes, the system stays in NO TRADE. The drawdown limit, confirmed the same day, is enforced by the gate:
no strategy reaches `PAPER` unless its research evidence records a backtest drawdown no deeper than 20R,
the point where the decay rule disables a strategy (at 0.5% risk per trade, the kill switch's 10%).

## Project layout

| Path | What it is |
|---|---|
| `dashboard.py` | Ops console (Streamlit, read-only): health, the paper account, decisions, strategies, runs |
| `scripts/register_tasks.ps1` | Creates the Windows scheduled tasks: the daily run, the health check, Telegram commands, news |
| `config/settings.toml` | Non-secret settings (data source, Telegram, AI, the paper and live accounts) |
| `config/strategies.toml` | Strategy registry: each strategy's status |
| `config/gate.toml` | The profitability gate: the evidence each status requires |
| `config/risk.toml`, `config/sectors.toml` | Hard risk limits; each stock's sector |
| `config/market_calendars.toml` | NSE and NYSE holidays and session hours (update every December) |
| `config/universes.toml` | The stock lists strategies trade (NIFTY 50, the NIFTY ETF, the 11 US sector SPDRs) |
| `trader/` | Config, logging and registry code |
| `trader/markets/` | Exchange calendars |
| `trader/core/` | Shared domain objects (trade intents, positions, portfolio state) |
| `trader/risk/`, `trader/portfolio/` | Risk engine, kill switch, position sizing, sector and correlation exposure |
| `trader/data/` | Data providers (Yahoo, Zerodha Kite) and the checks every bar must pass |
| `trader/features/` | Tested, look-ahead-free indicators (SMA, Wilder RSI, ATR) |
| `trader/strategies/` | Strategy rules (the Phase 3 swing hypotheses) and the catalog the paper trader runs |
| `trader/execution/` | End-of-day paper trading and its SQLite store; Zerodha orders (dry run, order management, live jobs, locked); paper evidence for the gate |
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
python -m trader.execution.eod            # the daily run: India's paper account, then the US one
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
python -m trader.data.kite check RELIANCE.NS     # data: recent candles, validated
python -m trader.execution.live check           # the account: read-only, places nothing
```

The second check shows the account as Kite reports it (funds, holdings, orders, GTT stops) and confirms
every field the order system relies on is there. The session token is stored in `.kite_session.json`
(git-ignored) and is never printed or logged.

## Paper trading

Swing strategies are paper traded once a day, after the NSE close. No real order is ever placed. Every
run also fetches and validates NIFTYBEES (the market check), so the data path is tested daily even while
nothing trades, and the Telegram summary shows its close and the unattended record (N of 60).

```bash
python -m trader.execution.eod                       # process every completed session not yet done
python -m trader.execution.eod --start 2026-10-01    # first run only: replay from this session
python -m trader.execution.report                    # score each strategy's paper trades against the gate
python -m trader.execution.report --market US        # the same for the US paper account
python -m trader.execution.report --live             # small live capital against the gate (Level 6)
python -m trader.execution.broker                    # the Kite requests the dry run prepared (never sent)
python -m trader.execution.live status               # live trading: its locks, live holdings, open requests
python -m trader.execution.records live 2026         # tax records: India's FY 2026-27 and the US's 2026 (CSV)
python -m trader.execution.records paper-us 2026     # the US paper account's round trips in 2026
```

Each run uses the same fill rules as the backtester: orders decided at a close fill at the next open,
stops are checked against the day's range (a gap through the stop fills at the open), time exits happen
at the close, and costs come from the same Zerodha cost model. Every trade passes the risk engine, and
the kill switch blocks new entries but never stops an open position from exiting. Each session is one
database transaction in `state/paper.db` (git-ignored), so a crash or a second run can't duplicate
anything, and a missed day is caught up on the next run.

Telegram gets `[PAPER]` BUY SIGNAL, BUY EXECUTED, SELL SIGNAL, SELL EXECUTED and RISK ALERT messages
and a daily summary; with no approved strategy the summary says NO TRADE. A SELL SIGNAL comes when an
exit rule fires (sell at the next open) and on the evening before a time exit (sell at the next
close). A message that can't be sent is retried on the next run. A strategy whose paper results drift
from its research (`[decay]` in `config/gate.toml`) is suspended automatically.

Only strategies whose status `PAPER` is backed by research evidence are traded. **Today there are none**
(none of the twenty-five hypotheses tested passed), so every run records NO TRADE. To run it every day, see
[Running unattended](#running-unattended).

### The US paper account

The same 18:00 run then paper trades a second account: US stocks and ETFs, $10,000 (`[paper_us]` in
`config/settings.toml`, records in `state/paper-us.db`), on the NYSE calendar, with Yahoo data and SPY
as its market check. At 18:00 IST it takes the US session that closed early that morning (01:30 IST,
or 02:30 in the northern winter). A strategy trades in the account its stocks belong to, so one whose
universe is US stocks (such as `us_sector_etfs`) trades here. **None does today**: the account records
each session and checks SPY without sending anything. It stays quiet while it has nothing to trade,
and speaks up only when something is wrong.

Once a US strategy earns `PAPER`, you follow it by hand at your US broker. Nothing sends a US order.

- **BUY SIGNAL** (18:00 IST): buy at the next US open (19:00 IST, or 20:00 in the northern winter),
  then place the stop order it gives.
- **SELL SIGNAL**: when an exit rule fires, sell at the next US open. When a position's time limit
  ends, the signal comes the evening before: sell at that session's close. Either way, cancel the stop.
- Its messages are in dollars, and its daily summary and alerts say US.

The same risk limits apply, as fractions of the US account's own equity, except the smallest position:
$250 (`[limits.US]` in `config/risk.toml`). One kill switch covers both accounts: a 10% drawdown in
either stops new entries in both, and its reason says which account. Telegram's `/status`,
`/positions` and `/trades`, the dashboard and the health checks (`US daily run`, `US backup`, ...)
cover the US account too, and the heartbeat is pinged only when both accounts' runs were clean.

## Running unattended

Five Windows scheduled tasks run the system. `scripts/register_tasks.ps1` creates them: review it, then
run it once with `powershell -ExecutionPolicy Bypass -File scripts\register_tasks.ps1`. They run on
battery too (by Windows' default a laptop that isn't plugged in would skip them), and without a console
window, so nothing pops up to be closed by accident; their output is in `logs/`. Run the script again
whenever it changes.

| Task | When | Runs |
|---|---|---|
| Daily run | 18:00 IST every day; if the PC was off then, as soon as it is back | `python -m trader.execution.eod` (India's account, then the US one) |
| Health check | 21:00 IST every day; if the PC was asleep or off then, as soon as it is back, after giving a catch-up daily run 10 minutes | `python -m trader.ops.health --notify --scheduled` |
| Telegram commands | Always, from logon (no console window; restarted if it stops) | `python -m trader.notify.bot` |
| News | Every 15 minutes, all day; a run missed while the PC slept starts when it wakes, and hours it slept through are fetched whole from NSE's announcement API | `python -m trader.research.news collect` |
| Forward tests 2 and 3, then paper trial 1 (one task, "Trading agent - forward tests") | 19:30 every evening; if the PC was off or asleep then, as soon as it is back | `python -m trader.research.forward2 daily` (N2 in paper mode on new NSE sessions), `python -m trader.research.forward3 daily` (E2 in paper mode on new results meetings, with NSE's board-meeting notices fetched each evening), then `python -m trader.research.trial daily` (E2 x3 + V2 x2 in one paper account); research only |

From your Telegram chat with the bot: `/status` (health, mode, equity, positions), `/positions`,
`/trades` (the latest closed trades; both accounts), `/kill reason`, which stops all new trades at
once while open positions still exit as planned, `/kitecheck` (the read-only Kite check: counts and a
verdict, no money figures), and `/login`, Kite's daily login from your phone: it sends the link, you
log in and send back the address Kite returns to, and the PC makes the session (the API secret and the
access token never pass through Telegram). Only your chat (`TELEGRAM_CHAT_ID`) is answered. No
command can release the kill switch, change a limit or place an order; releasing is only possible on
the PC.

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

The health check also counts clean sessions in a row since the last failure. Paper-trading evidence
(the audit's Level 5) needs 60 before any real order.

After every run that didn't fail, the records are copied to `state/backups/paper-<date>.db` (the US
account's to `paper-us-<date>.db`; inside OneDrive here, so the copies leave the PC), and the record of
what happened (fills, closed trades, decisions, session snapshots) can't be edited or deleted: the
database refuses. **What each alert means, what to do about it, and the plan for losses decided in
advance are in [docs/runbook.md](docs/runbook.md).**

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
python -m trader.research.round6                                  # re-run research round 6 (Chan)
python -m trader.research.round7                                  # round 7: ran once; refuses a second run
python -m trader.research.nse_bhavcopy build                      # NSE's daily files -> the adjusted, survivorship-free panel
python -m trader.research.nse_bhavcopy audit                      # its data-quality report
python -m trader.research.round8 --stage 1                        # round 8's development stage (2006-2013)
python -m trader.research.round8 --stage 2                        # round 8's decision: ran once; refuses a second run
python -m trader.research.round9 --stage 1                        # round 9's development stage (2006-2013)
python -m trader.research.round9 --stage 2                        # round 9's decision: ran once; refuses a second run
python -m trader.research.round10 --stage 1                       # round 10's development stage (2009-2013, 2015-2017)
python -m trader.research.round10 --stage 2                       # round 10's decision: ran once; refuses a second run
python -m trader.research.forward1                                # forward test 1: H11, H12 on new sessions
python -m trader.research.forward2 status                         # forward test 2: N2 in paper mode, the ledger so far
python -m trader.research.forward2 look                           # its look: informational any time, a decision each January
python -m trader.research.forward3 status                         # forward test 3: E2 in paper mode, signals and positions so far
python -m trader.research.forward3 look                           # its look: informational any time, a decision each January
python -m trader.research.trial status                            # paper trial 1: E2 x3 + V2 x2 in one paper account, so far
python -m trader.research.trial look                              # forward test 4 on its trades: informational; a decision each January
python -m trader.research.forward5 status                         # forward test 5: the trial's trades hedged with short NIFTY futures
python -m trader.research.forward5 look                           # its look: informational any time; a decision each January
python -m trader.research.news status                             # the news history: counts, events, gaps, days seen whole
python -m trader.research.news backfill --from 2026-10-01         # whole past days from NSE's announcement API
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
  in `docs/research/evidence/` with a backtest drawdown no deeper than 20R, `LIVE_SMALL` also needs
  passing paper-trading evidence, and `LIVE` also
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
- US trades are placed by hand: the US paper account's signals tell you what to place, and nothing
  sends a US order. Each paper step for an NSE stock records the exact Zerodha Kite request
  that would carry it out (a dry run: `python -m trader.execution.broker`, or the dashboard's Decisions
  tab). Live trading (`python -m trader.execution.live`) is built and locked: it sends those orders only
  for a strategy at `LIVE_SMALL` or `LIVE` on paper-trading evidence, after you turn it on, within limits
  on size and count, and only while the account holds every share the system believes it holds. Never
  the same order twice, even after a crash or a lost answer. Going live also needs a static IP
  registered with Kite and a DDPI with Zerodha ([docs/runbook.md](docs/runbook.md#before-the-first-real-order)).

## Roadmap

| Phase | Goal | Status |
|---|---|---|
| 0 | Containment: secrets out of code, all rules disabled, honest docs, pinned dependencies | Done |
| 1 | Data: market calendars, validation, Zerodha Kite data for NSE | Done (Kite awaiting a live check: log in, then the two checks under Market data) |
| 2 | Backtesting reliability: the harness in `trader/research/` | Done |
| 3 | Evidence: pre-registered swing-trading hypotheses, tested on frozen data | Done: 0 of 3 passed |
| 3b | Research round 2: the same rules on US stocks, US sector ETFs and Indian index ETFs | Done: 0 of 3 passed |
| 3c | Research round 3: confirm or retire H6 on unseen data | Done: not confirmed; pullback rules retired |
| 3d | Research round 4: the turn-of-the-month effect, US and India | Done: 0 of 2 passed |
| 3e | Research round 5: four monthly effects at once | Done: 0 of 4 passed |
| 3f | Research round 6: six strategies from Chan's *Algorithmic Trading* | Done: 0 of 6 passed |
| 3g | Forward test 1: H11 and H12 on sessions after 13 Oct 2026 | Running: decisions each January, 2028 to 2036 |
| 3h | Research round 7: intraday momentum on Kite's minute data | Done: 0 of 3 passed |
| 3i | Research round 8: stock momentum on a survivorship-free NSE universe (NSE's own daily files, 2005-2026) | Done: 0 of 2 passed; N2 (mid caps) beat random picks but failed the win-rate, stability and drawdown rules |
| 3j | Forward test 2: N2, unchanged, in paper mode on months after 30 Oct 2026 | Running: picks recorded each month-end, decisions each January, 2028 to 2036 |
| 3k | Research round 9: low volatility and volatility-adjusted momentum on the same NSE universe | Done: 0 of 3 passed; L2 had the right payoff but no edge, V2 the strongest edge but N2's failures |
| 3l | Research round 10: results drift, promoter buying and their mix, on new NSE event data | Done: 0 of 3 passed; E2 passed 11 of 13 (all but beating random picks significantly) |
| 3m | Forward test 3: E2, unchanged, in paper mode on results meetings from 19 Oct 2026 | Running: signals and paper trades recorded each evening, decisions each January, 2028 to 2036 |
| 3n | Paper trial 1: the best bunch of near-misses (E2 x3 + V2 x2) in one paper account | Running from 22 Oct 2026: not evidence, changes no status; live stays locked |
| 3o | Forward test 4: paper trial 1's trades judged against the mandatory criteria | Running: decisions each January, 2028 to 2036; any failed criterion keeps NO TRADE |
| 3p | Research round 11: value, dividend flows, option-implied signals (new F&O data) | Done: 10 screened, O2 decided and REJECTED (no edge) |
| 3q | Forward test 5: paper trial 1 hedged with short NIFTY futures (paper only) | Running from 22 Oct 2026; decisions each January 2028-2036 |
| 4 | Profitability gate enforced from evidence reports | Done |
| 5-6 | Risk engine and portfolio limits | Done |
| 7 | Paper trading (end-of-day, for swing strategies) | Done: India's account and, since 2026-10-12, a US one whose signals you place by hand. No strategy is eligible yet; the 60 unattended sessions are being counted (the health check shows how many) |
| 8 | Broker integration: Zerodha Kite orders, still on paper capital | Done: the dry run, and the order management system (orders and GTT stops, never sent twice, rejects, partial fills, reconciliation with the account), tested against an in-memory Kite (Kite has no sandbox) |
| 9 | AI research layer: news to structured tags, advisory only | Built: NSE's announcements collected every 15 minutes into a history with every gap recorded, tagged by rules (optional AI tags, schema-checked, off until a new key); no trading code can read them. Kept only if a pre-registered research round shows the tags improve a strategy |
| 10 | Observability: run records, alerts on failure and on silence, health checks, ops console | Done |
| 11 | Controlled live trading | Built and locked: the live jobs (18:30, 09:20, 15:15) and their locks, live-against-paper tracking, the Level 6 evidence for `LIVE`, and Level 7's capital steps (at most double, 4 weeks apart, automatic step-down). Nothing is sent until a strategy earns `LIVE_SMALL` on paper-trading evidence and you turn it on |

## Data

Market data from Yahoo Finance is for personal research only. It lives in `data/`, which is
git-ignored: don't commit or redistribute it.
