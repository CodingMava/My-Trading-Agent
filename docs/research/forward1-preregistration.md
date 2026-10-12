# Forward test 1 pre-registration: the turn of the month (H11, H12) on sessions after 13 Oct 2026

Written and pinned on 13 Oct 2026, before any session this test judges had happened: its first trade can only be signalled at the close of Thursday 29 Oct 2026, October's second-to-last trading day. The rules, data, costs, criteria and decisions below are fixed. Results are reported against this file whatever they show, and `trader/research/forward1.py` checks this file's SHA-256 (LF line endings) before every look.

## Why a forward test

Twenty hypotheses have been tested in this project on overlapping historical data (H1-H14 in rounds 1-5, C1-C6 in round 6), and none passed. Every further test on the same data raises the chance that something passes by luck (data-mining bias), so the project stopped running new rounds on it. The only data no one has seen is the future.

H11 and H12 are the two strongest effects found so far. Both beat random timing in research (Holm-adjusted p < 0.001 and 0.039), and each failed a single criterion: H11 lost money in each of 2024, 2025 and 2026, so not every third of its span was profitable; H12's profit factor was 1.27, against the 1.3 required. This test asks whether they keep working after their rules were fixed. No other candidate is added, because each one would weaken the correction for multiple tests below.

## Rules (unchanged from round 5)

- Signal at the close of each month's second-to-last trading day; enter at the next open (the month's last trading day); exit at the close of the next month's third trading day, or at a protective stop 2.5 x ATR(14) below entry, filled at the stop price, or at the open if the day gaps through it. These are `trader.strategies.swing.turn_of_month_signals` with `TURN_OF_MONTH`, simulated by `trader.research.round4.turn_of_month_trades`, exactly as in round 5.
- H11: ^NSEBANK, ^NSMIDCP, ^CNXIT and ^CNXPHARMA, the index levels standing in for BANKBEES, JUNIORBEES, ITBEES and PHARMABEES as in round 5. Round-trip cost 0.1386% (`round5.INDIA_ETF`).
- H12: EWA, EWC, EWG, EWH, EWJ, EWL, EWS, EWT, EWU, EWW, EWY, EWZ, FXI, MCHI and INDA. Round-trip cost 0.1028% (`round5.COUNTRY_ETF`).

## Data

Yahoo daily bars (adjusted), fetched at each look from 1 Jun 2026, so the ATR is ready well before the first signal, and frozen with checksums under `data/forward1/<look date>/` (git-ignored). They are cleaned as in round 5: bars without prices and flat zero-volume placeholder bars are dropped. Every daily move above 20% must be classified in `forward1.CLASSIFIED_MOVES` before a look can run, as in every round. Only trades signalled from 14 Oct 2026 up to the look's cut-off count.

## Looks

- Any time: informational. Nothing is decided.
- Decision looks: one each January from 2028 to 2036, with data through the end of the previous December. January 2028 is look 1, January 2029 look 2, and so on.

## Criteria at a decision look (forward trades only)

Round 5's criteria 1-11, unchanged, computed on the forward trades alone, over the forward span (14 Oct 2026 to the cut-off):

1. At least 50 trades.
2. Win rate at least 50%.
3. Expectancy above zero at base costs and at 1.5x costs.
4. t-statistic at least 2.0.
5. Beats its random baseline (the same four-day hold and stop entered on random days of the forward span, simultaneous entries kept together; 2,000 draws, seed 7): the p-value, Holm-corrected across H11 and H12, below 0.05 / L at look L, because each look is another chance of a lucky pass.
6. Profit factor at least 1.3.
7. Average loss at most 1.5 x the average win; no trade worse than -3R.
8. Expectancy above zero in each half of the forward span.
9. Expectancy above zero in each third of the forward span (round 5's rule for monthly strategies).
10. At least 60% of instruments with 5+ trades profitable, and expectancy above zero without the top-contributing instrument.
11. Cluster-robust t-statistic (signal weeks as clusters) at least 2.0.

## Decisions, for each hypothesis on its own

| At a decision look | Decision |
|---|---|
| Every criterion passes | Candidate for PAPER. Its research evidence is written under a new id (H11F or H12F), so the round 5 records stay as they are. It is paper traded only once you approve it, and real money still needs the paper-trading stage (Level 5) and small live capital (Level 6). |
| From January 2029 (look 2): the forward expectancy net of base costs is zero or below | REJECTED: the effect did not last beyond its research period. The test ends for it. |
| January 2036 (look 9) without a pass | REJECTED. The test ends. |
| Otherwise | Continue to the next January. |

## What to expect

At the effect sizes measured in research, the slowest criteria are the t-statistics (4 and 11), because one turn of the month moves all of a hypothesis's instruments together. H11's cluster-robust t grew by about 0.73 per square root of a year (3.15 over 18.8 years), so reaching 2.0 on new data alone would take about 7.5 years at even odds. H12's was 2.02 over 26 years, so it can't be expected to pass within this test. In practice this test can show that an effect has stopped working well before it can show that one still works. Nothing from it is expected to trade before 2030.
