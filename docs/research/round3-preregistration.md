# Research round 3 pre-registration: confirming or retiring H6

Written 2026-10-09, **before** any strategy was run on any of this data. The rules, data, costs,
tests, pass criteria and decision below are fixed. Results are reported against this document whatever
they show; the results file records this file's SHA-256 so any later edit is detectable.

## Why this round

In round 2, H6 (the Phase 3 pullback rules on the 11 US sector SPDRs) made +0.24% per trade net over
2022-2026: 431 trades, 65% winners, profit factor 1.37, 9 of 11 years positive. But it was not clearly
better than buying the same ETFs on random days with the same exits (p = 0.069; 0.21 after the Holm
correction; cluster-robust t 1.86), so it was rejected. It can't be re-tested on that data. This round
tests the same rules, unchanged, on two sets of data that nothing in this project has examined:

1. **H7: the same kind of ETFs, earlier years.** The 9 original sector SPDRs, 2000-2015.
2. **H8: different ETFs, the same years.** 15 liquid iShares single-country ETFs, 2016-2026.

A real effect should show up in both. This is the last test of these rules: if it isn't confirmed, the
pullback rules are retired and no variant of them is tested again in this project.

## Data and periods

| Item | H7 | H8 |
|---|---|---|
| Instruments | XLB, XLE, XLF, XLI, XLK, XLP, XLU, XLV, XLY (all listed 22 Dec 1998) | EWA, EWC, EWG, EWH, EWJ, EWL, EWS, EWT, EWU, EWW, EWY, EWZ, FXI, MCHI, INDA |
| Bars used | From listing to 31 Dec 2015; nothing later is used, so trades that would end after it are dropped | 12 years up to 8 Oct 2026 |
| Evaluation | 1 Jan 2000 to 31 Dec 2015 | 1 Jan 2016 to 8 Oct 2026 |
| Halves | 2000-2007 and 2008-2015 | 2016-2020 and 2021-2026 |

Source: Yahoo Finance daily bars, split- and dividend-adjusted, frozen in `data/round3/` with checksums
and a validation report. Earlier bars only warm up the indicators.

**H8's instruments** were chosen from data availability and liquidity only, before any strategy ran:
every iShares single-country ETF (and FXI, iShares' China large-cap fund) with Yahoo history from before
2015 that traded a median of at least $20 million a day over the 60 sessions to 8 Oct 2026. That is 15
of the 40 surveyed (Australia, Canada, Germany, Hong Kong, Japan, Switzerland, Singapore, Taiwan, UK,
Mexico, South Korea, Brazil, China twice, India).

**Nothing is fitted in this round**, so there is no design/holdout split: each hypothesis is judged on
its whole evaluation span, and each half of it must be profitable on its own.

**Known limitations.**

- The rules come from Connors & Alvarez (2008, 2009), whose tests mostly used data from before 2008, so
  H7's first half overlaps the years in which the effect was found. The second half (2008-2015) has to
  be profitable on its own (criterion 8).
- Today's costs are applied throughout. Trading in 2000 cost more (prices moved in sixteenths of a
  dollar until 2001, and brokers charged commissions), but the decision is about trading now.
- H8's ETFs were chosen by today's liquidity. The random baseline uses the same ETFs.
- Asian and Pacific ETFs trade in US hours while their home markets are closed, so their opening prices
  carry overnight news. Entries and exits use those prices, as a trader would get them.

**Data cleaning, fixed now.** As in round 2: bars without prices and Yahoo's flat zero-volume
placeholder bars are dropped; every daily move above 20% is classified before any strategy runs, a
corporate action Yahoo didn't adjust splits that instrument's series at that date, and a genuine price
move is kept. The results file lists every flag and how it was classified.

## Execution and costs

- As in Phase 3 and round 2: signals use completed daily bars; entries fill at the next day's open;
  rule-based exits are decided on a close and fill at the next open; stops fill at the stop price, or at
  the open if the day gaps through it; a time exit fills at the close of the last allowed day.
- H7: as H6, a commission-free broker, the SEC fee on sales and 0.02% slippage per side, 0.043% round
  trip at $10,000.
- H8: 0.05% slippage per side, because country ETFs have wider spreads than the sector SPDRs and noisier
  opening prices: 0.103% round trip at $10,000.
- Currency conversion and taxes are not included. Stress test: every cost x 1.5.

## Hypotheses

Both use the Phase 3 H1 rules unchanged, the same rules as H6 (`pullback_signals` with the default
`PullbackParams` in `trader/strategies/swing.py`):

- Entry signal: close > 200-day SMA **and** 2-day RSI (Wilder) < 10.
- Exit: the first close above the 5-day SMA (sell next open); or a stop 2.5 x ATR(14, Wilder) below
  entry, sized at the signal day's close; or after 10 trading days (sell at that close).
- One position per instrument at a time. R (risk unit) = the stop distance.

### H7: Oversold pullback in an uptrend, US sector SPDRs, 2000-2015

### H8: Oversold pullback in an uptrend, iShares country ETFs, 2016-2026

## Tests

As in round 2, on each hypothesis's whole evaluation span, net of base costs unless stated:

- Trade statistics: count, win rate, average win and loss, profit factor, expectancy, t-statistic,
  worst trade in R, drawdown, Sharpe.
- The random-entry baseline that keeps simultaneous trades together (2,000 draws): for every day on
  which the strategy entered, one random day of the span is drawn on which all the instruments it
  entered that day could be entered, and random trades are taken in those instruments on that day with
  the same exits. The two p-values are corrected for multiple testing with Holm's method.
- The cluster-robust t-statistic, with trades grouped by the calendar week of their signal.
- Stability: each half, each calendar year, each instrument, result without the top contributor.

## Pass criteria (whole evaluation span, base costs unless stated)

| # | Criterion |
|---|---|
| 1 | At least 50 trades |
| 2 | Win rate at least 50% |
| 3 | Expectancy above zero at base costs and at 1.5x costs |
| 4 | t-statistic at least 2.0 |
| 5 | Beats the random-entry baseline above: Holm-adjusted p below 0.05 |
| 6 | Profit factor at least 1.3 |
| 7 | Average loss at most 1.5 x average win; worst trade no worse than -3R |
| 8 | Expectancy above zero in each half of the span |
| 9 | At least 70% of calendar years (with 10+ trades) have positive expectancy |
| 10 | At least 60% of instruments with 5+ trades are profitable, and expectancy stays above zero without the top-contributing instrument |
| 11 | Cluster-robust t-statistic (signal weeks as clusters) at least 2.0 |
| 12 | The other hypothesis of this round also passes criteria 1-11 |

Criteria 1-11 are round 2's, judged on the whole span; criterion 8 replaces "design period also
profitable" because nothing here has a design period. Criterion 12 makes the round a single test: the
effect has to show up in both places.

**Decision.**

| Outcome | Registry status |
|---|---|
| Both hypotheses pass every criterion | `PAPER` for H7 and H8: the rules may be paper traded on the 9 sector SPDRs and the 15 country ETFs once the paper engine supports US markets; US orders stay manual |
| Only criterion 1 (sample size) fails | `RESEARCH`: inconclusive |
| Anything else | `REJECTED` for both, and the pullback rules are retired |

## Informational (does not affect the decision)

- Each p-value computed with Phase 3's baseline (independent random entries).
- The sector SPDRs' whole record under these rules, 2000-2026: H7's trades followed by H6's.
