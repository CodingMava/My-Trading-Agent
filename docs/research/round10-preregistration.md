# Research round 10 pre-registration: results drift, promoter buying, and the two combined

> **Pinned on 17 Oct 2026 at 17:45 IST, before the decision span was computed for any of these rules.** What was computed before
> pinning is listed in full under "What was seen before pinning": 28 rule variants, screened only on development years
> that the decision tests below never use. This file's SHA-256 (LF line endings) is recorded in
> `trader/research/round10.py`, which refuses to run if the file changes.

## Why this round

- **28 hypotheses failed** on historical data (H1-H14, C1-C6, I1-I3, N1-N2, L1, L2, V2), so the system is in NO TRADE.
  You asked on 17 Oct 2026 for the search to continue, and suggested a mix of 3-5 strategies whose losses offset each
  other.
- **What a mix can and can't do.** A mix's win rate, profit per trade and profit factor are averages of its parts, so
  a part without an edge only dilutes it. What a mix can improve is stability: losing years of one part can be offset by
  another, which helps the year criterion (9), the halves (8) and drawdown (13). Each part still needs its own edge, and
  parts already tested on 2013-2026 (N2, V2, L2, H11, H12) can't be combined on that span: their results there are known.
- **New data, never used by any round.** (1) NSE's board-meeting records, with the time each notice was filed (2009-2026).
  (2) NSE's insider-trading disclosures under SEBI's 2015 insider-trading rules, with the time each was published (from
  November 2015).
- **Method.** Candidate rules were screened only on early years the decision tests don't use (2009 to May 2013 for
  board-meeting rules; November 2015 to December 2017 for insider rules). Two survived, E2 and Q. This round tests each
  one and the mix of the two (M) on later years, once. Every screened variant counts in the multiple-testing record.

## The hypotheses

| Id | Rule | Decision span (entries) | Evidence |
|---|---|---|---|
| E2 | Drift after a strong results reaction: among the 300 most liquid stocks, a stock whose price reaction to its results (two sessions, relative to the universe) is in the top 10% of the past year's reactions is bought two sessions after the meeting and held 40 sessions, with a 15% stop; at most 5 positions, strongest reactions first | 3 Jun 2013 to 31 Jul 2026 | Post-announcement drift: Bernard and Thomas (*Journal of Accounting Research* 1989, from memory); drift measured by the price reaction itself: Brandt, Kishore, Santa-Clara and Venkatachalam (working paper 2008, from memory). Against: Martineau (*Critical Finance Review* 2022) finds US drift gone in large stocks; Indian studies disagree. Screening: S17 below |
| Q | Promoter buying: a promoter or promoter-group open-market purchase of Rs 10 lakh or more, disclosed on NSE, in one of the 300 most liquid stocks; bought at the next open after publication and held 40 sessions, with a 15% stop; at most 5 positions | 1 Jan 2018 to 31 Mar 2026 | Insider purchases predict returns: Lakonishok and Lee (*Review of Financial Studies* 2001), Jeng, Metrick and Zeckhauser (*Review of Economics and Statistics* 2003), Cohen, Malloy and Pomorski (*Journal of Finance* 2012), all from memory and US-based. No Indian study was checked. Screening: Q4 below |
| M | The mix: E2 and Q in one account sharing the 5 positions; each evening E2's candidates come first (strongest first), then Q's | 1 Jan 2018 to 31 Mar 2026 | Your suggestion. E2 trades in and after results seasons; Q trades all year, and promoters bought most when prices were falling (2018-2020) |

## What was seen before pinning (development years only)

Every rule screened, in the order run, with every result. "Beat random" is the trade's net return minus the mean net
return of all same-tier universe stocks bought at the same open with the same exit; t is clustered by entry month.
Screens 1, 2 and 4 used round 8's costs at Rs 50,000 (slightly lower than this round's, below); all trades start and end
inside the development span.

**Screen 1: board-meeting rules, 2 Jan 2009 to 31 May 2013, every event, 10% stop.**

