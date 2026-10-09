# Phase 3 pre-registration: swing-trading hypotheses

Written 2026-10-09, **before** any of these strategies was run on any data. The rules, parameters,
data, costs, tests and pass criteria below are fixed. Results are reported against this document
whatever they show; the results file records this file's SHA-256 so any later edit is detectable.
Parameters come from published sources and are not tuned. A failed hypothesis is rejected, not
adjusted and re-tested on the same data.

## Data and periods

| Item | Choice |
|---|---|
| India universe | NIFTY 50 constituents as of 8 Dec 2025 (`.NS` symbols), daily bars |
| India index | NIFTY 50 (`^NSEI`), daily bars |
| Source | Yahoo Finance, split- and dividend-adjusted, frozen with checksums and a validation report |
| Fetched span | about 12 years up to the last complete session (8 Oct 2026) |
| Evaluation | 1 Jan 2016 to 8 Oct 2026 (earlier bars only warm up the indicators) |
| Design period | 1 Jan 2016 to 31 Dec 2021 |
| Holdout period | 1 Jan 2022 to 8 Oct 2026 (pass/fail is decided here) |

**Known bias.** Today's index members over a past decade over-represent winners (survivorship bias),
which flatters long-only results. Every strategy is therefore compared with random entries in the
same instruments over the same period (below), which shares that bias.

## Execution and costs

- Signals use completed daily bars. Entries fill at the next day's open. Rule-based exits are decided
  on a close and fill at the next open. Stops fill at the stop price, or at the open if the day
  gaps through it. A time exit fills at the close of the last allowed day.
- Stocks pay Zerodha delivery costs at Rs 1 lakh per position: STT 0.1% on each side, stamp duty,
  exchange and SEBI fees, GST, the Rs 15.34 DP charge, plus 0.03% slippage per side (0.298% round trip).
- The index strategy is executed through a NIFTY 50 ETF: STT 0.001% on the sell side only, the same
  other charges, plus 0.03% slippage per side (about 0.10% round trip). Index prices stand in for the
  ETF's, which track it closely.
- Stress test: every cost x 1.5.

## Hypotheses

### H1: Oversold pullback in an uptrend, NIFTY 50 stocks

Short-term reversal of sharp pullbacks inside long-term uptrends (Connors & Alvarez, *Short Term
Trading Strategies That Work*, 2008; short-term reversal: Jegadeesh 1990, Lehmann 1990).

- Entry signal: close > 200-day SMA **and** 2-day RSI (Wilder) < 10.
- Exit: the first close above the 5-day SMA (sell next open); or a stop 2.5 x ATR(14, Wilder) below
  entry, sized at the signal day's close; or after 10 trading days (sell at that close).
- One position per stock at a time. R (risk unit) = the stop distance.

### H2: Oversold pullback in an uptrend, NIFTY 50 index (via ETF)

The same mean-reversion effect at index level, where it is usually reported to be more reliable, with
much lower costs. Rules identical to H1, applied to `^NSEI`, with ETF costs.

### H3: 12-1 month momentum, NIFTY 50 stocks

Stocks with the best past-year returns, excluding the last month, keep outperforming over the next
month (Jegadeesh & Titman 1993; documented in Indian equities too).

- On each month's last trading day, rank stocks with at least 273 trading days of history by their
  return from 252 trading days ago to 21 trading days ago.
- Buy the top 5 at the next open; sell each at the next open after the following month-end (one
  trade per stock per month; costs are charged on every monthly trade, even if the stock is kept).
- No stop. Random baseline: 5 stocks drawn at random from the same eligible stocks each month.

## Tests

For each hypothesis, net of base costs unless stated:

- Trade statistics: count, win rate, average win and loss, profit factor, expectancy, t-statistic,
  worst trade (R where a stop exists), drawdown, Sharpe.
- Random-entry baseline (2,000 draws), computed on the holdout:
  - H1: random entry days in the same stocks, with the same exits.
  - H2: random entry days in the index, with the same exits.
  - H3: random 5-stock picks from the same month's eligible stocks.
- The three holdout random-entry p-values are corrected for multiple testing with Holm's method.
- Stability: design vs holdout; each calendar year; each stock; result without the top contributor.

## Pass criteria (holdout, base costs unless stated)

| # | Criterion |
|---|---|
| 1 | At least 50 trades |
| 2 | Win rate at least 50% (the "not mostly losing" floor) |
| 3 | Expectancy above zero at base costs and at 1.5x costs |
| 4 | t-statistic at least 2.0 |
| 5 | Beats random entries: Holm-adjusted p below 0.05 |
| 6 | Profit factor at least 1.3 |
| 7 | Average loss at most 1.5 x average win; with a stop, worst trade no worse than -3R |
| 8 | Design-period expectancy also above zero |
| 9 | At least 70% of calendar years (with 10+ trades, whole evaluation span) have positive expectancy |
| 10 | Stock strategies: at least 60% of stocks with 5+ trades are profitable, and expectancy stays above zero without the top-contributing stock |

Maximum drawdown is reported but judged in Phase 6, where position sizing makes it meaningful.

**Decision.**

| Outcome | Registry status |
|---|---|
| All criteria pass | `PAPER`: eligible for paper trading once Phases 4-7 exist |
| Only criterion 1 (sample size) fails | `RESEARCH`: inconclusive |
| Anything else fails | `REJECTED` |

Nothing here can emit a live signal: only `LIVE_SMALL` and `LIVE` can, and reaching those needs
paper-trading evidence.

## Informational check (does not affect the decision)

H1 and H2 are also run on 20 US large caps and on SPY (US costs), to see whether any edge
generalises beyond India.
