# Research round 2 pre-registration: the pullback rules on new markets

Written 2026-10-09, **before** any of these strategies was run on any of this data. The rules, data,
costs, tests and pass criteria below are fixed. Results are reported against this document whatever
they show; the results file records this file's SHA-256 so any later edit is detectable. A failed
hypothesis is rejected, not adjusted and re-tested on the same data.

## Why this round

Phase 3 rejected all three of its hypotheses. Two lessons shape this round:

1. **Costs decide.** H1's pullback rules picked better entries than chance on NIFTY 50 stocks
   (+0.25% gross per trade vs +0.14% for random entries), but Indian delivery costs (0.30% round
   trip, mostly STT) took all of it. Index ETFs in India pay almost no STT, and US stocks and ETFs
   cost about 0.04% round trip.
2. **The rules stay fixed.** No parameter is fitted here. Every hypothesis reuses the Phase 3 H1
   rules exactly; only the market and the instruments change, and every instrument is new. Nothing
   used in the 2026-10-08 audit or in Phase 3 is reused: not the NIFTY 50 index or its stocks, not
   SPY, and not the 20 US large caps.

## Data and periods

| Item | Choice |
|---|---|
| US stocks (H4) | The 82 stocks listed below |
| US sector ETFs (H6) | The 11 Select Sector SPDRs: XLB, XLC, XLE, XLF, XLI, XLK, XLP, XLRE, XLU, XLV, XLY |
| India indices (H5) | NIFTY BANK (`^NSEBANK`), NIFTY IT (`^CNXIT`), NIFTY PHARMA (`^CNXPHARMA`), NIFTY NEXT 50 (`^NSMIDCP`) |
| Source | Yahoo Finance daily bars, split- and dividend-adjusted, frozen in `data/round2/` with checksums and a validation report |
| Fetched span | 12 years up to the last complete session used, 8 Oct 2026 (later bars are dropped) |
| Evaluation | 1 Jan 2016 to 8 Oct 2026 (earlier bars only warm up the indicators) |
| Design period | 1 Jan 2016 to 31 Dec 2021 |
| Holdout period | 1 Jan 2022 to 8 Oct 2026 (pass/fail is decided here) |

**US stocks (H4).** The S&P 100 members, excluding the 20 stocks already examined and GOOG (a second
share class of GOOGL): ABBV, ABT, ACN, ADBE, AIG, AMD, AMGN, AMT, AXP, BA, BKNG, BLK, BMY, BNY, BRK-B,
C, CAT, CHTR, CL, CMCSA, COF, COP, CRM, CSCO, CVS, CVX, DE, DHR, DIS, DUK, EMR, F, FDX, GD, GE, GILD,
GM, GS, HON, IBM, INTC, INTU, ISRG, LIN, LMT, LOW, MA, MCD, MDLZ, MDT, MET, MMM, MO, MRK, MS, NEE,
NFLX, NKE, NOW, ORCL, PEP, PFE, PLTR, PM, PYPL, QCOM, RTX, SBUX, SCHW, SO, SPG, T, TGT, TMO, TMUS, TXN,
UBER, UNP, UPS, USB, VZ, WFC. Stocks listed after 2015 (PLTR, UBER, PYPL) trade from their first
usable bar.

**India instruments (H5)**, chosen from data availability and liquidity only, before any strategy
ran: NSE indices with Yahoo history from before 2015 **and** an ETF tracking that index that traded a
median of at least Rs 10 crore a day over the 60 sessions to 8 Oct 2026:

| Index | ETF that would be traded | Median daily value | ETF vs index daily-return correlation |
|---|---|---:|---:|
| NIFTY BANK | BANKBEES | Rs 32 crore | 0.98 |
| NIFTY IT | ITBEES | Rs 32 crore | 0.98 |
| NIFTY NEXT 50 | JUNIORBEES | Rs 24 crore | 0.92 |
| NIFTY PHARMA | PHARMABEES | Rs 11 crore | 0.96 |

Excluded: NIFTY 50 (tested as H2), NIFTY MIDCAP 50, NIFTY 100 and NIFTY 500 (no ETF tracking them
trades Rs 10 crore a day), and other sector indices (no Yahoo history). Index prices stand in for the
ETFs' because Yahoo's own ETF series contain broken unit splits (BANKBEES and PSUBNKBEES show their
December 2019 splits as a four-day drop to a tenth of the price) and bad opening prints (JUNIORBEES
+18% on 9 Sep and 6 Nov 2020). The correlations above exclude the split days.

**Known biases.** Today's S&P 100 members over a past decade over-represent winners (survivorship
bias), which flatters long-only results. Every strategy is therefore compared with random entries in
the same instruments over the same period, which shares that bias.

**Data cleaning, fixed now.** Bars without prices and Yahoo's flat zero-volume placeholder bars are
dropped, as in Phase 3. The data-quality report flags every daily move above 20%. Before any
strategy runs, each flag in a US stock is classified: a corporate action Yahoo didn't adjust (for
example a spin-off) splits that stock's series at that date, so no trade or indicator spans the fake
jump; a genuine price move is kept. The results file lists every flag and how it was classified.

## Execution and costs

