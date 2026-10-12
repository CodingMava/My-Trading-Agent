# Research round 6 results: Ernest Chan's strategies

Generated 2026-10-13 00:01 by `python -m trader.research.round6`, judged against [the pre-registration](round6-preregistration.md) (SHA-256 `31537d73fbb83c10...`, unchanged since it was pinned on 12 Oct 2026 at 23:35 IST, before any of these rules ran on this data). Returns are per trade, net of costs, over the decision span 2013-07-01 to 2026-10-08: after the book appeared in 2013, so data its rules were never designed on.

The round was first run outside the project on 12 Oct 2026. The book's text wasn't available, so the rules are as described by secondary sources (see the pre-registration); this is a test of those rules, not a verdict on the book. It was recorded here on 13 Oct, with the same runner and data, so the project's count of tested hypotheses stays complete: 20 (H1-H14, C1-C6), and none has passed.

## Verdict

| Hypothesis | Trades | Win rate | Net per trade | Profit factor | t | Cluster-robust t | p vs random (raw / Holm) | Decision |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| C1: Buy-on-gap, NIFTY 50 stocks (intraday, MIS) | 111 | 54.1% | +0.154% | 1.19 | 0.73 | 0.71 | 0.015 / 0.087 | **REJECTED** |
| C2: Buy-on-gap, 82 S&P 100 stocks (intraday) | 355 | 51.0% | +0.007% | 1.01 | 0.06 | 0.04 | 0.170 / 0.848 | **REJECTED** |
| C3: Opening-gap momentum, NIFTY 50 index (intraday, long/short) | 1055 | 40.9% | -0.159% | 0.58 | -6.41 | -6.67 | 0.812 / 1.000 | **REJECTED** |
| C4: Opening-gap momentum, SPY (intraday, long/short) | 1066 | 47.9% | -0.056% | 0.82 | -2.34 | -2.25 | 0.703 / 1.000 | **REJECTED** |
| C5: Time-series momentum, NIFTY 50 (index or cash, monthly) | 127 | 55.1% | +0.505% | 1.37 | 1.30 | 1.30 | 0.858 / 1.000 | **REJECTED** |
| C6: Time-series momentum, SPY (SPY or T-bills, monthly) | 141 | 70.2% | +0.997% | 1.94 | 3.01 | 3.01 | 0.698 / 1.000 | **REJECTED** |

## The criteria

