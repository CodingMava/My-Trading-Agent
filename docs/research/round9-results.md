# Research round 9 results: low volatility and volatility-adjusted momentum on the NSE universe

Run on 2026-10-14 23:52 IST by `python -m trader.research.round9 --stage 2` (runner SHA-256 `23d80754878d4a99...`), against [the pre-registration](round9-preregistration.md) (SHA-256 `2f35fd4b44e1b9ef...`) and round 8's frozen panel (SHA-256 `afb79ad2ce778f18...`). Every hypothesis is reported. Returns are per trade, net of round 8's costs.

## Summary

| Hypothesis | Trades | Wins / losses | Win rate | Net per trade | Median | Avg win / avg loss | t | Cluster t | Random picks (same rules) | p raw / Holm | Drawdown | Decision |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| L1: Low volatility: the 5 least volatile of the 100 most liquid NSE stocks, monthly | 795 | 409 / 386 | 51.4% | +0.577% | +0.225% | +5.82% / -4.97% | 2.36 | 1.62 | +0.522% | 0.42743 / 0.85486 | 17.1R | **REJECTED** |
| L2: Low volatility: the 5 least volatile of liquidity ranks 101-300, monthly | 795 | 419 / 376 | 52.7% | +0.671% | +0.321% | +5.43% / -4.64% | 2.85 | 2.05 | +0.679% | 0.50437 / 0.85486 | 12.9R | **REJECTED** |
| V2: Volatility-adjusted momentum: the top 5 of liquidity ranks 101-300, monthly | 791 | 363 / 428 | 45.9% | +2.068% | -2.685% | +15.55% / -9.36% | 3.51 | 2.57 | +0.669% | 0.00020 / 0.00060 | 30.4R | **REJECTED** |

## The criteria

| # | Criterion | L1 | L2 | V2 |
|---|---|---|---|---|
| 1 | At least 50 trades | 795 (pass) | 795 (pass) | 791 (pass) |
| 2 | Win rate at least 50% | 51.4% (pass) | 52.7% (pass) | 45.9% (**fail**) |
| 3 | Expectancy above 0 at base and 1.5x costs | +0.5772% / +0.3980% (pass) | +0.6706% / +0.4394% (pass) | +2.0677% / +1.8203% (pass) |
| 4 | t-statistic at least 2.0 | 2.36 (pass) | 2.85 (pass) | 3.51 (pass) |
| 5 | Beats the random baseline: Holm-adjusted p below 0.05 | 0.85486 (**fail**) | 0.85486 (**fail**) | 0.00060 (pass) |
| 6 | Profit factor at least 1.3 | 1.24 (**fail**) | 1.31 (pass) | 1.41 (pass) |
| 7 | Average loss at most 1.5x the average win; no trade worse than -3R | -4.975% vs +5.817% (0.86x); worst -1.53R (pass) | -4.635% vs +5.432% (0.85x); worst -1.46R (pass) | -9.364% vs +15.546% (0.60x); worst -2.64R (pass) |
| 8 | Expectancy above 0 in each half of the span | +0.8565% / +0.3015% (split 2020-01-29) (pass) | +0.4359% / +0.9024% (split 2020-01-29) (pass) | +0.8670% / +3.2653% (split 2020-01-29) (pass) |
| 9 | At least 70% of calendar years with 10+ trades profitable | 57% of 14 years (**fail**) | 71% of 14 years (pass) | 64% of 14 years (**fail**) |
| 10 | At least 60% of stocks with 5+ trades profitable; expectancy above 0 without the top stock | 70% of 27 stocks; +0.5359% without HINDUNILVR (pass) | 67% of 36 stocks; +0.6311% without COLPAL (pass) | 80% of 46 stocks; +1.8487% without CUPID (pass) |
| 11 | Cluster-robust t-statistic (signal months as clusters) at least 2.0 | 1.62 (**fail**) | 2.05 (pass) | 2.57 (pass) |
| 12 | Raw random-baseline p below 0.05/28 = 0.00179 | 0.42743 (**fail**) | 0.50437 (**fail**) | 0.00020 (pass) |
| 13 | Drawdown no deeper than 20R (cumulative R in exit order) | 17.1R (pass) | 12.9R (pass) | 30.4R (**fail**) |

## L1: Low volatility: the 5 least volatile of the 100 most liquid NSE stocks, monthly

Signals 2013-06-28 to 2026-08-31 (159 months with trades). Mean net +0.577% a trade against +0.522% for 5 random stocks from the same tier with the same rules (p = 0.42743, Holm 0.85486).

**Decision: REJECTED.**

Informational (not part of any decision):

