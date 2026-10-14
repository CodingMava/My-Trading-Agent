# Research round 8 results: stock momentum on a survivorship-free NSE universe

Run on 2026-10-14 01:48 IST by `python -m trader.research.round8 --stage 2` (runner SHA-256 `54651892c8ed2682...`), against [the pre-registration](round8-preregistration.md) (SHA-256 `ea4a3c0c281eed61...`) and the frozen panel `data/round8/nse_eq` (SHA-256 `afb79ad2ce778f18...`). Every hypothesis is reported. Returns are per trade, net of costs: N1 0.3532% a round trip, N2 0.4532% a round trip.

## Summary

| Hypothesis | Trades | Wins / losses | Win rate | Net per trade | Median | Avg win / avg loss | t | Cluster t | Random picks (same rules) | p raw / Holm | Drawdown | Decision |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| N1: 12-1 month momentum, top 5 of the 100 most liquid NSE stocks, monthly | 795 | 386 / 409 | 48.6% | +0.413% | -0.588% | +10.00% / -8.63% | 1.00 | 0.72 | +0.522% | 0.63847 / 0.63847 | 45.5R | **REJECTED** |
| N2: 12-1 month momentum, top 5 of liquidity ranks 101-300, monthly | 792 | 348 / 444 | 43.9% | +1.751% | -4.680% | +16.28% / -9.63% | 2.92 | 2.21 | +0.668% | 0.00190 / 0.00380 | 34.1R | **REJECTED** |

## The criteria

| # | Criterion | N1 | N2 |
|---|---|---|---|
| 1 | At least 50 trades | 795 (pass) | 792 (pass) |
| 2 | Win rate at least 50% | 48.6% (**fail**) | 43.9% (**fail**) |
| 3 | Expectancy above 0 at base and 1.5x costs | +0.4131% / +0.2272% (pass) | +1.7515% / +1.5022% (pass) |
| 4 | t-statistic at least 2.0 | 1.00 (**fail**) | 2.92 (pass) |
| 5 | Beats the random baseline: Holm-adjusted p below 0.05 | 0.63847 (**fail**) | 0.00380 (pass) |
| 6 | Profit factor at least 1.3 | 1.09 (**fail**) | 1.32 (pass) |
| 7 | Average loss at most 1.5x the average win; no trade worse than -3R | -8.633% vs +9.998% (0.86x); worst -2.13R (pass) | -9.634% vs +16.278% (0.59x); worst -2.64R (pass) |
| 8 | Expectancy above 0 in each half of the span | -0.5239% / +1.3384% (split 2020-01-29) (**fail**) | +1.0101% / +2.4891% (split 2020-01-29) (pass) |
| 9 | At least 70% of calendar years with 10+ trades profitable | 50% of 14 years (**fail**) | 64% of 14 years (**fail**) |
| 10 | At least 60% of stocks with 5+ trades profitable; expectancy above 0 without the top stock | 58% of 66 stocks; +0.2372% without ADANIENT (**fail**) | 61% of 70 stocks; +1.5296% without CUPID (pass) |
| 11 | Cluster-robust t-statistic (signal months as clusters) at least 2.0 | 0.72 (**fail**) | 2.21 (pass) |
| 12 | Raw random-baseline p below 0.05/25 = 0.0020 | 0.63847 (**fail**) | 0.00190 (pass) |
| 13 | Drawdown no deeper than 20R (cumulative R in exit order) | 45.5R (**fail**) | 34.1R (**fail**) |

## N1: 12-1 month momentum, top 5 of the 100 most liquid NSE stocks, monthly

Signals 2013-06-28 to 2026-08-31 (159 months with trades). Mean net +0.413% a trade against +0.522% for 5 random stocks from the same tier with the same rules (p = 0.63847, Holm 0.63847).

**Decision: REJECTED.**

Informational (not part of any decision):

