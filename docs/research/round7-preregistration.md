# Research round 7 pre-registration: market intraday momentum in NIFTYBEES, on 1-minute bars

> **DRAFT for review, not pinned.** Written on 13 Oct 2026. Nothing has been computed on the frozen minute data
> except the completeness and data-error checks in `docs/research/kite-minute-data.md`: no returns, signals or
> patterns. Once you approve it, this note is removed and the file is pinned, pushed and only then used (see
> "Protocol" at the end).

## Why this round

- **Daily data is exhausted.** Twenty hypotheses on daily data (H1-H14, C1-C6) failed, and the project runs no
  more rounds on that data.
- **New data.** Kite's 1-minute bars, frozen on 13 Oct 2026, so fills can be modelled at the minutes a real
  order would get them.
- **The effect: market intraday momentum.** From Gao, Han, Li and Zhou, "Market intraday momentum", Journal of
  Financial Economics, 2018. The market's return over the first half hour of the day, from the previous close,
  predicts its return in the last half hour, in the same direction. The effect is stronger on volatile days.
  - It was published before any of this data existed, with its rules fixed then, so all of 2020-2026 is out of
    sample for it.
  - It hasn't been tested in this project; round 6's C3 traded the opening gap from the open to the close.
- **The instrument: NIFTYBEES,** an ETF on the NIFTY 50.
  - It has no survivorship problem and has been liquid since 2020.
  - It can be traded intraday (it is on Zerodha's MIS list, below).
  - Signals come from the NIFTY 50 index itself, whose opening prints are sound; NIFTYBEES' 09:15 prints are not,
    in 2020-2022.
- **The hurdle, stated before the test.** For SPY, Gao et al. found about 6.7% a year from the last half hour,
  roughly 0.03% a day before costs. Here a round trip costs about 0.12%. I1 and I2 can pass only if the effect in
  India is several times larger. I3 trades only big mornings, where the effect was strongest. Failing on costs is
  the most likely outcome, and an honest one.

## Checked on 13 Oct 2026

- **Zerodha's intraday (MIS) charges,** from zerodha.com/charges:
  - brokerage 0.03% or Rs 20 per executed order, whichever is lower;
  - STT 0.025% on the sell side;
  - NSE transaction charge 0.00307% per side;
  - SEBI fee Rs 10 per crore per side;
  - stamp duty 0.003% on the buy side;
  - GST 18% on brokerage plus the transaction and SEBI charges.
- **STT on ETFs:** intraday (non-delivery) sales of equity ETF units pay the same 0.025%; the 0.001% rate is for
  delivery sales only. The Finance Act 2026 raised STT only on derivatives.
- **Intraday eligibility:** NIFTYBEES is on Zerodha's intraday margin list at 20% margin (up to 5x), list updated
  13 Oct 2026. No leverage is used here. Intraday (MIS) orders may sell first and buy back the same day for
  listed scrips. A short NIFTYBEES order is to be confirmed in Kite's order window before any short side is
  ever paper traded; the backtest doesn't depend on it.
- **Auto square-off:** Zerodha squares off intraday positions at 15:12 for stocks in NSE's closing auction and at
  15:25 for the rest (F&O at 15:26), with a charge of Rs 50 + GST per order. NIFTYBEES is not in the closing
  auction: its bars run every minute to 15:29 since the auction began on 3 Aug 2026. Its square-off is therefore
  15:25, and every trade here closes by 15:14.

## Data

- `data/kite_minute/nifty_1m`, git-ignored, loaded through its checksums; the runner refuses changed files:
  - `NIFTYBEES.NS.parquet`: 628,692 rows, SHA-256
    `50366de7326503bc73d0ade0210bce612eaa2821167d35b17a6e25a5f2c8ce8d`.
  - `^NSEI.parquet`: 628,721 rows, SHA-256 `943600f23529989296aeb0528be3bba28801bd9f6d72b94816836376dc562a96`.
- **Span:** 1 Jan 2020 to 12 Oct 2026, 1,684 sessions.
- **Bar labels:** each bar is labelled by the minute it starts, so the 09:44 bar covers 09:44:00-09:44:59. Every
  regular session runs from a 09:15 bar to a 15:29 bar.
- **Cleaning:** none, except sorting timestamps and dropping duplicates (there are none). The research loaders'
  filter for Yahoo's holiday placeholders is not applied, because it would drop real minutes.
- **Known issues and how they are met:**
  - NIFTYBEES' unreliable 09:15 prints are never used.
  - The index has been flat from 15:15 since the closing auction began, so every rule ends by the 15:14 bar, in
    every year, and the "previous close" is the previous session's 15:14 index bar.
  - Minutes without trades are handled by the timing rules below.
  - Muhurat sessions have no 09:44 or 14:45 bars, so they drop out by themselves. The Budget-day session
    (Sunday 1 Feb 2026, normal hours) counts like any other session.

## Timing: everything a decision uses is known before it is made

| When (IST) | What happens | Uses only |
|---|---|---|
| 09:45:00 | r_first is known | Index: the close of today's 09:44 bar and of the previous session's 15:14 bar |
| 09:45:00 | I3's "big morning" test | Today's r_first, and the r_first of the previous 250 sessions |
| 14:45:00 | Entry: a market order, filled at the open of NIFTYBEES' 14:45 bar | The above, and that the 14:45 bar traded (volume above 0) |
| 14:45-15:14 | The stop is watched minute by minute | Each bar's low (for longs) or high (for shorts) as it happens |
| 15:14 | Exit, if not stopped: at the close of NIFTYBEES' 15:14 bar | The last trade before 15:15 |

- **r_first** = close of the index's 09:44 bar / close of the previous session's 15:14 index bar - 1. It is the
  overnight change plus the first 30 minutes.
- **The previous session** is the latest earlier session that has an index 15:14 bar.
- **A session is traded** only if r_first can be computed and NIFTYBEES' 14:45 bar exists with volume above 0.
  Both are known at 14:45, so no session is dropped because of anything that happens after the entry. Sessions
  that can't be traded are counted and reported.
- **The exit** is at the close of the 15:14 bar. If that bar is missing or had no trades, the exit is at the
  close of the last NIFTYBEES bar with volume before it: the last price at which anyone actually traded.
  Missing minutes inside the window simply offer no price for the stop.

## Definitions

- **Big morning** (I3): |r_first| at or above the 80th percentile of the previous 250 sessions' |r_first|
  values. These are the sessions just before, with r_first computable, today excluded. The percentile uses
  numpy's default linear interpolation. I3 can start only after 250 such sessions, in early 2021.
- **R:** 0.5% of the entry price. Gross return: for a long, exit / entry - 1; for a short, 1 - exit / entry.

## Simulating the 0.5% stop on minute bars

- **Placed at the entry:** 0.5% below the entry price for a long (entry x 0.995), 0.5% above for a short
  (entry x 1.005).
- **Triggered** by the first bar from 14:45 to 15:14 whose low reaches the stop (for a long) or whose high
  reaches it (for a short).
  - This includes the 14:45 bar itself. Its open is the entry, and its low and high happened at or after the
    open, so a touch within that minute is real.
  - A rule with a stop and no target never needs to know the order of prices inside a minute.
- **Filled** at the stop price, or at the bar's open if the price jumped past the stop between minutes: the
  lower of stop and open for a long, the higher for a short.
- **Slippage:** a stopped trade pays twice the usual slippage on its exit, an extra 0.03% beyond the round-trip
  cost below. Stops fire in fast markets.
- **Realism:**
  - A real stop would be sent as a market order the moment the price crosses it. In a fast jump a stop-limit
    order could fail to fill, which these rules don't model. That is why gap fills are taken at the worse
    price and slippage is doubled.
  - The results report how many stops filled at the stop price and how many at a gap.
  - A trade worse than -3R needs a jump of more than 1.5% inside the window; criterion 7 rejects any hypothesis
    that has one.

## Hypotheses (three separate tests)

| Id | Rule |
|---|---|
| I1 | Long side: on every traded session with r_first > 0, buy NIFTYBEES at 14:45 and exit as above |
| I2 | Short side: on every traded session with r_first < 0, short NIFTYBEES at 14:45 (intraday, MIS) and exit as above |
| I3 | Big mornings: on every traded session with a big morning, trade in r_first's direction at 14:45 (long if above 0, short if below) and exit as above |

- Each hypothesis takes at most one trade a session, with no re-entry after a stop.
- **Each is judged on its own,** with its own baseline, criteria and decision.
- I3's trades are a subset of I1's and I2's, and the correction below allows for that.
- **No selecting or combining afterwards:** they are never pooled, and none can be swapped for another, or for a
  blend of them.

## Costs, slippage, size and risk limits

- **Charges** (as checked above), at Rs 2,00,000 a trade: brokerage 0.0200%, STT 0.0250%, transaction 0.0061%,
  SEBI 0.0002%, GST 0.0047%, stamp 0.0030%. That is 0.0591% per round trip.
  - The project's shared cost model still has the older 0.00297% transaction charge. This round uses its own
    copy with today's figure, and leaves earlier rounds as they were.
- **Slippage:** 0.03% per side, 0.06% per round trip, plus 0.03% more on a stop exit. This is round 6's
  assumption for NIFTYBEES, and conservative for an ETF whose spread is usually one paisa.
- **Total:** 0.1191% per round trip (0.1491% for a stopped trade), taken from every trade's gross return, the
  same for longs and shorts.
- **Size:** Rs 2,00,000 a trade. Risking 0.5% of equity with a 0.5% stop would call for a position worth 100% of
  equity, so the risk engine's 20% cap on the Rs 10,00,000 paper account binds. Each trade risks 0.1% of equity,
  paid in full: no leverage.
- **Risk limits** as the engine applies them: one position at a time per hypothesis, no new entry after a 2%
  daily loss, and the kill switch at a 10% drawdown. They don't bind in this per-trade test; they apply to the
  portfolio view and to any later paper trading.

## The random baseline, precisely

- **The question it answers:** does trading on r_first beat trading the same window on randomly chosen
  sessions?
- **The pools:** for every traded session (as defined above), the gross return of the window traded long and
  traded short, under the same stop and exit rules. For I3, the pools hold only the sessions where its
  threshold exists.
- **The draws:**
  - 20,000 draws, from numpy's `default_rng(7)`, with replacement.
  - I1: each draw takes as many sessions from the long pool as I1 traded.
  - I2: as many from the short pool as I2 traded.
  - I3: as many from each pool as I3 took longs and shorts, respectively.
- **The p-value:** a draw's statistic is its mean gross return. With k the number of draws at least as high as
  the hypothesis's own mean gross return, p = (k + 1) / (20,000 + 1). This is the standard Monte Carlo p-value,
  which is never zero. Costs are the same for every trade, so comparing gross returns is the same as comparing
  net.
- **Why 20,000 draws:** p is resolved to 0.00005, fine enough for criterion 12's bar of 0.0022 (earlier rounds
  used 2,000).

