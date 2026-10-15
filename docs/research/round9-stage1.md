# Research round 9, stage 1 (development and replication, decides nothing)

Run on 2026-10-14 23:37 IST by `python -m trader.research.round9 --stage 1` (runner SHA-256 `23d80754878d4a99...`), against [the pre-registration](round9-preregistration.md) (SHA-256 `2f35fd4b44e1b9ef...`) and round 8's frozen panel (SHA-256 `afb79ad2ce778f18...`). Every hypothesis is reported. Returns are per trade, net of round 8's costs.

## Summary

| Hypothesis | Trades | Wins / losses | Win rate | Net per trade | Median | Avg win / avg loss | t | Cluster t | Random picks (same rules) | p raw / Holm | Drawdown | |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| L1: Low volatility: the 5 least volatile of the 100 most liquid NSE stocks, monthly | 440 | 221 / 219 | 50.2% | +0.166% | +0.013% | +6.96% / -6.69% | 0.41 | 0.27 | -0.060% | 0.31448 / 0.71486 | 22.2R | (stage 1) |
| L2: Low volatility: the 5 least volatile of liquidity ranks 101-300, monthly | 440 | 207 / 233 | 47.0% | -0.090% | -0.439% | +6.96% / -6.35% | -0.23 | -0.17 | +0.018% | 0.56907 / 0.71486 | 25.4R | (stage 1) |
| V2: Volatility-adjusted momentum: the top 5 of liquidity ranks 101-300, monthly | 438 | 173 / 265 | 39.5% | +0.446% | -3.723% | +14.72% / -8.87% | 0.60 | 0.44 | +0.053% | 0.23829 / 0.71486 | 32.4R | (stage 1) |

## The criteria (stage 1: reported, not applied)

| # | Criterion | L1 | L2 | V2 |
|---|---|---|---|---|
| 1 | At least 50 trades | 440 (pass) | 440 (pass) | 438 (pass) |
| 2 | Win rate at least 50% | 50.2% (pass) | 47.0% (**fail**) | 39.5% (**fail**) |
| 3 | Expectancy above 0 at base and 1.5x costs | +0.1664% / -0.0161% (**fail**) | -0.0897% / -0.3276% (**fail**) | +0.4464% / +0.1985% (pass) |
| 4 | t-statistic at least 2.0 | 0.41 (**fail**) | -0.23 (**fail**) | 0.60 (**fail**) |
| 5 | Beats the random baseline: Holm-adjusted p below 0.05 | 0.71486 (**fail**) | 0.71486 (**fail**) | 0.71486 (**fail**) |
| 6 | Profit factor at least 1.3 | 1.05 (**fail**) | 0.97 (**fail**) | 1.08 (**fail**) |
| 7 | Average loss at most 1.5x the average win; no trade worse than -3R | -6.690% vs +6.960% (0.96x); worst -1.54R (pass) | -6.349% vs +6.956% (0.91x); worst -1.94R (pass) | -8.873% vs +14.721% (0.60x); worst -1.88R (pass) |
| 8 | Expectancy above 0 in each half of the span | -0.0775% / +0.3517% (split 2009-04-01) (**fail**) | -1.0259% / +0.6218% (split 2009-04-01) (**fail**) | +0.1045% / +0.7035% (split 2009-04-01) (pass) |
| 9 | At least 70% of calendar years with 10+ trades profitable | 75% of 8 years (pass) | 62% of 8 years (**fail**) | 50% of 8 years (**fail**) |
| 10 | At least 60% of stocks with 5+ trades profitable; expectancy above 0 without the top stock | 53% of 19 stocks; -0.0130% without RELIANCE (**fail**) | 41% of 27 stocks; -0.2479% without COLPAL (**fail**) | 45% of 29 stocks; +0.0722% without UNITECH (**fail**) |
| 11 | Cluster-robust t-statistic (signal months as clusters) at least 2.0 | 0.27 (**fail**) | -0.17 (**fail**) | 0.44 (**fail**) |
| 12 | Raw random-baseline p below 0.05/28 = 0.00179 | 0.31448 (**fail**) | 0.56907 (**fail**) | 0.23829 (**fail**) |
| 13 | Drawdown no deeper than 20R (cumulative R in exit order) | 22.2R (**fail**) | 25.4R (**fail**) | 32.4R (**fail**) |

## L1: Low volatility: the 5 least volatile of the 100 most liquid NSE stocks, monthly

Signals 2006-02-28 to 2013-05-31 (88 months with trades). Mean net +0.166% a trade against -0.060% for 5 random stocks from the same tier with the same rules (p = 0.31448, Holm 0.71486).

