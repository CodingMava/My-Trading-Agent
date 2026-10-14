# Research round 8, stage 1 (development and replication, decides nothing)

Run on 2026-10-14 01:46 IST by `python -m trader.research.round8 --stage 1` (runner SHA-256 `54651892c8ed2682...`), against [the pre-registration](round8-preregistration.md) (SHA-256 `ea4a3c0c281eed61...`) and the frozen panel `data/round8/nse_eq` (SHA-256 `afb79ad2ce778f18...`). Every hypothesis is reported. Returns are per trade, net of costs: N1 0.3532% a round trip, N2 0.4532% a round trip.

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

Signals 2006-02-28 to 2013-05-31 (88 months with trades). Mean net +0.219% a trade against -0.060% for 5 random stocks from the same tier with the same rules (p = 0.27794, Holm 0.27794).

Informational (not part of any decision):

- Win rate 95% interval (Wilson): 41.8% to 51.0%. Mean net per month of picks, 95% interval (month-block bootstrap): -1.527% to +2.007%.
- Monthly excess of the picks over the random-pick expectation: +0.274% (95% interval -1.094% to +1.557%). The dividends missing from price returns lower the baseline by at most about 0.08% a month.
- Stops: 186, of which 16 filled at a gap. Picks kept from one month to the next: 34% of trades.
- Net per trade at 0x / 1x / 1.5x / 2x / 3x costs: +0.593% / +0.219% / +0.032% / -0.155% / -0.529%; with a stock picked again the next month kept instead of re-traded: +0.344%.
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

Trades entering or exiting on a demerger-type ex-date, or filled at an open more than 8% from that session's close (listed, not changed): 31.

| Stock | Entry | Exit | How | Gross | Why |
|---|---|---|---|---:|---|
| BEML | 2006-03-01 | 2006-04-03 | time | +5.2% | entry -11.5% from the close |
| STER | 2006-06-01 | 2006-06-02 | stop | -10.0% | entry +9.4% from the close |
| BAJAJHIND | 2006-06-01 | 2006-06-01 | stop | -10.0% | entry +11.8% from the close |
| SAKHTISUG | 2006-06-01 | 2006-06-01 | stop | -10.0% | entry +12.5% from the close |
| BALRAMCHIN | 2006-06-01 | 2006-06-01 | stop | -10.0% | entry +9.9% from the close |
| UNITECH | 2006-10-03 | 2006-11-01 | time | +20.8% | exit +8.3% from the close |
| UNITECH | 2006-11-01 | 2006-12-01 | time | +20.4% | entry +8.3% from the close |
| INDIABULLS | 2007-01-02 | 2007-02-01 | time | +87.4% | demerger-type ex-date; entry -35.2% from the close |
| EKC | 2007-07-02 | 2007-08-01 | time | +1.8% | exit +11.1% from the close |
| IIFL | 2007-08-01 | 2007-08-01 | stop | -10.0% | entry +13.2% from the close |
| TELEDATAIN | 2007-08-01 | 2007-08-06 | stop | -10.0% | entry +9.7% from the close |
| NAGARFERT | 2007-11-01 | 2007-11-01 | stop | -10.0% | entry +12.0% from the close |
| NAGARFERT | 2007-12-03 | 2008-01-01 | time | +9.9% | entry -9.6% from the close |
| GUJNRECOKE | 2008-04-01 | 2008-05-02 | time | +18.9% | entry -10.6% from the close |
| RNRL | 2008-07-01 | 2008-07-01 | stop | -10.0% | entry +10.6% from the close |
| LITL | 2008-07-01 | 2008-07-01 | stop | -10.0% | entry +8.6% from the close |
| VEDL | 2008-07-01 | 2008-07-01 | stop | -10.0% | entry +12.8% from the close |
| NATIONALUM | 2008-11-03 | 2008-11-03 | stop | -10.0% | entry +11.7% from the close |
| POWERGRID | 2009-04-01 | 2009-04-08 | stop | -10.0% | entry +8.6% from the close |
| TATACOMM | 2009-06-01 | 2009-06-01 | stop | -10.0% | entry +12.0% from the close |
| BPCL | 2009-07-01 | 2009-08-03 | time | +14.4% | entry -8.7% from the close |
| JPASSOCIAT | 2009-11-03 | 2009-12-01 | time | +8.2% | entry +8.6% from the close |
| TMPV | 2010-02-01 | 2010-03-02 | time | +4.7% | exit -9.8% from the close |
| TMPV | 2010-03-02 | 2010-04-01 | time | +5.6% | entry -9.8% from the close |
| DELTACORP | 2011-02-01 | 2011-02-01 | stop | -10.0% | entry +11.0% from the close |
| DELTACORP | 2011-03-01 | 2011-04-01 | time | +17.7% | exit -10.8% from the close |
| DELTACORP | 2011-04-01 | 2011-05-02 | time | +15.4% | entry -10.8% from the close |
| TITAN | 2011-04-01 | 2011-05-02 | time | +17.0% | exit +13.6% from the close |
| JUBLFOOD | 2011-06-01 | 2011-07-01 | time | +13.1% | exit +12.1% from the close |
| JUBLFOOD | 2011-07-01 | 2011-07-01 | stop | -10.0% | entry +12.1% from the close |
| JUBLFOOD | 2012-04-02 | 2012-05-02 | time | +9.3% | entry -9.9% from the close |

## N2: 12-1 month momentum, top 5 of liquidity ranks 101-300, monthly