- Win rate 95% interval (Wilson): 48.0% to 54.9%. Mean net per month of picks, 95% interval (month-block bootstrap): -0.082% to +1.247%.
- Monthly excess over the random-pick expectation: +0.057% (95% interval -0.586% to +0.693%).
- Stops: 84, of which 16 filled at a gap.
- Net per trade at 0x / 1x / 1.5x / 2x / 3x costs: +0.936% / +0.577% / +0.398% / +0.219% / -0.140%.
- The account at the engine's size (Rs 10,00,000, 5 x 5%), marked daily: final Rs 1,245,265, deepest drawdown -8.6%; the 10% kill switch never engaged.
- Deflated Sharpe ratio of the monthly excess: 0.340 (Sharpe 0.05 a year; 28 trials).

| Portfolio (monthly) | CAGR | Volatility | Sharpe | Sortino | Max drawdown |
|---|---:|---:|---:|---:|---:|
| engine size (5 x 5%) | +1.7% | +3.9% | 0.45 | 0.71 | -8.3% |
| fully invested (5 x 20%) | +5.9% | +15.6% | 0.45 | 0.71 | -30.5% |
| tier average, bought and held (no stop, no costs) | +11.9% | +20.5% | 0.66 | 1.01 | -49.4% |
| NIFTY 50 price index | +12.8% | +15.8% | 0.85 | 1.30 | -24.6% |

| Variant (sensitivity, never used to choose) | Trades | Win rate | Net per trade | Monthly excess over random |
|---|---:|---:|---:|---:|
| 10 picks | 1590 | 51.4% | +0.400% | -0.120% |
| no stop | 795 | 51.9% | +0.710% | -0.055% |
- NIFTY above its 200-session average: yes: 585 trades, 50.8% winners, +0.499% a trade, t 1.88; no: 210 trades, 53.3% winners, +0.796% a trade, t 1.44.
- India VIX above its 250-session median: yes: 395 trades, 52.7% winners, +0.613% a trade, t 1.63; no: 400 trades, 50.2% winners, +0.542% a trade, t 1.73.

| Year | Trades | Net per trade |
|---|---:|---:|
| 2013 | 35 | +0.503% |
| 2014 | 60 | +3.042% |
| 2015 | 60 | -0.937% |
| 2016 | 60 | -0.012% |
| 2017 | 60 | +3.285% |
| 2018 | 60 | -0.681% |
| 2019 | 60 | +0.648% |
| 2020 | 60 | +2.318% |
| 2021 | 60 | +0.964% |
| 2022 | 60 | -0.886% |
| 2023 | 60 | +1.259% |
| 2024 | 60 | +0.026% |
| 2025 | 60 | -0.272% |
| 2026 | 40 | -2.098% |

Trades entering or exiting on a demerger-type ex-date, or filled at an open more than 8% from that session's close (listed, not changed): 4.

| Stock | Entry | Exit | How | Gross | Why |
|---|---|---|---|---:|---|
| ITC | 2020-01-01 | 2020-02-01 | time | -0.7% | exit +8.2% from the close |
| ITC | 2020-02-01 | 2020-02-03 | stop | -10.0% | entry +8.2% from the close |
| ITC | 2025-12-01 | 2026-01-01 | time | -0.0% | exit +10.7% from the close |
| ITC | 2026-01-01 | 2026-01-02 | stop | -10.6% | entry +10.7% from the close |

## L2: Low volatility: the 5 least volatile of liquidity ranks 101-300, monthly

Signals 2013-06-28 to 2026-08-31 (159 months with trades). Mean net +0.671% a trade against +0.679% for 5 random stocks from the same tier with the same rules (p = 0.50437, Holm 0.85486).

**Decision: REJECTED.**

Informational (not part of any decision):

- Win rate 95% interval (Wilson): 49.2% to 56.2%. Mean net per month of picks, 95% interval (month-block bootstrap): +0.120% to +1.257%.
- Monthly excess over the random-pick expectation: -0.006% (95% interval -0.752% to +0.730%).
- Stops: 74, of which 2 filled at a gap.
- Net per trade at 0x / 1x / 1.5x / 2x / 3x costs: +1.133% / +0.671% / +0.439% / +0.208% / -0.254%.
- The account at the engine's size (Rs 10,00,000, 5 x 5%), marked daily: final Rs 1,294,287, deepest drawdown -6.8%; the 10% kill switch never engaged.
- Deflated Sharpe ratio of the monthly excess: 0.151 (Sharpe -0.00 a year; 28 trials).