Informational (not part of any decision):

- Win rate 95% interval (Wilson): 45.6% to 54.9%. Mean net per month of picks, 95% interval (month-block bootstrap): -0.786% to +1.135%.
- Monthly excess over the random-pick expectation: +0.221% (95% interval -0.841% to +1.157%).
- Stops: 104, of which 9 filled at a gap.
- Net per trade at 0x / 1x / 1.5x / 2x / 3x costs: +0.531% / +0.166% / -0.016% / -0.199% / -0.564%.
- The account at the engine's size (Rs 10,00,000, 5 x 5%), marked daily: final Rs 1,027,856, deepest drawdown -10.6%; the 10% kill switch would have engaged on 2008-11-03.
- Deflated Sharpe ratio of the monthly excess: 0.354 (Sharpe 0.11 a year; 28 trials).

| Portfolio (monthly) | CAGR | Volatility | Sharpe | Sortino | Max drawdown |
|---|---:|---:|---:|---:|---:|
| engine size (5 x 5%) | +0.4% | +5.0% | 0.10 | 0.15 | -9.8% |
| fully invested (5 x 20%) | +0.0% | +20.1% | 0.10 | 0.15 | -35.0% |
| tier average, bought and held (no stop, no costs) | +2.7% | +37.0% | 0.25 | 0.40 | -68.5% |
| NIFTY 50 price index | +0.7% | +29.1% | 0.17 | 0.25 | -56.8% |

| Variant (sensitivity, never used to choose) | Trades | Win rate | Net per trade | Monthly excess over random |
|---|---:|---:|---:|---:|
| 10 picks | 880 | 51.9% | +0.571% | +0.625% |
| no stop | 440 | 53.2% | +0.910% | +0.483% |
- NIFTY above its 200-session average: yes: 190 trades, 48.9% winners, +0.375% a trade, t 0.70; no: 155 trades, 49.0% winners, -0.418% a trade, t -0.60.
- India VIX above its 250-session median: yes: 105 trades, 56.2% winners, +1.046% a trade, t 1.26; no: 210 trades, 46.2% winners, -0.387% a trade, t -0.78.

| Year | Trades | Net per trade |
|---|---:|---:|
| 2006 | 55 | +1.129% |
| 2007 | 60 | +0.229% |
| 2008 | 60 | -2.392% |
| 2009 | 60 | +2.118% |
| 2010 | 60 | +0.133% |
| 2011 | 60 | -0.828% |
| 2012 | 60 | +0.525% |
| 2013 | 25 | +0.958% |

Trades entering or exiting on a demerger-type ex-date, or filled at an open more than 8% from that session's close (listed, not changed): 7.

| Stock | Entry | Exit | How | Gross | Why |
|---|---|---|---|---:|---|
| ACC | 2006-03-01 | 2006-04-03 | time | +25.8% | entry -8.7% from the close |
| SBIN | 2006-10-03 | 2006-11-01 | time | +22.1% | exit +12.8% from the close |
| SBIN | 2006-11-01 | 2006-11-01 | stop | -10.0% | entry +12.8% from the close |
| DRREDDY | 2007-09-03 | 2007-10-01 | time | -6.4% | exit -9.0% from the close |
| DRREDDY | 2007-10-01 | 2007-11-01 | time | +2.0% | entry -9.0% from the close |
| INDHOTEL | 2007-12-03 | 2008-01-01 | time | +18.5% | exit -8.4% from the close |
| DRREDDY | 2008-11-03 | 2008-11-18 | stop | -10.0% | entry +8.2% from the close |

## L2: Low volatility: the 5 least volatile of liquidity ranks 101-300, monthly

Signals 2006-02-28 to 2013-05-31 (88 months with trades). Mean net -0.090% a trade against +0.018% for 5 random stocks from the same tier with the same rules (p = 0.56907, Holm 0.71486).

Informational (not part of any decision):

- Win rate 95% interval (Wilson): 42.4% to 51.7%. Mean net per month of picks, 95% interval (month-block bootstrap): -1.181% to +1.024%.
- Monthly excess over the random-pick expectation: -0.109% (95% interval -1.428% to +0.997%).
- Stops: 99, of which 10 filled at a gap.
- Net per trade at 0x / 1x / 1.5x / 2x / 3x costs: +0.386% / -0.090% / -0.328% / -0.565% / -1.041%.
- The account at the engine's size (Rs 10,00,000, 5 x 5%), marked daily: final Rs 973,801, deepest drawdown -12.7%; the 10% kill switch would have engaged on 2008-10-07.
- Deflated Sharpe ratio of the monthly excess: 0.311 (Sharpe -0.05 a year; 28 trials).

