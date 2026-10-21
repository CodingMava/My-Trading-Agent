# Live readiness

Where the path to the first real order stands, as of 21 Oct 2026. The rules are unchanged: real money only for a
strategy that passes every criterion on future data, then the paper and small-live stages, with no waivers
(docs/runbook.md, "Before the first real order"). Nothing here turns live trading on: `[live] enabled = false`,
capital Rs 0, and no strategy is at `LIVE_SMALL`.

## Built and tested

| Piece | Where | Status |
|---|---|---|
| Live jobs (evening, morning, pre-close), their locks, the order system (each request sent at most once, looked up after a lost answer), reconciliation with the account, kill switch, capital steps | `trader/execution/live.py`, `oms.py`, `kite_orders.py`, `broker.py` | Built before; tests pass |
| Orders from each strategy's own paper account: the paper engine's for H1/H2, **paper trial 1's for its bunch B1F** (entries and time exits planned the evening before by the trial's own rules) | `trader/execution/sources.py`, `trader.research.trial.next_open` | New. A test checks, session by session, that each evening's plan is exactly what the trial records the next evening |
| **Dry run**: the same jobs against a simulated Zerodha account on real Kite prices; only quotes are read, nothing is sent | `trader/execution/simkite.py`, `--dry-run` | New, tested. First dry-run order placed 21 Oct 23:05 IST: buy 54 UNIONBANK at the 22 Oct open (simulated), the trial's E2 entry at Rs 3,00,000 |
| The live evening job runs right after paper trial 1 (it was 18:30, before the trial's data existed) | `scripts/register_tasks.ps1` | Changed; not yet registered |
| The read-only check also confirms the quotes a dry run fills at | `python -m trader.execution.live check` | Changed; not yet run against your account (no Kite login since 14 Oct) |
| 08:30 login reminder while a dry run holds simulated orders or shares | `trader/notify/bot.py` | Changed; the running bot picks it up when restarted |

## Waiting on you

1. **Kite login** before 09:20 on 22 Oct (`/login` to the bot, or `python -m trader.data.kite login`). The dry run's
   morning job needs it to fill UNIONBANK at the open and place its stop. Then the read-only check:
   `python -m trader.execution.live check`.
2. **Register the dry run** to run every day: `powershell -ExecutionPolicy Bypass -File scripts\register_tasks.ps1 -LiveDryRun`
   (it also restarts the Telegram bot on the current code).
3. **A static IP registered with Kite.** Since April 2026 Kite rejects order requests from any other address. A home
   connection usually needs the ISP's fixed IP, or the jobs need to run on a server that has one. No dry run can
   test this.
4. **A DDPI with Zerodha**, or every sale needs a TPIN approval by hand.
5. **The capital, written down in the runbook**: an amount whose total loss you could accept. For B1F it has to be
   about Rs 3,00,000 or more, or too many entries round to less than one share for live to track the trial (14% of
   E2's possible stocks at Rs 1,00,000; 4% at Rs 3,00,000).

## Not built yet (needed before B1F can go live, not before January 2028)

- **B1F's approval stages.** After forward test 4 decides PAPER, the registry needs B1F's paper evidence and, later,
  small-live evidence. `python -m trader.execution.report` scores only the paper engine's account; scoring B1F from
  the trial's ledger needs your decision on which trades count (for example, the trial's trades entered after the
  passing look).
- **Live-against-paper tracking for B1F** (`track` compares with the paper engine's fills only).
- **Order sources for forward tests 1-3** (H11/H12, N2, E2 alone), should one of them pass on its own. Forward test 5
  (the futures hedge) needs F&O orders, which the live path doesn't place at all (delivery shares only).
- **The closing auction** for time exits before the close (H1/H2-type strategies). B1F never meets it: its exits are
  at the open.

## Known differences between B1F live and the trial

- An E2 candidate that can't be bought at the open (locked at its upper band all day) while another candidate that
  day waited for the same place: the trial then buys the other, live doesn't. Rare.
- Live stops sit at the live fill less the part's stop (15% E2, 10% V2), the trial's at the open's price less it.
- Whole shares: a position is 50-100% of its target rupees (median about 97% at Rs 3,00,000).
- A split or bonus while a position is held leaves its GTT at the old price: replace it by hand.
- A stock that doesn't trade on its exit day: the after-market sale doesn't fill; the next evening sends it again.
