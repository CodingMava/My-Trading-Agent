# Research round 7 results: market intraday momentum in NIFTYBEES

Run once on 2026-10-13 15:50 IST by `python -m trader.research.round7` at commit `0e604d1c03d5`, against [the pre-registration](round7-preregistration.md) (SHA-256 `68cac73e66d2c285...`, pinned and pushed before this code was written) and the frozen data `data/kite_minute/nifty_1m` (checksums as pinned). Every hypothesis is reported, pass or fail. Returns are per trade and net of costs: 0.1191% a round trip, 0.1491% for a stopped trade.

Sessions: 1684 in the data, 1673 could be traded. The rest were skipped because: no index 09:44 bar: 6; no NIFTYBEES 14:45 bar: 3; no earlier session with an index 15:14 bar: 1; NIFTYBEES 14:45 bar without trades: 1.

## Verdict

| Hypothesis | Trades | Win rate | Net per trade | t | Cluster-robust t | p vs random (raw / Holm) | Drawdown | Decision |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| I1: Long side: buy after a rising morning | 959 | 24.4% | -0.1106% | -16.83 | -18.71 | 0.41928 / 1.00000 | 212.2R | **REJECTED** |
| I2: Short side: short after a falling morning | 714 | 23.5% | -0.1281% | -15.36 | -15.06 | 0.56492 / 1.00000 | 182.9R | **REJECTED** |
| I3: Big mornings: trade in the morning's direction | 279 | 26.9% | -0.1230% | -9.56 | -9.94 | 0.59597 / 1.00000 | 68.6R | **REJECTED** |

## The criteria

| # | Criterion | I1 | I2 | I3 |
|---|---|---|---|---|
| 1 | At least 50 trades | 959 (pass) | 714 (pass) | 279 (pass) |
| 2 | Win rate at least 50% | 24.4% (**fail**) | 23.5% (**fail**) | 26.9% (**fail**) |
| 3 | Expectancy above 0 at base and 1.5x costs | -0.1106% / -0.1708% (**fail**) | -0.1281% / -0.1881% (**fail**) | -0.1230% / -0.1833% (**fail**) |
| 4 | t-statistic at least 2.0 | -16.83 (**fail**) | -15.36 (**fail**) | -9.56 (**fail**) |
| 5 | Beats the random baseline: Holm-adjusted p below 0.05 | 1.00000 (**fail**) | 1.00000 (**fail**) | 1.00000 (**fail**) |
| 6 | Profit factor at least 1.3 | 0.22 (**fail**) | 0.22 (**fail**) | 0.21 (**fail**) |
| 7 | Average loss at most 1.5x the average win; no trade worse than -3R | -0.188% vs +0.130% (1.44x); worst -1.33R (pass) | -0.216% vs +0.156% (1.38x); worst -1.32R (pass) | -0.214% vs +0.123% (1.73x); worst -1.32R (**fail**) |
| 8 | Expectancy above 0 in each half of the span | -0.1029% / -0.1186% (split 2023-05-23) (**fail**) | -0.1460% / -0.1112% (split 2023-05-23) (**fail**) | -0.1351% / -0.1144% (split 2023-11-22) (**fail**) |
| 9 | At least 70% of calendar years with 10+ trades profitable | 0% of 7 years (**fail**) | 0% of 7 years (**fail**) | 0% of 6 years (**fail**) |
| 11 | Cluster-robust t-statistic (signal ISO weeks as clusters) at least 2.0 | -18.71 (**fail**) | -15.06 (**fail**) | -9.94 (**fail**) |
| 12 | Raw random-baseline p below 0.05/23 = 0.00217 | 0.41928 (**fail**) | 0.56492 (**fail**) | 0.59597 (**fail**) |
| 13 | Drawdown no deeper than 20R (cumulative R in exit order) | 212.2R (**fail**) | 182.9R (**fail**) | 68.6R (**fail**) |

## I1: Long side: buy after a rising morning

Span 2020-01-02 to 2026-10-12 (1673 sessions it could trade). Mean gross +0.0097% a trade against +0.0083% for the same window on random sessions (p = 0.41928, Holm 1.00000).

**Decision: REJECTED.**

Informational (not part of the decision):