| Portfolio (monthly) | CAGR | Volatility | Sharpe | Sortino | Max drawdown |
|---|---:|---:|---:|---:|---:|
| engine size (5 x 5%) | -0.4% | +4.3% | -0.06 | -0.08 | -12.1% |
| fully invested (5 x 20%) | -2.5% | +17.3% | -0.06 | -0.08 | -43.3% |
| tier average, bought and held (no stop, no costs) | +1.3% | +39.5% | 0.22 | 0.35 | -74.0% |
| NIFTY 50 price index | +0.7% | +29.1% | 0.17 | 0.25 | -56.8% |

| Variant (sensitivity, never used to choose) | Trades | Win rate | Net per trade | Monthly excess over random |
|---|---:|---:|---:|---:|
| 10 picks | 880 | 47.6% | +0.068% | +0.049% |
| no stop | 440 | 51.1% | +0.466% | +0.181% |
- NIFTY above its 200-session average: yes: 190 trades, 52.1% winners, +1.325% a trade, t 2.51; no: 155 trades, 40.6% winners, -1.553% a trade, t -2.29.
- India VIX above its 250-session median: yes: 105 trades, 43.8% winners, -0.583% a trade, t -0.74; no: 210 trades, 49.0% winners, +0.602% a trade, t 1.18.

| Year | Trades | Net per trade |
|---|---:|---:|
| 2006 | 55 | -1.581% |
| 2007 | 60 | +0.036% |
| 2008 | 60 | -2.146% |
| 2009 | 60 | +2.757% |
| 2010 | 60 | +0.738% |
| 2011 | 60 | -2.090% |
| 2012 | 60 | +1.222% |
| 2013 | 25 | +0.657% |

Trades entering or exiting on a demerger-type ex-date, or filled at an open more than 8% from that session's close (listed, not changed): 8.

| Stock | Entry | Exit | How | Gross | Why |
|---|---|---|---|---:|---|
| VIDEOIND | 2007-11-01 | 2007-12-03 | time | +9.5% | exit -15.0% from the close |
| GTL | 2008-10-01 | 2008-10-06 | stop | -10.0% | entry +8.9% from the close |
| SHREEASHTA | 2009-03-02 | 2009-04-01 | time | +17.1% | exit +8.9% from the close |
| COLPAL | 2009-03-02 | 2009-04-01 | time | -17.6% | exit -18.1% from the close |
| SHREEASHTA | 2009-04-01 | 2009-05-04 | time | -4.1% | entry +8.9% from the close |
| COLPAL | 2009-04-01 | 2009-05-04 | time | +27.8% | entry -18.1% from the close |
| SHREEASHTA | 2009-10-01 | 2009-10-01 | stop | -10.0% | entry -9.8% from the close |
| VIDEOIND | 2012-11-01 | 2012-12-03 | time | +23.4% | exit -10.5% from the close |

Trades that ended at a suspension or a last close:

| Stock | Signal | Entry | Exit | How | Gross |
|---|---|---|---|---|---:|
| MORGANSTAN | 2008-11-28 | 2008-12-01 | 2008-12-04 | no further rows | +3.9% |

## V2: Volatility-adjusted momentum: the top 5 of liquidity ranks 101-300, monthly

Signals 2006-02-28 to 2013-05-31 (88 months with trades). Mean net +0.446% a trade against +0.053% for 5 random stocks from the same tier with the same rules (p = 0.23829, Holm 0.71486).

Informational (not part of any decision):

- Win rate 95% interval (Wilson): 35.0% to 44.1%. Mean net per month of picks, 95% interval (month-block bootstrap): -1.298% to +2.131%.
- Monthly excess over the random-pick expectation: +0.379% (95% interval -1.519% to +2.040%).
- Stops: 187, of which 34 filled at a gap.
- Net per trade at 0x / 1x / 1.5x / 2x / 3x costs: +0.942% / +0.446% / +0.198% / -0.049% / -0.545%.
- The account at the engine's size (Rs 10,00,000, 5 x 5%), marked daily: final Rs 1,075,986, deepest drawdown -16.1%; the 10% kill switch would have engaged on 2008-07-01.
- Deflated Sharpe ratio of the monthly excess: 0.395 (Sharpe 0.14 a year; 28 trials).

| Portfolio (monthly) | CAGR | Volatility | Sharpe | Sortino | Max drawdown |
|---|---:|---:|---:|---:|---:|
| engine size (5 x 5%) | +1.0% | +8.3% | 0.16 | 0.29 | -15.0% |
| fully invested (5 x 20%) | +0.2% | +33.2% | 0.16 | 0.29 | -49.3% |
| tier average, bought and held (no stop, no costs) | +1.3% | +39.5% | 0.22 | 0.35 | -74.0% |
| NIFTY 50 price index | +0.7% | +29.1% | 0.17 | 0.25 | -56.8% |

