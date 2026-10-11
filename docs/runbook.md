# Runbook

What runs on its own, what each alert means and what to do about it, and the plan for losses, decided
in advance. Keep this file current: it is what you read when something goes wrong, so it must not need
interpreting under pressure.

## What runs on its own

| When | What | Where to look |
|---|---|---|
| 18:00 IST daily (Task Scheduler, "Trading agent - daily run") | `python -m trader.execution.eod` processes every completed NSE session not yet processed, sends `[PAPER]` Telegram messages, records the run and backs up the records | `logs/trader.log` |
| 21:00 IST daily ("Trading agent - health check") | `python -m trader.ops.health --notify` alerts you when anything below needs attention | `logs/health.log` |
| Always, from logon ("Trading agent - Telegram commands") | `python -m trader.notify.bot` answers `/status`, `/positions`, `/trades` and `/kill reason` from your chat only | `logs/bot.log` |
| Any time | `streamlit run dashboard.py` (read-only) or `python -m trader.ops.health` | |

No real order is ever placed: the system paper trades, and today it is in NO TRADE because no strategy has
passed the profitability gate. Telegram alerts need `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` in `.env`;
without them every alert only reaches the log files. Check with `python -m trader.notify.telegram --test`.

## When an alert arrives

Every alert is a `RISK ALERT` on Telegram with one of these titles.

| Alert | What it means | What to do |
|---|---|---|
| Daily run failed | The run crashed or couldn't start: no internet, the data provider down, a config error, no Kite login. Nothing half-done was recorded. | Read the end of `logs/trader.log`, fix the cause, then run `python -m trader.execution.eod` by hand. It catches up every missed session. |
| Market data missing | More than 20% of the instruments had no price yet for a session, so the run stopped before that session rather than record a day it couldn't see. | Usually the provider is late: do nothing, the next run retries. If that day was a market holiday missing from `config/market_calendars.toml`, add it. |
| Health check | Something the run can't report itself: the 18:00 run didn't happen or didn't finish, the last run failed or stopped early, the kill switch is on, messages are stuck, or the records don't reconcile. The alert lists which. | For a missed run: was the PC off, asleep or logged out? Check Task Scheduler for "Trading agent - daily run" (if its Conditions tab says "Start the task only if the computer is on AC power", run `scripts\register_tasks.ps1` again), then run it by hand. For anything else, see its row here. |
| Kill switch | The account fell 10% from its peak, or reconciliation failed. No new trades until a person releases it; exits keep running. | Find out why first. Release only once the cause is understood and written down (see the loss plan): `python -m trader.risk.killswitch release`. |
| Reconciliation failed | Cash or holdings no longer match the recorded fills: a bug or a damaged database. The kill switch engages automatically. | Don't release the kill switch. Compare the records with the latest backup and restore it if they are damaged (see Backups). Treat it as a bug to fix before anything trades again. |
| Daily loss limit | Today's loss reached 2% of equity, so no new entries today. | Nothing: it resets with the next session. |
| Strategy suspended | Its paper results drifted from its research: over its last 50 trades it won clearly less often or lost money on average, or it fell 20R from its best. | Review its trades against its research with `python -m trader.execution.report`. It stays suspended; putting it back needs new evidence, not a config edit. |
| Stale data | No price today for a stock you hold, so its stop wasn't checked today. | Usually a one-day gap. If it repeats for days, find out why (a trading suspension, a delisting, a symbol change). |
| Rejected order | A queued buy couldn't fill at the open: not enough cash, no price, or the strategy is gone. | Nothing, unless it keeps happening. |
| Duplicate order prevented | Something tried to place the same order twice and the database refused it. | A bug: find out why before trusting the next run. |
| Dry-run order invalid | Kite would refuse a request the dry run prepared: a price off NSE's tick, a bad quantity, a stop above the price. Nothing was sent. | A bug in the order path: look at it with `python -m trader.execution.broker` and fix it before any live trading. |

The dashboard and `python -m trader.ops.health` also show warnings that don't page you: research evidence
about to expire, next year's market holidays missing (all of December), no Kite login, a stale backup,
dry-run Kite requests that Kite would refuse.

## The plan for losses, decided in advance

These limits act automatically (`config/risk.toml`, `config/gate.toml`):

