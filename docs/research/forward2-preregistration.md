# Forward test 2 pre-registration: round 8's N2 on months after 15 Oct 2026, in paper mode

Written on 14-15 Oct 2026, before any session this test judges has happened: its first picks come at the close of Friday
30 Oct 2026, the last session of October, and are bought in paper at the open of Monday 2 Nov 2026. The rules, data,
costs, criteria and decisions below are fixed. Results are reported against this file whatever they show, and
`trader/research/forward2.py` checks this file's SHA-256 (LF line endings) before every update and look.

## Why

You asked for it on 14 Oct 2026: keep N2's rules unchanged and judge them on future market data, in paper mode, while
research continues on other ideas.

N2 is one of the two hypotheses in this project that beat random entries at the project's multiple-testing bar (the
other is H11, in forward test 1). In round 8 (June 2013 to August 2026) its picks earned +1.75% a trade net of costs
against +0.67% for random stocks from the same tier (p 0.0019), but it failed three criteria: a 43.9% win rate (50%
needed), 64% of calendar years profitable (70%) and a 34.1R drawdown (20R). After the decision it also showed that its
edge leaned on a few large winners and on the years since 2020. Only data that didn't exist when its rules were fixed
can say whether the edge is real.

## Rules (unchanged from round 8)

Everything as in [round8-preregistration.md](round8-preregistration.md), hypothesis N2, computed by the same code
(`trader.research.round8`):

- **Signal:** at each month's last session, the eligible NSE equity shares (EQ series, close at least Rs 10, at least
  273 rows and rows on 227 of the last 252 sessions, a momentum score) are ranked by liquidity (median traded value over
  126 sessions, a session without a row counting as zero). N2's tier is ranks 101-300. Its picks are the 5 highest
  12-1 month momentum scores in the tier (adjusted close 21 sessions back / 252 sessions back - 1).
- **Paper entry:** at the official open of the next session, unless the stock has no row that day or is locked at its
  upper band all day.
- **Stop:** 10% below the entry price, watched from the entry session through the next month's last session; filled at
  the stop, or at the open if the open was already below it.
- **Exit:** at the official open of the session after the next month-end; a suspended stock at its next open; a stock
  that never trades again at its last close.
- **Costs:** Zerodha delivery at Rs 50,000 a position: 0.4532% a round trip, plus 0.10% more on a stop's exit.
- **R:** 10% of the entry price.

## Data

- NSE's daily capital-market files (bhavcopies) for every session from 14 Oct 2026, downloaded each evening from
  nsearchives.nseindia.com into `data/forward2/bhavcopy_raw/` (git-ignored, kept unchanged), on top of round 8's frozen
  archive for the history the signals need.
- NSE's corporate-action records for the current and previous month, refreshed each evening into
  `data/forward2/corporate_actions/` (they replace round 8's copy of October 2026 and any later month), and NSE's list of
  symbol changes, refreshed weekly.
- Corporate actions are applied exactly as in round 8 (`trader.research.nse_bhavcopy`). Each update rebuilds the
  adjusted panel in `data/forward2/panel/` from all of these files.

## Paper mode: what is recorded, and when

Every evening (19:30 IST, or as soon as the PC is on after that), after the new files are in:

- **Picks.** Once a month-end is known (the NSE calendar says the next session is in a new month, or a session of the new
  month is in the data), the month's 5 picks are written to the paper ledger, `state/forward2.db`, with their scores and
  tier ranks, and sent to Telegram labelled as forward-test paper picks, not trading signals. They are never chosen
  again: if a later rebuild of the data would pick differently (a corrected file, a late corporate action), the ledger
  keeps what was chosen at the time and the difference is noted in the run record.
- **Trades.** When a position closes (stop or month-end), its entry and exit dates and prices, gross and net returns and
  how it ended are written to the ledger. A pick that couldn't be bought is written as not bought.
- **Random baseline.** When a month's positions have closed, the net return of every stock in that month's tier that
  could have been bought, traded by the same rules, is written to the ledger: the random-pick pool for that month.
- The ledger refuses changes and deletions. Open positions are reported from the data each evening, not stored.

## Looks

- **Any time:** informational (`python -m trader.research.forward2 look`). Nothing is decided.
- **Decision looks:** each January from 2028 to 2036, with the trades signalled from 30 Oct 2026 to the previous
  31 December. January 2028 is look 1, January 2029 look 2, and so on.

## Criteria at a decision look (the ledger's trades only)

Round 8's criteria, unchanged, on the forward trades alone:

1. At least 50 trades.
2. Win rate at least 50%.
3. Expectancy above zero at base costs and at 1.5x costs.
4. t-statistic at least 2.0.
5. Beats the random baseline: 20,000 draws (seed 8); in each, for every month with k trades, k distinct stocks from that
   month's recorded pool; p = (k + 1) / (20,000 + 1) for the share of draws at least as good as the trades. The p-value
   must be below 0.05 / L at look L, because each look is another chance of a lucky pass.
6. Profit factor at least 1.3.
7. Average loss at most 1.5x the average win; no trade worse than -3R.
8. Expectancy above zero in each half of the forward span.
9. At least 70% of calendar years with 10+ trades profitable.
10. At least 60% of stocks with 5+ trades profitable, and expectancy above zero without the top-contributing stock.
11. Cluster-robust t-statistic (signal months as clusters) at least 2.0.
13. Drawdown no deeper than 20R: cumulative R, trades in exit order.

Criterion 12 (the cross-round correction for hypotheses tested on historical data) doesn't apply: forward data can't
have been mined. Like forward test 1, this test isn't counted among the project's historical hypotheses.

## Decisions

| When | Decision |
|---|---|
| A decision look at which every criterion passes | Candidate for PAPER. Its research evidence is written under a new id, N2F, so round 8's record stays as it is. The gate's paper account trades it only once you approve, and real money still needs the paper-trading stage (Level 5) and small live capital (Level 6). |
| Any update: the ledger's drawdown passes 20R | REJECTED at once: the risk engine's kill switch would have stopped it (20R is 10% of equity at 0.5% risk a position). |
| From January 2029 (look 2): forward expectancy net of base costs is zero or below | REJECTED: the edge did not last. |
| January 2036 (look 9) without a pass | REJECTED. |
| Otherwise | Continue. |

## What to expect, stated now

- **The win-rate floor will probably fail again.** These rules won 43.9% of their trades in 2013-2026, and nothing
  about them changes. Unless the forward months are unusual, criterion 2 fails at every look, so this test is most
  likely to end REJECTED. Its value is the answer to a narrower question: does N2's edge over random picks from its tier
  persist on data its rules never saw?
- **It is slow.** About 60 trades a year, which are really 12 monthly bets. With round 8's monthly edge (about +1.1%) and
  monthly spread (about 5%), the p-value would reach 0.05 / L only after roughly a decade, if ever. This test can show
  that the edge has gone long before it can show that it remains.
- Nothing from it can trade real money: the gate's rules are unchanged, and the system stays in NO TRADE.
