# Forward test 4 pre-registration: paper trial 1's bunch (E2 x3 + V2 x2) on future data

Written on 18 Oct 2026 (pinned 18 Oct 2026 at 12:24 IST), before any trade this test judges: the bunch's first possible entries are
E2's at the open of 22 Oct 2026 and V2's at the open of 2 Nov 2026. The criteria and decisions below are fixed. Results
are reported against this file whatever they show, and `trader/research/trial.py` checks this file's SHA-256 (LF line
endings) before every update and look.

## Why

You decided on 18 Oct 2026: keep E2 + V2 as a paper trial only; never waive or weaken a criterion to enable live
trading; evaluate it with realistic costs, out-of-sample validation, drawdown and statistical significance; if it fails
any mandatory criterion it stays NO TRADE for real money; if it passes, it goes through the existing approval process
without bypassing any safeguard. The goal is a genuinely profitable strategy, not forcing one into live trading.

The bunch was chosen after seeing 2013-2026 ([trial1-definition.md](trial1-definition.md)), so its backtest proves
nothing. Only data that didn't exist when it was chosen can test it. This file turns the trial's future record into that
test.

## What is judged

The closed trades of paper trial 1, exactly as recorded in `state/trial1.db` under the pinned definition
(`trial1-definition.md`, SHA-256 `ec1e9ace...`): both parts together, E2 with 3 of the 5 positions and V2 with 2, one
position per stock, with the trial's kill switch and decay brakes, entered from 22 Oct 2026. Rules, sizes, exits and
costs (Zerodha delivery at the engine's position sizes, with slippage, more on a stop) are the definition's, unchanged.
A part paused by the decay rule simply stops adding trades; the test judges what the account traded.

## The random baseline (criterion 5)

- **Pools**, recorded once every member's outcome has closed: for an E2 trade, every member of its tier (ranks 1-100 or
  101-300) at the month-end that defined the universe on its signal session, that could be bought at its entry open,
  held by E2's rules (40 sessions, 15% stop, E2's costs); for a V2 trade, every member of ranks 101-300 at its signal
  month-end that could be bought at its entry open, held by V2's rules (to the open after the next month-end, 10% stop,
  its costs).
- **Draws:** 20,000 from numpy's `default_rng(10)`; for each (part, month-end, tier, entry session) with k trades, k
  distinct members of that pool. A draw's statistic is the mean net return of all its trades.
- **p** = (k + 1) / (20,000 + 1), k being the number of draws at least as good as the trades' mean net return. It must
  be below 0.05 / L at look L.

## Criteria at a decision look (the closed trades only; every one mandatory)

Round 8's criteria 1-11 and 13, unchanged, read as round 10 reads them:

1. At least 50 trades.
2. Win rate at least 50%, net of costs.
3. Mean net return above 0 at base costs and at 1.5x costs.
4. t-statistic of the mean net return at least 2.0.
5. Beats the random baseline (above): p below 0.05 / L.
6. Profit factor at least 1.3.
7. Average loss at most 1.5x the average win; no trade worse than -3R.
8. Mean net above 0 in each half of the forward span.
9. At least 70% of calendar years with 10+ trades profitable.
10. At least 60% of stocks with 5+ trades profitable, and mean net above 0 without the top-contributing stock.
11. Cluster-robust t-statistic (entry months as clusters) at least 2.0.
13. Drawdown of cumulative R, trades netted by exit date in exit order, no deeper than 20R.

Halves and years use entry dates; each trade's R is its net return divided by its own stop distance (15% for E2, 10% for
V2). Criterion 12 (the cross-round correction for hypotheses tested on historical data) doesn't apply to forward data;
like forward tests 1-3, this test isn't counted among the project's historical hypotheses.

## Looks and decisions

- **Any time:** informational (`python -m trader.research.trial look`). Nothing is decided.
- **Decision looks:** each January from 2028 to 2036, with the trades entered from 22 Oct 2026 to the previous
  31 December. January 2028 is look 1, January 2029 look 2, and so on.

| When | Decision |
|---|---|
| A decision look at which every criterion passes | Candidate for PAPER under a new id, B1F. Nothing happens automatically: it needs your approval, then the gate's paper-trading stage (Level 5: 13 weeks, 40 trades, 60 clean unattended sessions, 20 reviewed trades, costs in line) and small live capital (Level 6), every safeguard as written. |
| Any update: the closed trades' drawdown passes 20R | REJECTED at once (the trial's kill switch also stops new entries). |
| From January 2029 (look 2): forward mean net return is zero or below | REJECTED. |
| January 2036 (look 9) without a pass | REJECTED. |
| Otherwise | Continue: still NO TRADE for real money. |

## What to expect, stated now

- **About 38 trades a year** (14 from E2, 24 from V2 in the backtest).
- **The 50% win-rate floor is the likeliest failure.** The bunch won 48.7% of its backtest trades (E2 54.5%, V2
  45.2%). The floor stays, as you decided, so unless the future months are kinder the bunch most likely stays NO TRADE.
- **Significance is slow.** At the backtest's edge over random picks (+1.45% a trade) and a spread of about 12% a
  trade, p below 0.05 / L needs roughly 300 trades: about 8 years. A loss of the edge would show much sooner.
- Nothing from it can trade real money without passing every criterion here and then the approval stages above.
