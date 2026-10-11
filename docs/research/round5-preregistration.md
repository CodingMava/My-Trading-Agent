# Research round 5 pre-registration: a batch of documented monthly effects

Written 2026-10-11, **before** any of these rules was run on any of this data. The rules, data, costs,
tests, pass criteria and decision below are fixed. Results are reported against this document whatever
they show; the results file records this file's SHA-256 so any later edit is detectable.

## Why this round

Ten swing hypotheses have failed. Rather than one idea at a time, this round tests four well-documented
effects at once, chosen for their economic reasons and published record, not for how they looked
recently. Two extend round 4's turn of the month to new markets; two test momentum among ETFs.

**One criterion changes, for these new hypotheses only.** Rounds 1-4 required at least 70% of calendar
years to be profitable. For a strategy trading about once a month that test is miscalibrated: with about
12 trades a year, a single year's average is so noisy that a genuine edge of round 4's size (+0.23% a
trade, t = 2.3) would show a profitable year only about 65% of the time, and so would fail the 70% rule
in about three samples out of four. It is replaced by: expectancy above zero in each third of the
evaluation span, which such an edge passes about three times in four. This change was prompted by round 4. It is fixed here,
before these hypotheses are run, applies only to them, and does not reopen any rejected hypothesis:
rounds 1-4 stand as judged. Every other criterion is unchanged.

## Data and periods

| Item | H11 | H12 | H13 | H14 |
|---|---|---|---|---|
| Effect | Turn of the month | Turn of the month | Sector momentum | Country momentum |
| Instruments | NIFTY BANK, NIFTY NEXT 50, NIFTY IT, NIFTY PHARMA (indices standing in for BANKBEES, JUNIORBEES, ITBEES, PHARMABEES) | The 15 iShares country ETFs of round 3 (EWA, EWC, EWG, EWH, EWJ, EWL, EWS, EWT, EWU, EWW, EWY, EWZ, FXI, MCHI, INDA) | The 9 original Select Sector SPDRs (XLB, XLE, XLF, XLI, XLK, XLP, XLU, XLV, XLY) | The same 15 country ETFs |
| Bars used | From Yahoo's first bar (Sep 2007; NIFTY PHARMA Jan 2011) | From each ETF's listing | From listing (Dec 1998); round 3's frozen dataset | From each ETF's listing |
| Evaluation (signal dates) | 1 Jan 2008 to 8 Oct 2026 | 1 Jan 2001 to 8 Oct 2026 | 1 Jan 2000 to 8 Oct 2026 | 1 Jan 2001 to 8 Oct 2026 |

Source: Yahoo Finance daily bars, split- and dividend-adjusted, frozen with checksums and a validation
report (`data/round5/`, and `data/round3/` for the sector SPDRs). Bars after 8 Oct 2026 are dropped. The
country ETFs are evaluated from 2001: before then several traded so thinly that some days have flat bars,
and US prices moved to decimals in 2001.

**Earlier use of these series**, disclosed: the NIFTY sector and Next 50 indices (2014-2026), the sector
SPDRs and the country ETFs were used before for the pullback rules (rounds 2 and 3), and round 4 tested
the turn of the month on the NIFTY 50 and SPY only. None of these four rules was examined on any of these
instruments.

**Nothing is fitted:** each hypothesis is judged on its whole evaluation span.

**Data cleaning, fixed now.** As before: bars without prices and Yahoo's flat zero-volume placeholder
bars are dropped; every daily move above 20% is classified before any strategy runs (a corporate action
Yahoo didn't adjust splits the series; a genuine move is kept), and the results list every flag.

## Execution and costs

- Signals use completed daily bars; entries fill at the next open; a stop fills at the stop price, or at
  the open on a gap through it; a time exit fills at the close of its last day.
- H11: Zerodha ETF delivery charges at Rs 1 lakh plus 0.05% slippage per side, as round 2's H5: 0.139%
  round trip.
- H12 and H14: a commission-free US broker, the SEC fee and 0.05% slippage per side (country ETFs have
  wider spreads), as round 3's H8: 0.103% round trip at $10,000.
- H13: the same with 0.02% slippage per side, as H6: 0.043% round trip.
- Stress test: every cost x 1.5.

## Hypotheses

**H11 and H12, the turn of the month:** round 4's rule unchanged. Buy at the open of each month's last
trading day; sell at the close of the next month's third trading day, or earlier at a stop 2.5 x
ATR(14, Wilder) below entry (sized at the signal day's close; no trade before that ATR exists). One
position per instrument; every instrument trades every turn of the month. Rationale: H11, month-start
salary and SIP inflows into Indian funds; H12, McConnell & Xu (2008) found the effect in 30 of 35
countries.

**H13 and H14, momentum** (Jegadeesh & Titman 1993; across industries Moskowitz & Grinblatt 1999; across
countries Richards 1997 and Asness, Moskowitz & Pedersen 2013): on each month's last trading day, rank the
instruments with at least 273 trading days of history by their return from 252 to 21 trading days
earlier; buy the top 3 at the next open; sell each at the next open after the following month's last
trading day. Costs are charged on every monthly trade, even when an ETF is kept. No stop, as in the
literature and in Phase 3's H3; if one passed, the risk engine would first need a tested way to size
positions that have no stop.

## Tests

For each hypothesis, on its whole evaluation span, net of base costs unless stated:

- Trade statistics as before: count, win rate, average win and loss, profit factor, expectancy,
  t-statistic, worst trade in R (H11 and H12), drawdown, Sharpe.
- **Random baselines (2,000 draws).**
  - H11 and H12: the same four-day hold with the same stop, entered on random days, with trades the
    strategy entered on the same day kept together (as in rounds 2-4).
  - H13 and H14: three ETFs picked at random each month from the same eligible list (Phase 3's H3
    baseline).
  - p = the share of draws whose average gross return per trade is at least the strategy's. The four
    p-values are corrected for multiple testing with Holm's method.
- The cluster-robust t-statistic, with trades grouped by the calendar week of their signal.
- Stability: each half, each third, each calendar year, each instrument.

## Pass criteria (whole evaluation span, base costs unless stated)

| # | Criterion |
|---|---|
| 1 | At least 50 trades |
| 2 | Win rate at least 50% |
| 3 | Expectancy above zero at base costs and at 1.5x costs |
| 4 | t-statistic at least 2.0 |
| 5 | Beats its random baseline: Holm-adjusted p below 0.05 |
| 6 | Profit factor at least 1.3 |
| 7 | Average loss at most 1.5 x average win; with a stop, worst trade no worse than -3R |
| 8 | Expectancy above zero in each half of the span |
| 9 | Expectancy above zero in each third of the span (replaces "70% of years", see above) |
| 10 | At least 60% of instruments with 5+ trades are profitable, and expectancy stays above zero without the top-contributing instrument |
| 11 | Cluster-robust t-statistic (signal weeks as clusters) at least 2.0 |

**Decision, for each hypothesis on its own.**

| Outcome | Registry status |
|---|---|
| All criteria pass | `PAPER`. H11 paper trades its four ETFs on the existing NSE engine. H12-H14 first need US support in the paper engine (H13 and H14 also a stop-free sizing rule); US orders stay manual |
| Only criterion 1 (sample size) fails | `RESEARCH`: inconclusive |
| Anything else | `REJECTED` |

## Informational (does not affect the decisions)

- The share of profitable calendar years, the criterion used in rounds 1-4.
