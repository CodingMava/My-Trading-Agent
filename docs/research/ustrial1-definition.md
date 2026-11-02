# US paper trial 1: E2 x3 + V2 x2 on US stocks, one paper account (definition)

> **Pinned on 2 Nov 2026 IST, before the first US open it can trade (Tue 3 Nov 2026).** This file fixes the
> trial's rules so that nothing is tuned after watching it. Its SHA-256 (LF line endings) is recorded in
> `trader/research/ustrial.py`, which refuses to run if the file changes. A changed rule means a new trial with its own
> file.

## What this is, and what it is not

You asked on 1 Nov 2026 for the same Telegram messages for US stocks as for Indian stocks. No US strategy has passed the
project's criteria (12 US ideas tested, all REJECTED), and you have ruled out waiving any criterion. So these messages
come the way India's come: from a paper trial, research only.

- **It is** a paper account that runs paper trial 1's rules (`docs/research/trial1-definition.md`) on S&P 500 stocks every
  evening before the US open, and reports on Telegram.
- **It is not evidence.** E2 and V2 were chosen on Indian stocks and have **never been tested on US stocks**: there is no
  US backtest behind them. Nothing here changes a strategy's status: `config/strategies.toml` stays as it is, and the
  gate's US paper account (`state/paper-us.db`) stays in NO TRADE.