## Multiple testing, precisely

- **Within this round (criterion 5):** the three raw p-values are Holm-corrected together. Sort them,
  p(1) <= p(2) <= p(3). The adjusted p(i) is the largest of min(1, (4 - j) x p(j)) over j = 1..i. Each
  hypothesis needs its adjusted p below 0.05.
- **Across the project (criterion 12):** each raw p must also be below 0.05 / 23 = 0.00217. The 23 hypotheses
  tested on overlapping historical data are:
  - H1-H14 (rounds 1-5);
  - C1-C6 (round 6);
  - I1-I3 (this round).
  Forward test 1 is not counted. It judges only data that didn't exist when it was pinned, and has its own
  correction.

## Pass criteria (each hypothesis on its own; every criterion must pass)

| # | Criterion | What it guards against |
|---|---|---|
| 1 | At least 50 trades | Too little evidence |
| 2 | Win rate at least 50% | Strategies that lose most of the time (your rule; see below) |
| 3 | Expectancy above zero at base costs and at 1.5x costs | Profits that costs, or worse costs, would erase |
| 4 | t-statistic at least 2.0 | Profit indistinguishable from noise, per trade (a risk-adjusted test) |
| 5 | Holm-adjusted random-baseline p below 0.05 | A signal no better than trading the window on random days |
| 6 | Profit factor at least 1.3 | Thin profits |
| 7 | Average loss at most 1.5 x the average win; no trade worse than -3R | Small wins paid for by rare large losses |
| 8 | Expectancy above zero in each half of the span | Profits from one period only. The halves split at the midpoint date between the hypothesis's first and last session. |
| 9 | At least 70% of calendar years with 10+ trades profitable | Instability from year to year |
| 11 | Cluster-robust t-statistic at least 2.0, with trades clustered by their signal's ISO week | Many trades that are really one event |
| 12 | Raw random-baseline p below 0.05 / 23 = 0.00217 | Luck across all the hypotheses this project has tried |
| 13 | Drawdown no deeper than 20R: cumulative R, trades taken in exit order | Losses the decay rule and kill switch wouldn't tolerate (the gate's limit for PAPER) |

