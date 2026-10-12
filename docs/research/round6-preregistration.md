# Chan round pre-registration (scratch round, outside the project): Ernest Chan's strategies on NSE and US data

Written 2026-10-12, **before** any rule below was run on any of this data. Data-quality checks made beforehand: (1) every daily move above 20% in the NIFTY 50 stock data was listed and classified (table below); (2) the share of index days whose open equals the previous close was measured (NIFTY 0.5%; SPY 1.6%, concentrated in 1993-94). Nothing about any strategy's trades or returns was computed. The rules, data, costs, tests, pass criteria and decisions below are fixed. Results are reported against this file whatever they show; the runner checks this file's SHA-256 (LF line endings) against the value recorded in `pin.txt` when it was written.

This round runs in the scratchpad and changes nothing in the project. It is numbered C1-C6 so it doesn't collide with the project's H-numbers, but it **counts toward the project's multiple-testing record**: after it, 20 hypotheses (H1-H14, C1-C6) will have been tested on overlapping data.

## Source of the rules, and what could not be verified

The rules come from Ernest P. Chan, *Algorithmic Trading: Winning Strategies and Their Rationale* (Wiley, 2013). The full text was **not** accessible in this session. The rules below are as described by secondary sources and by my own recollection of the book, so they may differ from the book's exact parameters:

- C1/C2 "buy-on-gap" (Ch. 4, Mean Reversion of Stocks and ETFs): rules as summarised by a public replication (financialnoob, "Buy on gap strategy and its performance").
- C3/C4 "opening gap" (Ch. 7, Intraday Momentum Strategies): Chan applied it to Dow Jones STOXX 50 index futures. The threshold (0.1 x the 90-day standard deviation) is as summarised by a forum replication; not verified against the book.
- C5/C6 time-series momentum (Ch. 6, Interday Momentum Strategies): the sign of the past 12-month return, the rule of Moskowitz, Ooi and Pedersen (2012), which Chan discusses. Long-only (hold the index or cash) and a one-month holding period are this round's choices, made because Indian delivery trades can't be short and US trades are manual.

The test is therefore of these rules as written here, not a verdict on the book.

## Common definitions