| Variant | Rule | Trades | Net | Win rate | PF | Beat random | t |
|---|---|---:|---:|---:|---:|---:|---:|
| S1 | Buy 3 sessions before the results meeting, sell 2 sessions after | 5,379 | -1.02% | 41.5% | 0.69 | +0.04% | 0.4 |
| S2 | Buy 3 sessions before, sell at the meeting session's open | 5,424 | -0.46% | 44.8% | 0.79 | +0.40% | 4.1 |
| S3 | Buy the open after the notice, sell at the meeting session's open | 5,468 | -0.62% | 43.3% | 0.81 | +0.44% | 4.5 |
| S4 | Top 10% results reaction, hold 20 sessions | 442 | -0.38% | 46.6% | 0.92 | +0.88% | 1.9 |
| S5 | Top 10% reaction, hold 40 | 430 | +1.69% | 45.1% | 1.31 | +1.69% | 3.0 |
| S6 | Top 20% reaction, hold 20 | 966 | -0.48% | 44.1% | 0.90 | +0.50% | 1.0 |
| S7 | Bonus or split meeting: buy after the notice, sell 2 sessions after the meeting | 38 | -1.77% | 39.5% | 0.51 | -0.38% | -0.4 |
| S8 | Bonus or split: buy after the notice, hold 20 | 38 | -1.23% | 42.1% | 0.76 | +0.36% | 0.2 |
| S9 | Buyback meeting: buy after the notice, sell 2 sessions after | 26 | +0.07% | 46.2% | 1.02 | +0.39% | 0.2 |

The results-meeting event study (mean abnormal close-to-close return by session) showed the rise before results
(+0.62% over sessions m-5 to m-1), nothing on results day (m, m+1), and a drift after strong reactions.

**Screen 2: the top-reaction rule's payoff, same span; 15% stop unless stated.**

| Variant | Rule | Trades | Net | Win rate | PF | Beat random | t |
|---|---|---:|---:|---:|---:|---:|---:|
| S10 | Top 10%, hold 20 | 442 | +0.71% | 54.1% | 1.15 | +1.74% | 3.5 |
| S11 | Top 10%, hold 40 | 430 | +3.37% | 57.2% | 1.61 | +2.66% | 3.8 |
| S12 | Top 10%, hold 60, 10% stop | 419 | +1.79% | 40.3% | 1.30 | +1.81% | 2.9 |
| S13 | Top 10%, hold 60 | 419 | +3.32% | 52.7% | 1.54 | +2.67% | 3.1 |
| S14 | Top 5%, hold 40 | 209 | +4.34% | 60.3% | 1.80 | +3.82% | 4.5 |
| S15 | Top 5%, hold 60 | 207 | +4.66% | 53.6% | 1.75 | +4.11% | 3.4 |
| S16 | Top 10%, hold 40, no stop (diagnostic; the engine requires a stop) | 430 | +4.11% | 60.5% | 1.82 | +2.69% | 3.9 |
| S11c | S11 with the 5-position cap, pseudo-random order | 98 | +4.52% | 62.2% | 1.97 | +4.67% | 3.8 |
| S13c | S13 with the 5-position cap | 91 | +5.69% | 53.8% | 2.02 | +4.82% | 2.9 |
| S17 | S11 with the 5-position cap, strongest reactions first (**= E2**) | 98 | +3.88% | 59.2% | 1.75 | +3.98% | 2.9 |

S11's edge over random was positive in every year: 2009 +3.98%, 2010 +0.51%, 2011 +2.10%, 2012 +4.57%, 2013 +0.86%;
+2.11% without its 5 best trades. Its net return by year: +17.9%, -0.8%, -3.6%, +8.3%, -9.1% (2010-2013 were weak years
for Indian mid caps).

**Screen 3: promoter purchases, 19 Nov 2015 to 31 Dec 2017, 15% stop, hold as stated.**

| Variant | Rule | Trades | Net | Win rate | PF | Beat random | t |
|---|---|---:|---:|---:|---:|---:|---:|
| Q1 | Rs 10 lakh or more, hold 40, every event | 186 | +4.81% | 58.6% | 2.32 | +1.59% | 1.4 |
| Q2 | Rs 10 lakh or more, hold 20 | 241 | +3.00% | 62.7% | 2.32 | +1.14% | 1.7 |
| Q3 | Rs 1 crore or more, hold 40 | 141 | +4.72% | 61.0% | 2.38 | +1.68% | 1.6 |
| Q4 | Q1 with the 5-position cap (**= Q**) | 65 | +4.58% | 67.7% | 2.26 | +2.92% | 1.9 |

Random picks earned +3.2% a trade in the same windows (a strong market), so most of the net return was the market's.

**Screen 4: two more independent ideas, 2009 to May 2013.**

