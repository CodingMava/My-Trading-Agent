# Research round 4 pre-registration: the turn-of-the-month effect

Written 2026-10-11, **before** this rule was run on any data. The rule, data, costs, tests, pass criteria
and decision below are fixed. Results are reported against this document whatever they show; the results
file records this file's SHA-256 so any later edit is detectable.

## Why this round

No swing rule has passed in three rounds, and the pullback rules are retired. This round tests a
different kind of effect: a calendar effect with nothing to fit, and one of the longest-documented
regularities in stock returns. Index returns cluster around the turn of the month: the month's last
trading day and the next month's first three (Ariel 1987; Lakonishok & Smidt 1988; McConnell & Xu 2008,
who found it in US stocks from 1926 to 2005 and in 30 of 35 countries). Proposed causes include
month-end salary, pension and fund inflows.

The honest prior: the effect may have weakened since it became widely known, and with one trade a month
only long histories give the tests enough power. Either could make it fail.

## Data and periods

| Item | H9 | H10 |
|---|---|---|
| Instrument | SPY (S&P 500 ETF) | NIFTY 50 index (`^NSEI`), standing in for the NIFTYBEES ETF that would be traded |
| Bars used | From listing (29 Jan 1993) to 8 Oct 2026 | From 17 Sep 2007 (Yahoo's first bar) to 8 Oct 2026 |
| Evaluation (signal dates) | 1 Feb 1993 to 8 Oct 2026 | 1 Jan 2008 to 8 Oct 2026 |
| Halves | 1993-2009 and 2010-2026 | 2008-2016 and 2017-2026 |

Source: Yahoo Finance daily bars, split- and dividend-adjusted, frozen in `data/round4/` with checksums
and a validation report. Later bars are dropped.

**Earlier use of these series.** SPY's and the NIFTY 50's daily bars since 2014 were used before, for the
unrelated pullback rules (Phase 3's H2 and an informational check). Nothing about month-ends was examined,
and this rule has nothing to fit, so that use can't have shaped it.

**The NIFTY 50 index stands in for NIFTYBEES** because Yahoo's NIFTYBEES series is poor (17% of its 2012
bars are flat). The index excludes dividends (about 1.2% a year), which if anything understates the ETF.

**Nothing is fitted**, so each hypothesis is judged on its whole evaluation span, and each half must be
profitable on its own.

**Data cleaning, fixed now.** As in rounds 2 and 3: bars without prices and Yahoo's flat zero-volume
placeholder bars are dropped; every daily move above 20% is classified before any strategy runs (a
corporate action Yahoo didn't adjust splits the series; a genuine move is kept), and the results list
every flag.

## Execution and costs

- Signals use completed daily bars; entries fill at the next open; a stop fills at the stop price, or at
  the open if the day gaps through it; the time exit fills at the close of the last day.
- H9: a commission-free US broker, the SEC fee on sales and 0.02% slippage per side, 0.043% round trip
  at $10,000.
- H10: Zerodha ETF delivery charges at Rs 1 lakh (STT 0.001% on the sell side only, stamp duty, exchange
  and SEBI fees, GST, the Rs 15.34 DP charge) plus 0.03% slippage per side, since NIFTYBEES trades about
  Rs 143 crore a day: 0.099% round trip.
- Stress test: every cost x 1.5.

## Hypotheses

The rule, for both:

- **Entry:** at the close of each month's second-to-last trading day, buy at the next open, which is the
  open of the month's last trading day.
- **Exit:** at the close of the next month's third trading day (four trading days in the market), or
  earlier at the stop.
- **Stop:** 2.5 x ATR(14, Wilder) below entry, sized at the signal day's close. It is there because the
  risk engine sizes every position from its stop; over four days it should rarely be hit. A month without
  that ATR yet (the first weeks of data) gets no trade. R (risk unit) = the stop distance.
- Which day is a month's last trading day comes from the trading calendar; in the backtest, from the
  bars' own dates. The final bars, whose next month isn't in the data, never signal.

### H9: Turn of the month, S&P 500 (SPY)

### H10: Turn of the month, NIFTY 50 (via NIFTYBEES)

## Tests

For each hypothesis, on its whole evaluation span, net of base costs unless stated:

- Trade statistics as before: count, win rate, average win and loss, profit factor, expectancy,
  t-statistic, worst trade in R, drawdown, Sharpe.
- **Random baseline:** the same instrument held for the same four days with the same stop, entered on
  randomly chosen days of the evaluation span, as many trades as the strategy has, 2,000 times. p = the
  share of those random sets whose average gross return per trade is at least the strategy's. The two
  p-values are corrected with Holm's method.
- The cluster-robust t-statistic (signal weeks as clusters). With one trade a month it equals the
  ordinary t-statistic.
- Stability: each half and each calendar year.

## Pass criteria (whole evaluation span, base costs unless stated)

| # | Criterion |
|---|---|
| 1 | At least 50 trades |
| 2 | Win rate at least 50% |
| 3 | Expectancy above zero at base costs and at 1.5x costs |
| 4 | t-statistic at least 2.0 |
| 5 | Beats the random baseline: Holm-adjusted p below 0.05 |
| 6 | Profit factor at least 1.3 |
| 7 | Average loss at most 1.5 x average win; worst trade no worse than -3R |
| 8 | Expectancy above zero in each half of the span |
| 9 | At least 70% of calendar years (with 10+ trades) have positive expectancy |
| 11 | Cluster-robust t-statistic (signal weeks as clusters) at least 2.0 |

These are round 3's criteria. Criterion 10 (breadth across instruments) doesn't apply because each
hypothesis trades a single instrument, and there is no "both must pass" rule: the two hypotheses test the
effect in different markets, and a pass in one is a tradable result there.

**Decision, for each hypothesis on its own.**

| Outcome | Registry status |
|---|---|
| All criteria pass | `PAPER`. H10 paper trades NIFTYBEES on the existing NSE engine; H9 first needs US support in the paper engine, and US orders stay manual |
| Only criterion 1 (sample size) fails | `RESEARCH`: inconclusive |
| Anything else | `REJECTED` |

## Informational (does not affect the decisions)

- The rest of the month: the random baseline's average four-day return next to the turn of the month's.
