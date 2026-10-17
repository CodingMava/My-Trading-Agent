# Research round 10, stage 1 (development; decides nothing)

Run on 2026-10-17 17:53 IST by `python -m trader.research.round10 --stage 1` (runner SHA-256 `21f3bba31e2aa179...`), against [the pre-registration](round10-preregistration.md) (SHA-256 `c973d560263b7caa...`), the board-meeting and insider manifests (`1e7accb2...`, `4955502b...`) and round 8's frozen panel (`afb79ad2...`). Every hypothesis is reported. Returns are per trade, net of costs (Rs 33,333 positions, 15% stop, R = 15%).

## Summary

| Hypothesis | Entries | Trades | Win rate | Net per trade | Avg win / avg loss | PF | t | Cluster t | Random picks | p raw / Holm | Drawdown | |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| E2: Drift after a strong results reaction (top 10%), 40 sessions, 15% stop, 5 positions | 2009-01-02 to 2013-03-28 | 97 | 60.8% | +4.635% | +15.66% / -12.49% | 1.95 | 2.60 | 1.63 | -0.058% | 0.001650 / 0.003300 | 12.4R | (stage 1) |
| Q: Promoter open-market purchases of Rs 10 lakh+, 40 sessions, 15% stop, 5 positions | 2015-11-19 to 2017-10-31 | 63 | 63.5% | +4.992% | +13.14% / -9.19% | 2.49 | 2.65 | 2.31 | +2.159% | 0.049448 / 0.049448 | 3.8R | (stage 1) |

## The criteria (stage 1: reported, not applied)

| # | Criterion | E2 | Q |
|---|---|---|---|
| 1 | At least 50 trades | 97 (pass) | 63 (pass) |
| 2 | Win rate at least 50% | 60.8% (pass) | 63.5% (pass) |
| 3 | Expectancy above 0 at base and 1.5x costs | +4.6349% / +4.4071% (pass) | +4.9917% / +4.7706% (pass) |
| 4 | t-statistic at least 2.0 | 2.60 (pass) | 2.65 (pass) |
| 5 | Beats the random baseline: Holm-adjusted p below 0.05 | 0.00330 (pass) | 0.04945 (pass) |
| 6 | Profit factor at least 1.3 | 1.95 (pass) | 2.49 (pass) |
| 7 | Average loss at most 1.5x the average win; no trade worse than -3R | -12.486% vs +15.662% (0.80x); worst -1.12R (pass) | -9.188% vs +13.145% (0.70x); worst -1.04R (pass) |
| 8 | Expectancy above 0 in each half of the span | +7.0594% / +2.2600% (split 2011-02-14) (pass) | +0.9680% / +9.1453% (split 2016-11-09) (pass) |
| 9 | At least 70% of calendar years with 10+ trades profitable | 75% of 4 years (pass) | 100% of 2 years (pass) |
| 10 | At least 60% of stocks with 5+ trades profitable; expectancy above 0 without the top stock | 0% of 1 stocks; +3.7782% without LICHSGFIN (**fail**) | 50% of 2 stocks; +4.2648% without ADANIPORTS (**fail**) |
| 11 | Cluster-robust t-statistic (entry months as clusters) at least 2.0 | 1.63 (**fail**) | 2.31 (pass) |
| 12 | Raw random-baseline p below 0.05/57 = 0.000877 | 0.001650 (**fail**) | 0.049448 (**fail**) |
| 13 | Drawdown no deeper than 20R (cumulative R in exit order) | 12.4R (pass) | 3.8R (pass) |

## E2: Drift after a strong results reaction (top 10%), 40 sessions, 15% stop, 5 positions

Informational (not part of any decision):

