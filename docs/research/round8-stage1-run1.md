# Research round 8, stage 1 (development and replication, decides nothing)

Run on 2026-10-14 01:40 IST by `python -m trader.research.round8 --stage 1` (runner SHA-256 `c25910deb71bcb78...`), against [the pre-registration](round8-preregistration.md) (SHA-256 `ea4a3c0c281eed61...`) and the frozen panel `data/round8/nse_eq` (SHA-256 `afb79ad2ce778f18...`). Every hypothesis is reported. Returns are per trade, net of costs: N1 0.3532% a round trip, N2 0.4532% a round trip.

## Summary

| Hypothesis | Trades | Wins / losses | Win rate | Net per trade | Median | Avg win / avg loss | t | Cluster t | Random picks (same rules) | p raw / Holm | Drawdown | |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| N1: 12-1 month momentum, top 5 of the 100 most liquid NSE stocks, monthly | 440 | 204 / 236 | 46.4% | +0.219% | -2.008% | +10.95% / -9.06% | 0.37 | 0.26 | -0.060% | 0.27794 / 0.27794 | 37.8R | (stage 1) |
| N2: 12-1 month momentum, top 5 of liquidity ranks 101-300, monthly | 438 | 176 / 262 | 40.2% | +0.864% | -4.248% | +16.05% / -9.33% | 1.08 | 0.74 | +0.053% | 0.07605 / 0.15209 | 51.0R | (stage 1) |

## The criteria (stage 1: reported, not applied)

| # | Criterion | N1 | N2 |
|---|---|---|---|
| 1 | At least 50 trades | 440 (pass) | 438 (pass) |
| 2 | Win rate at least 50% | 46.4% (**fail**) | 40.2% (**fail**) |
| 3 | Expectancy above 0 at base and 1.5x costs | +0.2191% / +0.0320% (pass) | +0.8639% / +0.6138% (pass) |
| 4 | t-statistic at least 2.0 | 0.37 (**fail**) | 1.08 (**fail**) |
| 5 | Beats the random baseline: Holm-adjusted p below 0.05 | 0.27794 (**fail**) | 0.15209 (**fail**) |
| 6 | Profit factor at least 1.3 | 1.05 (**fail**) | 1.15 (**fail**) |
| 7 | Average loss at most 1.5x the average win; no trade worse than -3R | -9.056% vs +10.949% (0.83x); worst -1.68R (pass) | -9.335% vs +16.046% (0.58x); worst -1.88R (pass) |
| 8 | Expectancy above 0 in each half of the span | +0.2143% / +0.2229% (split 2009-04-01) (pass) | +0.3714% / +1.2343% (split 2009-04-01) (pass) |
| 9 | At least 70% of calendar years with 10+ trades profitable | 62% of 8 years (**fail**) | 75% of 8 years (pass) |
| 10 | At least 60% of stocks with 5+ trades profitable; expectancy above 0 without the top stock | 58% of 36 stocks; -0.1387% without INDIABULLS (**fail**) | 60% of 35 stocks; +0.4936% without UNITECH (pass) |
| 11 | Cluster-robust t-statistic (signal months as clusters) at least 2.0 | 0.26 (**fail**) | 0.74 (**fail**) |
| 12 | Raw random-baseline p below 0.05/25 = 0.0020 | 0.27794 (**fail**) | 0.07605 (**fail**) |
| 13 | Drawdown no deeper than 20R (cumulative R in exit order) | 37.8R (**fail**) | 51.0R (**fail**) |

## N1: 12-1 month momentum, top 5 of the 100 most liquid NSE stocks, monthly

Signals 2005-01-31 to 2013-05-31 (101 months). Mean net +0.219% a trade against -0.060% for 5 random stocks from the same tier with the same rules (p = 0.27794, Holm 0.27794).

Informational (not part of any decision):

