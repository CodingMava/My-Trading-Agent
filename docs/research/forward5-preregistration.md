# Forward test 5 pre-registration: paper trial 1's bunch hedged with short NIFTY futures (paper only)

Written on 19 Oct 2026 (pinned 19 Oct 2026 at 00:25 IST), before any trade this test judges: the bunch's first possible entries are at
the open of 22 Oct 2026 (E2) and 2 Nov 2026 (V2). Everything below is fixed. Results are reported against this file
whatever they show, and `trader/research/forward5.py` checks this file's SHA-256 (LF line endings) before every update
and look. Forward test 4 and paper trial 1 are not changed in any way: this test only reads the trial's ledger.

## Why

You decided on 19 Oct 2026: pre-register a paper-only forward test of E2 + V2 hedged with short NIFTY futures; F&O stays
paper; no live trading. The research report of 19 Oct 2026 ranked it first: every part tested so far is long-only Indian
equity, so a broad fall hits them together (in 2018 every part lost), and V2's failures (45.9% winners, 64% of years,
a 30.4R drawdown) are largely the market's. Removing the market's move keeps the parts' selection edge (E2 +1.50% and V2
+1.40% a trade over random picks in 2013-2026) and should make the record steadier. Variants of V2 can't be judged on
2013-2026, which has been seen, so only future data can test this.

## What is judged

Every closed trade of paper trial 1 entered on or after 22 Oct 2026, exactly as recorded in `state/trial1.db` under
`trial1-definition.md` (pinned, SHA-256 `ec1e9ace...`): E2 with 3 of the 5 positions and V2 with 2, with the trial's
entries, exits, costs, stops, kill switch and decay brakes, read and never changed. Each is paired with a hedge.

## The hedge (fixed)

- **Size:** a short NIFTY futures position of the same notional as the stock position at entry (hedge ratio 1).
- **Contract:** the NIFTY future with the nearest expiry on or after the entry session.
- **Entry:** at that future's open on the stock's entry session.
- **Rolls:** on each expiry session of the held contract that falls inside the holding (on or after the entry session
  and before the exit session), the leg closes at the expiring contract's settlement price and a new leg opens in the
  next expiry at its close that day.
- **Exit:** for a stock exit at an open (time, time delayed), at the held future's open on the exit session; for a stop
  or a stock that never trades again, at the held future's close on the stock's exit session (the stop's intraday time
  isn't known from daily data).
- **Hedge return:** h = the sum over legs of (leg entry price - leg exit price) / the first leg's entry price.
- **Costs:** 0.12% of notional for each leg (a futures round trip): Zerodha's charges as of October 2026 at this
  account's fractional notional (brokerage 0.03% an order, STT 0.02% on the sell, NSE transaction charge 0.00173% a side,
  stamp duty 0.002% on the buy, SEBI and IPF fees, 18% GST) plus 0.01% slippage a side.
- **Hedged trade:** gross = the stock's gross return + h; cost = the stock's costs + the futures costs; net = gross -
  cost. R = net / the stock's stop distance (15% for E2, 10% for V2).

## The random baseline (criterion 5)

For each closed trade's group (part, universe month-end, tier, entry session), the pool is every member of that tier and
universe that could be bought at the entry open, traded by the part's rules (E2: 40 sessions, 15% stop, E2's costs; V2:
to the open after the next month-end, 10% stop, its costs), each hedged by the rules above over its own holding. A pool
is recorded once every member's stock and hedge outcomes have closed. 20,000 draws from numpy's `default_rng(12)`; for
each group with k trades, k distinct pool members; p = (k + 1) / (20,000 + 1), k being the number of draws whose mean
net return is at least the hedged trades'. It must be below 0.05 / L at look L.

## Criteria at a decision look (the hedged closed trades; every one mandatory)

Round 8's criteria 1-11 and 13, unchanged, read as round 10 reads them (entry dates for halves and years, entry months as
clusters). Criterion 12 doesn't apply to forward data; this test isn't counted among the historical hypotheses.

## Looks and decisions

- **Any time:** informational (`python -m trader.research.forward5 look`). Nothing is decided.
- **Decision looks:** each January from 2028 to 2036, trades entered from 22 Oct 2026 to the previous 31 December
  (January 2028 is look 1).

| When | Decision |
|---|---|
| A decision look at which every criterion passes | Candidate for PAPER under the id B1HF, with your approval only. Real money would also need: your decision to enable F&O, a design that fits NIFTY lot sizes (below), and the paper (Level 5) and small-live (Level 6) stages. |
| Any update: the hedged trades' drawdown passes 20R | REJECTED at once. |
| From January 2029 (look 2): the hedged mean net return is zero or below | REJECTED. |
| January 2036 (look 9) without a pass | REJECTED. |
| Otherwise | Continue: NO TRADE for real money. |

## What this test can't show

- **Lot size.** A NIFTY lot is 65 units, about Rs 14.8 lakh of notional at a NIFTY of 22,700; the trial's positions are
  Rs 33,333 (E2) and Rs 50,000 (V2), about Rs 2 lakh together. On paper the hedge is fractional. With real money it would
  need about seven times the account, or a different hedge; a pass here would show whether hedging helps, not that this
  account can hold it.
- **Margin and F&O permission.** Short futures need margin (about 12-15% of notional) and F&O enabled: your decisions.
- **Taxes** on futures profits and the cost of carry beyond what the futures prices contain are not modelled.

## What to expect, stated now

- The hedged return of a trade is roughly the stock's return over NIFTY's plus the futures' carry (the premium of the
  future over the index, which decays to zero), minus about 0.12-0.24% of futures costs.
- **Steadier, not stronger:** years and drawdown should improve; the edge over random picks is the same selection edge
  (the random picks are hedged too), so significance is as slow as forward test 4 (several hundred trades).
- **Win rate** may be near 50%: hedging removes the market's up-drift that lifted the unhedged win rate in rising years.
- Nothing from it can trade real money: the gate's rules are unchanged, and the system stays in NO TRADE.

## Data

- NIFTY futures rows (open, high, low, close, settlement, expiry) from NSE's daily F&O file for each session from 19 Oct
  2026, fetched each evening (raw files kept unchanged outside OneDrive, in `NSE_RAW/fo`, see `trader/research/nse_fo.py`)
  and recorded once each in the append-only ledger `state/forward5.db`.
- Stock prices: forward test 2's rebuilt NSE history, as the trial uses.
