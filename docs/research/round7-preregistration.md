# Research round 7 pre-registration: market intraday momentum in NIFTYBEES, on 1-minute bars

> **DRAFT for review, not pinned.** Written on 13 Oct 2026. Nothing has been computed on the frozen minute data
> except the completeness and data-error checks in `docs/research/kite-minute-data.md`: no returns, signals or
> patterns. Once approved, this note is removed and the file is pinned by its SHA-256 and committed. The runner
> refuses to run if the file changes afterwards. Results are reported against it whatever they show, and no rule,
> cost or criterion changes after seeing them.

## Why this round

- Twenty hypotheses on daily data (H1-H14, C1-C6) failed, and the project runs no more rounds on that data.
- New data: Kite's 1-minute bars, frozen on 13 Oct 2026, so fills can be modelled at the minutes a real order
  would get them.
- The effect: market intraday momentum (Gao, Han, Li and Zhou, "Market intraday momentum", Journal of Financial
  Economics, 2018). The market's return over the first half hour of the day, from the previous close, predicts
  its return in the last half hour, in the same direction. The effect is stronger on volatile days. It was
  published before any of this data existed, with its rules fixed then, so all of 2020-2026 is out of sample
  for it. It hasn't been tested in this project: round 6's C3 traded the opening gap from the open to the close.
- Instrument: NIFTYBEES, an ETF on the NIFTY 50. It has no survivorship problem, has been liquid since 2020, and
  can be traded intraday both ways (MIS). Signals come from the NIFTY 50 index, whose opening prints are sound;
  NIFTYBEES' 09:15 prints are not, in 2020-2022.
- **The hurdle, stated before the test.** For SPY, Gao et al. found about 6.7% a year from the last half hour:
  roughly 0.03% a day before costs. Here a round trip costs about 0.12% (Indian intraday tax, charges and
  slippage). I1 and I2 can pass only if the effect in India is several times larger. I3 trades only big mornings,
  where the literature found the effect strongest. Failing on costs is the most likely outcome, and an honest one.

## Data

- `data/kite_minute/nifty_1m`, git-ignored, with one file for each instrument:
  - `NIFTYBEES.NS.parquet`: 628,692 rows, SHA-256
    `50366de7326503bc73d0ade0210bce612eaa2821167d35b17a6e25a5f2c8ce8d`.
  - `^NSEI.parquet`: 628,721 rows, SHA-256 `943600f23529989296aeb0528be3bba28801bd9f6d72b94816836376dc562a96`.
- Span: 1 Jan 2020 to 12 Oct 2026, 1,684 sessions. The runner loads both files through their checksums and
  refuses changed files.
- Known issues, handled as follows:
  - **NIFTYBEES' 09:15 prints** (unreliable in 2020-2022) are never used. The signal comes from the index, and
    every trade happens from 14:45.
  - **NSE's closing auction.** Since 3 Aug 2026 the index has been flat from 15:15, because its stocks stop
    trading continuously then. Brokers also square off intraday (MIS) positions shortly before the close. So
    every rule ends by the 15:14 bar, in every year, and the "previous close" is the previous session's 15:14
    index bar.
  - **Minutes without trades.** No fill is ever taken in a minute without volume. A session is skipped, and
    counted, when:
    - its NIFTYBEES 14:45 or 15:14 bar has zero volume;
    - any NIFTYBEES bar from 14:45 to 15:14 is missing;
    - the index's 09:44 bar, or the previous session's 15:14 index bar, is missing.
  - **The research loaders' filter for Yahoo's holiday placeholders is not applied**: it would drop real
    minutes. The only cleaning is sorting timestamps and dropping duplicates (there are none).
  - **Special sessions.** Muhurat sessions lack these bars and drop out by themselves. The Budget-day session
    (Sunday 1 Feb 2026, normal hours) counts like any other session.

## Definitions

- **r_first** = close of the index's 09:44 bar / close of the previous session's 15:14 index bar - 1. It is the
  overnight change plus the first 30 minutes, known at 09:45.
- **Big morning** (I3): |r_first| at or above the 80th percentile of the previous 250 sessions' |r_first|.
  I3 needs 250 previous sessions, so it starts in early 2021.
- **The window:** entry at the open of NIFTYBEES' 14:45 bar, exit at the close of its 15:14 bar (30 minutes),
  unless the stop is hit first.
- **The stop:** 0.5% from the entry, below it for a long and above it for a short. It is checked on each
  NIFTYBEES bar from 14:45 to 15:14:
  - a long stops when a bar's low reaches the stop; a short stops when a bar's high reaches it;
  - it fills at the stop price, or at the bar's open if the bar opened beyond the stop;
  - R is 0.5% of the entry price.
- **Gross return:** for a long, exit / entry - 1; for a short, 1 - exit / entry.

## Hypotheses