For an instrument on day t (all from completed bars before t's open unless stated):

- sigma_t: standard deviation (ddof 1) of the 90 daily close-to-close returns ending at t-1's close.
- MA20_t: mean of the 20 closes ending at t-1.
- ATR_t: Wilder ATR(14) at t-1's close (`trader.features.indicators.atr`), as a fraction of t-1's close.
- An intraday trade enters at t's open and exits at t's close. Its protective stop is ATR_t below entry for a long (above it for a short). The stop fills at the stop price if the day's low (high) reaches it. Every intraday trade has this stop, because the project's risk engine sizes by stop distance and refuses positions without one. The book's version has no stop and is reported as a variant (informational).

## Hypotheses

| Id | Rule | Market and data | Round-trip cost (base) |
|---|---|---|---|
| C1 | Buy-on-gap: a stock is eligible on day t if open_t / low_{t-1} - 1 < -sigma_t and open_t > MA20_t. Buy up to 10 eligible stocks with the most negative open_t / low_{t-1} - 1 (ties by symbol), intraday. | NIFTY 50 stocks (current list of 50), Yahoo daily, traded as Zerodha MIS | 0.1824% (Zerodha intraday at Rs 1,00,000 with 0.05% slippage per side) |
| C2 | Buy-on-gap, same rules | 82 S&P 100 stocks of round 2, manual US orders | 0.1028% (commission-free + SEC fee, 0.05% per side at $10,000) |
| C3 | Opening gap: long if open_t > high_{t-1} x (1 + 0.1 sigma_t); short if open_t < low_{t-1} x (1 - 0.1 sigma_t); intraday | NIFTY 50 index (^NSEI), traded as NIFTYBEES MIS (or NIFTY futures) | 0.1188% (Zerodha intraday at Rs 2,00,000, 0.03% slippage per side) |
| C4 | Opening gap, same rules | SPY | 0.0428% (commission-free, 0.02% per side) |
| C5 | Time-series momentum: on each month's last trading day t, be invested for the next month if close_t / close_{t-252} - 1 > 0, else hold cash. Switches fill at the next trading day's open. A "trade" is one invested month: from that open to the open after the next month-end. | NIFTY 50 price index (^NSEI; no dividends, for strategy and benchmark alike); cash earns 6.0% a year (an assumption) | 0.1386% per round trip (Zerodha ETF delivery, 0.05% per side), charged half on entering and half on leaving, only when the position changes |
| C6 | Time-series momentum, same rules | SPY (Yahoo-adjusted, dividends included); cash earns the 13-week T-bill yield (^IRX, the previous day's value) | 0.0428%, charged per side only when the position changes |

Buy-on-gap rationale (Chan): overnight panic selling or order imbalance pushes some stocks' opens too low, and those still above their 20-day average tend to recover during the day. Opening-gap rationale (Chan): stops triggered at a gap open push prices further the same way during the day. Time-series momentum rationale: trends persist over months (slow diffusion of information, hedging demand), and staying out after a 12-month loss avoids part of a bear market.

## Data

All Yahoo daily bars, split- and dividend-adjusted, frozen with checksums in the project's `data/` (git-ignored, read-only here), cut at 8 Oct 2026:

- C1: `data/phase3/nse_nifty50_daily` (30 Sep 2014 to 8 Oct 2026). Cleaned as in Phase 3: bars without prices and flat zero-volume placeholder bars dropped; series split at the three unadjusted corporate actions (ADANIENT.NS 2015-06-03 demerger, TMPV.NS 2025-10-14 demerger, TRENT.NS 2026-01-01 bonus). **Survivorship bias:** the list is today's constituents, so stocks that fell out of the index (e.g. YESBANK, ZEEL, VEDL) are missing. This inflates any rule that buys falling stocks. A pass would need a point-in-time universe test before paper trading.
- C2: `data/round2/us_stocks_daily` with round 2's cleaning and classification (`round2.load_clean`, DHR split at 2016-07-05). The same survivorship caveat applies.
- C3, C5: `data/round4/nse_nifty_daily` (^NSEI from 17 Sep 2007), round 4's cleaning.
- C4, C6: `data/round4/us_spy_daily` (SPY from 29 Jan 1993), round 4's cleaning.
- Regimes and cash: ^VIX, ^INDIAVIX and ^IRX, fetched on 2026-10-12 into the scratchpad (`aux_daily`).

Moves above 20% in the NIFTY 50 stock data, classified before any rule ran:

| Stock | Date | Classification |
|---|---|---|
| ADANIENT.NS | 2015-06-03 | Corporate action (demerger) Yahoo mis-adjusted: series split |
| ADANIENT.NS | 2017-04-26 | Not verified; the open gapped up (+0.2%), so it can't trigger a buy-on-gap entry; kept |
| SBIN.NS | 2017-10-25 | Genuine: government's bank recapitalisation plan |
| ADANIENT.NS | 2018-09-06 | Genuine (company news; not individually verified); gap up, can't trigger an entry; kept |
| ADANIENT.NS | 2019-05-20 | Genuine: election exit-poll rally |
| AXISBANK, BAJAJFINSV, BAJFINANCE, SHRIRAMFIN | 2020-03-23 | Genuine: COVID-19 crash |
| ADANIENT.NS | 2020-08-25 | Genuine (company news; not individually verified); gap up; kept |
| TMPV.NS | 2021-10-13 | Genuine: TPG investment in the EV unit |
| ADANIENT.NS | 2023-02-01, 2023-02-02, 2023-02-08 | Genuine: Hindenburg report and its aftermath |
| ADANIPORTS.NS | 2024-06-04 | Genuine: general-election results day |
| ADANIENT.NS | 2024-11-21 | Genuine: US indictment news |
| TMPV.NS | 2025-10-14 | Corporate action (demerger): series split |
| TRENT.NS | 2026-01-01 | Corporate action (bonus): series split |

## Evaluation span: after the book's publication

The book appeared in 2013, so its rules were fixed before any later data existed. Every hypothesis is **judged on signals from 1 Jul 2013 to 8 Oct 2026**: data its rules were never designed on. For C1/C2 the data begins in Sep 2014, and with the warm-up the first possible signal is in early 2015. Data before Jul 2013 (C3-C6) is reported as in-sample context only. Every rule's parameters are fixed: nothing is fitted.

## Tests

On the decision span, net of base costs unless stated:

- Trade statistics: count, win rate, average win and loss, profit factor, expectancy, t-statistic, worst trade in R (C1-C4), the share of stop exits.
- **Random baselines (2,000 draws, seed 7).** p = the share of draws whose mean gross return per trade is at least the strategy's.
  - C1/C2: same-day random entries. For each day the strategy traded, one random day in the decision span is drawn on which all of that day's stocks were tradeable (sigma, MA20 and ATR defined). Their intraday outcomes (same entry, exit and stop) on that day stand in for the strategy's (`validation.same_day_random_test`).
  - C3/C4: random days with the same side. Pools hold the intraday outcome of a long and of a short (same stop) on every tradeable day of the decision span (`validation.random_entry_test`, keyed by side).
  - C5/C6: random months. The same number of invested months is drawn from all months of the decision span, using the index's gross holding-month returns.
  - The six p-values are Holm-corrected together.
- Cluster-robust t-statistic, with trades clustered by the calendar week of their signal.

## Pass criteria (decision span, base costs unless stated)

| # | Criterion |
|---|---|
| 1 | At least 50 trades |
| 2 | Win rate at least 50% |
| 3 | Expectancy above zero at base costs and at 1.5x costs |
| 4 | t-statistic at least 2.0 |
| 5 | Beats its random baseline: Holm-adjusted p below 0.05 |
| 6 | Profit factor at least 1.3 |
| 7 | Average loss at most 1.5 x average win; with a stop, no trade worse than -3R |
| 8 | Expectancy above zero in each half of the span |
| 9 | C1-C4: at least 70% of calendar years with 10+ trades profitable. C5-C6 (about 12 trades a year): expectancy above zero in each third of the span (round 5's rule for monthly strategies) |
| 10 | C1/C2 only: at least 60% of stocks with 5+ trades profitable, and expectancy above zero without the top-contributing stock |
| 11 | Cluster-robust t-statistic (signal weeks as clusters) at least 2.0 |
| 12 | **New, for data-mining bias across rounds (Aronson):** the raw random-baseline p below 0.05 / 20 = 0.0025, because 20 hypotheses have now been tested in this project on overlapping data |

**Decisions, for each hypothesis on its own:**

| Outcome | Verdict |
|---|---|
| All criteria pass | Candidate for PAPER. The project still needs its own pre-registration in `trader/research`, the user's approval and the gate. C1/C2 would first need a point-in-time constituents test and a minute-data check of fills near the open. |
| Only criterion 1 (sample size) fails | Inconclusive |
| Anything else | Rejected |

## Informational (does not affect the decisions)

- Portfolio view. C1/C2: 10 slots of 10% of capital, a slot per position, so the day's return is the sum of net trade returns / 10. C3/C4: 100% of capital per trade. C5/C6: the timed portfolio including cash. Reported: CAGR, annual volatility, Sharpe (zero risk-free rate), Sortino and maximum drawdown, next to buy-and-hold of the index (C3-C6).
- Cost sensitivity at 0x, 1x, 1.5x and 2x.
- Regimes, all known before the open. Trend: the index's previous close above its 50-day average (`validation.trend_regime`; NIFTY for India, SPY for the US). Volatility: the volatility index's previous close above its 250-day median (`validation.volatility_regime`; ^INDIAVIX, ^VIX).
- In-sample context: C3-C6 before Jul 2013.
- Walk-forward (rolling 3-year training window, 1-year test, moving a year at a time, over all available data):
  - C1/C2: the gap threshold from {0.5, 1.0, 1.5} sigma.
  - C3/C4: the threshold from {0, 0.1, 0.25, 0.5} sigma.
  - C5/C6: the lookback from {63, 126, 252} days.
  - Selection uses the training window's net expectancy per trade for C1-C4 (at least 20 training trades, else the book value) and the training window's Sharpe ratio of the timed portfolio for C5-C6.
  - Reported: the concatenated test-year results against the fixed book parameters over the same years.
- The book's version without the protective stop (C1-C4).
- C5 with a cash yield of 0% and of 4%.