- Win rate 95% interval (Wilson): 45.1% to 52.0%. Mean net per month of picks, 95% interval (month-block bootstrap): -0.659% to +1.535%.
- Monthly excess of the picks over the random-pick expectation: -0.107% (95% interval -0.963% to +0.736%). The dividends missing from price returns lower the baseline by at most about 0.08% a month.
- Stops: 298, of which 26 filled at a gap. Picks kept from one month to the next: 39% of trades.
- Net per trade at 0x / 1x / 1.5x / 2x / 3x costs: +0.785% / +0.413% / +0.227% / +0.041% / -0.331%; with a stock picked again the next month kept instead of re-traded: +0.554%.
- With a 30% haircut on trades that ended at a last close: 795 trades, 48.6% winners, +0.413% a trade, t 1.00.
- The account at the engine's size (Rs 10,00,000, 5 x 5%), marked daily: final Rs 1,148,420, deepest drawdown -21.3%; the 10% kill switch would have engaged on 2016-02-11.
- Deflated Sharpe ratio of the monthly excess: 0.070 (Sharpe -0.06 a year; probability it beats zero 0.408; 25 trials, variant Sharpe variance 0.0025).
- Probability of backtest overfitting across the 12 variants: 0.39 (12870 combinations).

| Portfolio (monthly) | CAGR | Volatility | Sharpe | Sortino | Max drawdown |
|---|---:|---:|---:|---:|---:|
| engine size (5 x 5%) | +1.0% | +6.3% | 0.20 | 0.32 | -20.0% |
| fully invested (5 x 20%) | +1.9% | +25.1% | 0.20 | 0.32 | -62.2% |
| tier average, bought and held (no stop, no costs) | +11.9% | +20.5% | 0.66 | 1.01 | -49.4% |
| NIFTY 50 price index | +12.8% | +15.8% | 0.85 | 1.30 | -24.6% |

| Variant (sensitivity, never used to choose) | Trades | Win rate | Net per trade | Monthly excess over random |
|---|---:|---:|---:|---:|
| 6-1, top 5, stop 10% | 795 | 46.9% | +0.606% | +0.086% |
| 6-1, top 5, no stop | 795 | 51.2% | +1.169% | +0.404% |
| 6-1, top 10, stop 10% | 1590 | 47.3% | +0.437% | -0.083% |
| 6-1, top 10, no stop | 1590 | 51.1% | +0.901% | +0.137% |
| 9-1, top 5, stop 10% | 795 | 47.4% | +0.486% | -0.034% |
| 9-1, top 5, no stop | 795 | 52.7% | +1.371% | +0.607% |
| 9-1, top 10, stop 10% | 1590 | 47.8% | +0.595% | +0.076% |
| 9-1, top 10, no stop | 1590 | 52.3% | +1.335% | +0.570% |
| 12-1, top 5, stop 10% | 795 | 48.6% | +0.413% | -0.107% |
| 12-1, top 5, no stop | 795 | 54.3% | +1.272% | +0.507% |
| 12-1, top 10, stop 10% | 1590 | 47.4% | +0.489% | -0.031% |
| 12-1, top 10, no stop | 1590 | 51.6% | +1.158% | +0.393% |
- NIFTY above its 200-session average: yes: 585 trades, 47.4% winners, +0.092% a trade, t 0.19; no: 210 trades, 51.9% winners, +1.308% a trade, t 1.59.
- India VIX above its 250-session median: yes: 395 trades, 47.3% winners, +0.271% a trade, t 0.46; no: 400 trades, 49.8% winners, +0.554% a trade, t 0.95.

| Year | Trades | Net per trade |
|---|---:|---:|
| 2013 | 35 | +0.880% |
| 2014 | 60 | +2.557% |
| 2015 | 60 | -3.024% |
| 2016 | 60 | -1.041% |
| 2017 | 60 | -2.043% |
| 2018 | 60 | -0.625% |
| 2019 | 60 | +0.213% |
| 2020 | 60 | +1.192% |
| 2021 | 60 | +3.502% |
| 2022 | 60 | -1.076% |
| 2023 | 60 | +6.441% |
| 2024 | 60 | -2.809% |
| 2025 | 60 | -0.558% |
| 2026 | 40 | +3.348% |

Trades entering or exiting on a demerger-type ex-date, or filled at an open more than 8% from that session's close (listed, not changed): 16.