| # | Criterion | C1 | C2 | C3 | C4 | C5 | C6 |
|---|---|---|---|---|---|---|---|
| 1 | At least 50 trades | 111 (pass) | 355 (pass) | 1055 (pass) | 1066 (pass) | 127 (pass) | 141 (pass) |
| 2 | Win rate at least 50% | 54.1% (pass) | 51.0% (pass) | 40.9% (**fail**) | 47.9% (**fail**) | 55.1% (pass) | 70.2% (pass) |
| 3 | Expectancy above 0 at base and 1.5x costs | +0.154% / +0.063% (pass) | +0.007% / -0.045% (**fail**) | -0.159% / -0.218% (**fail**) | -0.056% / -0.078% (**fail**) | +0.505% / +0.499% (pass) | +0.997% / +0.996% (pass) |
| 4 | t-statistic at least 2.0 | 0.73 (**fail**) | 0.06 (**fail**) | -6.41 (**fail**) | -2.34 (**fail**) | 1.30 (**fail**) | 3.01 (pass) |
| 5 | Beats random entries (Holm-adjusted p < 0.05) | 0.087 (**fail**) | 0.848 (**fail**) | 1.000 (**fail**) | 1.000 (**fail**) | 1.000 (**fail**) | 1.000 (**fail**) |
| 6 | Profit factor at least 1.3 | 1.19 (**fail**) | 1.01 (**fail**) | 0.58 (**fail**) | 0.82 (**fail**) | 1.37 (pass) | 1.94 (pass) |
| 7 | Avg loss at most 1.5x avg win; worst trade no worse than -3R | -1.74% vs +1.76%; worst -1.1R (pass) | -1.73% vs +1.68%; worst -1.1R (pass) | -0.64% vs +0.54%; worst -1.2R (pass) | -0.60% vs +0.53%; worst -1.1R (pass) | -3.08% vs +3.42% (pass) | -3.55% vs +2.92% (pass) |
| 8 | Expectancy above 0 in each half of the span | +0.451% / +0.034% (pass) | +0.330% / -0.219% (**fail**) | -0.153% / -0.164% (**fail**) | -0.020% / -0.093% (**fail**) | +0.861% / +0.095% (pass) | +0.617% / +1.417% (pass) |
| 9 | At least 70% of years (10+ trades) positive | 43% of 7 years (**fail**) | 50% of 12 years (**fail**) | 0% of 14 years (**fail**) | 29% of 14 years (**fail**) | +1.213% / +0.111% / +0.150% (pass) | +0.833% / +0.615% / +1.663% (pass) |
| 10 | 60%+ of stocks profitable; still positive without the top stock | 50% of 4 stocks; +0.086% without TRENT.NS (**fail**) | 65% of 34 stocks; -0.024% without ACN (**fail**) | n/a | n/a | n/a | n/a |
| 11 | Cluster-robust t-statistic (signal weeks as clusters) at least 2.0 | 0.71 (**fail**) | 0.04 (**fail**) | -6.67 (**fail**) | -2.25 (**fail**) | 1.30 (**fail**) | 3.01 (pass) |
| 12 | Raw random-baseline p below 0.05/20 = 0.0025 (20 hypotheses tested) | 0.0145 (**fail**) | 0.1695 (**fail**) | 0.8125 (**fail**) | 0.7030 (**fail**) | 0.8575 (**fail**) | 0.6975 (**fail**) |

## Data and costs