| Variant | Rule | Trades | Net | Win rate | PF | Beat random | t |
|---|---|---:|---:|---:|---:|---:|---:|
| V1 | High-volume premium: a 50-session high in traded value, not within 5 sessions after a results meeting; hold 20, 15% stop | 3,817 | +1.15% | 46.8% | 1.22 | **-0.69%** | -3.0 |
| V2c | V1 with the 5-position cap | 318 | -0.04% | 43.7% | 0.99 | -0.42% | -0.7 |
| H1s | Same-month seasonality: top 5 by the past 5 years' returns in the coming calendar month; monthly, 15% stop | 250 | +2.27% | 50.0% | 1.44 | +1.23% | 1.0 |

**Screen 5: promoter pledge releases, November 2015 to December 2017, hold 40, 15% stop.**

| Variant | Rule | Trades | Net | Win rate | PF | Beat random | t |
|---|---|---:|---:|---:|---:|---:|---:|
| PR1 | A promoter's pledge revocation, every event | 182 | +2.26% | 54.4% | 1.46 | **-1.40%** | -1.3 |
| PR2 | PR1 with the 5-position cap | 70 | +0.63% | 51.4% | 1.12 | -1.80% | -1.2 |

**What this means for the tests below.**

- E2 and Q were chosen because they were best among what was screened. Their screening numbers are therefore
  optimistic (the winner's curse), and they come from short, partly unrepresentative spans. The decision tests use
  only later years.
- No E2 trade after 31 May 2013 and no Q trade after 31 Dec 2017 was computed before pinning.

## Data

- **Board-meeting records** (git-ignored, unchanged): `data/round10/board_meetings/`, from
  `nseindia.com/api/corporate-board-meetings`, downloaded 16 Oct 2026, one JSON file per half-month of meeting dates,
  1 Jan 2009 to 15 Oct 2026: 427 files, 183,875 records. Manifest `data/round10/board_meetings_manifest.json`, SHA-256
  `1e7accb269c143491bfa80831f3e404e08cb0dc5e9091c3e7921c98e26c5b30c`.
- **Insider-trading disclosures** (git-ignored, unchanged): `data/round10/pit/`, from `nseindia.com/api/corporates-pit`,
  downloaded 16-17 Oct 2026, one gzipped JSON file per half-month, 283 files, 341,514 records published 19 Nov 2015 to
  2 May 2026. Manifest `data/round10/pit_manifest.json`, SHA-256
  `4955502b6ef2b0a3026cb0df5bd6d2f07d4c711c2d6850fdfd18def64ec87b42`.
- **Prices:** round 8's frozen panel (`data/round8/nse_eq/panel.parquet`, SHA-256 `afb79ad2...`) with its adjustments,
  eligibility and liquidity ranks.

### Data audit (counts only)

- **Board meetings** (audited 16 Oct 2026): 122,510 results meetings; 17,651 with repeated
  notices for the same date (a meeting is known from its first notice); 855 (0.7%) rescheduled before their date; about a
  fifth of notices filed after 18:00 IST; 9% of meetings on a Saturday; 94-98% match a panel security; about 1,190 a
  year among the 300 most liquid stocks. NSE files the records by meeting date and under the company's current symbol.
- **Insider disclosures:** 30,559 promoter or promoter-group open-market purchases, 2016-2026 (229 in late 2015; 2,055
  to 4,710 a year). The publication time (`date`, to the minute) is never earlier than the company's own filing date
  (`intimDt`; median one day later), and the purchase itself was a median of 3 days earlier. **NSE's API returns no
  disclosures published after 2 May 2026** (thin in April 2026), probably because disclosures moved to another system;
  Q's decision span therefore ends on 31 Mar 2026, and Q can't be paper-traded until a current source is found.
- **What the data can't do:** the results' release time isn't recorded (only the meeting date), so E2's reaction spans
  the close before the meeting session to the close after it; no earnings numbers or forecasts (the reaction is the
  "surprise"); timestamps are as NSE stores them today. Everything else as round 8 (price returns, fills at the
  official open, no order book, corporate actions neutral inside a trade, delisted stocks exit at their last close).

## Definitions

- **Sessions, adjusted prices, eligibility, liquidity and tiers:** as round 8. **The universe at session d:** the 300
  stocks of round 8's tiers N1 (ranks 1-100) and N2 (ranks 101-300) at the latest month-end on or before d; a stock's tier
  is its tier there.
- **Known by session d:** filed or published on an earlier calendar date than d's, or on d's date at or before 18:00 IST.
- **Results notice:** a board-meeting record whose purpose matches `result|(un-?)?audited accounts|annual accounts`
  (case-insensitive), for a panel security whose `sid` equals `bm_symbol`.
- **A company's latest results notice by session d:** among its results notices known by d, the last by filing time
  (ties: the later meeting date).
- **Meeting session m:** the first session on or after the meeting date.

## E2: drift after a strong results reaction

| When | What happens | Uses only |
|---|---|---|
| Session m+1, after the close | The meeting was held as scheduled: the company's latest results notice known by m+1 names this meeting date. The company is in the universe at m+1 and has rows on m-1 and m+1. | Notices known by m+1; round 8's ranks |
| | **Reaction** = adjusted close at m+1 / adjusted close at m-1 - 1. **Abnormal reaction** = the reaction minus the mean reaction over the same sessions of every universe member at m+1 with rows on both. | Closes on m-1 and m+1 |
| | **Signal** if the abnormal reaction is at least the 90th percentile (numpy's default, linear) of the abnormal reactions of all such events whose session m+1 lies in the 250 sessions before this one (strictly before); with fewer than 300 such events, no signal. | Earlier events only |
| Session m+2 (= e), open | Buy at the official open, if a position is free (below) and round 8's "not bought" rule allows | The open |
| e to e+39 | The 15% stop is watched every session, from the entry session on | Each session's open and low |
| e+40, open | Exit at the official open, if not stopped | The open |

The same company and meeting can give only one signal; a stock already held is not a candidate.

## Q: promoter buying

| When | What happens | Uses only |
|---|---|---|
| Session d, after the close | A disclosure known by d (its `date`) with `personCategory` Promoters or Promoter Group, `acqMode` Market Purchase, `tdpTransactionType` Buy, an equity security (`secType` contains "equity", any case) and `secVal` of at least Rs 10,00,000; the company (`symbol` equal to a panel `sid`) is in the universe at d | Disclosures known by d; round 8's ranks |
| Session d+1 (= e), open | Buy at the official open, if a position is free and round 8's "not bought" rule allows | The open |
| e to e+39 | The 15% stop is watched every session | Each session's open and low |
| e+40, open | Exit at the official open, if not stopped | The open |

Several disclosures for the same company known by the same session are one candidate.

## M: the mix

E2's and Q's candidates, as defined above, in one account with one set of 5 positions. On each entry session E2's
candidates are taken first (strongest abnormal reaction first, ties by symbol), then Q's (in the order below). One
position per stock across both. Every trade keeps its own rule's exit, stop and costs.

## Positions, order, exits, costs and risk limits

- **At most 5 open positions** in each hypothesis's account (the risk engine's limit). A position exiting at an open
  frees its place for an entry at that same open (both orders are placed the evening before). A stopped position frees
  its place from the next session's open. A stock that never trades again frees it the session after its last row.
- **Candidates beyond the free places are dropped, not queued.** Order: E2 by abnormal reaction, highest first (ties by
  symbol); Q by the SHA-256 of `"<sid>|<entry date, YYYY-MM-DD>"`, lowest first (a fixed pseudo-random order, so the
  choice carries no information).
- **Exits:** round 8's (`round8.simulate(sec, e, e + 40, 0.15)`): a session whose low reaches the stop exits at the stop,
  or at the open if the open was already below it; a suspended stock exits at the open of its next session with a row;
  a stock that never trades again exits at its last close.
- **Size:** the risk engine's: 0.5% of equity at risk with a 15% stop is a position of 3.33% of equity, Rs 33,333 on the
  Rs 10,00,000 account; five positions are 16.7% of equity, each within 1% of its stock's daily traded value.
- **Costs** (round 8's Zerodha delivery model at Rs 33,333, NSE transaction charge 0.00307%): 0.3685% a round trip for N1
  (slippage 0.05% a side), 0.4685% for N2 (0.10% a side), and the tier's slippage once more on a stop's exit.
- **R:** 15% of the entry price. Gross return = exit / entry - 1 in adjusted prices; net = gross - costs.

## The random baseline, precisely

- **The question:** do the stocks a rule buys beat stocks bought at random from the same tier of the same universe, at
  the same open, held the same way?
- **The pools:** for every trade, every member of its tier at its universe month-end that could be bought at its entry
  open, traded with the same exit rule (40 sessions, 15% stop) and costs.
- **The draws:** 20,000 draws from numpy's `default_rng(10)`. For each (universe month-end, tier, entry session) with k
  trades, each draw takes k distinct members of that pool. A draw's statistic is the mean net return of all its trades.
- **The p-value:** p = (k + 1) / (20,000 + 1), k being the number of draws whose statistic is at least the hypothesis's
  own mean net return.

## Multiple testing

- **Within the round (criterion 5):** E2, Q and M's raw p-values are Holm-corrected together.
- **Across the project (criterion 12):** each raw p must be below 0.05 / 57 = 0.000877. The 57 are the 28 hypotheses
  tested before (H1-H14, C1-C6, I1-I3, N1-N2, L1, L2, V2), the 28 variants screened for this round (S1-S17, S11c, S13c,
  Q1-Q4, V1, V2c, H1s, PR1, PR2; E2 is S17 and Q is Q4), and M.

## Two stages, in order

1. **Stage 1 (development; decides nothing):** E2 with entries from 2 Jan 2009 to 28 Mar 2013; Q from 19 Nov 2015 to
   31 Oct 2017. M has no stage 1: its parts are checked through E2's and Q's. It writes
   `docs/research/round10-stage1.md`. After it, only bugs may be fixed, with both outputs kept; no rule, parameter,
   cost, criterion or span may change.
2. **Stage 2 (the decision, run once):** E2 with entries from 3 Jun 2013 to 31 Jul 2026 (the last exit is in late
   September 2026, before the panel ends on 13 Oct 2026); Q and M from 1 Jan 2018 to 31 Mar 2026. Each account starts
   empty. It writes `docs/research/round10-results.md` and the evidence for E2, Q and M.

## Pass criteria (stage 2, each hypothesis on its own; every criterion must pass)

Round 8's criteria 1-13, unchanged. Where round 8 says "signal month" or "signal date", read the entry session's
calendar month or date: halves (criterion 8, split at the midpoint date of the span), years (criterion 9) and clusters
(criterion 11, trades clustered by entry month) all use it. Criterion 12's bar is 0.05 / 57. Criterion 13 is the
drawdown of cumulative R (R = 15%), trades netted by exit date, in exit order, no deeper than 20R.

The 50% win-rate floor stays. A hypothesis that passes every criterion except 2 is REJECTED and labelled INELIGIBLE
UNDER CURRENT POLICY.

## Decisions

| Outcome | Decision |
|---|---|
| Every criterion passes | Candidate for PAPER, once you approve. Before paper trading: a daily board-meeting feed (E2, M) and a current insider-disclosure source (Q, M; NSE's API stopped in May 2026), the rule in `trader/strategies`, and the Level 5 paper stage. Live trading stays locked. |
| Only criterion 1 fails | Inconclusive (RESEARCH) |
| Anything else | REJECTED |

## Stated before the test

- **Power.** With 5 positions held 40 sessions, E2 makes about 20-25 trades a year (results seasons fill the places),
  about 280 over 2013-2026. With a trade-level standard deviation of the edge over random of about 13% (screening), the
  bar of 0.000877 (about 3.1 standard errors) needs an edge of about 2.4% a trade. Screening showed +4.0% on 98 trades;
  after the winner's curse, 1.5-3% is more realistic.
- **Q** has about 8 years and perhaps 200-250 trades; its screening edge (+2.9%, t 1.9 on 65 trades) would need to hold
  in full to pass.
- **M** spans 2018-2026: mostly E2's trades, with Q filling places between results seasons. It may pass the year and
  drawdown criteria more easily than either part, and the significance criteria less easily than E2 over its longer span.
- **Likeliest failures:** criterion 12 (the bar), 9 (70% of years profitable: mid caps had weak years in 2018, 2019 and
  2025), 11 (month-clustered t of net returns) and, for Q, everything that depends on the edge holding.
- **My estimate of passing all 13:** about 20% for E2, 7% for Q, 12% for M; about 25-30% that at least one passes.
  Nothing will be changed if they fail.

## Informational (stage 2; no effect on the decisions)

- Each rule with every qualifying event (no position cap), against its own baseline.
- M's trades split by part; E2's and Q's yearly net returns side by side in 2018-2026 (do their losing years differ?).
- Net per trade at 0x, 1x, 1.5x, 2x and 3x costs; stops and gapped stops; years; tiers; the 10 largest trades.

Patterns in these reports are hypotheses for future data, not findings.

## Protocol

1. This file is pinned: its SHA-256, both manifests' and the panel's are recorded in `trader/research/round10.py` with
   the time. (Committing and pushing the pin gives it a public timestamp; that needs your approval.)
2. The runner is written and tested on synthetic data only.
3. Stage 1 runs. Then stage 2 runs once. The runner refuses stage 2 if this file, a manifest or the panel changed, or if
   stage 2's results already exist.
4. Results are reported whatever they show, and recorded (registry, evidence, README) pass or fail.