| Stock | Entry | Exit | How | Gross | Why |
|---|---|---|---|---:|---|
| UNITDSPR | 2013-07-01 | 2013-08-01 | time | +7.5% | entry -10.5% from the close |
| RCOM | 2013-07-01 | 2013-08-01 | time | +17.9% | entry -10.5% from the close |
| WOCKPHARMA | 2015-05-04 | 2015-06-01 | time | +11.9% | entry -9.3% from the close |
| NBCC | 2015-06-01 | 2015-07-01 | time | +17.2% | exit -8.6% from the close |
| NBCC | 2015-07-01 | 2015-08-03 | time | +14.2% | entry -8.6% from the close |
| HEGAM | 2018-02-01 | 2018-02-02 | stop | -12.4% | entry +8.4% from the close |
| VAKRANGEE | 2018-02-01 | 2018-02-01 | stop | -10.0% | entry +21.7% from the close |
| SBILIFE | 2020-01-01 | 2020-02-01 | time | +3.4% | exit +11.7% from the close |
| ICICIPRULI | 2020-01-01 | 2020-02-01 | time | +5.9% | exit +13.2% from the close |
| ADANIENT | 2021-04-01 | 2021-05-03 | time | +9.7% | exit -8.8% from the close |
| ADANIENT | 2021-05-03 | 2021-06-01 | time | +15.3% | entry -8.8% from the close |
| ADANIENT | 2022-10-03 | 2022-11-01 | time | -2.3% | entry +9.0% from the close |
| ADANIGREEN | 2022-10-03 | 2022-10-03 | stop | -10.0% | entry +9.2% from the close |
| HAL | 2023-01-02 | 2023-02-01 | time | +1.4% | exit +8.9% from the close |
| ADANIENT | 2023-02-01 | 2023-02-01 | stop | -10.0% | entry +40.3% from the close |
| ADANIENT | 2023-03-01 | 2023-04-03 | time | +22.9% | entry -9.0% from the close |

## N2: 12-1 month momentum, top 5 of liquidity ranks 101-300, monthly

Signals 2013-06-28 to 2026-08-31 (159 months with trades). Mean net +1.751% a trade against +0.668% for 5 random stocks from the same tier with the same rules (p = 0.00190, Holm 0.00380).

**Decision: REJECTED.**

Informational (not part of any decision):

- Win rate 95% interval (Wilson): 40.5% to 47.4%. Mean net per month of picks, 95% interval (month-block bootstrap): +0.154% to +3.401%.
- Monthly excess of the picks over the random-pick expectation: +1.073% (95% interval +0.071% to +2.125%). The dividends missing from price returns lower the baseline by at most about 0.08% a month.
- Stops: 359, of which 52 filled at a gap. Picks kept from one month to the next: 33% of trades.
- Net per trade at 0x / 1x / 1.5x / 2x / 3x costs: +2.250% / +1.751% / +1.502% / +1.253% / +0.754%; with a stock picked again the next month kept instead of re-traded: +1.909%.
- With a 30% haircut on trades that ended at a last close: 792 trades, 43.8% winners, +1.711% a trade, t 2.84.
- The account at the engine's size (Rs 10,00,000, 5 x 5%), marked daily: final Rs 1,904,398, deepest drawdown -17.9%; the 10% kill switch would have engaged on 2015-09-07.
- Deflated Sharpe ratio of the monthly excess: 0.711 (Sharpe 0.52 a year; probability it beats zero 0.977; 25 trials, variant Sharpe variance 0.0030).
- Probability of backtest overfitting across the 12 variants: 0.28 (12870 combinations).

| Portfolio (monthly) | CAGR | Volatility | Sharpe | Sortino | Max drawdown |
|---|---:|---:|---:|---:|---:|
| engine size (5 x 5%) | +5.0% | +8.6% | 0.61 | 1.15 | -16.2% |
| fully invested (5 x 20%) | +16.5% | +34.5% | 0.61 | 1.15 | -58.0% |
| tier average, bought and held (no stop, no costs) | +17.5% | +22.3% | 0.84 | 1.30 | -48.4% |
| NIFTY 50 price index | +12.8% | +15.8% | 0.85 | 1.30 | -24.6% |

