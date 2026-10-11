# Research round 4 results: the turn-of-the-month effect

Generated 2026-10-11 16:24 by `python -m trader.research.round4`, judged against [the pre-registration](round4-preregistration.md) (SHA-256 `3346175fbab3abd9...`, unchanged since it was recorded before the rule ran on any data). Returns are per trade, net of costs, over each hypothesis's whole span.

## Verdict

| Hypothesis | Trades | Win rate | Net per trade | Profit factor | t | p vs random (Holm) | Decision |
|---|---:|---:|---:|---:|---:|---:|---|
| H9: Turn of the month, S&P 500 (SPY) | 404 | 57.7% | +0.229% | 1.34 | 2.26 | 0.067 | **REJECTED** |
| H10: Turn of the month, NIFTY 50 (via NIFTYBEES) | 225 | 56.4% | +0.277% | 1.34 | 1.65 | 0.033 | **REJECTED** |

## Data and costs

- Daily bars from Yahoo (adjusted), frozen in `data/round4/` with checksums, cut at 8 Oct 2026: SPY from its listing, and the NIFTY 50 index from Yahoo's first bar (17 Sep 2007), standing in for NIFTYBEES.
- Bars without prices and Yahoo's flat zero-volume placeholder bars were dropped.
- Round-trip costs: H9 0.043%, H10 0.099%; stress test at 1.5x.
- Daily moves above 20%: none in either series.

## H9: Turn of the month, S&P 500 (SPY)

| Period | Trades | Win rate | Avg win | Avg loss | Profit factor | Net per trade | t | Max drawdown | Sharpe |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1993-2009 | 203 | 57.1% | +1.69% | -1.82% | 1.24 | +0.184% | 1.19 | -5.0R | 0.34 |
| 2010-2026 | 201 | 58.2% | +1.44% | -1.35% | 1.48 | +0.274% | 2.10 | -5.2R | 0.44 |
| All 1993-2026 | 404 | 57.7% | +1.56% | -1.59% | 1.34 | +0.229% | 2.26 | -5.2R | 0.39 |

Random baseline (the same four-day hold and stop entered on random days of the span): +0.121% gross per trade vs +0.272% at the turn of the month; p = 0.067 (Holm-adjusted 0.067).

| # | Criterion | Value | Pass |
|---|---|---|---|
| 1 | At least 50 trades | 404 | yes |
| 2 | Win rate at least 50% | 57.7% | yes |
| 3 | Expectancy above 0 at base and 1.5x costs | +0.229% / +0.207% | yes |
| 4 | t-statistic at least 2.0 | 2.26 | yes |
| 5 | Beats random entries (Holm-adjusted p < 0.05) | 0.067 | **no** |
| 6 | Profit factor at least 1.3 | 1.34 | yes |
| 7 | Avg loss at most 1.5x avg win; worst trade no worse than -3R | -1.59% vs +1.56%; worst -1.3R | yes |
| 8 | Expectancy above 0 in each half of the span | +0.184% / +0.274% | yes |
| 9 | At least 70% of years (10+ trades) positive | 61% of 33 years | **no** |
| 11 | Cluster-robust t-statistic (signal weeks as clusters) at least 2.0 | 2.26 | yes |

**Decision: REJECTED.**

By year (net of base costs):

