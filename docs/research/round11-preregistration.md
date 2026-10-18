# Research round 11 pre-registration: new return sources (value, dividend flows, option-implied information)

> **Pinned on 18 Oct 2026 at 23:45 IST, before the decision span was computed for any rule here.** Everything computed before pinning is
> listed under "What was seen before pinning": ten variants screened only on development years. This file's SHA-256 (LF
> line endings) is recorded in `trader/research/round11.py`, which refuses to run if the file changes.

## Why this round

You asked on 18-19 Oct 2026 for research to become the priority: find genuinely different sources of return for a
portfolio whose parts complement each other, test them under the existing governance, and report the evidence.

The audit of rounds 1-10 (31 hypotheses decided, 28 variants screened): almost everything tested was either long-market
drift that random picks match (low volatility, sector and country rotation, time-series momentum) or a trend-type payoff
(12-1 and volatility-adjusted momentum, results drift) that fails the win-rate and stability rules. The current bunch,
E2 + V2, is two kinds of buying strength; both lost in 2016 and 2018. The obvious gaps were value-type returns (the
classic counterweight to momentum), flow-driven returns, and information from option prices. All three can be built
point-in-time from free NSE data: round 8's corporate-action records (dividends) and NSE's daily F&O files.

## What was seen before pinning (development years only)

Monthly, round 8's universe (eligible stocks of liquidity ranks 1-300) and signal dates, 5 picks, 15% stop, costs at the
engine's Rs 33,333 position (round 10's), total returns (dividends under 5% of the previous close added when held at the
close before the ex-date; larger ones are already in round 8's adjusted prices), every Security cut at 31 May 2013,
"beat random" = net minus the mean of the same universe's enterable members bought at the same open with the same exit,
t clustered by month.

| Variant | Rule | Trades | Net | Win rate | PF | Beat random | t |
|---|---|---:|---:|---:|---:|---:|---:|
| Y1a | Highest trailing-12-month dividend yield, ranks 1-300 | 430 | +0.53% | 48.4% | 1.10 | +0.26% | 0.5 |
| Y1b | Same, ranks 1-100 | 430 | +0.33% | 47.7% | 1.06 | +0.08% | 0.2 |
| Y1c | Same, ranks 101-300 | 430 | +0.21% | 47.4% | 1.04 | -0.06% | -0.1 |
| R1a | Long-term reversal: lowest return from 36 to 12 months ago, ranks 1-300 | 315 | -0.73% | 43.2% | 0.89 | -0.65% | -1.1 |
| R1b | Same, ranks 101-300 | 315 | -0.70% | 43.2% | 0.89 | -0.59% | -1.0 |
| DM1a | Dividend month (Hartzmark and Solomon 2013): expected to go ex-dividend next month (from a year earlier), highest such yield, ranks 1-300 | 405 | -0.01% | 49.1% | 1.00 | -0.11% | -0.2 |
| DM1b | Same, ranks 1-100 | 336 | -0.01% | 48.2% | 1.00 | +0.19% | 0.6 |
| O1 | Option volatility smirk (Xing, Zhang and Zhao 2010): lowest OTM-put IV minus ATM-call IV | 315 | -0.99% | 40.3% | 0.84 | -0.59% | -1.0 |
| **O2** | **Implied minus realized volatility (Bali and Hovakimian 2009): lowest** | **315** | **+0.87%** | **45.7%** | **1.16** | **+1.02%** | **1.3** |
| O3 | Call-put implied volatility spread (Cremers and Weinbaum 2010): highest | 315 | -0.39% | 43.8% | 0.93 | -0.23% | -0.4 |

Y1, R1 and DM1 spans start in 2006 (Y1, DM1) or 2008 (R1); O1-O3 in January 2008 (the first F&O month-end held). O2's
beat-random by year: 2008 +0.53%, 2009 +1.88%, 2010 -0.10%, 2011 -1.27%, 2012 +3.27%, 2013 (5 months) +3.24%.

**What this means.** Dividend yield, long-term reversal and the dividend month showed no edge over random picks; long-term
losers kept losing. Of the option signals only O2 beat random picks, by about 1% a trade (t 1.3, not significant), with a
45.7% win rate. O2 is tested below because it is the only survivor; being the best of ten, its screening numbers are
optimistic. No O2 trade after 31 May 2013 was computed before pinning.

## The hypothesis

| Id | Rule | Decision span (signals) |
|---|---|---|
| O2 | At each month's last session, among round 8's eligible stocks of liquidity ranks 1-300 that have the signal, the 5 with the LOWEST implied-minus-realized volatility; bought at the next open, held to the open after the next month-end, with a 15% stop | 28 Jun 2013 to 31 Aug 2026 |

Evidence: Bali and Hovakimian (*Management Science* 2009, from memory): stocks whose options are cheap relative to their
realized volatility earn higher returns over the next month (US); Goyal and Saretto (*JFE* 2009, from memory) on the
same spread in option returns. The economic story: option prices carry informed traders' views and the variance risk
premium; a stock whose options are cheap for its volatility is one informed traders aren't paying to protect. No Indian
study was checked.

## Definitions

- **Universe, signal dates, eligibility, tiers, exits:** round 8's. A stock is in O2's universe at signal session s if it
  is eligible with liquidity rank 1-300 and has the signal below.
- **Options used:** NSE's daily F&O file for session s, stock options only, the nearest expiry at least 7 calendar days
  after s, and only contracts that traded that day (contracts > 0; an untraded option's close is stale and its
  settlement price is NSE's model). Old-format files' American options (CA, PA, until 2011) are read as calls and puts.
- **Implied volatility:** Black-Scholes, European, from the option's last traded price (close); underlying = the
  stock's cash close on s (round 8's panel, raw price); r = 6.5% a year; no dividends; T = calendar days to expiry / 365;
  solved by bisection on [0.01, 3.0]; undefined if the price isn't above intrinsic value (with the strike discounted) or
  isn't below the underlying (calls) or the strike (puts).
- **ATM strike:** among strikes where both a call and a put traded, the one nearest the close with strike / close in
  [0.97, 1.03]; ATM IV = the mean of that call's and put's IVs (both must be defined).
- **Realized volatility:** the standard deviation (ddof 1) of the last 21 log returns of the adjusted close over the
  stock's last 22 rows within the 41 sessions ending at s, times sqrt(252); undefined with fewer than 22 rows.
- **Signal:** ATM IV - realized volatility. **Picks:** the 5 lowest (ties by symbol). The F&O file's symbol on s is
  matched to round 8's security by the panel's symbol on s.
- **Trade:** round 8's entry rule ("not bought": no row, a zero open, or locked at the upper band all day: the slot stays
  in cash for the month), 15% stop watched from the entry session, exit at the open after the next month-end; total
  return = adjusted price return + dividends under 5% of the previous close whose ex-date falls after the entry session
  and on or before the exit session, each in the security's adjusted terms on its ex-date, divided by the adjusted
  entry price.
