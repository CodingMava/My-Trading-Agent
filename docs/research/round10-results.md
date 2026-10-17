# Research round 10 results: results drift, promoter buying, and the two combined

Run on 2026-10-17 18:00 IST by `python -m trader.research.round10 --stage 2` (runner SHA-256 `21f3bba31e2aa179...`), against [the pre-registration](round10-preregistration.md) (SHA-256 `c973d560263b7caa...`), the board-meeting and insider manifests (`1e7accb2...`, `4955502b...`) and round 8's frozen panel (`afb79ad2...`). Every hypothesis is reported. Returns are per trade, net of costs (Rs 33,333 positions, 15% stop, R = 15%).

## Summary

| Hypothesis | Entries | Trades | Win rate | Net per trade | Avg win / avg loss | PF | t | Cluster t | Random picks | p raw / Holm | Drawdown | Decision |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| E2: Drift after a strong results reaction (top 10%), 40 sessions, 15% stop, 5 positions | 2013-06-03 to 2026-07-31 | 313 | 55.0% | +2.329% | +13.30% / -11.05% | 1.47 | 2.65 | 2.08 | +0.832% | 0.029649 / 0.088946 | 17.3R | **REJECTED** |
| Q: Promoter open-market purchases of Rs 10 lakh+, 40 sessions, 15% stop, 5 positions | 2018-01-01 to 2026-03-31 | 230 | 50.0% | +1.333% | +13.58% / -10.92% | 1.24 | 1.30 | 1.09 | +0.886% | 0.309485 / 0.360182 | 17.1R | **REJECTED** |
| M: E2 and Q in one account sharing 5 positions (E2 first) | 2018-01-01 to 2026-03-31 | 288 | 53.8% | +1.881% | +13.34% / -11.47% | 1.35 | 2.08 | 1.69 | +1.150% | 0.180091 / 0.360182 | 15.4R | **REJECTED** |

## The criteria

| # | Criterion | E2 | Q | M |
|---|---|---|---|---|
| 1 | At least 50 trades | 313 (pass) | 230 (pass) | 288 (pass) |
| 2 | Win rate at least 50% | 55.0% (pass) | 50.0% (pass) | 53.8% (pass) |
| 3 | Expectancy above 0 at base and 1.5x costs | +2.3289% / +2.1042% (pass) | +1.3328% / +1.1014% (pass) | +1.8806% / +1.6524% (pass) |
| 4 | t-statistic at least 2.0 | 2.65 (pass) | 1.30 (**fail**) | 2.08 (pass) |
| 5 | Beats the random baseline: Holm-adjusted p below 0.05 | 0.08895 (**fail**) | 0.36018 (**fail**) | 0.36018 (**fail**) |
| 6 | Profit factor at least 1.3 | 1.47 (pass) | 1.24 (**fail**) | 1.35 (pass) |
| 7 | Average loss at most 1.5x the average win; no trade worse than -3R | -11.055% vs +13.300% (0.83x); worst -1.41R (pass) | -10.919% vs +13.584% (0.80x); worst -1.30R (pass) | -11.473% vs +13.339% (0.86x); worst -1.36R (pass) |
| 8 | Expectancy above 0 in each half of the span | +2.9067% / +1.7548% (split 2020-01-01) (pass) | +2.4736% / -0.2313% (split 2022-02-14) (**fail**) | +2.0832% / +1.6511% (split 2022-02-14) (pass) |
| 9 | At least 70% of calendar years with 10+ trades profitable | 71% of 14 years (pass) | 50% of 8 years (**fail**) | 75% of 8 years (pass) |
| 10 | At least 60% of stocks with 5+ trades profitable; expectancy above 0 without the top stock | 67% of 6 stocks; +2.1249% without TATAELXSI (pass) | 70% of 10 stocks; +0.9513% without CHAMBLFERT (pass) | 83% of 6 stocks; +1.6671% without MASTEK (pass) |
| 11 | Cluster-robust t-statistic (entry months as clusters) at least 2.0 | 2.08 (pass) | 1.09 (**fail**) | 1.69 (**fail**) |
| 12 | Raw random-baseline p below 0.05/57 = 0.000877 | 0.029649 (**fail**) | 0.309485 (**fail**) | 0.180091 (**fail**) |
| 13 | Drawdown no deeper than 20R (cumulative R in exit order) | 17.3R (pass) | 17.1R (pass) | 15.4R (pass) |

