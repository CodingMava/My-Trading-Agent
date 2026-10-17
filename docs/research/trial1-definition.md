# Paper trial 1: E2 x3 + V2 x2, one paper account (definition)

> **Pinned on 17 Oct 2026 at 21:00 IST** (first pinned at 20:57 IST with wrong per-part backtest figures in the
> status-page line; corrected before the trial ever ran). This file fixes the trial's rules so that nothing is tuned after watching it. Its SHA-256 (LF
> line endings) is recorded in `trader/research/trial.py`, which refuses to run if the file changes. A changed rule
> means a new trial with its own file.

## What this is, and what it is not

You decided on 17 Oct 2026 to stop searching for one strategy that passes every criterion and to paper-trade the best
bunch of near-misses together, so that one part's bad years are offset by another's, while forward tests 1-3 keep
judging single strategies on future data.

- **It is** a paper account, research only, that runs the bunch every evening on NSE's own daily files, with the risk
  engine's position sizes, the 5-position limit, the kill switch and the gate's decay rule, and reports on Telegram.
- **It is not evidence.** The bunch was chosen after seeing 2013-2026 (below), so its backtest proves nothing, and the
  trial's own results are not a pre-registered test. Nothing it shows changes a strategy's status: E2 and V2 stay
  REJECTED in `config/strategies.toml`, the gate's paper account (`state/paper.db`) stays in NO TRADE, and live trading
  stays locked (`[live] enabled = false`, capital Rs 0). Real money still needs a strategy that passes every criterion
  on future data (forward tests) and the paper and small-live stages after that.

## Why this bunch (backtest, 2013-2026, informational only)

Each part exactly as tested in rounds 9 and 10, with fewer picks when it has fewer positions; fixed shares of the 5
positions, so no part crowds out another. R is a trade's net return divided by its stop distance; the account risks 0.5%
of equity per position, so a year's R x 0.5% is its return.

| Bunch (5 positions) | Trades | Win rate | Profit factor | Profitable years | Worst year | Max drawdown | Return a year |
|---|---:|---:|---:|---:|---:|---:|---:|
| **E2 x3 + V2 x2 (this trial)** | 503 | 48.7% | 1.42 | 10 of 14 | -10.4R (-5.2%) | 18.4R (9.2%) | +6.9R (+3.4%) |
| E2 x5 | 313 | 55.0% | 1.47 | 10 of 14 | -9.7R | 17.3R | +3.5R |
| E2 x3 + L2 x2 | 505 | 53.1% | 1.29 | 10 of 14 | -4.8R | 15.6R | +2.3R |
| E2 x2 + V2 x2 + L2 x1 | 598 | 48.7% | 1.35 | 10 of 14 | -10.0R | 22.7R | +6.1R |
| E2 x2 + V2 x2 + turn of the month x1 | 598 | 48.0% | 1.37 | 9 of 14 | -13.2R | 27.9R | +6.0R |
| V2 x5 | 786 | 45.8% | 1.40 | 9 of 14 | -11.7R | 30.4R | +11.5R |

E2 x3 + V2 x2 had the best return for its drawdown and stayed inside the 20R kill switch. The two parts' yearly results
were only loosely related (correlation 0.39): E2 earned in 2015 when momentum lost; V2 earned in 2017, 2019 and 2026 when
E2 was flat or negative; both lost in 2016 and 2018. N2 was left out (yearly correlation 0.90 with V2, and weaker), as
were the turn of the month (more drawdown) and L2 (steadier, but no edge and a third of the return).

## The account

- Rs 10,00,000 of paper money; 0.5% of equity at risk per position.
- **E2: 3 of the 5 positions.** Round 10's E2 rules, exactly as in forward test 3 (results meetings whose session is on
  or after 19 Oct 2026; signal when the two-session abnormal reaction is in the top 10% of the past 250 sessions' events;
  buy at the open two sessions after the meeting; 15% stop; exit at the open 40 sessions after entry; strongest
  reactions first). Positions of Rs 33,333; costs 0.3685% (ranks 1-100) or 0.4685% (101-300) a round trip, plus
  slippage again on a stop.
- **V2: 2 of the 5 positions.** Round 9's V2 rules: at each month's last session from 30 Oct 2026, the eligible stocks
  of liquidity ranks 101-300 ranked by volatility-adjusted momentum (the mean of the z-scores of 12-1 and 6-1 month
  returns each divided by volatility); the 2 highest not already held in the account are bought at the next open; a
  pick that can't be bought (no row, or locked at its upper band all day) leaves its position in cash for the month;
  10% stop; exit at the open after the next month-end. Positions of Rs 50,000; costs 0.4532% a round trip, plus 0.10% on
  a stop.
- **One position per stock** in the account: an E2 candidate already held is skipped; a V2 pick already held is
  passed over for the next one. On a session with entries from both, E2's are decided first.
- Exits, suspensions and delisted stocks as in rounds 9 and 10 (a stock with no row for 20 sessions after its exit date
  exits at its last close).

## Brakes (as the risk engine and the gate would apply them)

- **Kill switch:** once the account's closed trades, in exit order, fall 20R below their peak (10% of equity), no new
  entries are taken for the rest of the trial; open positions run to their exits.
- **Decay rule** (the gate's, `trader.gate.decay_check`, window 50 trades): a part whose last 50 closed trades won 15
  points less often than in research (E2 55.0%, V2 45.9%) or lost money on average is paused for the rest of the
  trial; a part whose own closed trades fall 20R below their peak is stopped.
- A brake takes effect from the session after the trade that triggered it closed, and is recorded once.

## Records and reports

- Every evening, after forward tests 2 and 3 (the same scheduled task), on forward test 2's rebuilt NSE history:
  signals, entry decisions, exits and brakes go into an append-only ledger, `state/trial1.db`, once each.
- Telegram messages labelled `[PAPER TRIAL 1 · paper only]`: entries, exits, brakes, and a summary when a month ends.
- `state/trial1-status.md`, rewritten each evening: open positions, closed trades, each part against its backtest
  (E2's 3 positions: 189 trades, 54.5% winners, +1.7R a year; V2's 2 positions: 314 trades, 45.2% winners, +5.1R a
  year), the account in rupees.
- The health check warns if the trial stops updating.

## What to expect, stated now

- About 15 E2 trades and 24 V2 trades a year. The backtest's typical year was +6.9R (+3.4%), but 4 of its 14 years
  lost money and its worst lost 10.4R. A losing first year would not be surprising; neither would one large month.
- The trial's main value is practical: the whole loop (data, signals, sizing, brakes, messages) running every day on
  real, unseen sessions, and a record of how the near-misses behave together. It cannot prove an edge.