| Portfolio (monthly) | CAGR | Volatility | Sharpe | Sortino | Max drawdown |
|---|---:|---:|---:|---:|---:|
| engine size (5 x 5%) | +2.0% | +3.6% | 0.56 | 0.88 | -6.4% |
| fully invested (5 x 20%) | +7.3% | +14.3% | 0.56 | 0.88 | -24.6% |
| tier average, bought and held (no stop, no costs) | +17.5% | +22.3% | 0.84 | 1.30 | -48.4% |
| NIFTY 50 price index | +12.8% | +15.8% | 0.85 | 1.30 | -24.6% |

| Variant (sensitivity, never used to choose) | Trades | Win rate | Net per trade | Monthly excess over random |
|---|---:|---:|---:|---:|
| 10 picks | 1590 | 52.7% | +0.685% | +0.009% |
| no stop | 795 | 53.6% | +0.778% | -0.333% |
- NIFTY above its 200-session average: yes: 585 trades, 52.0% winners, +0.483% a trade, t 1.93; no: 210 trades, 54.8% winners, +1.194% a trade, t 2.16.
- India VIX above its 250-session median: yes: 395 trades, 54.4% winners, +1.002% a trade, t 2.87; no: 400 trades, 51.0% winners, +0.344% a trade, t 1.09.

| Year | Trades | Net per trade |
|---|---:|---:|
| 2013 | 35 | -0.076% |
| 2014 | 60 | +1.667% |
| 2015 | 60 | -0.650% |
| 2016 | 60 | +0.395% |
| 2017 | 60 | +1.268% |
| 2018 | 60 | +0.609% |
| 2019 | 60 | -0.375% |
| 2020 | 60 | +1.644% |
| 2021 | 60 | +0.804% |
| 2022 | 60 | +0.159% |
| 2023 | 60 | +2.694% |
| 2024 | 60 | +0.621% |
| 2025 | 60 | +0.465% |
| 2026 | 40 | -0.556% |

Trades entering or exiting on a demerger-type ex-date, or filled at an open more than 8% from that session's close (listed, not changed): 2.

| Stock | Entry | Exit | How | Gross | Why |
|---|---|---|---|---:|---|
| PGHH | 2020-02-01 | 2020-03-02 | time | +1.2% | entry -8.6% from the close |
| RAJESHEXPO | 2020-04-01 | 2020-05-04 | time | +5.8% | exit +8.7% from the close |

Trades that ended at a suspension or a last close:

| Stock | Signal | Entry | Exit | How | Gross |
|---|---|---|---|---|---:|
| CASTROL | 2014-01-31 | 2014-02-03 | 2014-02-26 | no further rows | -2.6% |

## V2: Volatility-adjusted momentum: the top 5 of liquidity ranks 101-300, monthly

Signals 2013-06-28 to 2026-08-31 (159 months with trades). Mean net +2.068% a trade against +0.669% for 5 random stocks from the same tier with the same rules (p = 0.00020, Holm 0.00060).

**Decision: REJECTED.**

Informational (not part of any decision):

- Win rate 95% interval (Wilson): 42.4% to 49.4%. Mean net per month of picks, 95% interval (month-block bootstrap): +0.401% to +3.811%.
- Monthly excess over the random-pick expectation: +1.378% (95% interval +0.291% to +2.570%).
- Stops: 329, of which 43 filled at a gap.
- Net per trade at 0x / 1x / 1.5x / 2x / 3x costs: +2.562% / +2.068% / +1.820% / +1.573% / +1.078%.
- The account at the engine's size (Rs 10,00,000, 5 x 5%), marked daily: final Rs 2,152,518, deepest drawdown -15.8%; the 10% kill switch would have engaged on 2015-09-04.
- Deflated Sharpe ratio of the monthly excess: 0.959 (Sharpe 0.65 a year; 28 trials).

| Portfolio (monthly) | CAGR | Volatility | Sharpe | Sortino | Max drawdown |
|---|---:|---:|---:|---:|---:|
| engine size (5 x 5%) | +6.0% | +8.7% | 0.71 | 1.44 | -13.8% |
| fully invested (5 x 20%) | +20.8% | +34.9% | 0.71 | 1.44 | -47.4% |
| tier average, bought and held (no stop, no costs) | +17.5% | +22.3% | 0.84 | 1.30 | -48.4% |
| NIFTY 50 price index | +12.8% | +15.8% | 0.85 | 1.30 | -24.6% |