- Daily bars from Yahoo (adjusted), frozen with checksums in `data/` (git-ignored): the NIFTY 50 stocks of Phase 3 (from Sep 2014; today's list, so stocks that left the index are missing, which flatters buy-the-dip rules), round 2's 82 S&P 100 stocks, ^NSEI (from 2007) and SPY (from 1993) of round 4, and ^VIX, ^INDIAVIX and ^IRX for regimes and cash (`data/round6/aux_daily`). Cut at 8 Oct 2026.
- Intraday trades fill at the open and the close of daily bars. The gap rules also read the open as their signal, which real orders can't quite match: this flatters C1-C4.
- Round-trip costs: C1 0.182%, C2 0.103%, C3 0.119%, C4 0.043%, C5 0.139%, C6 0.043% (C5/C6 only on switches); stress test at 1.5x.

## C1: Buy-on-gap, NIFTY 50 stocks (intraday, MIS)

Random baseline: -0.074% gross per trade against +0.336% for the strategy; p = 0.015 (Holm 0.087).

**Decision: REJECTED.**

Informational (not part of the decision):

- Portfolio (10 slots of 10% of capital): CAGR +0.1%, Sharpe 0.21, max drawdown -1.8%; the index bought and held: CAGR +10.8%, Sharpe 0.72, max drawdown -38.4%.
- Stop exits: 23% of trades. The book's version without the stop: 111 trades, +0.134% a trade, t 0.59.
- Threshold re-chosen every year: 281 trades, +0.211% a trade, t 1.40; the fixed value over the same years: 92 trades, +0.092% a trade, t 0.42.
- Up to 8 positions on one day.
- Net per trade at 0x / 1x / 1.5x / 2x costs: +0.336% / +0.154% / +0.063% / -0.028%.
- By regime (judged at the previous close): uptrend -0.144% (n=70); not uptrend +0.663% (n=41); high vol +0.394% (n=50); not high vol -0.042% (n=61).

| Year | Trades | Win rate | Net per trade |
|---|---:|---:|---:|
| 2015 | 4 | 100.0% | +2.955% |
| 2016 | 11 | 45.5% | -0.064% |
| 2017 | 4 | 25.0% | -0.612% |
| 2018 | 6 | 16.7% | -0.420% |
| 2019 | 4 | 75.0% | +0.423% |
| 2020 | 11 | 36.4% | +0.286% |
| 2021 | 10 | 60.0% | -0.014% |
| 2022 | 8 | 75.0% | +0.590% |
| 2023 | 11 | 54.5% | +0.017% |
| 2024 | 12 | 58.3% | -0.273% |
| 2025 | 17 | 35.3% | -0.507% |
| 2026 | 13 | 84.6% | +1.019% |

## C2: Buy-on-gap, 82 S&P 100 stocks (intraday)

Random baseline: +0.019% gross per trade against +0.109% for the strategy; p = 0.170 (Holm 0.848).

**Decision: REJECTED.**

Informational (not part of the decision):

- Portfolio (10 slots of 10% of capital): CAGR +0.0%, Sharpe 0.01, max drawdown -5.8%; the index bought and held: CAGR +14.5%, Sharpe 0.89, max drawdown -33.7%.
- Stop exits: 27% of trades. The book's version without the stop: 355 trades, -0.005% a trade, t -0.03.
- Threshold re-chosen every year: 405 trades, -0.058% a trade, t -0.60; the fixed value over the same years: 266 trades, -0.119% a trade, t -0.84.
- Up to 10 positions on one day.
- Net per trade at 0x / 1x / 1.5x / 2x costs: +0.109% / +0.007% / -0.045% / -0.096%.
- By regime (judged at the previous close): uptrend -0.117% (n=260); not uptrend +0.345% (n=95); high vol -0.015% (n=200); not high vol +0.034% (n=155).

| Year | Trades | Win rate | Net per trade |
|---|---:|---:|---:|
| 2015 | 27 | 55.6% | +0.598% |
| 2016 | 46 | 63.0% | +0.404% |
| 2017 | 16 | 43.8% | -0.044% |
| 2018 | 27 | 44.4% | +0.004% |
| 2019 | 18 | 61.1% | +0.257% |
| 2020 | 46 | 43.5% | -0.583% |
| 2021 | 25 | 32.0% | -0.659% |
| 2022 | 33 | 60.6% | +0.540% |
| 2023 | 25 | 56.0% | +0.681% |
| 2024 | 26 | 46.2% | -0.358% |
| 2025 | 39 | 56.4% | -0.299% |
| 2026 | 27 | 40.7% | -0.259% |

## C3: Opening-gap momentum, NIFTY 50 index (intraday, long/short)

Random baseline: -0.019% gross per trade against -0.040% for the strategy; p = 0.812 (Holm 1.000).

**Decision: REJECTED.**

Informational (not part of the decision):

- Portfolio (1 slot of 100% of capital): CAGR -12.4%, Sharpe -1.76, max drawdown -82.3%; the index bought and held: CAGR +10.8%, Sharpe 0.72, max drawdown -38.4%.
- Stop exits: 13% of trades. The book's version without the stop: 1055 trades, -0.174% a trade, t -6.27.
- Threshold re-chosen every year: 871 trades, -0.148% a trade, t -5.10; the fixed value over the same years: 1166 trades, -0.154% a trade, t -6.51.
- By side: long 724 trades, -0.194% a trade, t -7.33; short 331 trades, -0.083% a trade, t -1.55.
- Before Jul 2013 (2008-05-02 to 2013-06-28): 206 trades, -0.188% a trade, t -2.92.
- Net per trade at 0x / 1x / 1.5x / 2x costs: -0.040% / -0.159% / -0.218% / -0.278%.
- By regime (judged at the previous close): uptrend -0.162% (n=692); not uptrend -0.153% (n=363); high vol -0.195% (n=520); not high vol -0.123% (n=530).

| Year | Trades | Win rate | Net per trade |
|---|---:|---:|---:|
| 2013 | 42 | 47.6% | -0.102% |
| 2014 | 71 | 39.4% | -0.112% |
| 2015 | 65 | 43.1% | -0.111% |
| 2016 | 75 | 40.0% | -0.083% |
| 2017 | 81 | 40.7% | -0.171% |
| 2018 | 93 | 39.8% | -0.236% |
| 2019 | 53 | 37.7% | -0.269% |
| 2020 | 92 | 51.1% | -0.109% |
| 2021 | 83 | 37.3% | -0.151% |
| 2022 | 112 | 43.8% | -0.145% |
| 2023 | 83 | 47.0% | -0.084% |
| 2024 | 73 | 23.3% | -0.319% |
| 2025 | 65 | 40.0% | -0.165% |
| 2026 | 67 | 40.3% | -0.182% |

## C4: Opening-gap momentum, SPY (intraday, long/short)

Random baseline: +0.000% gross per trade against -0.013% for the strategy; p = 0.703 (Holm 1.000).

**Decision: REJECTED.**

Informational (not part of the decision):

- Portfolio (1 slot of 100% of capital): CAGR -4.7%, Sharpe -0.64, max drawdown -49.4%; the index bought and held: CAGR +14.5%, Sharpe 0.89, max drawdown -33.7%.
- Stop exits: 12% of trades. The book's version without the stop: 1066 trades, -0.026% a trade, t -1.06.
- Threshold re-chosen every year: 1782 trades, -0.066% a trade, t -2.71; the fixed value over the same years: 2076 trades, -0.070% a trade, t -3.18.
- By side: long 679 trades, -0.007% a trade, t -0.26; short 387 trades, -0.143% a trade, t -3.05.
- Before Jul 2013 (1993-06-11 to 2013-06-28): 1268 trades, -0.089% a trade, t -2.92.
- Net per trade at 0x / 1x / 1.5x / 2x costs: -0.013% / -0.056% / -0.078% / -0.099%.
- By regime (judged at the previous close): uptrend -0.041% (n=748); not uptrend -0.092% (n=318); high vol -0.049% (n=515); not high vol -0.063% (n=551).

| Year | Trades | Win rate | Net per trade |
|---|---:|---:|---:|
| 2013 | 36 | 58.3% | -0.041% |
| 2014 | 75 | 45.3% | -0.085% |
| 2015 | 82 | 54.9% | +0.048% |
| 2016 | 73 | 46.6% | -0.029% |
| 2017 | 74 | 45.9% | -0.026% |
| 2018 | 82 | 53.7% | +0.058% |
| 2019 | 97 | 48.5% | -0.023% |
| 2020 | 102 | 45.1% | -0.276% |
| 2021 | 74 | 50.0% | -0.010% |
| 2022 | 83 | 48.2% | -0.064% |
| 2023 | 85 | 42.4% | -0.127% |
| 2024 | 72 | 47.2% | +0.025% |
| 2025 | 65 | 41.5% | -0.176% |
| 2026 | 66 | 48.5% | +0.002% |

## C5: Time-series momentum, NIFTY 50 (index or cash, monthly)

Random baseline: +0.962% gross per trade against +0.516% for the strategy; p = 0.858 (Holm 1.000).

**Decision: REJECTED.**

Informational (not part of the decision):

- The timed portfolio, cash included: CAGR +5.2%, Sharpe 0.44, max drawdown -31.5%; the index bought and held: CAGR +10.9%, Sharpe 0.74, max drawdown -29.7%. Invested 80% of months (22 switches), including 88% of the index's worst tenth of months.
- Before Jul 2013 (2008-09-30 to 2013-06-28): CAGR +6.3%, Sharpe 0.51, max drawdown -17.3%; bought and held CAGR +8.3%, Sharpe 0.44, max drawdown -29.7%.
- Lookback re-chosen every year (63/126/252 days): CAGR +5.2%, Sharpe 0.46, max drawdown -32.9%; the fixed 252 days over the same years: CAGR +4.8%, Sharpe 0.42, max drawdown -31.5%.
- Cash yield: 0% a year: CAGR +4.0%; 4% a year: CAGR +4.8%; 6% is the base case.
- Net per trade at 0x / 1x / 1.5x / 2x costs: +0.516% / +0.505% / +0.499% / +0.493%.
- By regime (judged at the previous close): uptrend +0.881% (n=87); not uptrend -0.313% (n=40); high vol +0.411% (n=62); not high vol +0.591% (n=64).

| Year | Trades | Win rate | Net per trade |
|---|---:|---:|---:|
| 2013 | 6 | 50.0% | +0.924% |
| 2014 | 12 | 75.0% | +3.219% |
| 2015 | 9 | 44.4% | -1.172% |
| 2016 | 6 | 33.3% | -0.135% |
| 2017 | 12 | 66.7% | +2.166% |
| 2018 | 12 | 33.3% | -0.064% |
| 2019 | 10 | 60.0% | +0.256% |
| 2020 | 5 | 20.0% | -4.476% |
| 2021 | 12 | 83.3% | +2.102% |
| 2022 | 9 | 22.2% | -1.918% |
| 2023 | 12 | 75.0% | +1.742% |
| 2024 | 12 | 66.7% | +0.679% |
| 2025 | 8 | 50.0% | -0.416% |
| 2026 | 2 | 0.0% | -3.881% |

## C6: Time-series momentum, SPY (SPY or T-bills, monthly)

Random baseline: +1.178% gross per trade against +0.999% for the strategy; p = 0.698 (Holm 1.000).

**Decision: REJECTED.**

Informational (not part of the decision):

- The timed portfolio, cash included: CAGR +10.6%, Sharpe 0.85, max drawdown -23.0%; the index bought and held: CAGR +14.0%, Sharpe 0.96, max drawdown -23.3%. Invested 89% of months (11 switches), including 75% of the index's worst tenth of months.
- Before Jul 2013 (1994-01-31 to 2013-06-28): CAGR +11.6%, Sharpe 1.00, max drawdown -17.1%; bought and held CAGR +8.6%, Sharpe 0.61, max drawdown -51.3%.
- Lookback re-chosen every year (63/126/252 days): CAGR +8.7%, Sharpe 0.83, max drawdown -15.8%; the fixed 252 days over the same years: CAGR +10.3%, Sharpe 0.86, max drawdown -23.0%.
- Net per trade at 0x / 1x / 1.5x / 2x costs: +0.999% / +0.997% / +0.996% / +0.995%.
- By regime (judged at the previous close): uptrend +0.810% (n=110); not uptrend +1.659% (n=31); high vol +1.424% (n=63); not high vol +0.652% (n=78).

| Year | Trades | Win rate | Net per trade |
|---|---:|---:|---:|
| 2013 | 6 | 66.7% | +0.984% |
| 2014 | 12 | 75.0% | +1.167% |
| 2015 | 11 | 45.5% | -0.842% |
| 2016 | 10 | 80.0% | +1.253% |
| 2017 | 12 | 91.7% | +1.952% |
| 2018 | 11 | 54.5% | -0.920% |
| 2019 | 11 | 72.7% | +1.539% |
| 2020 | 11 | 54.5% | +0.487% |
| 2021 | 12 | 83.3% | +1.744% |
| 2022 | 4 | 50.0% | -1.828% |
| 2023 | 9 | 66.7% | +1.932% |
| 2024 | 12 | 75.0% | +1.841% |
| 2025 | 12 | 83.3% | +1.413% |
| 2026 | 8 | 62.5% | +1.469% |