## E2: Drift after a strong results reaction (top 10%), 40 sessions, 15% stop, 5 positions

**Decision: REJECTED.**

Informational (not part of any decision):

- Edge over random picks: +1.501% a trade (month-clustered t 1.77).
- Stops: 79, of which 8 filled at a gap.
- Net per trade at 0x / 1x / 1.5x / 2x / 3x costs: +2.778% / +2.329% / +2.104% / +1.879% / +1.430%.
- By part: E2: 313 trades, net +2.329%, edge +1.501%, win 55.0%.
- By tier: N1: 123 trades, net +1.415%, edge +0.839%; N2: 190 trades, net +2.921%, edge +1.929%.
- E2 with every qualifying event (no position cap): 1597 trades, net +3.381%, win 55.7%, edge over random +1.761%.

| Year | Trades | Net per trade | E2 every event |
|---|---:|---:|---:|
| 2013 | 11 | +4.307% | +3.677% |
| 2014 | 21 | +12.832% | +11.408% |
| 2015 | 23 | +10.202% | +0.724% |
| 2016 | 26 | -3.401% | +3.424% |
| 2017 | 25 | +3.725% | +4.171% |
| 2018 | 25 | -5.829% | -1.909% |
| 2019 | 25 | +1.720% | +2.444% |
| 2020 | 29 | +3.014% | +4.097% |
| 2021 | 22 | +2.672% | +5.477% |
| 2022 | 26 | +1.564% | -1.691% |
| 2023 | 20 | +3.779% | +8.724% |
| 2024 | 22 | +4.949% | +3.822% |
| 2025 | 20 | -0.686% | +1.857% |
| 2026 | 18 | -4.559% | +0.444% |

Largest trades:

| Part | Stock | Entry | Exit | How | Net |
|---|---|---|---|---|---:|
| E2 | DISHMAN | 2015-09-02 | 2015-11-03 | time | +69.3% |
| E2 | UNIONBANK | 2022-10-24 | 2022-12-21 | time | +68.6% |
| E2 | DHANI | 2020-06-29 | 2020-08-24 | time | +55.4% |
| E2 | RIIL | 2020-04-24 | 2020-06-23 | time | +48.1% |
| E2 | MINDTREE | 2021-07-15 | 2021-09-14 | time | +45.7% |
| E2 | CHOLAFIN | 2020-11-02 | 2020-12-30 | time | +41.3% |
| E2 | TATAELXSI | 2015-01-23 | 2015-03-24 | time | +38.3% |
| E2 | EMBDL | 2014-04-28 | 2014-06-24 | time | +37.1% |
| E2 | SUZLON | 2024-07-24 | 2024-09-19 | time | +36.7% |
| E2 | TATAELXSI | 2014-01-29 | 2014-03-27 | time | +35.8% |

## Q: Promoter open-market purchases of Rs 10 lakh+, 40 sessions, 15% stop, 5 positions

**Decision: REJECTED.**

Informational (not part of any decision):

- Edge over random picks: +0.447% a trade (month-clustered t 0.52).
- Stops: 62, of which 6 filled at a gap.
- Net per trade at 0x / 1x / 1.5x / 2x / 3x costs: +1.796% / +1.333% / +1.101% / +0.870% / +0.407%.
- By part: Q: 230 trades, net +1.333%, edge +0.447%, win 50.0%.
- By tier: N1: 69 trades, net +3.503%, edge +1.187%; N2: 161 trades, net +0.403%, edge +0.131%.
- Q with every qualifying event (no position cap): 587 trades, net +2.273%, win 51.4%, edge over random +0.367%.

| Year | Trades | Net per trade | Q every event |
|---|---:|---:|---:|
| 2018 | 40 | -0.554% | -1.600% |
| 2019 | 27 | +0.326% | +2.277% |
| 2020 | 36 | +4.982% | +6.051% |
| 2021 | 26 | +6.374% | +4.525% |
| 2022 | 30 | -1.624% | -0.276% |
| 2023 | 21 | +4.319% | +3.473% |
| 2024 | 22 | -0.004% | +1.212% |
| 2025 | 21 | -1.794% | -0.321% |
| 2026 | 7 | -4.195% | -6.077% |