| Variant (sensitivity, never used to choose) | Trades | Win rate | Net per trade | Monthly excess over random |
|---|---:|---:|---:|---:|
| 6-1, top 5, stop 10% | 792 | 44.3% | +1.960% | +1.273% |
| 6-1, top 5, no stop | 792 | 51.5% | +2.856% | +1.741% |
| 6-1, top 10, stop 10% | 1587 | 44.5% | +1.548% | +0.869% |
| 6-1, top 10, no stop | 1587 | 50.9% | +2.406% | +1.292% |
| 9-1, top 5, stop 10% | 793 | 43.5% | +1.567% | +0.880% |
| 9-1, top 5, no stop | 793 | 51.6% | +2.703% | +1.588% |
| 9-1, top 10, stop 10% | 1585 | 44.9% | +1.460% | +0.783% |
| 9-1, top 10, no stop | 1585 | 51.9% | +2.622% | +1.510% |
| 12-1, top 5, stop 10% | 792 | 43.9% | +1.751% | +1.073% |
| 12-1, top 5, no stop | 792 | 52.5% | +2.928% | +1.817% |
| 12-1, top 10, stop 10% | 1586 | 46.6% | +1.950% | +1.278% |
| 12-1, top 10, no stop | 1586 | 53.7% | +2.824% | +1.718% |
- NIFTY above its 200-session average: yes: 583 trades, 43.4% winners, +1.210% a trade, t 1.89; no: 209 trades, 45.5% winners, +3.261% a trade, t 2.31.
- India VIX above its 250-session median: yes: 393 trades, 43.5% winners, +1.736% a trade, t 1.94; no: 399 trades, 44.4% winners, +1.766% a trade, t 2.19.

| Year | Trades | Net per trade |
|---|---:|---:|
| 2013 | 35 | +2.322% |
| 2014 | 60 | +6.353% |
| 2015 | 60 | -1.957% |
| 2016 | 60 | +0.403% |
| 2017 | 60 | +1.074% |
| 2018 | 60 | -1.783% |
| 2019 | 60 | +1.205% |
| 2020 | 59 | +5.755% |
| 2021 | 60 | +4.563% |
| 2022 | 58 | -2.438% |
| 2023 | 60 | +7.437% |
| 2024 | 60 | -3.109% |
| 2025 | 60 | -0.232% |
| 2026 | 40 | +6.763% |

Trades entering or exiting on a demerger-type ex-date, or filled at an open more than 8% from that session's close (listed, not changed): 29.

| Stock | Entry | Exit | How | Gross | Why |
|---|---|---|---|---:|---|
| AJANTPHARM | 2013-09-02 | 2013-10-01 | time | +43.3% | entry -8.9% from the close |
| JKLAKSHMI | 2015-03-02 | 2015-04-01 | time | +3.0% | entry -11.4% from the close |
| TITAGARH | 2015-04-01 | 2015-04-24 | stop | -10.0% | entry -8.1% from the close |
| GMBREW | 2016-03-01 | 2016-04-01 | time | +27.1% | entry -9.5% from the close |
| COSMOFIRST | 2016-03-01 | 2016-04-01 | time | +27.8% | entry -9.4% from the close |
| GMBREW | 2016-05-02 | 2016-06-01 | time | +5.0% | exit -10.9% from the close |
| GMBREW | 2016-06-01 | 2016-07-01 | time | +8.2% | entry -10.9% from the close |
| DWARKESH | 2016-08-01 | 2016-08-12 | stop | -10.1% | entry -14.4% from the close |
| UPERGANGES | 2017-01-02 | 2017-02-01 | time | +15.5% | entry -8.6% from the close |
| HEGAM | 2018-01-01 | 2018-02-01 | time | +15.6% | exit +8.4% from the close |
| CGCL | 2019-05-02 | 2019-06-03 | time | +19.9% | entry -8.5% from the close |
| ADANIPOWER | 2019-07-01 | 2019-08-01 | time | +16.7% | entry -13.3% from the close |
| CGCL | 2019-08-01 | 2019-09-03 | time | -0.5% | entry -8.8% from the close; exit -11.7% from the close |
| CGCL | 2019-09-03 | 2019-10-01 | time | +42.0% | entry -11.7% from the close |
| ISEC | 2020-02-01 | 2020-03-02 | time | +1.1% | exit +8.3% from the close |
| ISEC | 2020-03-02 | 2020-03-04 | stop | -10.0% | entry +8.3% from the close |
| SUVEN | 2020-04-01 | 2020-05-04 | time | +133.4% | exit +8.7% from the close |
| AUBANK | 2020-04-01 | 2020-04-03 | stop | -10.0% | entry +10.1% from the close |
| SUVEN | 2020-05-04 | 2020-05-05 | stop | -11.5% | entry +8.7% from the close |
| ADANIGREEN | 2020-08-03 | 2020-09-01 | time | +32.8% | exit -8.2% from the close |
| ADANIGREEN | 2020-09-01 | 2020-10-01 | time | +66.0% | entry -8.2% from the close |
| ATGL | 2021-05-03 | 2021-06-01 | time | +19.8% | entry -8.3% from the close |
| RENUKA | 2022-06-01 | 2022-06-20 | stop | -10.0% | entry -9.4% from the close |
| TTML | 2022-09-01 | 2022-10-03 | time | -7.1% | entry -12.2% from the close |
| PFOCUS | 2026-02-01 | 2026-03-02 | time | +8.6% | exit -11.0% from the close |
| MTARTECH | 2026-04-01 | 2026-05-04 | time | +85.6% | exit +9.3% from the close |
| MTARTECH | 2026-05-04 | 2026-06-01 | time | +17.8% | entry +9.3% from the close; exit +11.6% from the close |
| MTARTECH | 2026-06-01 | 2026-06-01 | stop | -10.0% | entry +11.6% from the close |
| THANGAMAYL | 2026-07-01 | 2026-07-02 | stop | -10.0% | entry +8.4% from the close |