- Stops: 40, of which 1 filled at a gap.
- before 3 Aug 2026: 938 trades, 24.7% winners, -0.1107% a trade, t -16.50; from 3 Aug 2026: 21 trades, 9.5% winners, -0.1081% a trade, t -5.85.
- By India VIX regime: high: 452 trades, 24.3% winners, -0.1148% a trade, t -10.32; normal: 492 trades, 24.6% winners, -0.1025% a trade, t -13.74.
- Without the stop: 959 trades, 24.6% winners, -0.1124% a trade, t -15.41.
- Net per trade at 0x / 1x / 1.5x / 2x costs: +0.0097% / -0.1106% / -0.1708% / -0.2309%.
- Portfolio (Rs 10,00,000, one Rs 2,00,000 position a session): CAGR -3.50%, Sharpe -6.28, Sortino -6.34, maximum drawdown -21.21%.

| Year | Trades | Net per trade |
|---|---:|---:|
| 2020 | 157 | -0.0899% |
| 2021 | 159 | -0.1241% |
| 2022 | 126 | -0.1003% |
| 2023 | 143 | -0.0961% |
| 2024 | 141 | -0.1293% |
| 2025 | 137 | -0.1116% |
| 2026 | 96 | -0.1282% |

## I2: Short side: short after a falling morning

Span 2020-01-02 to 2026-10-12 (1673 sessions it could trade). Mean gross -0.0079% a trade against -0.0065% for the same window on random sessions (p = 0.56492, Holm 1.00000).

**Decision: REJECTED.**

Informational (not part of the decision):

- Stops: 25, of which 3 filled at a gap.
- before 3 Aug 2026: 686 trades, 24.2% winners, -0.1272% a trade, t -14.72; from 3 Aug 2026: 28 trades, 7.1% winners, -0.1499% a trade, t -7.25.
- By India VIX regime: high: 337 trades, 27.0% winners, -0.1303% a trade, t -9.47; normal: 371 trades, 20.2% winners, -0.1273% a trade, t -12.72.
- Without the stop: 714 trades, 23.8% winners, -0.1285% a trade, t -13.93.
- Net per trade at 0x / 1x / 1.5x / 2x costs: -0.0079% / -0.1281% / -0.1881% / -0.2482%.
- Portfolio (Rs 10,00,000, one Rs 2,00,000 position a session): CAGR -2.98%, Sharpe -5.54, Sortino -5.74, maximum drawdown -18.29%.

| Year | Trades | Net per trade |
|---|---:|---:|
| 2020 | 92 | -0.1792% |
| 2021 | 87 | -0.1213% |
| 2022 | 121 | -0.1274% |
| 2023 | 102 | -0.1496% |
| 2024 | 105 | -0.1097% |
| 2025 | 111 | -0.1263% |
| 2026 | 96 | -0.0853% |

## I3: Big mornings: trade in the morning's direction

Span 2021-01-01 to 2026-10-12 (1424 sessions it could trade). Mean gross -0.0024% a trade against +0.0004% for the same window on random sessions (p = 0.59597, Holm 1.00000).

**Decision: REJECTED.**

Informational (not part of the decision):

- Stops: 14, of which 1 filled at a gap.
- before 3 Aug 2026: 272 trades, 27.2% winners, -0.1229% a trade, t -9.35; from 3 Aug 2026: 7 trades, 14.3% winners, -0.1278% a trade, t -2.53.
- By India VIX regime: high: 184 trades, 28.3% winners, -0.1271% a trade, t -7.75; normal: 94 trades, 24.5% winners, -0.1140% a trade, t -5.48.
- Without the stop: 279 trades, 26.9% winners, -0.1236% a trade, t -9.38.
- Net per trade at 0x / 1x / 1.5x / 2x costs: -0.0024% / -0.1230% / -0.1833% / -0.2436%.
- Portfolio (Rs 10,00,000, one Rs 2,00,000 position a session): CAGR -1.06%, Sharpe -3.29, Sortino -3.44, maximum drawdown -6.86%.

| Year | Trades | Net per trade |
|---|---:|---:|
| 2021 | 33 | -0.1044% |
| 2022 | 63 | -0.1475% |
| 2023 | 25 | -0.1382% |
| 2024 | 51 | -0.1061% |
| 2025 | 45 | -0.1409% |
| 2026 | 62 | -0.1027% |

## Informational, across hypotheses

- The window traded long on every tradable session, regardless of r_first: 1673 trades, 25.0% winners, -0.1121% a trade, t -20.63.

Patterns in the informational sections are hypotheses for future data, not findings. Nothing here changes a rule: a changed rule is a new hypothesis, which can only be judged on data that doesn't exist yet.