- Win rate 95% interval (Wilson): 41.8% to 51.0%. Mean net per month of picks, 95% interval (month-block bootstrap): -1.527% to +2.007%.
- Monthly excess of the picks over the random-pick expectation: +0.274% (95% interval -1.094% to +1.557%). The dividends missing from price returns lower the baseline by at most about 0.08% a month.
- Stops: 186, of which 16 filled at a gap. Picks kept from one month to the next: 34% of trades.
- Net per trade at 0x / 1x / 1.5x / 2x / 3x costs: +0.593% / +0.219% / +0.032% / -0.155% / -0.529% / +0.344%.
- With a 30% haircut on trades that ended at a last close: 440 trades, 46.4% winners, +0.219% a trade, t 0.37.
- The account at the engine's size (Rs 10,00,000, 5 x 5%), marked daily: final Rs 1,031,199, deepest drawdown -18.8%; the 10% kill switch would have engaged on 2006-07-19.
- Deflated Sharpe ratio of the monthly excess: 0.404 (Sharpe 0.15 a year; probability it beats zero 0.652; 25 trials, variant Sharpe variance 0.0012).
- Probability of backtest overfitting across the 12 variants: 0.78 (12870 combinations).

| Portfolio (monthly) | CAGR | Volatility | Sharpe | Sortino | Max drawdown |
|---|---:|---:|---:|---:|---:|
| engine size (5 x 5%) | +0.4% | +7.0% | 0.09 | 0.15 | -17.0% |
| fully invested (5 x 20%) | -1.1% | +27.8% | 0.09 | 0.15 | -54.3% |
| tier average, bought and held (no stop, no costs) | +2.7% | +37.0% | 0.25 | 0.40 | -68.5% |
| NIFTY 50 price index | +0.7% | +29.1% | 0.17 | 0.25 | -56.8% |

| Variant (sensitivity, never used to choose) | Trades | Win rate | Net per trade | Monthly excess over random |
|---|---:|---:|---:|---:|
| 6-1, top 5, stop 10% | 440 | 42.7% | +0.064% | +0.119% |
| 6-1, top 5, no stop | 440 | 53.9% | +1.165% | +0.737% |
| 6-1, top 10, stop 10% | 880 | 42.7% | -0.116% | -0.061% |
| 6-1, top 10, no stop | 880 | 52.4% | +0.880% | +0.452% |
| 9-1, top 5, stop 10% | 440 | 43.6% | +0.425% | +0.479% |
| 9-1, top 5, no stop | 440 | 52.7% | +0.496% | +0.068% |
| 9-1, top 10, stop 10% | 880 | 43.8% | +0.168% | +0.223% |
| 9-1, top 10, no stop | 880 | 52.4% | +0.693% | +0.265% |
| 12-1, top 5, stop 10% | 440 | 46.4% | +0.219% | +0.274% |
| 12-1, top 5, no stop | 440 | 54.1% | +0.563% | +0.135% |
| 12-1, top 10, stop 10% | 880 | 45.1% | +0.156% | +0.210% |
| 12-1, top 10, no stop | 880 | 53.2% | +0.393% | -0.035% |
- NIFTY above its 200-session average: yes: 190 trades, 54.2% winners, +0.667% a trade, t 0.93; no: 155 trades, 36.1% winners, -2.031% a trade, t -2.12.
- India VIX above its 250-session median: yes: 105 trades, 45.7% winners, -0.875% a trade, t -0.83; no: 210 trades, 48.6% winners, -0.239% a trade, t -0.34.

| Year | Trades | Net per trade |
|---|---:|---:|
| 2006 | 55 | +2.261% |
| 2007 | 60 | +3.180% |
| 2008 | 60 | -4.973% |
| 2009 | 60 | +2.195% |
| 2010 | 60 | +0.818% |
| 2011 | 60 | -1.955% |
| 2012 | 60 | +1.841% |
| 2013 | 25 | -3.771% |

## N2: 12-1 month momentum, top 5 of liquidity ranks 101-300, monthly

Signals 2005-01-31 to 2013-05-31 (101 months). Mean net +0.864% a trade against +0.053% for 5 random stocks from the same tier with the same rules (p = 0.07605, Holm 0.15209).

Informational (not part of any decision):