| Variant (sensitivity, never used to choose) | Trades | Win rate | Net per trade | Monthly excess over random |
|---|---:|---:|---:|---:|
| 10 picks | 1585 | 47.0% | +1.971% | +1.304% |
| no stop | 791 | 52.7% | +3.074% | +1.955% |
| 12-1 / vol alone | 792 | 47.7% | +2.283% | +1.595% |
| 6-1 / vol alone | 792 | 47.7% | +2.429% | +1.755% |
- NIFTY above its 200-session average: yes: 582 trades, 45.9% winners, +1.690% a trade, t 2.72; no: 209 trades, 45.9% winners, +3.119% a trade, t 2.23.
- India VIX above its 250-session median: yes: 393 trades, 44.5% winners, +2.228% a trade, t 2.47; no: 398 trades, 47.2% winners, +1.909% a trade, t 2.51.

| Year | Trades | Net per trade |
|---|---:|---:|
| 2013 | 35 | +0.590% |
| 2014 | 60 | +5.267% |
| 2015 | 60 | -3.430% |
| 2016 | 60 | +0.078% |
| 2017 | 60 | +3.482% |
| 2018 | 60 | -1.995% |
| 2019 | 60 | +1.962% |
| 2020 | 58 | +8.766% |
| 2021 | 60 | +4.255% |
| 2022 | 58 | -1.267% |
| 2023 | 60 | +7.865% |
| 2024 | 60 | -1.705% |
| 2025 | 60 | -1.591% |
| 2026 | 40 | +8.218% |

Trades entering or exiting on a demerger-type ex-date, or filled at an open more than 8% from that session's close (listed, not changed): 26.

| Stock | Entry | Exit | How | Gross | Why |
|---|---|---|---|---:|---|
| TITAGARH | 2015-04-01 | 2015-04-24 | stop | -10.0% | entry -8.1% from the close |
| WALCHANNAG | 2015-04-01 | 2015-04-28 | stop | -13.1% | entry -9.1% from the close |
| GMBREW | 2016-03-01 | 2016-04-01 | time | +27.1% | entry -9.5% from the close |
| COSMOFIRST | 2016-03-01 | 2016-04-01 | time | +27.8% | entry -9.4% from the close |
| GODFRYPHLP | 2016-03-01 | 2016-04-01 | time | +10.1% | entry -8.4% from the close |
| GMBREW | 2016-05-02 | 2016-06-01 | time | +5.0% | exit -10.9% from the close |
| GMBREW | 2016-06-01 | 2016-07-01 | time | +8.2% | entry -10.9% from the close |
| DWARKESH | 2016-08-01 | 2016-08-12 | stop | -10.1% | entry -14.4% from the close |
| AVANTIFEED | 2017-09-01 | 2017-10-03 | time | +11.2% | exit -8.6% from the close |
| AVANTIFEED | 2017-10-03 | 2017-11-01 | time | +39.0% | entry -8.6% from the close |
| BEPL | 2017-12-01 | 2017-12-04 | stop | -12.4% | entry +8.5% from the close |
| HEGAM | 2018-01-01 | 2018-02-01 | time | +15.6% | exit +8.4% from the close |
| CGCL | 2019-08-01 | 2019-09-03 | time | -0.5% | entry -8.8% from the close; exit -11.7% from the close |
| ISEC | 2020-03-02 | 2020-03-04 | stop | -10.0% | entry +8.3% from the close |
| SUVEN | 2020-04-01 | 2020-05-04 | time | +133.4% | exit +8.7% from the close |
| AUBANK | 2020-04-01 | 2020-04-03 | stop | -10.0% | entry +10.1% from the close |
| SUVEN | 2020-05-04 | 2020-05-05 | stop | -11.5% | entry +8.7% from the close |
| IOLCP | 2020-07-01 | 2020-08-03 | time | +76.2% | entry -10.0% from the close |
| ADANIGREEN | 2020-08-03 | 2020-09-01 | time | +32.8% | exit -8.2% from the close |
| ADANIGREEN | 2020-09-01 | 2020-10-01 | time | +66.0% | entry -8.2% from the close |
| ATGL | 2021-05-03 | 2021-06-01 | time | +19.8% | entry -8.3% from the close |
| RENUKA | 2022-06-01 | 2022-06-20 | stop | -10.0% | entry -9.4% from the close |
| FORCEMOT | 2025-07-01 | 2025-07-02 | stop | -10.0% | entry +9.6% from the close |
| MTARTECH | 2026-04-01 | 2026-05-04 | time | +85.6% | exit +9.3% from the close |
| MTARTECH | 2026-05-04 | 2026-06-01 | time | +17.8% | entry +9.3% from the close; exit +11.6% from the close |
| MTARTECH | 2026-06-01 | 2026-06-01 | stop | -10.0% | entry +11.6% from the close |

Patterns in the informational sections are hypotheses for future data, not findings.