- As in Phase 3: signals use completed daily bars; entries fill at the next day's open; rule-based
  exits are decided on a close and fill at the next open; stops fill at the stop price, or at the
  open if the day gaps through it; a time exit fills at the close of the last allowed day.
- US stocks and ETFs (H4, H6): a commission-free broker, the SEC fee on sales, and 0.02% slippage per
  side, 0.043% round trip at $10,000. Currency conversion (paid per fund transfer, not per trade) and
  taxes are not included.
- India ETFs (H5): Zerodha ETF delivery charges at Rs 1 lakh per position (STT 0.001% on the sell side
  only, stamp duty, exchange and SEBI fees, GST, the Rs 15.34 DP charge) plus 0.05% slippage per side,
  higher than H2's 0.03% to allow for sector ETFs' wider spreads and for an ETF's opening price
  differing from its index's: 0.139% round trip.
- Stress test: every cost x 1.5.

## Hypotheses

All three use the Phase 3 H1 rules unchanged (`pullback_signals` with the default `PullbackParams`
in `trader/strategies/swing.py`):

- Entry signal: close > 200-day SMA **and** 2-day RSI (Wilder) < 10.
- Exit: the first close above the 5-day SMA (sell next open); or a stop 2.5 x ATR(14, Wilder) below
  entry, sized at the signal day's close; or after 10 trading days (sell at that close).
- One position per instrument at a time. R (risk unit) = the stop distance.

### H4: Oversold pullback in an uptrend, US large caps

Short-term reversal of sharp pullbacks inside long-term uptrends (Connors & Alvarez 2008; Jegadeesh
1990; Lehmann 1990). In the audit's informational run on 20 other US large caps, these rules made
+0.35% per trade net over the 2022-2026 holdout (719 trades, 66% winners, t 2.64), but random entries
in the same stocks did nearly as well (p = 0.09). This tests the effect on 82 stocks never examined.

### H5: Oversold pullback in an uptrend, Indian index ETFs

The same effect at index level in India, where ETFs avoid the STT that sank H1. H2 (the NIFTY 50
alone) had the right sign in its holdout (+0.12% per trade, 63% winners) but too few trades to judge
(46); four other indices give enough trades to test it.

### H6: Oversold pullback in an uptrend, US sector ETFs

The same effect in diversified, very liquid ETFs (Connors & Alvarez, *High Probability ETF Trading*,
2009), without the earnings gaps of single stocks.

## Tests

For each hypothesis, net of base costs unless stated:

- Trade statistics as in Phase 3: count, win rate, average win and loss, profit factor, expectancy,
  t-statistic, worst trade in R, drawdown, Sharpe.
- **Random-entry baseline that keeps simultaneous trades together** (new in this round, 2,000 draws,
  on the holdout). Signals in correlated instruments often fire on the same day (many stocks after one
  market drop); treated as independent trades they make any baseline comparison look more certain
  than it is. So for every day on which the strategy entered, one random holdout day is drawn on which
  all the instruments it entered that day could be entered, and random trades are taken in those same
  instruments on that day, with the same exits. p = the share of draws whose average gross return per
  trade is at least the strategy's.
- The three holdout p-values are corrected for multiple testing with Holm's method.
- **Cluster-robust t-statistic** (new): the same expectancy, with its standard error computed from
  trades grouped by the calendar week of their signal, so trades that share a market move count as
  one cluster.
- Stability: design vs holdout; each calendar year; each instrument; result without the top contributor.

## Pass criteria (holdout, base costs unless stated)

| # | Criterion |
|---|---|
| 1 | At least 50 trades |
| 2 | Win rate at least 50% (the "not mostly losing" floor) |
| 3 | Expectancy above zero at base costs and at 1.5x costs |
| 4 | t-statistic at least 2.0 |
| 5 | Beats the random-entry baseline above: Holm-adjusted p below 0.05 |
| 6 | Profit factor at least 1.3 |
| 7 | Average loss at most 1.5 x average win; worst trade no worse than -3R |
| 8 | Design-period expectancy also above zero |
| 9 | At least 70% of calendar years (with 10+ trades, whole evaluation span) have positive expectancy |
| 10 | At least 60% of instruments with 5+ trades are profitable, and expectancy stays above zero without the top-contributing instrument |
| 11 | Cluster-robust t-statistic (signal weeks as clusters) at least 2.0 |

Criteria 1-10 are Phase 3's, with criterion 10 applied to every hypothesis because each trades
several instruments. Criterion 11 is new and only adds strictness.

**Decision.**

| Outcome | Registry status |
|---|---|
| All criteria pass | `PAPER`: eligible for paper trading |
| Only criterion 1 (sample size) fails | `RESEARCH`: inconclusive |
| Anything else fails | `REJECTED` |

A passing India strategy is paper traded on the ETFs listed above, not the indices. A passing US
strategy can't paper trade until the paper engine supports US markets (NYSE calendar, US costs and
currency); US orders stay manual. Nothing here can emit a live signal: only `LIVE_SMALL` and `LIVE`
can, and reaching those needs paper-trading evidence.

## Informational (does not affect the decisions)

Each hypothesis's p-value is also computed with Phase 3's baseline (independent random entries), to
show how much the treatment of simultaneous trades matters.