- **Costs:** round 8's Zerodha delivery model at Rs 33,333 (0.5% of equity at risk with a 15% stop): 0.3685% a round trip
  for ranks 1-100, 0.4685% for ranks 101-300, plus the tier's slippage again on a stop's exit. **R** = 15%.

## The random baseline

For each signal month, the pool is every member of O2's universe that month that could be bought at the entry open,
traded by the same rules and costs. 20,000 draws from numpy's `default_rng(11)`; in each, for a month with k trades, k
distinct pool members; p = (k + 1) / (20,000 + 1) for the share of draws whose mean net return is at least O2's.

## Multiple testing

- **Within the round (criterion 5):** one hypothesis; Holm leaves its p unchanged.
- **Across the project (criterion 12):** raw p below 0.05 / 67 = 0.000746. The 67 are the 57 counted after round 10
  (31 hypotheses decided, 28 variants screened for round 10 minus none double-counted, and M) plus the ten variants
  screened for this round (Y1a-c, R1a-b, DM1a-b, O1-O3; O2 is one of them).

## Two stages, in order

1. **Stage 1 (development; already seen in the screen):** signals from 31 Jan 2008 to 31 May 2013; writes
   `docs/research/round11-stage1.md`. Only bugs may be fixed afterwards, with both outputs kept.
2. **Stage 2 (the decision, run once):** signals 28 Jun 2013 to 31 Aug 2026 (the last exit is at the open of 1 Oct 2026);
   writes `docs/research/round11-results.md` and O2's evidence.

## Pass criteria and decisions

Round 8's criteria 1-13, unchanged, on stage 2's trades (criterion 12 at 0.05 / 67; R = 15%; clusters = signal months).
Every criterion passes: candidate for PAPER with your approval (forward evidence and Levels 5-6 before any real money).
Only criterion 1 fails: inconclusive. Anything else: REJECTED. The 50% win-rate floor stays.

## Stated before the test

- **Likely failures:** criterion 2 (O2 won 45.7% in screening) and criterion 12 (a 1% monthly edge with this spread needs
  about 300+ months for p below 0.00075; the span has 158). My estimate of passing everything: about 3%.
- **What would still be useful:** whether O2 beats random picks at all on 2013-2026 (criterion 5's p alone), and how its
  yearly results move against E2's and V2's. Both are reported; neither changes the decision.

## Informational (stage 2; no effect on the decision)

Net at 0x-3x costs; stops; years; tiers; price-only versus total return; the yearly R of O2 next to E2 x3 and V2 x2
(round 10's and round 9's rules, from the bunch backtest) and their correlation; bunches with O2 added (backtest on seen
data for the other parts: not evidence).

## Data

- NSE F&O month-end files 2008-2026 (and 59 early-2008 daily files fetched before the month-end-only download),
  stored outside OneDrive in `C:/Users/11231/nse_raw/fo` (environment variable NSE_RAW), manifest `fo_manifest.json`
  SHA-256 `d99ffe9ced87abf1d504fa83b6dd8e61cd42a475b690c01713d0f6e996bd2d90` (282 files); extracted by
  `python -m trader.research.nse_fo compact` into `fo_compact/` (19 yearly files; `compact_manifest.json` SHA-256
  `aa94ce3b6452a7dacccc6a20804f9a5d6d5c09e214a38072fe9c4e80b4bc7fdc`).
- Round 8's frozen panel (SHA-256 `afb79ad2...`) and corporate-action records (dividends).

## Protocol

Pinned before the runner computes the decision span: this file's SHA-256 and the two manifests' are recorded in
`trader/research/round11.py`, which is tested on synthetic data first, runs stage 1, then stage 2 once (refusing a second
run or changed inputs). Results are reported and recorded whatever they show.