Trades that ended at a suspension or a last close:

| Stock | Signal | Entry | Exit | How | Gross |
|---|---|---|---|---|---:|
| UPERGANGES | 2017-02-28 | 2017-03-01 | 2017-03-22 | no further rows | +7.1% |

Patterns in the informational sections are hypotheses for future data, not findings.

## Post-hoc checks (written by hand, 14 Oct 2026; not pre-registered, no effect on the decisions)

These were computed after the decision, to understand N2: with H11 (round 5), one of the two hypotheses in the project
to beat random entries at the cross-round bar. They can't change its status, and patterns in them are hypotheses for new
data only.

| N2 subset | Trades | Win rate | Net per trade | Random picks | Excess | p vs random |
|---|---:|---:|---:|---:|---:|---:|
| As tested | 792 | 43.9% | +1.751% | +0.668% | +1.08% | 0.0019 |
| Without the 29 trades filled at an open more than 8% from the close | 763 | 43.1% | +1.181% | +0.615% | +0.57% | 0.066 |
| Without its best trade (SUVEN, Apr 2020, +133%) | 791 | 43.9% | +1.586% | +0.655% | +0.93% | 0.0063 |
| Without its best 5 trades | 787 | 43.6% | +1.147% | +0.617% | +0.53% | 0.073 |
| Without its best 10 trades | 782 | 43.2% | +0.758% | +0.583% | +0.18% | 0.32 |
| First half, Jul 2013 - Jan 2020 | 395 | 42.0% | +1.010% | +0.315% | +0.70% | 0.089 |
| Second half, Feb 2020 - Aug 2026 | 397 | 45.8% | +2.489% | +1.014% | +1.48% | 0.0023 |
| 2013-2016 | 215 | 45.6% | +1.717% | +0.977% | +0.74% | 0.15 |
| 2017-2019 | 180 | 37.8% | +0.166% | -0.494% | +0.66% | 0.17 |
| 2020-2022 | 177 | 44.6% | +2.666% | +1.437% | +1.23% | 0.073 |
| 2023-2026 | 220 | 46.8% | +2.347% | +0.702% | +1.65% | 0.0068 |

What they say:

- **N2's edge over random picks is real in this sample but fragile.** It points the same way in every sub-period and in
  all 12 parameter variants (probability of backtest overfitting 0.28), but its significance rests on a handful of very
  large winners (10 trades of 792) and on the years since 2020. Momentum's payoff is right-skewed by nature, so losing
  significance without the best trades is expected; it also means a live version's results would depend on catching
  those few trades.
- **The 10% stop works against momentum here.** Without the stop (informational variants), N1 and N2 won 51-54% of
  their trades and beat random picks by more: N1 +0.51% a month, N2 +1.82% a month, for the 12-1, top-5 rule. With the
  stop, N1's edge disappears (-0.11%) and N2's shrinks (+1.07%). Momentum stocks are volatile, and a 10% stop exits many
  trades that later recover. The risk engine requires a stop and accepts up to 15%; a wider stop was not tested and,
  having seen these results, can only be judged on data that doesn't exist yet.
- **Against simply holding the tier.** N2's tier, equally weighted and bought and held without stops or costs, earned
  17.5% a year (2013-2026) against 16.5% for N2 fully invested and 12.8% for the NIFTY 50 price index. At the risk
  engine's size (five positions of 5%), N2 earned 5.0% a year with a drawdown of about 17%, and the 10% kill switch would have
  engaged in September 2015.
