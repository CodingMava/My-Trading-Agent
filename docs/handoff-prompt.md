# Prompt for a fresh Claude: my trading project, everything so far, and what I need from you

You are joining a project with no memory of it. This prompt is the full memory of eight days of work (8-16 October 2026)
with another Claude. Read all of it before answering. Accuracy matters more than speed: if you are unsure of a fact, a
paper or a number, say so, and never invent a citation. Today is 16 October 2026; flag anything (costs, SEBI rules, data
sources) that should be re-checked.

## 0. The short answer to "did we find a strategy?"

**No.** 31 strategy hypotheses were tested on historical data under strict, pre-registered rules (plus 28 variants
screened on development years only). None passed, so the system is in NO TRADE. The closest is round 10's E2 (drift
after a strong results reaction, 17 Oct 2026): profitable, 55% winners, 71% of years profitable, drawdown 17.3R, passed
11 of 13 criteria, but its edge over random picks (+1.5% a trade, p 0.03) is not significant at the bar this many tests
require (0.05 / 57 = 0.00088). The trading system itself is built and running on paper. What is missing is a strategy
that passes my rules.

The previous Claude's honest view, which you should challenge rather than repeat: with free daily data, long-only cash
equities, 0.35-0.45% delivery costs and the rules in §4 together, any single new hypothesis has perhaps a 2-5% chance of
passing. If you also think no plausible strategy can pass, tell me plainly, and tell me what would change that.

## 1. Who I am and what I want

