# Research programme report, 19 Oct 2026: what has been tested, why it failed, what to test next

**Bottom line.** No strategy and no combination qualifies. 32 hypotheses have been decided on historical data under
pre-registration and 38 more variants screened on development years; none passed all 13 criteria. The closest single
strategy is E2 (results drift, 11 of 13). The best combination found is E2 x3 + V2 x2, which is already being judged on
future data (paper trial 1, forward test 4). This round's new families (value, dividend flows, option prices) added no
edge. The next experiments that can change this are listed in section 5, ranked.

## 1. What has been tested, ranked by how close it came

| Rank | Strategy (round) | Data, span | Result | Why it failed | Where it stands |
|---:|---|---|---|---|---|
| 1 | **E2**: drift after a strong results reaction (10) | NSE stocks, board-meeting dates, 2013-2026 | 313 trades, 55.0% winners, +2.33% vs +0.83% random, PF 1.47, 71% of years, DD 17.3R | Edge over random not significant (p 0.030; bar 0.00088) | Forward test 3 |
| 2 | **V2**: volatility-adjusted mid-cap momentum (9) | NSE stocks 101-300, 2013-2026 | +2.07% vs +0.67% random (p 0.0002), PF 1.41 | 45.9% winners, 64% of years, DD 30.4R | Paper trial 1 (with E2) |
| 3 | **N2**: mid-cap 12-1 momentum (8) | Same | +1.75% vs +0.67% (p 0.0019) | 43.9% winners, 64% of years, DD 34.1R | Forward test 2 |
| 4 | **H11**: turn of the month, sector indices (5) | NSE indices as ETFs, 2008-2026 | 57.9% winners, +0.475%, t 4.8, Holm p < 0.001 | One third of the span flat; lost 2024-26 | Forward test 1 |
| 5 | **L2**: low volatility, ranks 101-300 (9) | NSE stocks, 2013-2026 | 52.7% winners, PF 1.31, 71% of years, DD 12.9R | Zero edge over random (p 0.50) | Rejected |
| 6 | **O2**: options cheap vs realized volatility (11) | NSE F&O, 2013-2026 | 49.6% winners, +0.72% vs +0.81% random, 71% of years, DD 16.7R | No edge (p 0.61); its 2008-13 edge was the winner's curse | Rejected today |
| 7 | H7, H12, H10 (3-5) | US sector SPDRs, country ETFs, NIFTY | Beat random | Loss size 1.57x; PF 1.27; t 1.65 | Rejected (H12 in forward test 1) |
| 8 | Q (promoter buying), M (E2 + Q) (10) | SEBI insider filings, 2018-2026 | Q +1.33% vs +0.89% | No edge (p 0.31); diluted E2 | Rejected |
| - | Everything else | | | Market drift (sector/country rotation, TSMOM, N1, L1), costs (intraday rules, I1-I3, gaps), retired pullback family, wrong-direction or noise in screening (holding through results, bonus/split/buyback, high volume, seasonality, pledges, dividend yield, long-term reversal, dividend month, smirk, call-put spread) | Rejected |

## 2. Why candidates fail: four mechanisms, with the evidence

1. **Drift, not selection.** A long-only rule earns the market's return; random picks from the same stocks at the same
   times earn it too. L2 and O2 passed most stability rules and still had no edge. The random baseline is the criterion
   most rules fail.
2. **Payoff shape.** The real selection edges found (V2, N2) are trend payoffs: under 46% winners and deep drawdowns.
   The win-rate floor, profit factor and drawdown rules reject them together.
3. **Costs.** Delivery costs 0.37-0.47% a round trip at the engine's position size. Every short-hold edge found (the
   pre-results run-up: +0.44% over random in 4-6 sessions, t 4.5 on 2009-13) is smaller than the costs.
4. **Power.** With 5 positions, a monthly rule has about 158 decisions in 13 years. The cross-round bar is now
   0.05 / 67 = 0.00075 (about 3.2 standard errors): a monthly edge needs to be about 1.2% over random to pass.