| Year | Trades | Win rate | Net per trade |
|---|---:|---:|---:|
| 1993 | 11 | 45.5% | -0.183% |
| 1994 | 12 | 33.3% | -0.362% |
| 1995 | 12 | 83.3% | +1.069% |
| 1996 | 12 | 66.7% | +0.308% |
| 1997 | 12 | 66.7% | +1.374% |
| 1998 | 12 | 50.0% | -0.737% |
| 1999 | 12 | 58.3% | +0.355% |
| 2000 | 12 | 58.3% | +1.083% |
| 2001 | 12 | 50.0% | +0.298% |
| 2002 | 12 | 41.7% | -0.924% |
| 2003 | 12 | 83.3% | +0.964% |
| 2004 | 12 | 58.3% | +0.295% |
| 2005 | 12 | 75.0% | +0.501% |
| 2006 | 12 | 50.0% | -0.157% |
| 2007 | 12 | 50.0% | -0.623% |
| 2008 | 12 | 50.0% | -0.018% |
| 2009 | 12 | 50.0% | -0.140% |
| 2010 | 12 | 83.3% | +1.399% |
| 2011 | 12 | 50.0% | -0.293% |
| 2012 | 12 | 50.0% | +0.371% |
| 2013 | 12 | 66.7% | +0.065% |
| 2014 | 12 | 58.3% | -0.276% |
| 2015 | 12 | 33.3% | -0.167% |
| 2016 | 12 | 41.7% | +0.073% |
| 2017 | 12 | 58.3% | +0.271% |
| 2018 | 12 | 58.3% | -0.323% |
| 2019 | 12 | 66.7% | +0.374% |
| 2020 | 12 | 75.0% | +1.600% |
| 2021 | 12 | 50.0% | +0.101% |
| 2022 | 12 | 58.3% | +0.234% |
| 2023 | 12 | 50.0% | +0.278% |
| 2024 | 12 | 58.3% | -0.004% |
| 2025 | 12 | 58.3% | +0.058% |
| 2026 | 9 | 77.8% | +1.096% |

## H10: Turn of the month, NIFTY 50 (via NIFTYBEES)

| Period | Trades | Win rate | Avg win | Avg loss | Profit factor | Net per trade | t | Max drawdown | Sharpe |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2008-2016 | 108 | 57.4% | +2.34% | -2.26% | 1.39 | +0.379% | 1.30 | -3.3R | 0.33 |
| 2017-2026 | 117 | 55.6% | +1.54% | -1.51% | 1.27 | +0.183% | 1.01 | -9.4R | 0.24 |
| All 2008-2026 | 225 | 56.4% | +1.93% | -1.86% | 1.34 | +0.277% | 1.65 | -9.4R | 0.29 |

Random baseline (the same four-day hold and stop entered on random days of the span): +0.028% gross per trade vs +0.376% at the turn of the month; p = 0.017 (Holm-adjusted 0.033).

| # | Criterion | Value | Pass |
|---|---|---|---|
| 1 | At least 50 trades | 225 | yes |
| 2 | Win rate at least 50% | 56.4% | yes |
| 3 | Expectancy above 0 at base and 1.5x costs | +0.277% / +0.228% | yes |
| 4 | t-statistic at least 2.0 | 1.65 | **no** |
| 5 | Beats random entries (Holm-adjusted p < 0.05) | 0.033 | yes |
| 6 | Profit factor at least 1.3 | 1.34 | yes |
| 7 | Avg loss at most 1.5x avg win; worst trade no worse than -3R | -1.86% vs +1.93%; worst -1.7R | yes |
| 8 | Expectancy above 0 in each half of the span | +0.379% / +0.183% | yes |
| 9 | At least 70% of years (10+ trades) positive | 61% of 18 years | **no** |
| 11 | Cluster-robust t-statistic (signal weeks as clusters) at least 2.0 | 1.65 | **no** |

**Decision: REJECTED.**

By year (net of base costs):

| Year | Trades | Win rate | Net per trade |
|---|---:|---:|---:|
| 2008 | 12 | 41.7% | -0.243% |
| 2009 | 12 | 75.0% | +1.778% |
| 2010 | 12 | 75.0% | +1.158% |
| 2011 | 12 | 66.7% | +0.362% |
| 2012 | 12 | 58.3% | +0.583% |
| 2013 | 12 | 50.0% | -0.544% |
| 2014 | 12 | 58.3% | +0.396% |
| 2015 | 12 | 41.7% | -0.347% |
| 2016 | 12 | 50.0% | +0.265% |
| 2017 | 12 | 75.0% | +0.303% |
| 2018 | 12 | 25.0% | -0.848% |
| 2019 | 12 | 41.7% | -0.341% |
| 2020 | 12 | 58.3% | +0.342% |
| 2021 | 12 | 75.0% | +1.500% |
| 2022 | 12 | 66.7% | +0.347% |
| 2023 | 12 | 58.3% | +0.705% |
| 2024 | 12 | 50.0% | -0.082% |
| 2025 | 12 | 41.7% | -0.122% |
| 2026 | 9 | 66.7% | -0.023% |