Signals 2006-02-28 to 2013-05-31 (88 months with trades). Mean net +0.864% a trade against +0.053% for 5 random stocks from the same tier with the same rules (p = 0.07605, Holm 0.15209).

Informational (not part of any decision):

- Win rate 95% interval (Wilson): 35.7% to 44.8%. Mean net per month of picks, 95% interval (month-block bootstrap): -1.441% to +2.888%.
- Monthly excess of the picks over the random-pick expectation: +0.791% (95% interval -1.220% to +2.553%). The dividends missing from price returns lower the baseline by at most about 0.08% a month.
- Stops: 206, of which 37 filled at a gap. Picks kept from one month to the next: 29% of trades.
- Net per trade at 0x / 1x / 1.5x / 2x / 3x costs: +1.364% / +0.864% / +0.614% / +0.364% / -0.136%; with a stock picked again the next month kept instead of re-traded: +1.000%.
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

Trades entering or exiting on a demerger-type ex-date, or filled at an open more than 8% from that session's close (listed, not changed): 19.

| Stock | Entry | Exit | How | Gross | Why |
|---|---|---|---|---:|---|
| MAHLIFE | 2006-06-01 | 2006-06-02 | stop | -10.0% | entry +8.1% from the close |
| UNITECH | 2006-08-01 | 2006-08-02 | stop | -14.0% | entry +10.5% from the close |
| ORIENTPPR | 2006-08-01 | 2006-09-01 | time | +10.8% | exit -8.3% from the close |
| KLGSYSTEL | 2006-12-01 | 2007-01-02 | time | +24.4% | exit -8.4% from the close |
| KESORAMIND | 2007-03-01 | 2007-03-01 | stop | -10.0% | entry +12.4% from the close |
| UFLEX | 2007-05-03 | 2007-05-04 | stop | -18.2% | entry +10.7% from the close |
| IIFL | 2007-07-02 | 2007-08-01 | time | +4.8% | exit +13.2% from the close |
| EKC | 2007-08-01 | 2007-08-01 | stop | -10.0% | entry +11.1% from the close |
| TATASTLBSL | 2007-09-03 | 2007-10-01 | time | +14.8% | entry -14.3% from the close |
| PRAKASH | 2008-07-01 | 2008-07-01 | stop | -10.0% | entry +11.4% from the close |
| PRAKASH | 2008-08-01 | 2008-09-01 | time | +13.4% | entry -13.2% from the close |
| ZANDUREALT | 2008-10-01 | 2008-10-03 | stop | -10.0% | entry +9.5% from the close |
| SHREEASHTA | 2009-03-02 | 2009-04-01 | time | +17.1% | exit +8.9% from the close |
| COLPAL | 2009-03-02 | 2009-04-01 | time | -17.6% | exit -18.1% from the close |
| SHREEASHTA | 2009-04-01 | 2009-05-04 | time | -4.1% | entry +8.9% from the close |
| UBL | 2011-03-01 | 2011-04-01 | time | +17.8% | entry -13.5% from the close |
| GRAVITA | 2012-01-02 | 2012-02-01 | time | +52.6% | entry -9.0% from the close |
| HATHWAY | 2012-04-02 | 2012-05-02 | time | -5.5% | exit -15.5% from the close |
| ESSDEE | 2013-04-01 | 2013-05-02 | time | +62.8% | entry -8.2% from the close; exit -8.3% from the close |

Trades that ended at a suspension or a last close:

| Stock | Signal | Entry | Exit | How | Gross |
|---|---|---|---|---|---:|
| UTVSOF | 2012-02-29 | 2012-03-01 | 2012-03-07 | no further rows | +2.2% |

Patterns in the informational sections are hypotheses for future data, not findings.

## Run history and what stage 1 found (written by hand, 14 Oct 2026)

- **Run 1** (01:40 IST) is kept as [round8-stage1-run1.md](round8-stage1-run1.md). Runs 2 and 3 changed only the report:
  the span line now counts months with trades (run 1 said "2005-01-31, 101 months"; the first trade was in February
  2006), the cost line names its sixth number (costs if a stock picked again were kept, not re-traded), and a new
  informational list shows trades that entered or exited on a demerger-type ex-date or filled at an open more than 8%
  from that session's close. Every number in the criteria is identical across the three runs. No rule, parameter, cost,
  criterion or span changed.
- **Data limits that stage 1 exposed** (stage 1 only; they bear on its numbers, not on stage 2's rules):
  - Before NSE's opening call auction (1 April 2013 for all stocks), some official opens were stray first trades far
    from the day's prices: Colgate opened 19.6% below its previous close on 1 Apr 2009 and closed flat (an exit at that
    open lost 17.6%); GSK Pharma's 21 May 2009 open was its low, 12.5% down. Stops and exits at such prints are counted
    as they are, for the strategy and the random picks alike.
  - On a demerger ex-date the opening print can be far from where the stock traded: Indiabulls Financial opened at 198
    on 2 Jan 2007 and closed at 305, so a trade entered at that open shows +87%. It is N1's largest stage-1 trade; without
    Indiabulls, N1's stage-1 expectancy is negative.
- **What stage 1 says, as replication (not a decision):** in 2006-2013 the rule with its 10% stop earned +0.22% (N1)
  and +0.86% (N2) a trade net, against -0.06% and +0.05% for random picks from the same tiers, not distinguishable from
  chance (p 0.28 and 0.08). Without the stop (an informational variant) the trades won more often (54% and 50%) and
  earned more in raw terms, but their edge over random picks was smaller, not larger. The published Indian momentum
  premium is visible in direction, weakly, and is not statistically distinguishable here.
