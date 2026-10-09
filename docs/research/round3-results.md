# Research round 3 results: confirming or retiring H6

Generated 2026-10-09 23:14 by `python -m trader.research.round3`, judged against [the pre-registration](round3-preregistration.md) (SHA-256 `78c1275b406b9bb9...`, unchanged since it was recorded before any strategy ran). Returns are per trade, net of costs, over each hypothesis's whole span.

## Verdict

| Hypothesis | Trades | Win rate | Net per trade | Profit factor | t | Cluster-robust t | p vs random (Holm) | Decision |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| H7: Oversold pullback in an uptrend, US sector SPDRs, 2000-2015 | 1085 | 71.1% | +0.323% | 1.56 | 5.30 | 3.48 | 0.012 | **REJECTED** |
| H8: Oversold pullback in an uptrend, iShares country ETFs, 2016-2026 | 1154 | 61.6% | +0.072% | 1.10 | 1.16 | 0.76 | 0.191 | **REJECTED** |

**H6 is not confirmed.** As pre-registered, the pullback rules are retired: no variant of them is tested again in this project.

## Data and costs

- Daily bars from Yahoo (adjusted), frozen in `data/round3/` with checksums: the 9 original sector SPDRs cut at 31 Dec 2015 (H7), and 15 iShares country ETFs cut at 8 Oct 2026 (H8).
- Bars without prices and Yahoo's flat zero-volume placeholder bars were dropped.
- Round-trip costs: H7 0.043%, H8 0.103% (0.05% slippage per side); stress test at 1.5x.

Every daily move above 20% in the evaluation data, classified before any strategy ran:

| Instrument | Date | Close to close | Open gap | Classification |
|---|---|---:|---:|---|
| XLF | 2008-09-19 | +12.9% | +22.1% | Genuine: US short-selling ban and bank rescue plan |
| EWZ | 2020-03-16 | -23.1% | -16.1% | Genuine: COVID-19 crash |
| FXI | 2022-03-16 | +21.2% | +11.7% | Genuine: China's pledge to support its markets |
| MCHI | 2022-03-16 | +20.9% | +12.5% | Genuine: China's pledge to support its markets |

## H7: Oversold pullback in an uptrend, US sector SPDRs, 2000-2015

| Period | Trades | Win rate | Avg win | Avg loss | Profit factor | Net per trade | t | Max drawdown | Sharpe |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2000-2007 | 525 | 69.0% | +1.29% | -1.93% | 1.49 | +0.291% | 3.27 | -6.6R | 0.95 |
| 2008-2015 | 560 | 73.0% | +1.24% | -2.06% | 1.63 | +0.353% | 4.22 | -11.7R | 1.04 |
| All 2000-2015 | 1085 | 71.1% | +1.27% | -1.99% | 1.56 | +0.323% | 5.30 | -11.7R | 0.99 |

Random baseline (random days with the same instruments, simultaneous entries kept together): +0.136% gross per trade vs +0.365% for the strategy; p = 0.006 (Holm-adjusted 0.012).

| # | Criterion | Value | Pass |
|---|---|---|---|
| 1 | At least 50 trades | 1085 | yes |
| 2 | Win rate at least 50% | 71.1% | yes |
| 3 | Expectancy above 0 at base and 1.5x costs | +0.323% / +0.301% | yes |
| 4 | t-statistic at least 2.0 | 5.30 | yes |
| 5 | Beats random entries (Holm-adjusted p < 0.05) | 0.012 | yes |
| 6 | Profit factor at least 1.3 | 1.56 | yes |
| 7 | Avg loss at most 1.5x avg win; worst trade no worse than -3R | -1.99% vs +1.27%; worst -2.9R | **no** |
| 8 | Expectancy above 0 in each half of the span | +0.291% / +0.353% | yes |
| 9 | At least 70% of years (10+ trades) positive | 88% of 16 years | yes |
| 10 | 60%+ of stocks profitable; still positive without the top stock | 100% of 9 stocks; +0.296% without XLF | yes |
| 11 | Cluster-robust t-statistic (signal weeks as clusters) at least 2.0 | 3.48 | yes |
| 12 | The other hypothesis of this round also passes criteria 1-11 | H8 fails | **no** |

**Decision: REJECTED.**

By year (net of base costs):

| Year | Trades | Win rate | Net per trade |
|---|---:|---:|---:|
| 2000 | 54 | 59.3% | +0.061% |
| 2001 | 50 | 70.0% | +0.515% |
| 2002 | 25 | 56.0% | -0.202% |
| 2003 | 56 | 83.9% | +0.796% |
| 2004 | 85 | 67.1% | +0.258% |
| 2005 | 87 | 65.5% | +0.152% |
| 2006 | 81 | 75.3% | +0.334% |
| 2007 | 87 | 67.8% | +0.252% |
| 2008 | 17 | 70.6% | -1.390% |
| 2009 | 58 | 74.1% | +1.065% |
| 2010 | 67 | 74.6% | +0.104% |
| 2011 | 72 | 68.1% | +0.275% |
| 2012 | 105 | 75.2% | +0.664% |
| 2013 | 82 | 78.0% | +0.490% |
| 2014 | 91 | 70.3% | +0.184% |
| 2015 | 68 | 70.6% | +0.087% |