I'm a retail trader in India (IST) building a personal, evidence-gated trading system called my_ai_agent (Python, a
Windows laptop, broker Zerodha Kite Connect). My hard rule: only a rule with a high share of profitable trades AND
positive expectancy after realistic costs may trade; otherwise NO TRADE. Telegram alerts are mandatory. An AI provider
may advise but can never bypass the deterministic risk engine. Simple monolith, no overengineering. Please write in
plain English (I'm not a quant), with numbers rather than adjectives. I'm frustrated by long process with no result: I
want a clear answer and real progress, not bookkeeping.

## 2. Rules you must keep (not negotiable)

- No live trading and no real orders. Research, backtests and paper trading only. Real money stays in NO TRADE until a
  strategy passes every rule below and I approve each step. Approving git operations is never approval to trade.
- Never weaken a risk limit or a validation criterion, and never change either after seeing results. The 50% win-rate
  floor stays (my decision of 13 Oct). A strategy that fails only that floor is labelled "INELIGIBLE UNDER CURRENT
  POLICY" and is still rejected.
- No purchases or subscriptions. My Kite Connect plan already includes historical data. No broker-permission changes:
  enabling F&O or short selling is my decision. You may propose it, with pros and cons, but don't assume it.
- Frozen forward-test rules, recorded results and failed experiments are never modified or deleted.
- Don't re-test a retired family, or a variant of a tested rule, on data it was already tested on (§7).
- India and the US are judged separately. US trading is manual only, and there is no survivorship-free US stock data.
- Commits, pushes and merges only with my explicit approval.

## 3. The system and its risk engine (built; fixed)

- **Paper account** Rs 10,00,000. Each position risks 0.5% of equity (Rs 5,000) between entry and its stop. A stop is
  mandatory and at most 15% from entry, so a 10% stop means a Rs 50,000 position. At most 5 positions; each at most 20%
  of equity and at most 1% of the stock's average daily traded value. No new entries after a 2% daily loss.
- **Kill switch:** a 10% fall in equity halts trading. At 0.5% risk per position that is 20R, hence criterion 13.
- **What can be executed:** NSE cash equities and ETFs through Kite, long only, delivery (CNC) or intraday (MIS). Orders
  go in after the close for the next open, with GTT stops and time exits. No overnight shorts (that needs F&O).
- **Lifecycle** (config/strategies.toml): RESEARCH -> PAPER -> LIVE_SMALL -> LIVE. PAPER needs research evidence that
  passes every criterion, a drawdown of 20R or less, and my approval. Live trading needs 13+ weeks of passing paper
  evidence, 60 clean unattended sessions and more; it is locked today ([live] enabled = false, capital Rs 0).
- **What exists and runs** (Windows scheduled tasks, windowless, battery-proof): the daily paper run at 18:00 IST
  (India, then a US paper account), a health check at 21:00, the NSE news collector every 15 minutes (catches up missed
  days whole), forward test 2 at 19:30, and a Telegram bot (/status /positions /trades /kill /login /kitecheck; it can
  never release the kill switch or place a trade). Also: append-only SQLite records with daily backups, a read-only
  dashboard, a Kite order path that exists only as a journaled dry run plus an order-management system tested against a
  fake Kite, tax records, and a CI suite with a 100% branch-coverage gate on the risk engine and order path.
- **The 60-session unattended record** began on 12 October 2026. It completes in the first week of January 2027 only if
  NSE's 2027 holidays are added to the calendar in December.

## 4. How a hypothesis is judged (exactly)

**Protocol.**

- Pre-register first: a Markdown file fixes every rule, cost, span and criterion, and its SHA-256 is pinned before any
  code computes the rule on real data. The runner refuses to run if that file changes.
- Two stages: stage 1 (a development span) checks the implementation and decides nothing; stage 2 (the decision span,
  usually June 2013 to August 2026) runs once. Between them only bugs may be fixed, with both outputs kept.
- Every result is recorded, pass or fail.

**The random baseline (criteria 5 and 12).** The same number of random picks from the same pool, at the same times,
with the same entry, stop, exit and costs: 20,000 draws, and p = (k + 1) / (N + 1), where k is the number of draws whose
mean net return is at least the strategy's. Most of our hypotheses failed here: their profit was what any entry in the
same market at the same times would have earned.

**The 13 criteria.** All must pass, each hypothesis judged on its own:

| # | Criterion |
|---|---|
| 1 | At least 50 trades |
| 2 | Win rate at least 50%, net of costs |
| 3 | Mean net return per trade above 0 at 1x and at 1.5x costs |
| 4 | t-statistic of the mean net return at least 2.0 |
| 5 | Beats the random baseline: Holm-adjusted p below 0.05 (Holm across that round's hypotheses) |
| 6 | Profit factor at least 1.3 |
| 7 | Average loss at most 1.5x the average win; no trade worse than -3R |
| 8 | Mean net above 0 in each half of the decision span |
| 9 | At least 70% of calendar years with 10+ trades profitable |
| 10 | At least 60% of stocks with 5+ trades profitable, and mean net above 0 without the single best stock (n/a for one-instrument rules) |
| 11 | Cluster-robust t-statistic (signal dates or months as clusters) at least 2.0 |
| 12 | Raw p against random below 0.05 / N, where N counts every hypothesis ever tested on historical data, including variants screened on development years: 57 now, so k new ones make the bar 0.05 / (57 + k) |
| 13 | Drawdown of cumulative R, trades in exit order, no deeper than 20R |

Decisions: every criterion passes -> candidate for PAPER (with my approval); only criterion 1 fails -> inconclusive
(stays RESEARCH); anything else -> REJECTED.

**What the criteria imply together (check this arithmetic).** With win rate p and average win / average loss = W/L,
profit factor = pW / ((1 - p)L). A profit factor of 1.3 needs W/L of at least 1.3(1 - p)/p: 1.30 at a 50% win rate, 1.06
at 55%, 0.87 at 60%, 0.70 at 65%. Criterion 7 needs W/L of at least 0.67. So the target is roughly 55-65% winners with
wins about as large as losses. Momentum's profile (40-45% winners, a long right tail) doesn't fit.

**Costs (Zerodha, October 2026).**

- Delivery (CNC) at Rs 50,000 a position: STT 0.1% each side, stamp duty 0.015% on the buy, NSE transaction charge
  0.00307% each side plus 18% GST, the SEBI fee, and a DP charge of about 0.031% on the sale: 0.2532% a round trip. Plus
  slippage of 0.05% a side for the 100 most liquid stocks or 0.10% a side for liquidity ranks 101-300, and once more on a
  stop exit. Totals: 0.3532% or 0.4532% a round trip.
- Intraday (MIS) on NIFTYBEES at Rs 2,00,000: 0.0591%, plus 0.03% slippage a side, so 0.1191% a round trip.

**Statistical power.** A monthly 5-stock strategy over 2013-2026 has about 158 decision months; beating random picks at
p of about 0.0017 needs an edge of roughly 1% a month in mid caps. Rules with thousands of independent events have more
power.

## 5. Data we have (free, frozen with checksums)

- **NSE equity bhavcopies:** daily open, high, low, close, previous close, traded value, series and ISIN for every session
  from 3 January 2005 to 13 October 2026 (5,402 sessions), delisted stocks included, so survivorship-free. Adjusted with
  NSE's 42,156 corporate-action records and symbol changes into a panel (splits, bonuses, rights at the theoretical
  ex-rights price, dividends of 5% or more, demergers at the ex-date close). Eligible stocks per month-end grew from 641
  (2006) to 1,820 (2026). Returns are price returns (dividends under 5% ignored for strategy and random picks alike).
  - Audit findings: NSE's previous close isn't adjusted for corporate actions; NSE files old actions under today's
    symbols; 2005-2008 records are incomplete; before April 2013 an open can be a stray first trade (call auction for all
    stocks since then); weekend special sessions exist.
- **NSE board-meeting records (new, 16 Oct 2026):** 183,875 notices, meetings 1 Jan 2009 to 15 Oct 2026, each with the
  company, meeting date, purpose and the time the notice was filed, delisted companies included. 122,510 results
  meetings; about 1,190 a year among the 300 most liquid stocks; 94-98% match the price panel. Notices come a median of
  7-11 days ahead; since SEBI's May 2024 amendment only two working days' notice is required. About a fifth are filed
  after 18:00. 0.7% of meetings were rescheduled before their date. Not used by any test yet.
- **Kite 1-minute bars** of NIFTYBEES and the NIFTY 50 index, 1 January 2020 to 12 October 2026 (NIFTYBEES has bad 09:15
  prints in 2020-2022; NSE's closing auction since 3 August 2026 makes 15:15-15:29 flat). Kite's minute history covers
  only instruments listed today, so any stock-level intraday test would be survivorship-biased.
- **Yahoo daily data** for US sector SPDRs, 15 iShares country ETFs, SPY, and Indian ETFs (quirks: broken unit splits,
  bad opens; NSE index prices preferred).
- **SEBI insider-trading disclosures (new, 16-17 Oct 2026):** 341,514 disclosures published 19 Nov 2015 to 2 May 2026,
  each with the exact publication time (30,559 promoter open-market purchases). NSE's API returns nothing after May 2026
  (probably a new system), so any live use needs another source.
- **NSE corporate announcements** with timestamps, collected every 15 minutes since 12 October 2026; NSE's API returns
  any past day whole (checked back to 2008, with fewer records in early years).
- **Not used yet, free from NSE (verify first):** F&O bhavcopies (futures and options with open interest), security-wise
  delivery percentages, bulk and block deals, India VIX, FII/DII flows, index-change announcements.
- **Not available:** survivorship-free US stock data (paid; not buying), point-in-time fundamentals or analyst
  estimates, SEC EDGAR (needs a declared contact email; my decision).

## 6. The record: 28 hypotheses tested on history, 0 passed

Before this protocol, 9 original intraday rules (R1-R8S: breakouts, reversals, Turtle, Crabel; 5-minute bars) all lost
0.10-0.20% a trade with 34-43% winners at 0.14% costs. Then:

| Id | Rule | Result | Why rejected |
|---|---|---|---|
| H1 | Oversold pullback in an uptrend (RSI(2)-style), NIFTY 50 stocks, daily | 1,771 trades, 60.2% winners, -0.05% net, PF 0.96 | Beat random before costs (p 0.04); 0.30% delivery costs ate the edge |
| H2 | Same rule, NIFTY 50 via ETF | 46 trades | Too few; no better than random days |
| H3 | 12-1 momentum, top 5 of today's NIFTY 50 | +1.18% a trade | Random picks from the same (survivorship-biased) list did nearly as well |
| H4 | Pullback, 82 S&P 100 stocks | 62% winners, +0.16% | Random entry days made most of it (p 0.22) |
| H5 | Pullback, Indian index ETFs | -0.06% | Edge vanished after 2021 |
| H6 | Pullback, 11 US sector SPDRs, 2016-2026 | 65% winners, +0.24%, PF 1.37 | p 0.069 against random (Holm 0.21) |
| H7 | H6's rules, 9 SPDRs, 2000-2015 | 71% winners, +0.32%, t 5.3, Holm p 0.012 | Average loss 1.57x the average win (limit 1.5x) |
| H8 | H6's rules, 15 country ETFs, 2016-2026 | +0.07% | No edge. The pullback family is RETIRED |
| H9 | Turn of the month (TOM), SPY, 1993-2026 | 57.7% winners, +0.23% | p 0.067; 61% of years profitable |
| H10 | TOM, NIFTYBEES, 2008-2026 | Beat random (Holm p 0.033) | t 1.65; 61% of years |
| H11 | TOM on BANKBEES, JUNIORBEES, ITBEES, PHARMABEES, 2008-2026 | 863 trades, 57.9% winners, +0.475%, t 4.8, Holm p < 0.001 | Failed only "each third of the span profitable"; lost money in 2024-2026. In forward test 1 |
| H12 | TOM, 15 country ETFs, 2001-2026 | 4,334 trades, +0.265%, Holm p 0.039 | Profit factor 1.27 (needs 1.3). In forward test 1 |
| H13, H14 | Momentum, top 3 of 9 US sector SPDRs / 15 country ETFs, monthly | About +0.8% a trade | Random sectors or countries did as well: market drift |
| C1, C2 | Chan's buy-on-gap, intraday, NIFTY 50 / S&P 100 stocks | +0.15% / +0.01% | Weak / flat |
| C3, C4 | Opening-gap momentum, NIFTY / SPY | Lost money before costs | Gaps faded |
| C5, C6 | Time-series momentum, NIFTY or SPY vs cash, monthly | Lower CAGR than holding | No better than random months |
| I1-I3 | NIFTYBEES 14:45-15:14 in the direction of the morning (Gao, Han, Li & Zhou) | 24-27% winners | Gross edge about 0.01% against 0.12% costs |
| N1 | 12-1 momentum, top 5 of the 100 most liquid NSE stocks, monthly, 10% stop, 2013-2026 | 795 trades, 48.6% winners, +0.41% vs +0.52% random (p 0.64) | No edge; drawdown 45.5R |
| N2 | Same rule, liquidity ranks 101-300 | 792 trades, +1.75% vs +0.67% random (p 0.0019), t 2.92, PF 1.32 | 43.9% winners, 64% of years profitable, drawdown 34.1R. In forward test 2 |
| L1 | 5 lowest-volatility stocks of the 100 most liquid, monthly, 10% stop | 795 trades, 51.4% winners, +0.58% vs +0.52% random (p 0.43) | No better than random; 57% of years; PF 1.24 |
| L2 | Same, ranks 101-300 | 795 trades, 52.7% winners, +0.671% vs +0.679% random (p 0.50), PF 1.31, 71% of years, drawdown 12.9R | Passed 11 of 13; failed only the two random-baseline tests: zero edge |
| V2 | Volatility-adjusted momentum (Nifty200 Momentum 30 style), ranks 101-300 | 791 trades, +2.07% vs +0.67% random (p 0.0002), t 3.51, PF 1.41 | 45.9% winners, 64% of years, drawdown 30.4R. Overlaps N2 |
| E2 | Round 10: buy a top-10% results reaction (2-session move vs the universe) 2 sessions after the board meeting, hold 40 sessions, 15% stop, 5 positions, 300 most liquid, 2013-2026 | 313 trades, 55.0% winners, +2.33% vs +0.83% random (p 0.030, Holm 0.089), PF 1.47, cluster t 2.08, 71% of years, drawdown 17.3R | Passed 11 of 13; failed only the two "beats random" tests. With every event (no cap): 1,597 trades, edge +1.76% |
| Q | Round 10: promoter open-market purchases of Rs 10 lakh+, hold 40, 15% stop, 2018-2026 | 230 trades, 50.0% winners, +1.33% vs +0.89% random (p 0.31) | No edge in the decision years |
| M | Round 10: E2 and Q sharing 5 positions, 2018-2026 | 288 trades, 53.8% winners, +1.88% vs +1.15% random (p 0.18), 75% of years | Passed 10 of 13; Q diluted E2 |

Round 10 also screened, on development years only, and dropped: holding through the results day (the rise comes before
it: +0.4% over random in the 5 sessions before, but not enough after 0.37-0.47% costs), bonus/split/buyback meetings (too
few), the high-volume premium (high-volume stocks did worse than random in India), same-month seasonality, and promoter
pledge releases. A 15% stop instead of 10% was what made the results-drift payoff fit the rules.

Round 9 sums up the problem: L2 had the payoff shape the rules want but no selection edge; V2 had the strongest
selection edge in the project but momentum's payoff shape. Post hoc notes (not evidence): N2's significance rests on a
few large winners and on 2020-2026; without the 10% stop, N2's and V2's picks won 51-54% of trades; V2's losing years
were 2015, 2018, 2022, 2024 and 2025.

## 7. What the record teaches (challenge it)

1. **Drift.** Most hypotheses failed to beat random entries. A long-only rule that is simply in the market earns the
   market; the random baseline cancels that. A pass needs real selection or timing skill.
2. **Near misses** (H7, H10, H11, H12, N2, V2 beat random) each failed something else: loss size, sample size,
   stability, profit factor, or win rate plus stability plus drawdown. L2 failed the opposite way.
3. **Payoff shape.** The win-rate floor, profit factor and loss-size rules together favour 55-65% winners with
   symmetric payoffs: mean-reversion-like or event-like edges, not trends.
4. **Stops and win rate interact.** A tight stop on a noisy stock cuts trades that would have won.
5. **Drawdown and stability.** Five long positions all stopped in one month costs 5R; broad falls sink unhedged
   long-only stock rules; 70% of years profitable is hard for anything with market exposure.
6. **Costs.** Delivery STT makes short single-stock holds expensive: a 3-5 day trade needs a gross edge well above
   0.45% beyond random.
7. **Power.** A bar near 0.0017 needs a large edge or thousands of independent events.
8. **Structurally ineligible:** overnight-drift strategies (gap risk beyond -3R), opening-range breakouts (about 25%
   winners), classic trend following (36% winners in our audit).
9. **Data already used.** NSE stocks 2013-2026 have been used for 12-1 momentum, low volatility and volatility-adjusted
   momentum (2006-2013 was their development span, also seen). A new hypothesis there must be a genuinely different
   family. Variants of N2, V2, L2, H11 and H12 can only be judged on future data.

## 8. Where things stand (16 October 2026)

- **Trading:** NO TRADE everywhere. Live off, Rs 0. Every strategy in the registry is REJECTED or DISABLED.
- **Forward test 1:** H11 and H12, rules unchanged, judged only on sessions from 14 October 2026. January looks begin
  in 2028; realistically nothing is decided before 2030.
- **Forward test 2:** N2, rules unchanged, pinned 14 October 2026 23:27 IST, runs daily at 19:30. First picks at the 30
  October 2026 close; January looks 2028-2036. Its pinned rules were pushed to GitHub on 16 October (public timestamp).
- **Round 10 (pinned 17 Oct 17:45 IST, run once, all REJECTED):** see §6 (E2, Q, M). The earlier draft below was replaced
  by the pinned pre-registration (E1 was dropped by screening; E2 got a 15% stop and 40-session hold):
  File docs/research/round10-preregistration.md. Universe: round 8's 300 most liquid stocks at the latest month-end.
  - **E1, earnings-announcement premium** (Lamont & Frazzini, NBER WP 13090, 2007; Barber, De George, Lehavy & Trueman,
    JFE 108(1), 2013: significant in 9 of 20 countries with enough data; whether India was one is not confirmed): buy at
    the open 3 sessions before the results meeting, if the meeting was notified by 18:00 the evening before; sell at the
    open 2 sessions after it; 10% stop; at most 5 positions, candidates taken in a fixed pseudo-random order. About
    1,700 trades in 2013-2026.
  - **E2, drift after a strong results reaction:** the stock's return from the close before the meeting session to the
    close after it, minus the universe's mean, in the top 10% of the previous 250 sessions' events; buy at the next
    open, hold 20 sessions, 10% stop; strongest reactions first. Roughly 600-900 trades.
  - Tier-matched random baseline; criteria unchanged; N becomes 30 (bar 0.00167). Estimated chance of passing everything:
    about 5% (E1) and 3% (E2). E1's likeliest failure is the 50% win-rate floor (5-session holds against 0.35-0.45%
    costs). Indian evidence on announcement effects is mixed.
  - Open choices listed at the end of the draft: keep E2 or not, entry timing, exits at the open, the 5-position cap,
    the baseline, E2's threshold and holding, re-checking costs.
- **Code:** GitHub CodingMava/My-Trading-Agent. origin/main = 9c81576 (rounds 1-7). origin/forward-test-2 = 151539b
  (rounds 8 and 9, forward test 2, news catch-up). Local main = 151539b (fast-forwarded, not yet pushed). Branch
  round10-draft holds round 10 (runner, tests, pre-registration, stage 1, results, evidence, registry, README) and this
  prompt, all uncommitted.
- **Open items that are mine:** rotate the leaked Gemini and Supabase keys (they are in the public repo's old history);
  run the Kite live check after a login; add NSE 2027 holidays in December; decide on an always-on host for the news
  collector (GitHub Actions cron or a small VM; NSE may block cloud IPs); push main.
- **Known gaps before any real order:** the 15:15 pre-close exit job must be redesigned for NSE's closing auction; a
  static IP registered with Kite, DDPI with Zerodha, a daily Kite login.

## 9. What I want from you

Think first, then answer in this order:

1. **One plain sentence:** do you think a strategy that passes all 13 criteria is likely to exist within my constraints,
   and roughly how likely?
2. **Round 10:** review the E1/E2 design above. Should I run it as drafted, change it before pinning (say exactly what
   and why), or skip it? Estimate each one's chance of passing every criterion.
3. **Better candidates:** at most 3-5 hypotheses you think beat round 10, ranked by chance of passing everything. For
   each: the economic reason and who is on the other side; published evidence (authors, year, journal; say when
   unsure) and any Indian evidence; exact mechanical rules computable at decision time; the free data and its
   survivorship and point-in-time problems; expected trades, win rate, average win and loss, net per trade after the
   costs above, edge over random, drawdown in R, share of profitable years; your chance for each of the 13 criteria;
   a power calculation for the bar 0.05 / (28 + k); how it could fail.
4. **Which one to pre-register first,** with a draft in the project's style: hypotheses table, definitions, multiple
   testing, criteria unchanged, two stages, expectations stated before testing, sensitivity checks reported but never
   used to choose.
5. **If no plausible strategy passes these rules,** say so plainly, and say what would change that: more forward data,
   different data, or a policy decision that is mine to make (explained, not assumed; never applied retroactively to
   results already seen).

Avoid: fitting to the numbers above (say when an idea was suggested by results already seen); many variants of one idea
(each counts toward N); anything needing live trading, purchases, shorting or F&O unless flagged as my decision;
anything that changes the criteria.

## 10. If you are running inside the repository (Claude Code)

- **Where things are.** C:\Users\11231\OneDrive\Desktop\my_ai_agent; use venv\Scripts\python.exe.
- **Tests.** Fast: `pytest` (387 pass). Slow: `pytest -m slow` (20 regression tests, rounds 1-10, all pass). A 100%
  branch-coverage gate covers the risk engine, portfolio and order path (`coverage run -m pytest`, then
  `coverage report`). Never disable tests to make code pass.
- **Research code** in trader/research/: round8.py (universe, tiers, trade, costs, random baseline, criteria);
  nse_bhavcopy.py (NSE data and adjustments); round9.py (a round that reuses round 8); forward2.py (forward-test runner);
  news.py (NSE announcements API). Board-meeting data: data/round10/board_meetings (427 JSON files, git-ignored;
  manifest SHA-256 1e7accb2...). Records: docs/research/ (pre-registrations and results), docs/research/evidence/,
  config/strategies.toml (registry), config/gate.toml (thresholds).
- **Pinned files:** 12 pre-registrations, all fingerprints valid (round 10: c973d560...). Write pinned files as bytes with LF line endings
  (Windows); the hash is datasets.text_sha256, which reads CRLF as LF.
- **IST times:** from Python zoneinfo; Git Bash's TZ prints UTC.
- **Git:** commit, push or merge only with my explicit approval; scan for secrets before any commit; never commit .env
  values; leave branches paper-split-adjustment and claude/gifted-mccarthy-6ef268 alone; don't send my email address to
  outside services.
- **Never change** trader/risk, the kill switch, the live locks ([live] enabled = false, capital 0), frozen
  forward-test rules or recorded results. The scheduled tasks run whatever branch is checked out: keep main (or a branch
  containing it) checked out.