| Variant (sensitivity, never used to choose) | Trades | Win rate | Net per trade | Monthly excess over random |
|---|---:|---:|---:|---:|
| 10 picks | 877 | 41.5% | +0.463% | +0.417% |
| no stop | 438 | 48.4% | +1.712% | +1.353% |
| 12-1 / vol alone | 438 | 42.2% | +0.544% | +0.480% |
| 6-1 / vol alone | 438 | 41.3% | +0.738% | +0.670% |
- NIFTY above its 200-session average: yes: 190 trades, 45.3% winners, +1.355% a trade, t 1.39; no: 155 trades, 31.0% winners, -2.258% a trade, t -2.22.
- India VIX above its 250-session median: yes: 105 trades, 41.0% winners, +0.081% a trade, t 0.06; no: 210 trades, 40.0% winners, -0.152% a trade, t -0.17.

| Year | Trades | Net per trade |
|---|---:|---:|
| 2006 | 53 | +3.200% |
| 2007 | 60 | +2.062% |
| 2008 | 60 | -4.687% |
| 2009 | 60 | +0.828% |
| 2010 | 60 | +2.781% |
| 2011 | 60 | -0.337% |
| 2012 | 60 | -0.058% |
| 2013 | 25 | -0.375% |

Trades entering or exiting on a demerger-type ex-date, or filled at an open more than 8% from that session's close (listed, not changed): 21.

| Stock | Entry | Exit | How | Gross | Why |
|---|---|---|---|---:|---|
| UNITECH | 2006-08-01 | 2006-08-02 | stop | -14.0% | entry +10.5% from the close |
| KLGSYSTEL | 2006-12-01 | 2007-01-02 | time | +24.4% | exit -8.4% from the close |
| UFLEX | 2007-05-03 | 2007-05-04 | stop | -18.2% | entry +10.7% from the close |
| IIFL | 2007-07-02 | 2007-08-01 | time | +4.8% | exit +13.2% from the close |
| ENIL | 2007-08-01 | 2007-08-01 | stop | -10.0% | entry +10.9% from the close |
| TATASTLBSL | 2007-09-03 | 2007-10-01 | time | +14.8% | entry -14.3% from the close |
| PRAKASH | 2008-07-01 | 2008-07-01 | stop | -10.0% | entry +11.4% from the close |
| ZANDUREALT | 2008-10-01 | 2008-10-03 | stop | -10.0% | entry +9.5% from the close |
| SHREEASHTA | 2009-03-02 | 2009-04-01 | time | +17.1% | exit +8.9% from the close |
| COLPAL | 2009-03-02 | 2009-04-01 | time | -17.6% | exit -18.1% from the close |
| SHREEASHTA | 2009-04-01 | 2009-05-04 | time | -4.1% | entry +8.9% from the close |
| COLPAL | 2009-04-01 | 2009-05-04 | time | +27.8% | entry -18.1% from the close |
| UFLEX | 2010-12-01 | 2010-12-07 | stop | -10.0% | entry -9.7% from the close |
| UBL | 2011-03-01 | 2011-04-01 | time | +17.8% | entry -13.5% from the close |
| OSWALGREEN | 2011-04-01 | 2011-05-02 | time | +19.6% | entry -9.6% from the close |
| STAR | 2012-03-01 | 2012-04-02 | time | -7.0% | exit -15.9% from the close |
| STAR | 2012-04-02 | 2012-05-02 | time | +33.9% | entry -15.9% from the close |
| ZYLOG | 2012-06-01 | 2012-07-02 | time | -10.3% | exit -9.0% from the close |
| ZYLOG | 2012-07-02 | 2012-07-26 | stop | -10.0% | entry -9.0% from the close |
| MOTHERSON | 2013-02-01 | 2013-03-01 | time | -14.0% | exit -12.3% from the close |
| ESSDEE | 2013-04-01 | 2013-05-02 | time | +62.8% | entry -8.2% from the close; exit -8.3% from the close |

Trades that ended at a suspension or a last close:

| Stock | Signal | Entry | Exit | How | Gross |
|---|---|---|---|---|---:|
| BANKRAJAS | 2010-07-30 | 2010-08-02 | 2010-08-23 | no further rows | +18.2% |
| UTVSOF | 2012-02-29 | 2012-03-01 | 2012-03-07 | no further rows | +2.2% |

Patterns in the informational sections are hypotheses for future data, not findings.
