# Prompt for a fresh Claude: find a trading strategy that can pass this project's gates

You are joining a research project with no history of it. Read all of this before answering. Accuracy matters more
than speed: if you are unsure of a fact, a paper or a number, say so, and never invent a citation. Today is 15 October
2026; your training data may be older, so flag anything (costs, SEBI rules, data sources) that should be re-checked.

## 1. Who I am and what I want

I'm a retail trader in India (IST) building a personal, evidence-gated trading system called my_ai_agent (Python, a
Windows laptop, broker Zerodha Kite Connect). In the last week an AI agent and I tested 28 strategy hypotheses on
historical data under strict, pre-registered rules. None passed, so the system is in NO TRADE.

I want you to think hard and propose the strategy, or strategies, most likely to pass every gate below on a fresh,
honest test: a genuinely profitable strategy with robust statistical evidence, controlled drawdowns and realistic
transaction costs. Tell me plainly how likely it is to pass. Please write in plain English (I'm not a quant), with
numbers rather than adjectives.

## 2. Rules you must keep (not negotiable)

- No live trading and no real orders. Research, backtests and paper trading only. Real money stays in NO TRADE until a
  strategy passes every rule below and I approve each step.
- Never weaken a risk limit or a validation criterion, and never change either after seeing results. The 50% win-rate
  floor stays. A strategy that fails only that floor is labelled "INELIGIBLE UNDER CURRENT POLICY" and is still rejected.
- No purchases or subscriptions. My Kite Connect plan already includes historical data. No broker-permission changes:
  enabling F&O (futures and options) or short selling is my decision. You may propose it, with pros and cons, but
  don't assume it.
- Frozen forward-test rules, recorded results and failed experiments are never modified or deleted.
- Don't re-test a retired family, or a variant of a tested rule, on data it was already tested on (details in §7).
- India and the US are judged separately; nothing combines results across markets. US trading is manual only (no US
  broker integration), and the project has no survivorship-free US stock data.

## 3. The system and its risk engine (fixed)

- Paper account Rs 10,00,000. Each position risks 0.5% of equity (Rs 5,000) between entry and its stop. A stop is
  mandatory and may be at most 15% from entry, so a 10% stop means a Rs 50,000 position. At most 5 positions; each at
  most 20% of equity and at most 1% of the stock's average daily traded value.
- Kill switch: a 10% fall in equity halts trading. At 0.5% risk a position, that is 20R, hence criterion 13 below.
- What can be executed: NSE cash equities and ETFs through Kite, long only, either delivery (CNC, held overnight) or
  intraday (MIS, closed the same day). Orders go in after the close for the next open, with GTT stops and time exits.
  The system holds no short positions overnight (that would need F&O).
- Lifecycle (config/strategies.toml): RESEARCH -> PAPER -> LIVE_SMALL -> LIVE; anything missing counts as not approved.
  PAPER needs research evidence that passes every criterion, a recorded drawdown of 20R or less, and my approval. Live
  trading also needs at least 13 weeks of passing paper evidence and more; it is locked today (enabled = false,
  capital Rs 0).

## 4. How a hypothesis is judged (exactly)

**Protocol.**

- Pre-register first. A Markdown file fixes every rule, cost, span and criterion, and its SHA-256 is pinned before any
  code computes the rule on real data. The runner refuses to run if that file changes.
- Two stages. Stage 1 (a development span, e.g. 2006 to May 2013 for NSE stocks) checks the implementation and decides
  nothing. Stage 2 (the decision span, e.g. June 2013 to August 2026) runs once. Between them only bugs may be fixed,
  with both outputs kept; no rule, parameter, cost, criterion or span may change.
- Every result is recorded, pass or fail.

**The random baseline (criteria 5 and 12).** The same number of random picks from the same pool, at the same times,
with the same entry, stop, exit and costs: 20,000 draws, and p = (k + 1) / (N + 1), where k is the number of draws
whose mean net return is at least the strategy's. For a timing rule on one instrument, the comparison is random entry
days (or times) with the same holding rules. This is the test most of our hypotheses failed: their profit was what any
entry in the same market at the same times would have earned.

**The 13 criteria.** All must pass, and each hypothesis is judged on its own:

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
| 12 | Raw p against random below 0.05 / N, where N counts every hypothesis ever tested on historical data: 28 now, so a round of k new hypotheses makes the bar 0.05 / (28 + k) (k = 3 gives 0.0016) |
| 13 | Drawdown of cumulative R, trades in exit order, no deeper than 20R |

Decisions: every criterion passes -> candidate for PAPER (with my approval); only criterion 1 fails -> inconclusive
(stays RESEARCH); anything else -> REJECTED.

**What the criteria imply together (my arithmetic; check it).** With win rate p and average win / average loss = W/L,
the profit factor is pW / ((1 - p)L). A profit factor of 1.3 needs W/L of at least 1.3(1 - p)/p: 1.30 at a 50% win
rate, 1.06 at 55%, 0.87 at 60%, 0.70 at 65%. Criterion 7 needs W/L of at least 0.67. So the target payoff is roughly
55-65% winners with wins about as large as losses. Momentum's profile (40-45% winners, a long right tail) doesn't fit.

**Costs (Zerodha, as of October 2026; use these or justify a change).**

- Delivery (CNC) at Rs 50,000 a position: STT 0.1% on each side, stamp duty 0.015% on the buy, NSE transaction charge
  0.00307% each side plus 18% GST, the SEBI fee, and a DP charge of about 0.031% on the sale. That is 0.2532% for a
  round trip. Add slippage of 0.05% a side for the 100 most liquid stocks or 0.10% a side for liquidity ranks 101-300,
  and once more on a stop exit. Totals: 0.3532% or 0.4532% a round trip.
- Intraday (MIS) on NIFTYBEES at Rs 2,00,000: 0.0591%, plus 0.03% slippage a side, so 0.1191% a round trip.

**Statistical power, stated before testing.** A monthly 5-stock strategy over 2013-2026 has about 158 decision months.
A 5-stock pick's monthly return has a standard deviation of about 4% (large caps) or 5% (mid caps). Beating random
picks at p of about 0.0017 therefore needs an edge of roughly 1% a month in mid caps. Rules with many independent
events have more power than monthly rules.

## 5. Data we have (free, frozen with checksums)

- **NSE equity bhavcopies**: daily open, high, low, close, previous close, traded value, series and ISIN for every
  session from 3 January 2005 to 13 October 2026. That is 5,402 sessions, delisted stocks included, so the history is
  survivorship-free. It is adjusted with NSE's 42,156 corporate-action records and symbol changes into a panel: splits,
  bonuses, rights at the theoretical ex-rights price, dividends of 5% or more, and demergers at the ex-date close.
  - Eligible stocks per month-end grew from 641 (2006) to 1,820 (2026).
  - Returns are price returns; dividends under 5% are ignored for the strategy and the random picks alike.
  - What the data audit found: NSE's previous close isn't adjusted for corporate actions. NSE files old actions under
    today's symbols. Records for 2005-2008 are incomplete (standard ratios were inferred). Before April 2013 an open
    can be a stray first trade; every stock has had a call auction at the open since then. Weekend special sessions
    exist (Muhurat, Budget days).
- **Kite 1-minute bars** of NIFTYBEES and the NIFTY 50 index, 1 January 2020 to 12 October 2026. NIFTYBEES has bad
  09:15 prints in 2020-2022. NSE's closing auction, since 3 August 2026, makes 15:15-15:29 flat. Kite's minute history
  (from 2015) covers only instruments listed today, so any stock-level intraday test would be survivorship-biased.
- **Yahoo daily data** for ETFs and indices: US sector SPDRs, 15 iShares country ETFs and SPY; NIFTYBEES, BANKBEES,
  JUNIORBEES, ITBEES and PHARMABEES. Yahoo has quirks (broken unit splits, bad opens), so NSE index prices are
  preferred.
- **NSE corporate announcements**, with timestamps. The API returns any past day whole, and announcements have been
  collected every 15 minutes since 12 October 2026 into a local database. How far back the API goes hasn't been
  checked yet.
- **Not used yet**, free from NSE's archives as far as I know (verify before relying on any of them): F&O bhavcopies
  (daily futures and options, with open interest), security-wise delivery percentages, bulk and block deals, India VIX,
  FII/DII flows and NSE's index-change announcements.
- **Not available**: survivorship-free US stock data (paid; not buying), point-in-time fundamentals or analyst
  estimates, and SEC EDGAR (it needs a declared contact email; that's my decision).

## 6. The record: 28 hypotheses tested on history, 0 passed

Before this protocol existed, 9 original intraday rules (R1-R8S: breakouts, reversals, Turtle, Crabel; 5-minute bars;
1% stop, 2% target) all lost 0.10-0.20% a trade with 34-43% winners at 0.14% costs. Then:

| Id | Rule | Result | Why rejected |
|---|---|---|---|
| H1 | Oversold pullback in an uptrend (RSI(2)-style), NIFTY 50 stocks, daily | 1,771 trades, 60.2% winners, -0.05% net, PF 0.96 | Beat random before costs (p 0.04), but 0.30% delivery costs ate the edge |
| H2 | Same rule, NIFTY 50 via ETF | 46 trades | Too few; no better than random days |
| H3 | 12-1 momentum, top 5 of today's NIFTY 50 | +1.18% a trade | Random picks from the same (survivorship-biased) list did nearly as well |
| H4 | Pullback, 82 S&P 100 stocks | 62% winners, +0.16% | Random entry days made most of it (p 0.22) |
| H5 | Pullback, Indian index ETFs | -0.06% | Edge vanished after 2021 |
| H6 | Pullback, 11 US sector SPDRs, 2016-2026 | 65% winners, +0.24%, PF 1.37 | p 0.069 against random (Holm 0.21) |
| H7 | H6's rules, 9 SPDRs, 2000-2015 | 71% winners, +0.32%, t 5.3, Holm p 0.012 | Average loss 1.57x the average win (limit 1.5x) |
| H8 | H6's rules, 15 country ETFs, 2016-2026 | +0.07% | No edge. The pullback family is RETIRED |
| H9 | Turn of the month (TOM), SPY, 1993-2026 | 57.7% winners, +0.23% | p 0.067; 61% of years profitable |
| H10 | TOM, NIFTYBEES, 2008-2026 | Beat random (Holm p 0.033) | t 1.65; 61% of years |
| H11 | TOM on BANKBEES, JUNIORBEES, ITBEES, PHARMABEES, 2008-2026 | 863 trades, 57.9% winners, +0.475%, t 4.8, Holm p < 0.001 | Failed only "each third of the span profitable" (2014-2020 flat); lost money in 2024, 2025 and 2026. Now in forward test 1 |
| H12 | TOM, 15 country ETFs, 2001-2026 | 4,334 trades, +0.265%, Holm p 0.039; all 15 countries profitable | Profit factor 1.27 (needs 1.3). Now in forward test 1 |
| H13, H14 | Momentum, top 3 of 9 US sector SPDRs / 15 country ETFs, monthly | About +0.8% a trade | Random sectors or countries did as well (p 0.20, 0.18): market drift |
| C1, C2 | Chan's buy-on-gap, intraday, NIFTY 50 / S&P 100 stocks | +0.15% / +0.01% | Weak (lost money in 2024-2025) / flat |
| C3, C4 | Opening-gap momentum, NIFTY / SPY | Lost money before costs | Gaps faded |
| C5, C6 | Time-series momentum, NIFTY or SPY vs cash, monthly | Lower CAGR than holding | No better than random months |
| I1-I3 | NIFTYBEES 14:45-15:14 in the direction of the morning (Gao, Han, Li & Zhou) | 24-27% winners | Gross edge of about 0.01% against 0.12% costs |
| N1 | 12-1 momentum, top 5 of the 100 most liquid NSE stocks, monthly, 10% stop, 2013-2026 | 795 trades, 48.6% winners, +0.41% vs +0.52% for random picks (p 0.64) | No edge; drawdown 45.5R |
| N2 | Same rule, liquidity ranks 101-300 | 792 trades, +1.75% vs +0.67% for random (p 0.0019, Holm 0.0038), t 2.92, cluster t 2.21, PF 1.32 | 43.9% winners, 64% of years profitable, drawdown 34.1R. Now in forward test 2 |
| L1 | Round 9: the 5 lowest-volatility stocks of the 100 most liquid, monthly, 10% stop, 2013-2026 | 795 trades, 51.4% winners, +0.58% vs +0.52% random (p 0.43), PF 1.24, 17.1R | No better than random; 57% of years profitable; cluster t 1.62 |
| L2 | Same rule, liquidity ranks 101-300 | 795 trades, 52.7% winners, +0.671% vs +0.679% random (p 0.50), t 2.85, cluster t 2.05, PF 1.31, 71% of years profitable, drawdown 12.9R | Passed 11 of 13 criteria; failed only the two random-baseline tests (5 and 12): zero edge over random picks |
| V2 | Volatility-adjusted momentum (like NSE's Nifty200 Momentum 30: z-scores of 12-1 and 6-1 returns divided by volatility), ranks 101-300 | 791 trades, +2.07% vs +0.67% random (p 0.0002, Holm 0.0006), t 3.51, cluster t 2.57, PF 1.41, deflated Sharpe 0.96 | 45.9% winners, 64% of years profitable, drawdown 30.4R (kill switch hit Sep 2015). Overlaps N2 |

Round 9 sums up the problem. L2 had the payoff shape the rules want but no selection edge. V2 had the strongest
selection edge in the project but momentum's payoff shape. Neither may be re-tested in a modified form on 2013-2026.

Post hoc notes, which are not evidence:

- N2's significance rests on a few large winners (p 0.07 without its best 5 of 792 trades) and on 2020-2026.
- Without the 10% stop, N2's picks won 51-54% of their trades and the edge over random was larger. The same holds for
  V2: 52.7% winners and +1.96% a month over random. The risk engine requires a stop (at most 15%).
- V2's losing years: 2015, 2018, 2022, 2024, 2025. It earned more per trade when the NIFTY was below its 200-session
  average (+3.1%) than above it (+1.7%).
- In 2006-2013, V2 often picked smooth risers that later collapsed (e.g. SHREEASHTA, CASTEXTECH). In Indian small and
  mid caps, rewarding smooth returns may select circuit-limited or manipulated stocks (unverified).

## 7. What the record teaches (my synthesis; challenge it)

1. **Drift.** 19 of the first 23 hypotheses failed to beat random entries. A long-only rule that is simply in the
   market earns the market, and the random baseline cancels that. A pass needs real selection or timing skill.
2. **Near misses.** The six that beat random (H7, H10, H11, H12, N2, V2) each failed something else: loss size, sample
   size, stability across sub-periods and recent years, profit factor, or (N2 and V2) win rate, stability and drawdown
   together. L2 failed the opposite way: every rule except beating random.
3. **Payoff shape.** The win-rate floor, the profit-factor rule and the loss-size rule together favour 55-65% winners
   with symmetric payoffs. That points to mean-reversion-like or event-like edges, not trends.
4. **Stops and win rate interact.** A tight stop on a noisy stock cuts trades that would have won. The engine allows up
   to 15%, but a wider stop means a smaller position at the same 0.5% risk.
5. **Drawdown and stability.** Five long positions all stopped in one month costs 5R; four such months reach the kill
   switch. Broad falls (2008, 2011, 2015-16, March 2020) sink unhedged long-only stock rules. 70% of years profitable is
   hard for anything with market exposure.
6. **Costs.** Delivery STT (0.2% a round trip) makes short holds in single stocks expensive: a 3-5 day trade needs a
   gross edge well above 0.45% beyond random. Intraday ETF costs of 0.12% killed an edge of 0.01%.
7. **Power.** A bar near 0.0016 needs a large edge or many independent observations: about 150 independent months for
   a monthly rule, against thousands of independent events, spread over many days, for an event rule.
8. **Structurally ineligible under these rules:**
   - Overnight-drift strategies: the gap risk exceeds -3R (on 23 March 2020 the NIFTY opened about 9% lower).
   - Opening-range breakouts: about 25% winners.
   - Classic trend following: 36% winners in our audit.
9. **Data already used.** NSE stocks 2013-2026 have been used for 12-1 momentum, low volatility and volatility-adjusted
   momentum (the 2006-2013 span was their development stage, also seen). A new hypothesis on that span must be a
   genuinely different family. Variants or combinations of N2, V2 and L2 (another stop, a market filter, no stop,
   momentum among low-volatility stocks) can only be judged on future data, not on that span. The same holds for H11
   and H12's data.

## 8. Ideas considered but not yet tested (starting points, not conclusions)

- **High-volume return premium** (Gervais, Kaniel & Mingelgrin, *Journal of Finance* 2001): stocks with unusually high
  volume tend to rise afterwards. There is cross-country evidence; it is untested in India. It fits the NSE panel, but
  its short holds make costs bind.
- **Earnings-announcement effects in India** (post-earnings drift, the announcement premium): use NSE's announcement
  timestamps to date results. Check how far back the data goes and whether it is complete. With no point-in-time
  estimates, "surprise" would have to come from prices (e.g. the reaction on the announcement day).
- **Delivery-percentage signals**: India-specific; the evidence is thin, so check it.
- **Index inclusions and exclusions**: NSE announces NIFTY changes weeks ahead. The idea is the drift between
  announcement and effective date. The sample is small.
- **F&O data as signals for cash stocks** (open-interest build-up, futures basis, put-call ratios): the data is free,
  and execution stays long-only cash.
- **Hedged or market-neutral versions of mid-cap momentum**: these need shorting through stock or NIFTY futures, which
  is an F&O permission decision for me. They could only be judged on data N2 hasn't used, or on future data.
- **Retired or not recommended**: RSI(2)-style pullbacks (retired), short-term reversal (costs, and close to the retired
  family), sector or country ETF momentum, single-index time-series momentum, NIFTYBEES intraday, overnight drift.

## 9. Where things stand (15 October 2026, about 00:05 IST)

- NO TRADE everywhere. The paper engine records each session; its 60-session unattended record began on 12 October 2026.
- **Forward test 1**: H11 and H12, rules unchanged, judged only on sessions from 14 October 2026. January looks begin in
  2028.
- **Forward test 2**: N2, rules unchanged, pinned on 14 October 2026 at 23:27 IST. It runs daily at 19:30 on NSE's new
  files. First picks come at the 30 October 2026 close; January looks run from 2028 to 2036. Realistically it can't
  confirm an edge before about 2030; a forward loss can retire it sooner.
- **Round 9** (L1, L2, V2): pinned on 14 October 2026 at 23:33 IST; decision run at 23:52 IST; all three REJECTED.
- **Code**: GitHub CodingMava/My-Trading-Agent. main holds rounds 1-7; branch round8-research holds round 8. Round 9,
  forward test 2 and a news-collector fix are on a local branch (forward-test-2), not yet committed.

## 10. What I want from you

Think first, then answer in this order:

1. **Diagnosis** (one paragraph): which structural properties a strategy needs to pass all 13 criteria at once, given
   the random baseline and the risk engine.
2. **3-5 candidate hypotheses**, ranked by your estimate of their chance of passing everything. For each:
   - the economic reason it should work, and who is on the other side;
   - the published evidence (authors, year, journal; say when you're unsure), and any India-specific evidence;
   - exact, mechanical rules: universe, a signal computable at decision time from data known then, entry time and
     price, exit, a stop of at most 15%, holding period, number of positions and sizing;
   - the data: a free source, its span, and its survivorship and point-in-time problems;
   - expected trade count, win rate, average win and loss, net per trade after the costs above, edge over the random
     baseline, drawdown in R and share of profitable years;
   - your estimate of the chance of passing each of the 13 criteria;
   - a power calculation for the bar 0.05 / (28 + k);
   - how it could fail, and what would retire it early.
3. **Which one to pre-register first**, and a draft pre-registration in the project's style: a hypotheses table,
   definitions, multiple testing, the criteria unchanged, two stages, expectations stated before the test, and
   sensitivity checks that are reported but never used to choose.
4. **What you're unsure of**, and what to verify before pinning.
5. **If you think no plausible strategy passes these rules**, say so plainly. Then say what would change that: more
   forward data, different data, or a policy decision that is mine to make (explained, not assumed).

Avoid:

- Fitting to the numbers above. Say when an idea was suggested by results already seen, and treat it as weaker
  evidence.
- Many variants of one idea: each one counts toward N.
- Anything that needs live trading, purchases, shorting or F&O, unless you flag it as my decision.
- Anything that changes the criteria.

## 11. If you are running inside the repository (Claude Code)

- **Where things are.** The project is at C:\Users\11231\OneDrive\Desktop\my_ai_agent; use venv\Scripts\python.exe.
- **Tests.** Fast: `pytest`. Slow: `pytest -m slow`. A 100% branch-coverage gate covers the risk engine, portfolio and
  order path (`coverage run -m pytest`, then `coverage report`). Never disable tests to make code pass.
- **Research code** is in trader/research/:
  - round8.py: universe, tiers, trade, costs, random baseline, criteria;
  - nse_bhavcopy.py: NSE data and adjustments;
  - round9.py: an example of a round that reuses round 8;
  - forward2.py: the forward-test runner.
- **Project records.** Pre-registrations and results: docs/research/. Evidence: docs/research/evidence/. Registry:
  config/strategies.toml. Thresholds: config/gate.toml.
- **Pinned files.** Write them as bytes with LF line endings (this is Windows). The hash is datasets.text_sha256, which
  reads CRLF as LF.
- **IST times.** Get them from Python zoneinfo; Git Bash's TZ prints UTC.
- **Git.**
  - Commit, push or merge only with my explicit approval, and scan for secrets before any commit.
  - Never commit .env values.
  - Leave the branches paper-split-adjustment and claude/gifted-mccarthy-6ef268 alone.
  - Don't send my email address to outside services.
- **Never change** trader/risk, the kill switch, the live locks ([live] enabled = false, capital 0), frozen forward-test
  rules or recorded results.
- **Round 9 is finished and recorded.** It is in docs/research/round9-results.md, the evidence files and the registry
  (L1, L2, V2 REJECTED), and the README. Its slow regression test, tests/research/test_round9_regression.py,
  recomputes the decision run and matches it exactly.
- **Two stage-1 notes**, both explained and neither affecting 2013-2026:
  - V2's two 4-pick months: the top stock couldn't be bought (round 8's rule).
  - MORGANSTAN, a closed-end fund without an ISIN, was counted as a company by round 8's data audit (2006-2008 only).
- **Committing the forward-test-2 branch** needs my approval.
- **The news task is fixed and verified.** Its first automatic run was at 00:00 on 15 October (result 0x0, 11 new
  announcements, 14 October re-fetched whole from the API). A start missed while the laptop sleeps now runs on waking,
  and missed days are fetched whole. Moving the collector to an always-on host is still my decision: GitHub Actions
  cron or a small VM. NSE may block cloud IP addresses.