- **It places no orders.** The bot sends orders only for NSE stocks, and Zerodha's pages (read 1 Nov 2026) mention no Kite
  Connect access for US stocks. If you copy a trade by hand (Kite's International tab, in beta since October 2026), the
  bot doesn't know: this ledger records the rules' paper fills, not yours. Whether to copy is your own decision.

## The account

- $10,000 of paper money; 0.5% of it at risk per position, so fixed positions of $333.33 (E2) and $500 (V2).
- **The stocks:** the S&P 500's companies as Wikipedia's constituents table lists them when each run starts, one share
  class per company: the one already on the list if the table still shows it, otherwise the first listed. A company stays on
  the list once seen, and if a ticker gets a new CIK, both are read. At each month-end they are ranked as in round 8: at
  least 273 rows, 227 of the last 252 sessions, a close of at least 10, by median traded value over 126 sessions. Ranks 1-300
  are the trial's universe.
- **E2: 3 of the 5 positions.** Round 10's E2 rules, as in paper trial 1, with an SEC filing in place of NSE's board
  meeting. A results filing is an 8-K listing Item 2.02. Its session m is the session it was accepted in, if before 16:00
  New York time (on early-close days too); otherwise the next session. If a later results filing is known by session m+1, only the later one counts.
  The reaction is the close of m-1 to the close of m+1, in adjusted prices, minus the mean over the universe's members
  with rows on both (the universe at the latest month-end). Signal when it is at least the 90th percentile of the events
  of the past 250 sessions (at least 300 of them), at the close of m+1, for that member of the universe, from the 2 Nov
  2026 close. Buy at the next open, strongest reactions first; 15% stop; exit at the open 40 sessions after entry. Ranks and
  thresholds are computed on each evening's list, so a list change can make an old event a signal, with hindsight in it: a
  signal dated on or before the last session a good run had covered, whose entry session has passed, is recorded as late
  and is never a candidate.
- **V2: 2 of the 5 positions.** Round 9's V2 rules, as in paper trial 1: at each month's last session from 30 Nov 2026, the
  eligible stocks of ranks 101-300 ranked by volatility-adjusted momentum (the mean of the z-scores of 12-1 and 6-1 month
  returns each divided by volatility); the 2 highest not already held are bought at the next open; a pick that can't be
  bought (no row) leaves its position in cash for the month; 10% stop; exit at the open after the next month-end.
- **One position per stock:** an E2 candidate already held is skipped; a V2 pick already held is passed over for the next
  one. On a session with entries from both, E2's are decided first.
- **Costs:** Kite's US charges as read on 1 Nov 2026: per side 0.10% brokerage plus 18% GST on it and a 0.005% IFSCA fee;
  on a sale a 0.00206% SEC fee; and the project's 0.02% slippage per side, charged once more on a stop. About 0.29% a round
  trip. Currency conversion and bank charges are paid on moving money, not per trade, so they aren't counted.
- Exits and delisted stocks as in paper trial 1 (a stock with no row for 20 sessions after its exit date exits at its last
  close). If Yahoo stops answering for a held stock altogether (renamed, or bought out), a message says so, and its position
  stays open and keeps its place. If Yahoo answers again it carries on; after 20 sessions with no answer it closes at the
  last price on record (outcome "no further rows").

## Brakes

As in paper trial 1, with its numbers (there is no US research to take others from): once the account's closed trades fall
20R below their peak, no new entries for the rest of the trial; a part whose last 50 closed trades won 15 points less often
than E2's 55.0% or V2's 45.9%, or lost money on average, is paused for the rest of the trial; a part whose own closed trades
fall 20R below their peak is stopped. A brake takes effect from the session after the trade that triggered it closed.

## Data and timing

- **Sessions:** the NYSE calendar in `config/market_calendars.toml`. A session counts 30 minutes after its close.
- **Prices:** Yahoo Finance (free, unofficial), four years of daily rows for every stock and SPY, downloaded again each
  evening. Close is "as printed" (split-adjusted), Adj Close gives returns. Recorded trades are never recomputed.
- **Filings:** SEC's free submissions data (data.sec.gov), each evening for every company. Each results filing goes into
  the ledger once, with when it was first seen.
- **A run records no signals, decisions or trades** unless all of these hold (the companies and filings it read stay on
  record, and the failure is noted):
  - Yahoo's data reaches the last completed session, with no session of that year missing against the calendar, and covers
    at least 400 stocks. Tickers with no row are asked for once more.
  - Every stock with a row on the last good run's session (on the first run, every company on the list) has one on the
    newest session. From 18:15 IST at most 2% may not, since a stock can really stop trading.
  - Every such stock that is held, or is a candidate for the next decisions, has one, until the run is more than 3 sessions
    behind the last good run; after that it counts as gone.
  - Fewer than 25 companies' filings can't be read.
- **Schedule:** 17:15 IST daily ("Trading agent - US trial"), repeated every 15 minutes until 19:45 IST, before the US open
  (19:00 IST in the US summer, 20:00 IST in the US winter); a repeat does nothing once that evening's work is done. If the PC
  was asleep or off, it runs when it is back and catches up.

## Records and reports

- `state/ustrial1.db`, an append-only ledger: the companies, results filings, signals, entry decisions, closed trades,
  brakes, runs, the stocks with a row on each session, open positions' latest prices, and the messages.
  `state/ustrial1-status.md`, rewritten each evening: open positions, closed trades, the account.
- Telegram messages labelled `[US PAPER TRIAL · paper only]`: signals, paper entries, closed positions, brakes, a summary for
  each new session and for each month, and, on the evening of each US open, the list of what the rules buy and sell at that
  open, with the steps to copy it by hand (or a line saying there is nothing to do). A message Telegram doesn't take waits
  for the next run. A list goes out only on its own evening; after that evening's open it no longer says to buy.
- Kite has no stop-loss or GTT for US stocks yet (1 Nov 2026), so anyone copying by hand has no stop at the broker. The bot
  looks once a day, after the US close: a stop that fired on paper appears as a SELL in the next open's list, and so does a
  time exit whose own evening's list didn't get through. A SELL is told once.
- If the paper account and a list differ (a BUY the account didn't buy, or a buy no list told in time), a message says so.
- If a run fails close to the open, a message says so at once. The health check alerts if the trial's run fails, it stops
  updating, or messages can't be sent.

## What to expect, stated now

Unknown: there is no US backtest. The account can hold 5 stocks, so at most about 19 E2 and 24 V2 trades a year. Many E2
signals will find no free place during earnings season. A later judgement of these trades would need a pre-registered
forward test in its own file. The trial's value is practical: US messages every day, on real unseen sessions.
