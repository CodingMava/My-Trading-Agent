# Production acceptance

Requirement by requirement, what is verified, how, and what is left, as of 25 Oct 2026. This is the
builder's own review (Milestone F needs someone else). The rules are unchanged: real money only for a strategy that
passes every criterion on future data, then the paper and small-live stages, with no waivers (docs/runbook.md, "Before
the first real order"). `[live] enabled = false`, capital Rs 0, and no strategy is above REJECTED or DISABLED.

**Verdict.** The software is technically capable of paper trading and of carrying out a strategy's orders through
Kite, and both have been exercised against a simulated broker. The trading system is **not approved for live
capital**: no strategy passes its criteria (B), and the forward evidence can't exist before January 2028 (D). NO TRADE
is the correct state.

Results: **PASS** verified by the method shown; **FAIL** checked and not met; **BLOCKED** waits on something outside
the code (time, your action, a real order); **NOT TESTED**.

## A. Research correctness

| Requirement | Evidence | Method | Result | Remaining risk | Next action |
|---|---|---|---|---|---|
| Point-in-time data | Rounds 8-11 use NSE's own daily files, corporate-action records, board-meeting notices by intimation time, SEBI insider disclosures; audits in `docs/research/round8-research-review.md`, `kite-minute-data.md` | Audit reports; frozen data pinned by SHA-256 manifests | PASS | NSE 2005-2008 corporate-action records are incomplete (inferred); rounds 1-7 used Yahoo | None while nothing qualifies |
| No look-ahead | Every round pre-registered before running; entries at the next open; round 7's look-ahead caught in review and fixed before its run | Pre-registration review; synthetic tests per runner | PASS | No external reviewer has audited the runners | Milestone F |
| Survivorship | Round 8 on: every NSE stock incl. delisted ones; H3's result explained as the list's drift | Audit | PASS (rounds 8+) | Rounds 1-7 used survivor lists; all rejected anyway | - |
| Holdout discipline | Two stages: development years, then the decision span run once; runners refuse re-runs | Pins (`text_sha256`), regression tests | PASS | - | - |
| Multiple testing | Criterion 12: raw p below 0.05/N with N = every hypothesis and screened variant (77) | Criteria code | PASS | The bar is strict by design; it is a choice, not an error | - |
| Costs | Zerodha delivery charges checked 8 Oct 2026 (`trader/research/costs.py`), slippage per side | Charges page; cost tests | PASS | The trial's costs assume Rs 33,333 positions: 0.328% a round trip. At Rs 3,00,000 live capital an E2 position is Rs 10,000 and costs 0.436% (the fixed DP charge) | Account for it when choosing the capital |
| Results reproduce | 20 slow regression tests recompute every round's verdicts | `pytest -m slow` | PASS (22 Oct, on these changes: 20 passed, 5 min) | - | Re-run after research code changes |
| `round10.py` pandas warning | The results pattern's group only makes "un-" optional | Both patterns on all 183,875 frozen notices: identical masks (141,141 results notices) | PASS (cosmetic) | - | Leave the pinned round's code as it ran |

## B. A strategy passes its pre-registered criteria

**FAIL.** 0 of the 32 hypotheses with evidence files pass (more were rejected in scratch experiments; N = 77 counting
screened variants). Why, from the evidence files:

| Why it failed | Hypotheses |
|---|---|
| Made money, but random stocks from the same universe did about as well (criterion 5): the profit is the market's drift, not the rule | H3, H4, H6, H8, H9, H13, H14, L1, L2, C1, C5, C6, M, N1, O2, Q |
| Beat random picks, but the payoff shape failed: win rate under the 50% floor, under 70% of years profitable, drawdown over 20R | V2 (p 0.0002), N2 (p 0.0019) |
| Beat random picks, failed a significance or stability criterion | H11 (lost money in its last third), H12 (profit factor 1.27 < 1.3), H7 (average loss 1.57x average win; its round's partner H8 failed), H10 (t 1.65 < 2; under 70% of years profitable) |
| Passed everything except significance at the multiple-testing bars | E2: p 0.030 vs Holm 0.05 (0.089) and the cross-round bar 0.000877 |
| No profit after costs, or too few trades | H1, H5, C3, C4, I1, I2, I3 (lost money); C2 (loses at 1.5x costs); H2 (46 trades, under 50) |

Forward tests (future data only, decisions each January 2028-2036): 1 (H11, H12), 2 (N2), 3 (E2), 4 (paper trial 1's
bunch, B1F), 5 (B1F hedged with futures, paper only). What they can be expected to show:

- **B1F and N2 are expected to fail criterion 2**: their own backtests won 48.7% and 43.9% of trades, under the 50%
  floor their forward tests apply. B1F's backtest drawdown (18.4R) is also close to the 20R limit that rejects it at
  once.
- **E2 (forward test 3)**, the only forward-tested rule whose backtest passes everything but significance: a
  simulation of its January looks (25 Oct 2026; about 24 trades a year, each trade's edge over random picks as noisy
  as in round 10, 50 trades needed, p below 0.05 / L, rejected from 2029 once expectancy is zero or below, every
  other criterion assumed to pass, so these are upper bounds) gives a pass by January 2036 in **about 30%** of
  futures if E2's real edge is as large as round 10's (+1.5% a trade; the earliest in January 2029, 8%), **12%** at
  half that edge, and **4%** with no edge at all (a false pass). Since E2 was the best of 57 rules tested, its real
  edge is more likely smaller than round 10's than larger. Most likely outcome: rejected, at January 2036 or earlier.

## C. Paper execution and broker-state reconciliation

| Requirement | Evidence | Method | Result | Remaining risk | Next action |
|---|---|---|---|---|---|
| Paper engine runs unattended | 7 sessions recorded, each reconciled (cash and holdings rebuilt from fills) | Health check 22 Oct 00:12: 0 alerts, 0 warnings | PASS | NO TRADE, so no fills yet | - |
| Order lifecycle (intent, request checks, sending, status, fills, holdings, stops, exits) | `tests/execution/test_oms.py`, `test_live.py`, `test_broker.py`, `test_kite_orders.py` | Tests against an in-memory Kite; 100% branch coverage of the order path | PASS | Kite's real answers can differ from the fake | Read-only check, then the first real orders' messages |
| Duplicate orders / idempotency | Tags from paper keys; a request on record is never sent twice; re-running an evening sends nothing new | `test_an_entry_goes_out_once...`, `test_a_lost_answer_is_looked_up_and_a_restart_carries_on` | PASS | - | - |
| Timeouts and lost answers | A write that may have arrived is never resent; looked up by tag (orders) or by stock, trigger and quantity (GTTs) | `test_a_write_that_may_have_arrived_is_never_resent`, `test_a_lost_answer_is_looked_up_not_resent`, dry-run lost-answer test | PASS | - | - |
| Crash between sending and recording | Recorded SENDING before it leaves; looked up after a restart; half-done changes roll back | `test_a_crash_between_sending_and_recording_is_safe`, `test_the_live_store_rolls_back_a_half_done_change` | PASS | - | - |
| Partial, rejected, cancelled fills | Recorded as filled; refusals final; no trade at the open cancels the entry | `test_partial_and_missing_fills`, `test_refusals_are_final`, dry-run no-trade test | PASS | - | - |
| Stops: placement, rejection, gaps | GTT per holding from 09:20; the morning job repeats every 15 minutes until 15:00, so a stop missed for want of a login goes in soon after it; a rejected GTT is reported once a day to place by hand; gap below the limit becomes MARKET | `test_the_morning_job_handles_stops_that_cant_wait`, `test_a_stop_missed_for_want_of_a_login_goes_in_after_the_login`, simulator gap test | PASS | A split during a holding leaves its GTT at the old price | Replace by hand (runbook) |
| A failing job doesn't flood Telegram | Each kind of failure (login, error, reconciliation, a missing stop, a request Kite has no record of) is told once a day; repeats go to the log; a kill switch engaged again after a release is told again | `test_failures_are_reported`, `test_a_mismatch_with_the_account_engages_the_kill_switch` | PASS (25 Oct) | - | - |
| Market hours, holidays | Each job refuses outside its window; non-trading days do nothing | `test_a_job_run_late_sends_nothing`, weekend tests | PASS | - | - |
| Broker state differs from local records | Fewer shares than the system holds: kill switch engaged, nothing sent | `test_a_mismatch_with_the_account_engages_the_kill_switch` | PASS | - | - |
| B1F's orders reach the live jobs | The trial's next-open plan is exactly what it records the next evening | `test_the_next_open_planned_the_evening_before_is_what_the_trial_then_does` | PASS | Rare: a locked E2 candidate's place goes to the next one in paper, not live | - |
| A trial that refuses to run (changed pin) is reported | Was a silent exit; now a reported failure | `test_a_trial_that_refuses_to_run_is_a_reported_failure` | PASS (fixed 22 Oct) | - | - |
| Dry run at real times on real prices | Evening 21 Oct 23:05: AMO for 54 UNIONBANK (simulated), filled at the 22 Oct open (Rs 182.95). The morning job failed on 22 and 23 Oct (no Kite login at the time; on 23 Oct it ran at 10:56, the login came at 11:07), so the holding has had **no stop** since 22 Oct | Simulated account `state/live-dryrun/`, task results, health warnings 22-24 Oct | Evening PASS; morning **FAILED**, fixed 25 Oct (the job repeats until 15:00), **to verify** | A morning without a login | Re-register the tasks (`register_tasks.ps1 -LiveDryRun`), log in on 26 Oct, check the `[LIVE DRY RUN]` stop message |
| Charges in the dry run | Each simulated fill pays Zerodha's delivery charges | Simulator tests with exact charges | PASS (added 22 Oct) | - | - |
| Read-only check of the real account | `python -m trader.execution.live check` only reads (margins, holdings, positions, orders, GTTs, quotes) | Code review; the check's test asserts no writes | **NOT TESTED** on your account | Kite session expired 14 Oct | Run it after the 22 Oct login |
| What only real orders meet | Static IP (Kite rejects orders from unregistered addresses since Apr 2026), DDPI, Kite's margin and market-protection checks, real partial fills | - | **BLOCKED** | - | Static IP and DDPI are yours to arrange |
| Live entries pass the risk engine | Every live entry, from any source, goes through `RiskEngine.review` on the live account: kill switch, drawdown (from the best recorded evening equity since the capital step began), daily loss (from the previous evening's), stop, one position a stock, position count, sector and gross exposure, and for B1F correlation (60 days, from paper trial 1's prices). It may cut the order, never enlarge it; the Rs 25,000 minimum position stays the paper account's | `test_live_entries_pass_the_risk_engine_on_the_live_account`, `test_a_bad_day_stops_new_live_entries_and_a_smaller_account_buys_less`, `test_no_reviewed_order_ever_breaks_a_limit` | PASS (25 Oct) | Most of B1F's stocks aren't in `config/sectors.toml`, so they count as one sector "UNKNOWN" (the stricter reading); a refused entry is a difference from paper and counts against Level 6's fill rate | - |

## D. Forward-testing evidence

| Requirement | Evidence | Method | Result | Remaining risk | Next action |
|---|---|---|---|---|---|
| 60 clean unattended sessions (Level 5) | 7 of 60 (sessions since the last failed or dead run) | Health check | **BLOCKED** (time): about the first week of January 2027 | Needs NSE's 2027 holidays in `config/market_calendars.toml` before 1 Jan 2027 | Add them when NSE publishes (December) |
| Each run names its code and configuration | Runs now record the commit, a digest of the source and of `config/*.toml` | `test_each_run_names_the_code_and_configuration_that_processed_it`, migration test | PASS from 22 Oct | The first 7 sessions don't have it | - |
| Signals, decisions, orders, fills, P&L, exposure, kill-switch events per session | Paper engine tables (sessions, decisions, orders, fills, trades, outbox, runs); trial ledger (signals, decisions, trades, brakes, pools, runs) | Append-only triggers; restore drill | PASS | The trial ledger doesn't record its code version | - |
| Forward tests' decision looks | First looks January 2028 | Pinned pre-registrations | **BLOCKED** (time) | See B | - |
| B1F's paper stage (13 weeks, 40 trades, 20 reviewed) and small-live scoring | `report.py` scores only the paper engine's account | Code review | **NOT BUILT** | Needs your decision on which trial trades count | Before January 2028 |

## E. Security, risk controls, recovery, monitoring

| Requirement | Evidence | Method | Result | Remaining risk | Next action |
|---|---|---|---|---|---|
| Secrets out of git and logs | `.env`, `.kite_session.json`, `state/`, `data/`, `logs/` git-ignored; logging masks secrets; Kite token never printed | `git check-ignore`; `tests/test_no_secrets.py`, `test_logging_setup.py`; staged-diff scan against 6 local secret values before each commit | PASS | Keys leaked earlier in the public repository's history (reported 11 Oct; Gemini and Supabase not confirmed revoked) | Revoke them, if not done |
| Telegram commands | Only the configured chat is answered; no command trades, changes a limit or releases the kill switch | `test_only_commands_from_the_configured_chat_are_answered`; code review | PASS | - | - |
| Kill switch | Blocks entries, never exits; released only by a person | Tests (paper, live, dry run) | PASS | - | - |
| Risk limits (paper engine) | 0.5% risk a trade, 20% a position, 5 positions, 100% gross, 40% a sector, 2% daily loss, 10% drawdown, 15% widest stop, Rs 25,000 minimum, 1% of volume | 100% branch coverage of `trader/risk` and `trader/portfolio` | PASS | The paper engine doesn't pass daily returns, so its 0.8 correlation limit isn't applied there (live B1F entries do get it, see C) | Pass returns if a catalogue strategy ever qualifies |
| Bad or stale data | A session missing for over 20% of instruments halts the run; a suspicious jump blocks entries, not stops; one bad instrument doesn't stop others | `test_adversarial.py`, validator tests | PASS | - | - |
| Backups and restore | A backup after every run that didn't fail; restore drill 22 Oct on a copy of `paper-2026-10-21.db`: integrity ok, reconciles, 7 of 7 sessions, fills refuse updates and deletes | Drill in a scratch folder (deleted after) | PASS | Backups sit in the OneDrive-synced folder | - |
| Monitoring and alerts | 21:00 health check, Telegram alerts; failed or stale forward runs alert; the dry run is now watched too | Health tests | PASS | Warnings print but don't reach Telegram; a PC that is off runs nothing | An always-on host, if you want one |
| Process supervision | Task Scheduler: catch-up after sleep, on battery, windowless; the bot restarts itself | Tasks inspected 21 Oct 23:16 | PASS | A laptop that is off or asleep all day | - |
| Calendar | NSE 2026 covered | Health check | **BLOCKED** from 1 Jan 2027 | Nothing trades or runs forward tests correctly without 2027's holidays | December |
| Dependency vulnerabilities | - | - | **NOT TESTED** | No scanner installed (adding one needs your OK) | Optional: `pip-audit` |

## F. Independent acceptance review

**NOT DONE.** Everything above was checked by the person who built it.

## G. Limited live deployment

**NOT APPROVED by evidence.** Approval needs B and D, the static IP and DDPI, the capital written down (at least about
Rs 3,00,000 for B1F to track the trial, more for its cost assumptions), F, and your explicit approval of a reviewed
deployment.

**A real-money trial instead, by your decision (25 Oct 2026):** you chose to trade B1F with a small amount of real
money without B and D, at your own risk. It is built, off until you write the override in `config/overrides.toml`
and turn live trading on, and limited: at most 92 days at a time, a capital cap, every risk limit (2% daily loss,
10% drawdown kill switch), no capital increase, and when it ends its trades only exit (`test_a_real_money_trial_*`,
`test_when_a_trial_ends_or_a_status_falls_its_live_trades_only_exit`). It still needs the static IP and DDPI. Its
results are not evidence: B and D are unchanged. Steps: docs/runbook.md, "A real-money trial".
