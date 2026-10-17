# Forward test 3 pre-registration: round 10's E2 on results meetings from 19 Oct 2026, in paper mode

Written on 17 Oct 2026 (pinned 17 Oct 2026 at 19:02 IST), before any session this test judges has happened. It judges E2's signals for
results meetings whose meeting session is on or after Monday 19 Oct 2026; the first possible signal is at the close of
Wednesday 21 Oct 2026 (20 Oct is an NSE holiday), bought in paper at the open of Thursday 22 Oct 2026. The rules, data,
costs, criteria and decisions below are fixed. Results are reported against this file whatever they show, and
`trader/research/forward3.py` checks this file's SHA-256 (LF line endings) before every update and look.

## Why

You asked for it on 17 Oct 2026: keep E2's rules frozen and judge them on future months, in paper mode, with a daily
board-meeting feed.

In round 10 (entries June 2013 to July 2026) E2 passed 11 of the 13 criteria: 313 trades, 55.0% winners, +2.33% a trade
net of costs against +0.83% for random stocks from the same tier, profit factor 1.47, 71% of years profitable, drawdown
17.3R. It failed only the two tests of beating random picks: its edge (+1.50% a trade) had p 0.030, short of both the
round's Holm test (0.089 against 0.05) and the cross-round bar (0.05 / 57). Only data that didn't exist when its rules
were fixed can say whether that edge is real.

## Rules (unchanged from round 10)

Everything as in [round10-preregistration.md](round10-preregistration.md), hypothesis E2, computed by the same code
(`trader.research.round10`):

- **Universe:** round 8's liquidity ranks 1-300 at the latest month-end on or before the signal session; tiers N1 (ranks
  1-100) and N2 (101-300).
- **Notices:** board-meeting records whose purpose matches `result|(un-?)?audited accounts|annual accounts`, used with
  NSE's filing time: known by session d if filed before d's date or on it by 18:00 IST. A meeting counts when the
  company's latest results notice known by session m+1 names its date (m: the first session on or after the meeting).
- **Signal:** at the close of m+1, the reaction (adjusted close m+1 / adjusted close m-1 - 1) minus the mean reaction of
  every universe member with rows on both sessions is at least the 90th percentile of the same quantity for all such
  events with session m+1 in the 250 sessions before (at least 300 of them). Events before this test's start count toward
  that threshold, exactly as in round 10.
- **Paper entry** at the official open of m+2, if one of the 5 places is free (a position exiting at an open frees its
  place at that open; a stop or a last close frees it from the next session), the stock isn't already held, and round
  8's "not bought" rule allows; several candidates on one session are taken strongest abnormal reaction first (ties by
  symbol), and those without a place are dropped.
- **Stop** 15% below the entry price, from the entry session; **exit** at the open 40 sessions after entry; a suspended
  stock at its next open; a stock with no row for 20 sessions after its exit date at its last close.
- **Costs:** Zerodha delivery at Rs 33,333 a position: 0.3685% a round trip for N1, 0.4685% for N2, plus the tier's
  slippage again on a stop's exit. **R:** 15% of the entry price.

## Data

- **Prices:** forward test 2's NSE daily files and adjusted panel (`data/forward2/`), rebuilt each evening on top of
  round 8's frozen archive, with corporate actions applied as in round 8.
- **Board meetings:** round 10's frozen archive (`data/round10/board_meetings/`, meetings to 15 Oct 2026, manifest
  SHA-256 `1e7accb2...`), plus NSE's board-meeting API (`nseindia.com/api/corporate-board-meetings`) fetched each evening
  for meetings from 20 days back to 45 days ahead (further back after missed days), saved unchanged and gzipped in
  `data/forward3/board_meetings/`, one file per fetch, named by the fetch time. Every record is used with NSE's filing
  time, as in round 10; the time each was first fetched is recorded for audit.

## Paper mode: what is recorded, and when

Every evening, straight after forward test 2's update (one scheduled task runs both, in that order, at 19:30 IST or as
soon as the PC is on after that), into the append-only ledger `state/forward3.db`:

- **Signals:** each new E2 signal for a meeting session on or after 19 Oct 2026, with its reaction, abnormal reaction
  and threshold, the first time it is seen. Never recomputed: if rebuilt data would give a different set or different
  values, the ledger keeps what it recorded and the difference is noted in the run record. A signal first seen after
  its entry session's decisions were recorded is recorded as late and is not a candidate (a live system would not have
  had it).
- **Entries:** once an entry session's prices are in, each candidate's outcome (bought, not bought, no free place,
  already held), once.
- **Trades:** each closed position (stop, time, time delayed, no further rows) with its prices and returns, once.
- **Random baseline:** for each (month-end, tier, entry session) with a trade, once every member's outcome has closed,
  the net returns of every tier member that could have been bought at that open, traded by the same rules.
- Telegram messages are labelled as forward-test paper results, not trading signals. Nothing here can place an order
  or reach the gate's paper account.

## Looks

- **Any time:** informational (`python -m trader.research.forward3 look`). Nothing is decided.
- **Decision looks:** each January from 2028 to 2036, with the trades entered from 22 Oct 2026 to the previous
  31 December. January 2028 is look 1, January 2029 look 2, and so on.

## Criteria at a decision look (the ledger's closed trades only)

Round 8's criteria 1-11 and 13, unchanged, read as round 10 reads them (entry dates for halves and years, entry months as
clusters, R = 15%). Criterion 5: 20,000 draws from numpy's `default_rng(10)`; in each, for every (month-end, tier, entry
session) with k trades, k distinct members of its recorded pool; p = (k + 1) / (20,000 + 1) for the share of draws at
least as good as the trades; p must be below 0.05 / L at look L. Criterion 12 doesn't apply: forward data can't have
been mined, and like forward tests 1 and 2 this test isn't counted among the project's historical hypotheses.

## Decisions

| When | Decision |
|---|---|
| A decision look at which every criterion passes | Candidate for PAPER. Its research evidence is written under a new id, E2F, so round 10's record stays as it is. The gate's paper account trades it only once you approve; real money still needs the paper-trading stage (Level 5) and small live capital (Level 6). |
| Any update: the ledger's drawdown passes 20R | REJECTED at once. |
| From January 2029 (look 2): forward expectancy net of base costs is zero or below | REJECTED. |
| January 2036 (look 9) without a pass | REJECTED. |
| Otherwise | Continue. |

## What to expect, stated now

- **About 20-25 trades a year**: results seasons fill the 5 places. The first come in October-November 2026.
- **It is slow.** At round 10's edge (+1.5% a trade over random picks) and spread (about 13% a trade), reaching
  p below 0.05 / L needs several hundred trades: more than a decade. Most likely this test will either keep running
  without a decision for years or be rejected from 2029 if its expectancy turns negative. Its quickest use is as an
  early warning that the edge has gone.
- **Win rate, profit factor, years and drawdown** passed in round 10 with some margin (55%, 1.47, 71%, 17.3R), so they
  may pass on forward data too; the baseline test is the hard part.
- If NSE changes its board-meeting API or stops publishing a session's file, updates pause (recorded as failed runs;
  the health check warns) and resume when the data does; nothing judged is changed.
- Nothing from it can trade real money: the gate's rules are unchanged, and the system stays in NO TRADE.
