# Research round 11 results: option-implied information (O2)

Run on 2026-10-19 00:12 IST by `python -m trader.research.round11 --stage 2` (runner SHA-256 `3f67b85f90e77484...`), against [the pre-registration](round11-preregistration.md) (SHA-256 `a2b4c2b8efb5bbf4...`), the F&O manifests (`d99ffe9c...`, `aa94ce3b...`) and round 8's panel (`afb79ad2...`). Total returns after costs (Rs 33,333 positions, 15% stop).

Signals 2013-06-28 to 2026-08-31: 795 trades; stocks with the signal per month: median 173.

| Trades | Win rate | Net per trade | Avg win / avg loss | PF | t | Cluster t | Random picks | p raw | Drawdown | Decision |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 795 | 49.6% | +0.724% | +9.76% / -8.15% | 1.18 | 1.69 | 1.20 | +0.807% | 0.605220 | 16.7R | **REJECTED** |

| # | Criterion | Value | Result |
|---|---|---|---|
| 1 | At least 50 trades | 795 | pass |
| 2 | Win rate at least 50% | 49.6% | **fail** |
| 3 | Expectancy above 0 at base and 1.5x costs | +0.7244% / +0.4142% | pass |
| 4 | t-statistic at least 2.0 | 1.69 | **fail** |
| 5 | Beats the random baseline: Holm-adjusted p below 0.05 | 0.60522 | **fail** |
| 6 | Profit factor at least 1.3 | 1.18 | **fail** |
| 7 | Average loss at most 1.5x the average win; no trade worse than -3R | -8.152% vs +9.758% (0.84x); worst -1.48R | pass |
| 8 | Expectancy above 0 in each half of the span | +0.6639% / +0.7841% (split 2020-01-29) | pass |
| 9 | At least 70% of calendar years with 10+ trades profitable | 71% of 14 years | pass |
| 10 | At least 60% of stocks with 5+ trades profitable; expectancy above 0 without the top stock | 59% of 54 stocks; +0.6250% without SAIL | **fail** |
| 11 | Cluster-robust t-statistic (signal months as clusters) at least 2.0 | 1.20 | **fail** |
| 12 | Raw random-baseline p below 0.05/67 = 0.000746 | 0.605220 | **fail** |
| 13 | Drawdown no deeper than 20R (cumulative R in exit order) | 16.7R | pass |

Informational (not part of any decision):

- Beat random picks by -0.084% a trade (month-clustered t -0.20).
- Dividends added +0.100% a trade; price-only net +0.624%.
- Net per trade at 0x / 1x / 1.5x / 2x / 3x costs: +1.144% / +0.724% / +0.514% / +0.304% / -0.115%.
- Stops: 123, of which 11 filled at a gap.
- By tier: N1: 473 trades, net +1.087%; N2: 322 trades, net +0.192%.

| Year | Trades | Net per trade | Beat random by |
|---|---:|---:|---:|
| 2013 | 35 | +2.026% | +1.228% |
| 2014 | 60 | +1.962% | -1.922% |
| 2015 | 60 | -1.559% | +0.437% |
| 2016 | 60 | +2.137% | +0.767% |
| 2017 | 60 | +0.847% | -0.975% |
| 2018 | 60 | -1.841% | +0.023% |
| 2019 | 60 | +1.642% | +1.744% |
| 2020 | 60 | +0.174% | -2.277% |
| 2021 | 60 | +0.862% | -1.323% |
| 2022 | 60 | -1.483% | -0.929% |
| 2023 | 60 | +4.914% | +2.072% |
| 2024 | 60 | +0.579% | +0.560% |
| 2025 | 60 | +0.332% | +0.067% |
| 2026 | 40 | -0.225% | -0.103% |

Patterns in the informational sections are hypotheses for future data, not findings.