| Id | Rule |
|---|---|
| I1 | Long side: on every session with r_first > 0, buy NIFTYBEES over the window |
| I2 | Short side: on every session with r_first < 0, short NIFTYBEES over the window (intraday, MIS) |
| I3 | Big mornings: on every session with a big morning, trade in r_first's direction over the window (long if above 0, short if below) |

Each hypothesis takes one trade per session at most, with no re-entry after a stop. I3's trades are a subset of
I1's and I2's; the Holm correction allows for that.

## Costs, slippage, size and risk limits

- **Charges:** Zerodha intraday (MIS), as of 13 Oct 2026:
  - brokerage 0.03% or Rs 20 per order, whichever is lower;
  - STT 0.025% on the sell side;
  - NSE transaction charge 0.00307% per side;
  - SEBI fee Rs 10 per crore per side;
  - GST 18% on brokerage plus transaction and SEBI charges;
  - stamp duty 0.003% on the buy side.
  At Rs 2,00,000 a trade this is 0.0591% per round trip. (The project's shared cost model still has the older
  0.00297% transaction charge; this round uses today's figure and leaves earlier rounds as they were.)
- **Slippage:** 0.03% per side, on the entry and on every exit, stops included: 0.06% per round trip. This is
  round 6's assumption for NIFTYBEES and is conservative for an ETF whose spread is usually one paisa.
- **Total:** 0.1191% per round trip, taken from every trade's gross return, the same for longs and shorts.
- **Size:** Rs 2,00,000 a trade. Risking 0.5% of equity with a 0.5% stop would call for a position worth 100% of
  equity, so the risk engine's 20% cap on the Rs 10,00,000 paper account binds, and each trade risks 0.1% of
  equity.
- **Risk limits:** as the engine applies them: one position at a time per hypothesis, no leverage, no new entry
  after a 2% daily loss, and the kill switch at a 10% drawdown. They don't bind in this per-trade test, but they
  apply to the portfolio view and to any later paper trading.

## Tests

- Statistics for each hypothesis over the whole span, net of costs.
- **Random baseline** (criterion 5). For each hypothesis, a pool of the same window traded the same way (side
  and stop) on every usable session; for I3, on every session where its threshold can be computed. 2,000 draws
  (seed 7), each of as many sessions as the hypothesis traded; for I3, as many of each side as it traded. p is
  the share of draws whose mean gross return is at least the hypothesis's. The three p-values are
  Holm-corrected together.
- A cluster-robust t-statistic, clustering trades by the calendar week of their signal.

## Pass criteria (each hypothesis on its own; every criterion must pass)

| # | Criterion |
|---|---|
| 1 | At least 50 trades |
| 2 | Win rate at least 50% |
| 3 | Expectancy above zero at base costs and at 1.5x costs |
| 4 | t-statistic at least 2.0 |
| 5 | Beats its random baseline: Holm-adjusted p below 0.05 |
| 6 | Profit factor at least 1.3 |
| 7 | Average loss at most 1.5 x the average win; no trade worse than -3R |
| 8 | Expectancy above zero in each half of the span |
| 9 | At least 70% of calendar years with 10+ trades profitable |
| 11 | Cluster-robust t-statistic (signal weeks as clusters) at least 2.0 |
| 12 | Raw random-baseline p below 0.05 / 23 = 0.0022: 23 hypotheses will then have been tested in this project |
| 13 | Drawdown no deeper than 20R: cumulative R, trades taken in exit order (the gate's limit for PAPER) |

Criterion 10 (breadth across instruments) doesn't apply to one instrument.

## Decisions

| Outcome | Decision |
|---|---|
| Every criterion passes | Candidate for PAPER, once you approve. Paper trading first needs an intraday paper path (today's engine is end-of-day only) and, for I2 and I3, short selling (after checking that Zerodha allows NIFTYBEES short in MIS); then the paper-trading stage (Level 5). Live trading stays locked. |
| Only criterion 1 fails | Inconclusive |
| Anything else | REJECTED |

Nothing above changes once this file is pinned. A changed rule is a new hypothesis, which can only be judged on
data that doesn't exist yet: a forward test.

## Informational (no effect on the decisions)

- Results by calendar year, and before and after 3 Aug 2026 (the closing auction).
- Results by India VIX regime: its previous close above or below its 250-day median, from
  `data/round6/aux_daily`.
- The window traded every session, regardless of r_first, long only.
- Each hypothesis without the stop.
- Costs at 0x, 1x, 1.5x and 2x.
- The portfolio view: Rs 10,00,000 and positions of 20%.

Patterns seen in these reports are hypotheses for future data, not findings.

## Runner

`trader/research/round7.py`, written after this file is pinned, tested on synthetic bars, then run once on the
frozen data. It writes `docs/research/round7-results.md` and evidence files for I1-I3, each recording the
backtest's drawdown in R.