Largest trades:

| Part | Stock | Entry | Exit | How | Net |
|---|---|---|---|---|---:|
| Q | JUSTDIAL | 2020-09-29 | 2020-11-25 | time | +63.3% |
| Q | CGPOWER | 2021-02-15 | 2021-04-16 | time | +55.1% |
| Q | MASTEK | 2021-03-24 | 2021-05-26 | time | +53.7% |
| Q | CCAVENUE | 2018-07-10 | 2018-09-06 | time | +51.7% |
| Q | SUNTECK | 2019-02-04 | 2019-04-03 | time | +38.5% |
| Q | UPL | 2020-11-25 | 2021-01-22 | time | +36.2% |
| Q | SUNPHARMA | 2020-03-13 | 2020-05-15 | time | +33.3% |
| Q | CHAMBLFERT | 2022-02-16 | 2022-04-19 | time | +32.5% |
| Q | LUPIN | 2020-04-07 | 2020-06-08 | time | +30.8% |
| Q | ABFRL | 2021-08-24 | 2021-10-21 | time | +29.1% |

## M: E2 and Q in one account sharing 5 positions (E2 first)

**Decision: REJECTED.**

Informational (not part of any decision):

- Edge over random picks: +0.732% a trade (month-clustered t 0.93).
- Stops: 81, of which 8 filled at a gap.
- Net per trade at 0x / 1x / 1.5x / 2x / 3x costs: +2.337% / +1.881% / +1.652% / +1.424% / +0.968%.
- By part: E2: 131 trades, net +2.113%, edge +0.723%, win 54.2%; Q: 157 trades, net +1.686%, edge +0.739%, win 53.5%.
- By tier: N1: 106 trades, net +3.647%, edge +1.741%; N2: 182 trades, net +0.852%, edge +0.144%.
- E2 with every qualifying event (no position cap): 995 trades, net +2.594%, win 54.2%, edge over random +1.600%.
- Q with every qualifying event (no position cap): 587 trades, net +2.273%, win 51.4%, edge over random +0.367%.

| Year | Trades | Net per trade | E2 every event | Q every event |
|---|---:|---:|---:|---:|
| 2018 | 38 | -2.425% | -1.909% | -1.600% |
| 2019 | 35 | +2.307% | +2.444% | +2.277% |
| 2020 | 38 | +5.996% | +4.097% | +6.051% |
| 2021 | 38 | +3.737% | +5.477% | +4.525% |
| 2022 | 41 | -3.478% | -1.691% | -0.276% |
| 2023 | 28 | +8.833% | +8.724% | +3.473% |
| 2024 | 31 | +0.888% | +3.822% | +1.212% |
| 2025 | 31 | +2.749% | +1.857% | -0.321% |
| 2026 | 8 | -4.287% | -5.573% | -6.077% |

Largest trades:

| Part | Stock | Entry | Exit | How | Net |
|---|---|---|---|---|---:|
| Q | JUSTDIAL | 2020-09-23 | 2020-11-19 | time | +67.2% |
| Q | MASTEK | 2021-03-24 | 2021-05-26 | time | +53.7% |
| E2 | MINDTREE | 2021-07-15 | 2021-09-14 | time | +45.7% |
| E2 | GAIL | 2020-11-12 | 2021-01-11 | time | +42.6% |
| Q | JINDALSAW | 2023-06-23 | 2023-08-22 | time | +41.7% |
| E2 | LAURUSLABS | 2020-08-03 | 2020-09-28 | time | +41.4% |
| Q | PERSISTENT | 2020-11-20 | 2021-01-19 | time | +39.2% |
| Q | SUNTECK | 2019-02-04 | 2019-04-03 | time | +38.5% |
| E2 | NIITLTD | 2021-11-12 | 2022-01-10 | time | +34.8% |
| Q | SUNPHARMA | 2020-03-13 | 2020-05-15 | time | +33.3% |

Patterns in the informational sections are hypotheses for future data, not findings.