Criterion 10 (breadth across instruments) doesn't apply to one instrument.

## Why the 50% win-rate floor stays, and what it does

Statistically, a win rate says nothing on its own about profit. Expectancy is p x average win - (1 - p) x
average loss, so a strategy can profit with 40% winners and big wins, or lose with 70% winners and big losses.
The criteria that test profit, risk and significance are 3, 4, 5, 6, 7, 11, 12 and 13, and every one of them
must pass.

The floor adds one restriction. Since the profit factor is p x average win / ((1 - p) x average loss), criterion
6 alone requires p >= 1.3 x L / (1 + 1.3 x L), where L is the average loss divided by the average win:

- if L = 1.5, p must be at least 66%;
- if L = 1, at least 56.5%;
- if L = 0.77, at least 50%;
- only below about L = 0.77 does the 50% floor bind.

So the floor rules out only strategies that lose often and win big, the trend-following style. It is a choice
of style that you made on 13 Oct 2026, not a statistical safeguard. It costs nothing here: these trades are
symmetric 30-minute holds whose average loss should be close to their average win, so criterion 6 already
demands a win rate near 56%. Any change to the floor has to be decided now, before the data is looked at, never
after.

## Decisions

| Outcome | Decision |
|---|---|
| Every criterion passes | Candidate for PAPER, once you approve. Paper trading needs, first: an intraday paper path (today's engine is end-of-day only); for I2 and I3, short selling, after confirming it in Kite. Then the paper-trading stage (Level 5). Live trading stays locked. |
| Only criterion 1 fails | Inconclusive |
| Anything else | REJECTED |

Results are reported whatever they show. No rule, parameter, cost or criterion changes once this file is pinned.
A changed rule is a new hypothesis, which can only be judged on data that doesn't exist yet: a forward test.

## Informational (no effect on the decisions)

- Results by calendar year, and before and after 3 Aug 2026 (the closing auction).
- Results by India VIX regime: its previous close above or below its 250-day median, from `data/round6/aux_daily`.
- The window traded on every traded session, regardless of r_first, long only.
- Each hypothesis without the stop.
- Costs at 0x, 1x, 1.5x and 2x.
- Stops: how many there were, and how many filled at a gap.
- Sessions that couldn't be traded, and why.
- The portfolio view: Rs 10,00,000 with positions of Rs 2,00,000. Daily P&L, CAGR, annualised Sharpe and Sortino,
  and maximum drawdown.

Patterns seen in these reports are hypotheses for future data, not findings.

## Protocol: pinned, pushed, run once

1. You approve this text. The DRAFT note is removed, the file's SHA-256 is recorded, and the file is committed
   and pushed. GitHub's timestamp then shows that the rules existed before any test ran.
2. `trader/research/round7.py` is written and tested only on synthetic bars, then committed and pushed.
3. It runs once on the frozen data, from that pushed commit. It refuses to run if this file or the data changed.
   It writes `docs/research/round7-results.md` and evidence for I1-I3, recording the pin, the commit and each
   backtest's drawdown in R.
4. The results are committed whatever they show.
5. If a bug is found in the runner after the run, the fix is documented in the results, which show both
   outputs. A fix may never change a rule.
