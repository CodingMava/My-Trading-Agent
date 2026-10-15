# Research round 9 pre-registration: low volatility and volatility-adjusted momentum on the NSE universe

> **Pinned on 14 Oct 2026 at 23:33 IST, before any code computed these rules on real data.** Round 8's results on
> the same data were seen first; they are stated below, with what they suggested. This file's SHA-256 (LF line endings)
> is recorded in `trader/research/round9.py`, which refuses to run if the file changes.

## Why this round

You asked on 14 Oct 2026 for research to continue, in parallel with forward test 2, until a strategy passes every
criterion, without weaker standards. Round 8 built the project's first survivorship-free history of NSE stocks
(2005-2026). Two documented effects that it can test, and that no earlier round has tested, are below. Both are judged
exactly as round 8 was: same universe, tiers, trade, stop, costs, random baseline, criteria and two-stage protocol.

### What round 8 showed, and what it suggests (stated so it can be discounted)

- 12-1 momentum among liquidity ranks 101-300 (N2) beat random picks from its tier (p 0.0019) but failed on its win rate
  (43.9%), the share of profitable years (64%) and drawdown (34.1R). Among the 100 most liquid stocks (N1) it had no edge.
- Its 10% stop was hit often: momentum stocks are volatile, and many stopped trades later recovered. Without the stop
  (an informational variant) the picks won 51-54% of their trades.
- That observation is one reason to test the two hypotheses below, so their p-values are not as clean as round 8's.
  The cross-round correction (criterion 12) counts them, and each is backed by evidence published before this data was
  examined.

## The hypotheses

| Id | Tier (liquidity ranks) | Pick each month | Evidence |
|---|---|---|---|
| L1 | 1-100 | The 5 lowest volatilities | Ang, Hodrick, Xing & Zhang (*J. Finance* 2006): high-volatility stocks earn low returns; Blitz & van Vliet (*J. Portfolio Management* 2007); Blitz, Pang & van Vliet (*Emerging Markets Review* 2013): low volatility beat high volatility in 30 emerging markets, 1988-2010; Frazzini & Pedersen (*JFE* 2014), betting against beta. India's own evidence is mixed (significant before, not after, controlling for beta). |
| L2 | 101-300 | The 5 lowest volatilities | As L1 |
| V2 | 101-300 | The 5 highest volatility-adjusted momentum scores | NSE's Nifty200 Momentum 30 (launched 2020) ranks by 6- and 12-month returns each divided by volatility; Barroso & Santa-Clara (*JFE* 2015) and Daniel & Moskowitz (*JFE* 2016): momentum's crashes come in high-volatility states, and scaling by volatility helps; Da, Gurun & Warachka (*RFS* 2014): momentum built from many small moves lasts longer than momentum from a few jumps |

V1 (volatility-adjusted momentum among the 100 most liquid) is not tested: raw momentum had no edge there in round 8,
and each extra hypothesis raises the bar for all of them.

## Definitions (everything else exactly as in round 8)

- **Eligibility, tiers, sessions, signal dates, the trade, the stop (10%), exits, costs, R and the random baseline:** as
  in [round8-preregistration.md](round8-preregistration.md). L1 uses round 8's N1 tier and costs (0.3532% a round trip);
  L2 and V2 use N2's (0.4532%). Eligibility still requires a 12-1 momentum score, so all three choose from exactly the
  stocks round 8 chose from.
- **Volatility at signal date s:** the standard deviation of the last 252 daily log returns of the adjusted close (row to
  row, the security's own trading days, ending at s), times √252; undefined with fewer than 200 such returns, and then
  the stock is not a candidate for L1, L2 or V2 that month.
- **L1, L2:** the 5 eligible tier members with the lowest volatility (ties by symbol).
- **V2:** for each eligible member of the 101-300 tier with a volatility, m12 = its 12-1 month return (as round 8) /
  volatility and m6 = its 6-1 month return (adjusted close 21 sessions back / 126 sessions back - 1) / volatility. Each of
  m12 and m6 is turned into a z-score across that month's tier members (minus the mean, divided by the standard
  deviation, ddof 1); the score is (z12 + z6) / 2; the picks are the 5 highest (ties by symbol). Unlike NSE's index, the
  latest month is skipped (as in round 8), no score is winsorised, and there are 5 picks, not 30.

## Multiple testing

- Within the round (criterion 5): the three raw p-values are Holm-corrected together.
- Across the project (criterion 12): each raw p must be below 0.05 / 28 = 0.00179. The 28 hypotheses tested on historical
  data are H1-H14, C1-C6, I1-I3, N1-N2 and L1, L2, V2.

## Pass criteria and decisions

Round 8's criteria 1-13, unchanged (criterion 12 at 0.05 / 28), each hypothesis judged on its own:

| Outcome | Decision |
|---|---|
| Every criterion passes | Candidate for PAPER, once you approve: the gate's paper account, a monthly NSE feed for the universe (forward test 2 built one), and the Level 5 paper stage. Live trading stays locked. |
| Only criterion 1 fails | Inconclusive (RESEARCH) |
| Anything else | REJECTED |

The 50% win-rate floor stays. A hypothesis that passes everything except criterion 2 is REJECTED and labelled INELIGIBLE
UNDER CURRENT POLICY.

## Stated before the test

- **Power.** As in round 8: about 158 decision months of 5 picks. Beating random picks at p below 0.0018 needs an edge of
  roughly 1% a month for a mid-cap tier, about what N2 had.
- **L1 and L2 are likely to fail the baseline.** Low-volatility stocks' advantage is mostly risk-adjusted; the baseline
  compares raw returns, and random picks from the same tier earned well in 2013-2026. They may well pass the win rate,
  stability and drawdown criteria, where momentum failed.
- **V2 is the likeliest to pass the baseline** and less likely than N2 to fail on drawdown, but it overlaps N2: many
  months' picks will be the same stocks.
- Nothing is changed if this happens. The outcome is reported as it is.

## Two stages, in order

As round 8: stage 1 (signals from early 2006 through 31 May 2013) checks the implementation on real data and decides
nothing; then stage 2 (signals 28 Jun 2013 through 31 Aug 2026) runs once and decides. Bugs found after stage 1 may be
fixed, with both outputs kept; no rule, parameter, cost, criterion or span may change.

## Informational (stage 2; no effect on the decisions)

As round 8: benchmarks, portfolio views at the engine's size and fully invested, the kill switch replay, Wilson and
bootstrap intervals, the deflated Sharpe ratio (28 trials), costs at 0x-3x, regimes, years, suspect fills, and the
delisted holdings. Sensitivity, never used to choose: for L1 and L2, 10 picks instead of 5 and no stop; for V2, 12-1
alone or 6-1 alone (each divided by volatility), 10 picks, and no stop.

## Protocol

Pinned before any code computes these rules on real data: this file's SHA-256 goes into `trader/research/round9.py`, which
refuses to run if it changes, and the frozen panel is round 8's (SHA-256 `afb79ad2...`). The runner is tested on
synthetic data first. Results are reported whatever they show.