- Win rate 95% interval (Wilson): 35.7% to 44.8%. Mean net per month of picks, 95% interval (month-block bootstrap): -1.441% to +2.888%.
- Monthly excess of the picks over the random-pick expectation: +0.791% (95% interval -1.220% to +2.553%). The dividends missing from price returns lower the baseline by at most about 0.08% a month.
- Stops: 206, of which 37 filled at a gap. Picks kept from one month to the next: 29% of trades.
- Net per trade at 0x / 1x / 1.5x / 2x / 3x costs: +1.364% / +0.864% / +0.614% / +0.364% / -0.136% / +1.000%.
- With a 30% haircut on trades that ended at a last close: 438 trades, 40.0% winners, +0.794% a trade, t 0.99.
- The account at the engine's size (Rs 10,00,000, 5 x 5%), marked daily: final Rs 1,171,076, deepest drawdown -23.8%; the 10% kill switch would have engaged on 2008-04-01.
- Deflated Sharpe ratio of the monthly excess: 0.533 (Sharpe 0.27 a year; probability it beats zero 0.759; 25 trials, variant Sharpe variance 0.0012).
- Probability of backtest overfitting across the 12 variants: 0.81 (12870 combinations).

| Portfolio (monthly) | CAGR | Volatility | Sharpe | Sortino | Max drawdown |
|---|---:|---:|---:|---:|---:|
| engine size (5 x 5%) | +2.2% | +9.4% | 0.27 | 0.52 | -22.6% |
| fully invested (5 x 20%) | +4.0% | +37.6% | 0.27 | 0.52 | -65.8% |
| tier average, bought and held (no stop, no costs) | +1.3% | +39.5% | 0.22 | 0.35 | -74.0% |
| NIFTY 50 price index | +0.7% | +29.1% | 0.17 | 0.25 | -56.8% |

| Variant (sensitivity, never used to choose) | Trades | Win rate | Net per trade | Monthly excess over random |
|---|---:|---:|---:|---:|
| 6-1, top 5, stop 10% | 437 | 40.5% | +0.300% | +0.215% |
| 6-1, top 5, no stop | 437 | 49.4% | +0.219% | -0.185% |
| 6-1, top 10, stop 10% | 876 | 41.1% | +0.314% | +0.252% |
| 6-1, top 10, no stop | 876 | 49.1% | +0.579% | +0.240% |
| 9-1, top 5, stop 10% | 437 | 41.6% | +0.926% | +0.836% |
| 9-1, top 5, no stop | 437 | 49.9% | +1.430% | +1.063% |
| 9-1, top 10, stop 10% | 877 | 41.2% | +0.502% | +0.452% |
| 9-1, top 10, no stop | 877 | 49.6% | +0.780% | +0.465% |
| 12-1, top 5, stop 10% | 438 | 40.2% | +0.864% | +0.791% |
| 12-1, top 5, no stop | 438 | 49.5% | +0.933% | +0.554% |
| 12-1, top 10, stop 10% | 878 | 40.2% | +0.371% | +0.332% |
| 12-1, top 10, no stop | 878 | 49.3% | +0.325% | +0.010% |
- NIFTY above its 200-session average: yes: 190 trades, 46.8% winners, +1.665% a trade, t 1.69; no: 155 trades, 27.7% winners, -3.165% a trade, t -3.01.
- India VIX above its 250-session median: yes: 105 trades, 42.9% winners, +0.277% a trade, t 0.21; no: 210 trades, 39.0% winners, -0.152% a trade, t -0.16.

| Year | Trades | Net per trade |
|---|---:|---:|
| 2006 | 53 | +5.871% |
| 2007 | 60 | +2.979% |
| 2008 | 60 | -6.893% |
| 2009 | 60 | +2.772% |
| 2010 | 60 | +2.025% |
| 2011 | 60 | +0.076% |
| 2012 | 60 | +1.031% |
| 2013 | 25 | -2.087% |

Trades that ended at a suspension or a last close:

| Stock | Signal | Entry | Exit | How | Gross |
|---|---|---|---|---|---:|
| UTVSOF | 2012-02-29 | 2012-03-01 | 2012-03-07 | no further rows | +2.2% |

Patterns in the informational sections are hypotheses for future data, not findings.