By instrument (net of base costs):

| Instrument | Trades | Win rate | Net per trade |
|---|---:|---:|---:|
| XLF | 114 | 72.8% | +0.552% |
| XLE | 113 | 73.5% | +0.508% |
| XLV | 130 | 75.4% | +0.442% |
| XLY | 136 | 71.3% | +0.441% |
| XLI | 127 | 75.6% | +0.358% |
| XLP | 125 | 68.8% | +0.232% |
| XLU | 106 | 65.1% | +0.151% |
| XLB | 120 | 70.0% | +0.119% |
| XLK | 114 | 65.8% | +0.065% |

## H8: Oversold pullback in an uptrend, iShares country ETFs, 2016-2026

| Period | Trades | Win rate | Avg win | Avg loss | Profit factor | Net per trade | t | Max drawdown | Sharpe |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2016-2020 | 493 | 63.1% | +1.29% | -2.00% | 1.10 | +0.077% | 0.83 | -40.4R | 0.09 |
| 2021-2026 | 661 | 60.5% | +1.33% | -1.87% | 1.09 | +0.068% | 0.82 | -23.2R | 0.30 |
| All 2016-2026 | 1154 | 61.6% | +1.31% | -1.92% | 1.10 | +0.072% | 1.16 | -40.4R | 0.19 |

Random baseline (random days with the same instruments, simultaneous entries kept together): +0.103% gross per trade vs +0.175% for the strategy; p = 0.191 (Holm-adjusted 0.191).

| # | Criterion | Value | Pass |
|---|---|---|---|
| 1 | At least 50 trades | 1154 | yes |
| 2 | Win rate at least 50% | 61.6% | yes |
| 3 | Expectancy above 0 at base and 1.5x costs | +0.072% / +0.021% | yes |
| 4 | t-statistic at least 2.0 | 1.16 | **no** |
| 5 | Beats random entries (Holm-adjusted p < 0.05) | 0.191 | **no** |
| 6 | Profit factor at least 1.3 | 1.10 | **no** |
| 7 | Avg loss at most 1.5x avg win; worst trade no worse than -3R | -1.92% vs +1.31%; worst -2.5R | yes |
| 8 | Expectancy above 0 in each half of the span | +0.077% / +0.068% | yes |
| 9 | At least 70% of years (10+ trades) positive | 55% of 11 years | **no** |
| 10 | 60%+ of stocks profitable; still positive without the top stock | 60% of 15 stocks; +0.046% without EWT | yes |
| 11 | Cluster-robust t-statistic (signal weeks as clusters) at least 2.0 | 0.76 | **no** |
| 12 | The other hypothesis of this round also passes criteria 1-11 | H7 fails | **no** |

**Decision: REJECTED.**

By year (net of base costs):

| Year | Trades | Win rate | Net per trade |
|---|---:|---:|---:|
| 2016 | 95 | 68.4% | +0.410% |
| 2017 | 141 | 70.2% | +0.363% |
| 2018 | 71 | 52.1% | -0.429% |
| 2019 | 102 | 56.9% | -0.171% |
| 2020 | 84 | 61.9% | -0.051% |
| 2021 | 132 | 65.9% | +0.179% |
| 2022 | 38 | 52.6% | -0.907% |
| 2023 | 116 | 56.9% | -0.095% |
| 2024 | 135 | 57.0% | +0.105% |
| 2025 | 141 | 64.5% | +0.260% |
| 2026 | 99 | 59.6% | +0.164% |

By instrument (net of base costs):

| Instrument | Trades | Win rate | Net per trade |
|---|---:|---:|---:|
| EWT | 87 | 66.7% | +0.391% |
| EWC | 97 | 68.0% | +0.333% |
| EWG | 79 | 68.4% | +0.325% |
| EWU | 79 | 69.6% | +0.284% |
| EWS | 80 | 60.0% | +0.243% |
| EWA | 84 | 66.7% | +0.209% |
| EWY | 68 | 58.8% | +0.192% |
| EWJ | 75 | 62.7% | +0.107% |
| INDA | 70 | 58.6% | +0.064% |
| EWL | 84 | 61.9% | -0.040% |
| EWW | 72 | 62.5% | -0.072% |
| EWZ | 70 | 51.4% | -0.205% |
| FXI | 75 | 58.7% | -0.239% |
| EWH | 64 | 51.6% | -0.276% |
| MCHI | 70 | 51.4% | -0.507% |

## Informational (doesn't affect the decisions)

The same comparison with every random entry drawn independently, as in Phase 3:

| Hypothesis | p, simultaneous entries kept together | p, independent draws |
|---|---:|---:|
| H7 | 0.006 | 0.001 |
| H8 | 0.191 | 0.093 |

The sector SPDRs under these rules, 2000-2026 (H7's trades, then round 2's H6 on the 11 SPDRs), net of 0.043% per trade: 2026 trades, 68.7% winners, +0.279% per trade, t 6.24, cluster-robust t 4.07.
