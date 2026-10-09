# Phase 3 results: swing-trading hypotheses

Generated 2026-10-09 01:05 by `python -m trader.research.phase3`, judged against [the pre-registration](phase3-preregistration.md) (SHA-256 `4be087a7804f6499...`, unchanged since it was recorded before any strategy ran). Returns are per trade, net of costs; holdout = 2022 to 8 Oct 2026.

## Verdict

| Hypothesis | Holdout trades | Win rate | Net per trade | Profit factor | t | p vs random (Holm) | Decision |
|---|---:|---:|---:|---:|---:|---:|---|
| H1: Oversold pullback in an uptrend, NIFTY 50 stocks | 1771 | 60.2% | -0.050% | 0.96 | -0.67 | 0.120 | **REJECTED** |
| H2: Oversold pullback in an uptrend, NIFTY 50 index via ETF | 46 | 63.0% | +0.122% | 1.26 | 0.60 | 0.309 | **REJECTED** |
| H3: 12-1 month momentum, top 5 NIFTY 50 stocks monthly | 280 | 55.7% | +1.180% | 1.40 | 2.12 | 0.309 | **REJECTED** |

## Data and costs

- NIFTY 50 stocks: 50 symbols, daily, Yahoo (adjusted), frozen in `data/phase3/` with checksums.
- Cleaning, fixed after the data-quality report and before any strategy ran: bars without prices (Yahoo's broken 8 Oct 2026 bar) and Yahoo's flat zero-volume placeholder bars on NSE holidays were dropped; three unadjusted corporate actions split their series (ADANIENT 3 Jun 2015 demerger, TMPV 14 Oct 2025 demerger, TRENT 1 Jan 2026 bonus).
- Round-trip costs: stocks 0.298% (Zerodha delivery), NIFTY ETF 0.099%, US 0.043%; stress test at 1.5x.
- Survivorship bias: today's index members over a past decade over-represent winners. The random baselines use the same stocks and period, so they share that bias.

## H1: Oversold pullback in an uptrend, NIFTY 50 stocks

| Period | Trades | Win rate | Avg win | Avg loss | Profit factor | Net per trade | t | Max drawdown | Sharpe |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Design 2016-2021 | 2038 | 64.8% | +2.04% | -3.52% | 1.07 | +0.085% | 1.07 | -64.1R | 0.12 |
| Holdout 2022-2026 | 1771 | 60.2% | +1.85% | -2.92% | 0.96 | -0.050% | -0.67 | -43.6R | -0.52 |
| All | 3809 | 62.7% | +1.95% | -3.22% | 1.02 | +0.022% | 0.40 | -64.1R | -0.14 |

Random baseline (random days, same stocks, same exits), holdout: +0.139% gross per trade vs +0.247% for the strategy; p = 0.040 (Holm-adjusted 0.120).

| # | Criterion | Value | Pass |
|---|---|---|---|
| 1 | At least 50 holdout trades | 1771 | yes |
| 2 | Win rate at least 50% | 60.2% | yes |
| 3 | Expectancy above 0 at base and 1.5x costs | -0.050% / -0.199% | **no** |
| 4 | t-statistic at least 2.0 | -0.67 | **no** |
| 5 | Beats random entries (Holm-adjusted p < 0.05) | 0.120 | **no** |
| 6 | Profit factor at least 1.3 | 0.96 | **no** |
| 7 | Avg loss at most 1.5x avg win; worst trade no worse than -3R | -2.92% vs +1.85%; worst -2.5R | **no** |
| 8 | Design-period expectancy also above 0 | +0.085% | yes |
| 9 | At least 70% of years (10+ trades) positive | 55% of 11 years | **no** |
| 10 | 60%+ of stocks profitable; still positive without the top stock | 52% of 50 stocks; +0.005% without HINDALCO.NS | **no** |

**Decision: REJECTED.**

By year (all trades, net of base costs):

| Year | Trades | Win rate | Net per trade |
|---|---:|---:|---:|
| 2016 | 292 | 64.7% | -0.296% |
| 2017 | 341 | 64.2% | +0.184% |
| 2018 | 285 | 65.3% | -0.034% |
| 2019 | 304 | 62.2% | -0.053% |
| 2020 | 279 | 66.3% | +0.155% |
| 2021 | 537 | 65.7% | +0.334% |
| 2022 | 340 | 57.1% | -0.377% |
| 2023 | 366 | 62.6% | +0.031% |
| 2024 | 498 | 63.7% | +0.291% |
| 2025 | 358 | 61.5% | +0.165% |
| 2026 | 209 | 50.7% | -0.841% |

## H2: Oversold pullback in an uptrend, NIFTY 50 index via ETF

| Period | Trades | Win rate | Avg win | Avg loss | Profit factor | Net per trade | t | Max drawdown | Sharpe |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Design 2016-2021 | 56 | 60.7% | +1.10% | -1.95% | 0.87 | -0.097% | -0.38 | -6.9R | -0.22 |
| Holdout 2022-2026 | 46 | 63.0% | +0.93% | -1.25% | 1.26 | +0.122% | 0.60 | -2.2R | 0.30 |
| All | 102 | 61.8% | +1.02% | -1.64% | 1.00 | +0.002% | 0.01 | -6.9R | -0.02 |

Random baseline (random days, same index, same exits), holdout: +0.007% gross per trade vs +0.221% for the strategy; p = 0.154 (Holm-adjusted 0.309).

| # | Criterion | Value | Pass |
|---|---|---|---|
| 1 | At least 50 holdout trades | 46 | **no** |
| 2 | Win rate at least 50% | 63.0% | yes |
| 3 | Expectancy above 0 at base and 1.5x costs | +0.122% / +0.073% | yes |
| 4 | t-statistic at least 2.0 | 0.60 | **no** |
| 5 | Beats random entries (Holm-adjusted p < 0.05) | 0.309 | **no** |
| 6 | Profit factor at least 1.3 | 1.26 | **no** |
| 7 | Avg loss at most 1.5x avg win; worst trade no worse than -3R | -1.25% vs +0.93%; worst -1.1R | yes |
| 8 | Design-period expectancy also above 0 | -0.097% | **no** |
| 9 | At least 70% of years (10+ trades) positive | 67% of 6 years | **no** |

**Decision: REJECTED.**

By year (all trades, net of base costs):

| Year | Trades | Win rate | Net per trade |
|---|---:|---:|---:|
| 2016 | 5 | 80.0% | -0.557% |
| 2017 | 9 | 55.6% | -0.324% |
| 2018 | 11 | 45.5% | -0.362% |
| 2019 | 9 | 55.6% | -0.221% |
| 2020 | 10 | 70.0% | +0.296% |
| 2021 | 12 | 66.7% | +0.274% |
| 2022 | 10 | 40.0% | -0.641% |
| 2023 | 9 | 66.7% | +0.330% |
| 2024 | 11 | 63.6% | +0.410% |
| 2025 | 13 | 84.6% | +0.367% |
| 2026 | 3 | 33.3% | -0.080% |

## H3: 12-1 month momentum, top 5 NIFTY 50 stocks monthly

| Period | Trades | Win rate | Avg win | Avg loss | Profit factor | Net per trade | t | Max drawdown | Sharpe |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Design 2016-2021 | 360 | 53.9% | +8.92% | -6.77% | 1.54 | +1.681% | 3.00 | -142.7% | 0.87 |
| Holdout 2022-2026 | 280 | 55.7% | +7.39% | -6.63% | 1.40 | +1.180% | 2.12 | -137.6% | 0.68 |
| All | 640 | 54.7% | +8.24% | -6.71% | 1.48 | +1.462% | 3.67 | -142.7% | 0.79 |

Random baseline (5 random stocks from the same month's eligible list), holdout: +1.265% gross per trade vs +1.478% for the strategy; p = 0.287 (Holm-adjusted 0.309).

| # | Criterion | Value | Pass |
|---|---|---|---|
| 1 | At least 50 holdout trades | 280 | yes |
| 2 | Win rate at least 50% | 55.7% | yes |
| 3 | Expectancy above 0 at base and 1.5x costs | +1.180% / +1.031% | yes |
| 4 | t-statistic at least 2.0 | 2.12 | yes |
| 5 | Beats random entries (Holm-adjusted p < 0.05) | 0.309 | **no** |
| 6 | Profit factor at least 1.3 | 1.40 | yes |
| 7 | Avg loss at most 1.5x avg win | -6.63% vs +7.39% | yes |
| 8 | Design-period expectancy also above 0 | +1.681% | yes |
| 9 | At least 70% of years (10+ trades) positive | 82% of 11 years | yes |
| 10 | 60%+ of stocks profitable; still positive without the top stock | 79% of 38 stocks; +1.303% without ADANIENT.NS | yes |

**Decision: REJECTED.**

By year (all trades, net of base costs):

| Year | Trades | Win rate | Net per trade |
|---|---:|---:|---:|
| 2016 | 60 | 56.7% | +2.742% |
| 2017 | 60 | 56.7% | +3.032% |
| 2018 | 60 | 43.3% | -0.280% |
| 2019 | 60 | 55.0% | +0.430% |
| 2020 | 60 | 53.3% | +1.195% |
| 2021 | 60 | 58.3% | +2.965% |
| 2022 | 60 | 45.0% | +0.512% |
| 2023 | 60 | 66.7% | +3.485% |
| 2024 | 60 | 60.0% | +2.111% |
| 2025 | 60 | 53.3% | +0.259% |
| 2026 | 40 | 52.5% | -1.291% |

H3's drawdown above adds up five simultaneous positions. As equally weighted monthly portfolios over the holdout months, each net of its own monthly trading costs (informational; doesn't affect the decision):

| Portfolio | Average month | Total return | Max drawdown |
|---|---:|---:|---:|
| H3: momentum, top 5 stocks | +1.18% | +75.0% | -25.3% |
| All eligible NIFTY 50 stocks, equal weight | +0.96% | +63.2% | -17.0% |
| NIFTY 50 index via ETF | +0.42% | +21.7% | -15.2% |

## Informational: the same rules in the US (doesn't affect the decisions)

| Test | Holdout trades | Win rate | Net per trade | t | p vs random |
|---|---:|---:|---:|---:|---:|
| H1 rules on 20 US large caps | 719 | 66.1% | +0.354% | 2.64 | 0.094 |
| H2 rules on SPY | 45 | 71.1% | +0.263% | 1.24 | 0.234 |
