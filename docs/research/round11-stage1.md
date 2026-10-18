# Research round 11, stage 1 (development; decides nothing)

Run on 2026-10-18 23:51 IST by `python -m trader.research.round11 --stage 1` (runner SHA-256 `3f67b85f90e77484...`), against [the pre-registration](round11-preregistration.md) (SHA-256 `a2b4c2b8efb5bbf4...`), the F&O manifests (`d99ffe9c...`, `aa94ce3b...`) and round 8's panel (`afb79ad2...`). Total returns after costs (Rs 33,333 positions, 15% stop).

Signals 2008-01-31 to 2013-05-31: 325 trades; stocks with the signal per month: median 73.

| Trades | Win rate | Net per trade | Avg win / avg loss | PF | t | Cluster t | Random picks | p raw | Drawdown | |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 325 | 45.2% | +0.722% | +13.86% / -10.13% | 1.13 | 0.80 | 0.45 | -0.297% | 0.029249 | 26.0R | (stage 1) |

| # | Criterion | Value | Result |
|---|---|---|---|
| 1 | At least 50 trades | 325 | pass |
| 2 | Win rate at least 50% | 45.2% | **fail** |
| 3 | Expectancy above 0 at base and 1.5x costs | +0.7215% / +0.4285% | pass |
| 4 | t-statistic at least 2.0 | 0.80 | **fail** |
| 5 | Beats the random baseline: Holm-adjusted p below 0.05 | 0.02925 | pass |
| 6 | Profit factor at least 1.3 | 1.13 | **fail** |
| 7 | Average loss at most 1.5x the average win; no trade worse than -3R | -10.129% vs +13.861% (0.73x); worst -1.52R | pass |
| 8 | Expectancy above 0 in each half of the span | +1.9979% / -0.5162% (split 2010-09-30) | **fail** |
| 9 | At least 70% of calendar years with 10+ trades profitable | 50% of 6 years | **fail** |
| 10 | At least 60% of stocks with 5+ trades profitable; expectancy above 0 without the top stock | 56% of 16 stocks; +0.3702% without HDIL | **fail** |
| 11 | Cluster-robust t-statistic (signal months as clusters) at least 2.0 | 0.45 | **fail** |
| 12 | Raw random-baseline p below 0.05/67 = 0.000746 | 0.029249 | **fail** |
| 13 | Drawdown no deeper than 20R (cumulative R in exit order) | 26.0R | **fail** |

Informational (not part of any decision):

- Beat random picks by +1.015% a trade (month-clustered t 1.36).
- Dividends added +0.089% a trade; price-only net +0.632%.
- Net per trade at 0x / 1x / 1.5x / 2x / 3x costs: +1.129% / +0.722% / +0.518% / +0.314% / -0.094%.
- Stops: 88, of which 4 filled at a gap.
- By tier: N1: 251 trades, net +1.243%; N2: 74 trades, net -1.047%.

| Year | Trades | Net per trade | Beat random by |
|---|---:|---:|---:|
| 2008 | 60 | -3.393% | +0.319% |
| 2009 | 60 | +7.533% | +2.056% |
| 2010 | 60 | -1.109% | -0.385% |
| 2011 | 60 | -1.992% | -0.488% |
| 2012 | 60 | +2.846% | +2.629% |
| 2013 | 25 | +0.055% | +3.279% |

Patterns in the informational sections are hypotheses for future data, not findings.