- Edge over random picks: +4.696% a trade (month-clustered t 3.52).
- Stops: 24, of which 1 filled at a gap.
- Net per trade at 0x / 1x / 1.5x / 2x / 3x costs: +5.091% / +4.635% / +4.407% / +4.179% / +3.724%.
- By part: E2: 97 trades, net +4.635%, edge +4.696%, win 60.8%.
- By tier: N1: 35 trades, net +5.674%, edge +6.748%; N2: 62 trades, net +4.048%, edge +3.537%.
- E2 with every qualifying event (no position cap): 430 trades, net +3.353%, win 57.2%, edge over random +2.656%.

| Year | Trades | Net per trade | E2 every event |
|---|---:|---:|---:|
| 2009 | 19 | +17.348% | +17.919% |
| 2010 | 24 | +0.926% | -0.768% |
| 2011 | 26 | -3.423% | -3.593% |
| 2012 | 23 | +8.965% | +8.302% |
| 2013 | 5 | -3.889% | -9.127% |

Largest trades:

| Part | Stock | Entry | Exit | How | Net |
|---|---|---|---|---|---:|
| E2 | LICHSGFIN | 2009-04-27 | 2009-06-24 | time | +79.9% |
| E2 | POLARIS | 2009-04-22 | 2009-06-19 | time | +41.5% |
| E2 | PRSMJOHNSN | 2009-07-09 | 2009-09-03 | time | +38.9% |
| E2 | PATNI | 2011-10-20 | 2011-12-21 | time | +35.6% |
| E2 | TULIP | 2009-07-01 | 2009-08-26 | time | +34.2% |
| E2 | BEL | 2009-11-04 | 2010-01-04 | time | +29.2% |
| E2 | UCOBANK | 2010-07-27 | 2010-09-22 | time | +28.8% |
| E2 | UNIONBANK | 2012-11-06 | 2013-01-04 | time | +28.5% |
| E2 | KTKBANK | 2012-10-19 | 2012-12-19 | time | +27.6% |
| E2 | SYNDIBANK | 2012-01-24 | 2012-03-22 | time | +26.1% |

## Q: Promoter open-market purchases of Rs 10 lakh+, 40 sessions, 15% stop, 5 positions

Informational (not part of any decision):

- Edge over random picks: +2.821% a trade (month-clustered t 1.81).
- Stops: 9, of which 0 filled at a gap.
- Net per trade at 0x / 1x / 1.5x / 2x / 3x costs: +5.434% / +4.992% / +4.771% / +4.549% / +4.107%.
- By part: Q: 63 trades, net +4.992%, edge +2.821%, win 63.5%.
- By tier: N1: 24 trades, net +2.399%, edge +0.255%; N2: 39 trades, net +6.587%, edge +4.400%.
- Q with every qualifying event (no position cap): 192 trades, net +4.744%, win 59.4%, edge over random +1.422%.

| Year | Trades | Net per trade | Q every event |
|---|---:|---:|---:|
| 2015 | 5 | -5.206% | -10.236% |
| 2016 | 32 | +3.019% | +4.592% |
| 2017 | 26 | +9.380% | +8.295% |

Largest trades:

| Part | Stock | Entry | Exit | How | Net |
|---|---|---|---|---|---:|
| Q | RAYMOND | 2017-02-20 | 2017-04-21 | time | +47.4% |
| Q | VAKRANGEE | 2017-09-29 | 2017-11-28 | time | +43.2% |
| Q | JMFINANCIL | 2017-03-21 | 2017-05-19 | time | +39.8% |
| Q | NCC | 2017-10-11 | 2017-12-07 | time | +35.6% |
| Q | COX&KINGS | 2016-05-25 | 2016-07-21 | time | +31.9% |
| Q | EDELWEISS | 2017-07-19 | 2017-09-15 | time | +29.8% |
| Q | KEC | 2016-02-12 | 2016-04-13 | time | +26.5% |
| Q | ADANIPORTS | 2016-05-27 | 2016-07-25 | time | +21.7% |
| Q | ADANIPORTS | 2016-07-26 | 2016-09-23 | time | +21.5% |
| Q | INDUSINDBK | 2016-12-08 | 2017-02-03 | time | +17.8% |

Patterns in the informational sections are hypotheses for future data, not findings.