- At most 0.5% of equity is lost if a position's stop is hit; the stop distance sets the position size.
- At most 5 positions, 20% of equity in one position, 40% in one sector, nothing borrowed.
- After losing 2% in a day: no new entries until the next session.
- After falling 10% from the peak: the kill switch stops all new trades until a person releases it.
- A strategy whose last 50 trades win 15 percentage points less often than its research did, or lose
  money on average, is suspended, and so is one that falls 20R from its best.

What you commit to now, while nothing is at stake:

1. **Limits are never changed in response to a loss.** They change only after a deliberate review on a
   quiet day, and never loosened right after a loss.
2. **The kill switch is never released on the day it engaged**, and never before you have written down
   below why it engaged and what changed.
3. **A losing strategy is not tuned until it passes.** A rejected or suspended strategy can come back
   only as a new pre-registered hypothesis tested on data it hasn't seen.
4. **Money is never added to win back losses.**
5. **A losing streak is judged by the rules, not by feel.** Streaks happen to strategies with a real
   edge; the decay rules over 50 trades decide, not a bad week.

Before the first real rupee (Phase 11), write down here:

- The capital for small live trading, an amount whose total loss you could accept: ________
- What you will do if it is lost: ________
- How capital is increased afterwards: in steps, never more than doubling, and back to the previous step
  automatically whenever the drawdown exceeds the backtested maximum.

Kill switch log (date, why it engaged, what changed before it was released):

- (none yet)

## Backups and restoring

- After every run that didn't fail, the records are copied to `state/backups/paper-<date>.db`, one per
  day. The project folder is inside OneDrive, so the copies also leave this PC.
- The fills, closed trades, decisions and session records can't be edited or deleted: the database
  refuses. A backup is the way back from damage, not editing the database.
- To restore: disable "Trading agent - daily run" in Task Scheduler, copy the chosen backup over
  `state/paper.db`, check it with `python -m trader.ops.health`, then enable the task again (or run
  `python -m trader.execution.eod` by hand to catch up).
- Backups are small; delete old ones by hand whenever you like.

## Routine maintenance

- **Daily, only if Kite is the data source:** `python -m trader.data.kite login` before 18:00 (Kite
  sessions expire at 06:00 IST).
- **Weekly:** open the dashboard and read the decisions. Once a strategy trades, review its trades on the
  Chart tab: going live needs 20+ paper trades you have reviewed and agree with.
- **December:** add NSE's next-year holidays to `config/market_calendars.toml` when NSE publishes them,
  and NSE's Muhurat session when it is announced. Without the next year, nothing trades from 1 January.
- **Yearly:** research evidence expires after 365 days; the health check warns 30 days before.
- **After changing any code:** `pytest` and `pytest -m slow` must pass. The scheduled tasks run whatever
  branch is checked out.

## Before the first real order

Indian orders are a dry run until Phase 11: `python -m trader.execution.broker` shows the Kite request
behind each paper step and when a live system would send it. Before any of them is sent for real:

- **Evidence:** a strategy at `LIVE_SMALL`, earned by paper-trading evidence (see the README's safety
  rules), and a dry run whose health check has stayed OK: Kite would have accepted every request.
- **A static IP:** since April 2026 Kite rejects order requests from any address not registered in its
  developer console. Most home connections don't have a fixed address: ask the ISP for one, or send
  orders from a server that has one.
- **A DDPI with Zerodha:** without it, every sale of shares from the demat account needs a TPIN
  approval by hand, which an unattended system can't give.
- **A Kite login every trading day before 09:00:** sessions expire at 06:00 IST, and live orders go out
  at 09:20 and 15:15 as well as 18:00.
- **Two more scheduled jobs:** 09:20 (each new holding's stop as a GTT, the GTTs of holdings sold at the
  open, gap exits) and 15:15 (time exits), as `trader/execution/broker.py` describes.
- **Tick sizes from Kite's instrument list:** NSE re-sets each stock's tick every month; the dry run uses
  its price bands.
- **No orders from a catch-up:** a run that catches up missed sessions must not send their requests late.

## Stopping everything

- Block new trades now: send `/kill why` to the bot from your phone, or on the PC
  `python -m trader.risk.killswitch engage "why"` (exits keep running either way).
- Pause the schedule: disable the "Trading agent" tasks in Task Scheduler.
- Remove the schedule (PowerShell): `Unregister-ScheduledTask -TaskName "Trading agent*" -Confirm:$false`