## 3. Do combinations help? (2013-2026, informational: every part's results were already seen)

Fixed shares of the 5 positions; R summed by year; the account risks 0.5% of equity per position.

| Bunch | Win rate | PF | Return a year | Profitable years | Worst year | Drawdown | Edge over random |
|---|---:|---:|---:|---:|---:|---:|---:|
| E2 x3 + V2 x2 (trial 1) | 48.7% | 1.42 | +6.9R (+3.4%) | 10/14 | -10.4R | 18.4R | +1.45% |
| E2 x3 + V2 x1 + O2 x1 | 50.7% | 1.39 | +5.3R | 10/14 | -8.7R | 18.2R | +1.10% |
| E2 x3 + O2 x2 | 52.5% | 1.31 | +3.3R | 10/14 | -7.5R | 13.4R | +0.58% |
| E2 x2 + V2 x2 + L2 x1 | 48.7% | 1.35 | +6.1R | 10/14 | -10.0R | 22.7R | +0.80% |
| E2 x5 alone | 55.0% | 1.47 | +3.5R | 10/14 | -9.7R | 17.3R | +1.50% |

Yearly correlation of R with E2: V2 0.18, L2 -0.15, O2 0.03 (V2 with O2: 0.60). E2 earned in 2015 when V2 lost; V2 in
2026 when E2 lost; L2 and O2 earned in 2016; **in 2018 every part lost.**

**Conclusion.** Combining strategies with low correlation does smooth the record (fewer bad years, smaller worst year),
but every part tested is long-only Indian equity, so a broad mid-cap fall hits them all together. A genuinely
self-correcting portfolio needs a part that earns when the market falls: a hedge (index futures) or a different asset.
Adding parts without an edge raises the win rate but lowers the edge; it can't create profitability.

## 4. The exact evidence required for acceptance

- **Historical test:** all 13 pre-registered criteria on the decision span, including win rate at least 50%, profit
  factor at least 1.3, average loss at most 1.5x the average win, no trade worse than -3R, both halves positive, 70% of
  years profitable, breadth across stocks, t and month-clustered t at least 2, drawdown at most 20R, and beating random
  picks at Holm p below 0.05 and raw p below 0.05 / N (N = 67 now, growing with every test).
- **Forward tests (1-4):** the same criteria on future data at the January looks 2028-2036, with p below 0.05 / L at look
  L. Fail any criterion: NO TRADE for real money.
- **Then, with your approval:** 13 weeks of paper trading with 40+ trades and 60 clean sessions (Level 5), then small
  live capital (Level 6). Nothing is waived.

## 5. What to test next, ranked by expected value

| Rank | Experiment | Why | What it needs | Honest prior |
|---:|---|---|---|---|
| 1 | **A hedged bunch on future data**: E2 + V2 with the market's beta removed by shorting NIFTY futures (paper only) | Directly attacks the failure in section 3 (every part loses in a broad fall) and V2's failures (years, drawdown), while keeping its strong selection edge. Variants of V2 can't be judged on 2013-2026, so only forward data can test it | Your decision on F&O (index futures shorts), even for paper; a pre-registered forward test | The best candidate for a robust portfolio; evidence takes years |
| 2 | **Futures positioning signals** (open-interest build-up, basis) from daily F&O files | A source not yet tested; data is free | About 3 hours of downloads (outside OneDrive), a screen on 2008-2013 | Low to moderate; little published support |
| 3 | **A defensive asset sleeve** (gold ETF) in the bunch | Gold rose in several Indian equity down-years | Not a strategy with an edge: a portfolio choice that the current gate can't approve by itself | Smooths years; can't pass the random-baseline test |
| 4 | **Intraday event trades** (results day, MIS costs about 0.2%) | Lower costs than delivery | Daily data allow only decisions before the open; the event study showed no average results-day drift | Low |

Not recommended: more variants of momentum, low volatility, value or dividend timing on 2013-2026 (each adds to N, and
the families have been tested), or anything relaxing the criteria.
