# Research round 2 results: the pullback rules on new markets

Generated 2026-10-09 23:02 by `python -m trader.research.round2`, judged against [the pre-registration](round2-preregistration.md) (SHA-256 `f61e6ee0181c1e62...`, unchanged since it was recorded before any strategy ran). Returns are per trade, net of costs; holdout = 2022 to 8 Oct 2026.

## Verdict

| Hypothesis | Holdout trades | Win rate | Net per trade | Profit factor | t | Cluster-robust t | p vs random (Holm) | Decision |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| H4: Oversold pullback in an uptrend, US large caps | 2607 | 62.0% | +0.162% | 1.14 | 2.39 | 1.40 | 0.431 | **REJECTED** |
| H5: Oversold pullback in an uptrend, Indian index ETFs | 143 | 54.5% | -0.057% | 0.93 | -0.34 | -0.30 | 0.431 | **REJECTED** |
| H6: Oversold pullback in an uptrend, US sector ETFs | 431 | 65.2% | +0.243% | 1.37 | 2.40 | 1.86 | 0.206 | **REJECTED** |

## Data and costs

- Daily bars from Yahoo (adjusted), frozen in `data/round2/` with checksums, cut at 8 Oct 2026: 82 US large caps, 11 US sector SPDRs, and 4 NSE indices standing in for the ETFs that would be traded (^NSEBANK via BANKBEES.NS, ^CNXIT via ITBEES.NS, ^CNXPHARMA via PHARMABEES.NS, ^NSMIDCP via JUNIORBEES.NS).
- Bars without prices and Yahoo's flat zero-volume placeholder bars were dropped.
- Round-trip costs: US 0.043%, Indian ETFs 0.139% (including 0.05% slippage per side); stress test at 1.5x.
- Survivorship bias: today's S&P 100 members over a past decade over-represent winners. The random baseline uses the same instruments and period, so it shares that bias.

Every daily move above 20% in the evaluation data, classified before any strategy ran (2026 moves checked against press coverage):

| Instrument | Date | Close to close | Open gap | Classification |
|---|---|---:|---:|---|
| NFLX | 2014-10-16 | -19.4% | -25.8% | Genuine: Q3 results |
| NOW | 2016-01-28 | -15.7% | -23.3% | Genuine: Q4 results and guidance |
| AMD | 2016-04-22 | +52.3% | +21.8% | Genuine: Q1 results and China licensing deal |
| DHR | 2016-07-05 | +61.2% | +55.2% | Corporate action Yahoo mis-adjusted: series split here |
| AMD | 2017-05-02 | -24.2% | -13.9% | Genuine: Q1 results |
| AMD | 2018-10-25 | -15.4% | -21.4% | Genuine: Q3 results |
| QCOM | 2019-04-16 | +23.2% | +0.5% | Genuine: Apple settlement |
| TGT | 2019-08-21 | +20.4% | +16.8% | Genuine: Q2 results |
| COP | 2020-03-09 | -24.8% | -25.1% | Genuine: COVID-19 crash (oil price war) |
| XLE | 2020-03-09 | -20.1% | -17.5% | Genuine: COVID-19 crash (oil price war) |
| AIG | 2020-03-12 | -20.8% | -8.5% | Genuine: COVID-19 crash |
| ORCL | 2020-03-13 | +20.4% | +11.7% | Genuine: COVID-19 rebound |
| BA | 2020-03-16 | -23.8% | -12.2% | Genuine: COVID-19 crash |
| C | 2020-03-16 | -19.3% | -20.7% | Genuine: COVID-19 crash |
| COF | 2020-03-16 | -23.9% | -16.2% | Genuine: COVID-19 crash |
| LOW | 2020-03-16 | -24.8% | -11.3% | Genuine: COVID-19 crash |
| SPG | 2020-03-16 | -26.7% | -12.1% | Genuine: COVID-19 crash |
| CVX | 2020-03-18 | -22.1% | -6.3% | Genuine: COVID-19 crash |
| SPG | 2020-03-18 | -23.7% | -7.4% | Genuine: COVID-19 crash |
| UBER | 2020-03-18 | -21.6% | -6.1% | Genuine: COVID-19 crash |
| SPG | 2020-03-19 | +24.1% | +3.1% | Genuine: COVID-19 rebound |
| UBER | 2020-03-19 | +38.3% | +7.7% | Genuine: COVID-19 rebound |
| AXP | 2020-03-24 | +21.9% | +6.6% | Genuine: COVID-19 rebound |
| BA | 2020-03-24 | +20.9% | +17.1% | Genuine: COVID-19 rebound |
| COP | 2020-03-24 | +25.2% | +7.7% | Genuine: COVID-19 rebound |
| CVX | 2020-03-24 | +22.7% | +13.4% | Genuine: COVID-19 rebound |
| F | 2020-03-24 | +23.4% | +11.5% | Genuine: COVID-19 rebound |
| INTU | 2020-03-24 | +20.1% | +5.9% | Genuine: COVID-19 rebound |
| BA | 2020-03-25 | +24.3% | +21.3% | Genuine: COVID-19 rebound |
| CRM | 2020-08-26 | +26.0% | +16.6% | Genuine: Q2 results |
| AXP | 2020-11-09 | +21.4% | +14.3% | Genuine: Vaccine-news rally |
| SPG | 2020-11-09 | +27.9% | +21.0% | Genuine: Vaccine-news rally |
| PLTR | 2020-11-25 | +22.0% | +0.6% | Genuine: Retail rally after its listing |
| PLTR | 2020-12-07 | +21.3% | +2.5% | Genuine: Retail rally after its listing |
| PLTR | 2021-01-22 | +25.4% | -0.5% | Genuine: Retail rally after its listing |
| NFLX | 2022-01-21 | -21.8% | -21.2% | Genuine: Q4 results |
| PYPL | 2022-02-02 | -24.6% | -20.4% | Genuine: Q4 results |
| NFLX | 2022-04-20 | -35.1% | -29.7% | Genuine: Q1 results |
| PLTR | 2022-05-09 | -21.3% | -17.9% | Genuine: Q1 results |
| TGT | 2022-05-18 | -24.9% | -24.3% | Genuine: Q1 results |
| FDX | 2022-09-16 | -21.4% | -22.2% | Genuine: Profit warning |
| PLTR | 2023-02-14 | +21.2% | +12.9% | Genuine: Q4 results |
| PLTR | 2023-05-09 | +23.4% | +19.1% | Genuine: Q1 results |
| PLTR | 2023-11-02 | +20.4% | +17.2% | Genuine: Q3 results |
| PLTR | 2024-02-06 | +30.8% | +21.4% | Genuine: Q4 results |
| MMM | 2024-07-26 | +23.0% | +9.0% | Genuine: Q2 results |
| INTC | 2024-08-02 | -26.1% | -24.5% | Genuine: Q2 results and layoffs |
| SBUX | 2024-08-13 | +24.5% | +18.2% | Genuine: New CEO |
| PLTR | 2024-11-05 | +23.5% | +15.6% | Genuine: Q3 results |
| TGT | 2024-11-20 | -21.4% | -17.4% | Genuine: Q3 results |
| PLTR | 2025-02-04 | +24.0% | +22.8% | Genuine: Q4 results |
| AMD | 2025-04-09 | +23.8% | +1.3% | Genuine: Tariff-pause rally |
| ORCL | 2025-09-10 | +35.9% | +32.2% | Genuine: Q1 results (contract backlog) |
| INTC | 2025-09-18 | +22.8% | +27.6% | Genuine: Nvidia investment |
| AMD | 2025-10-06 | +23.7% | +37.5% | Genuine: OpenAI chip partnership |
| PYPL | 2026-02-03 | -20.3% | -18.0% | Genuine: Q4 results and CEO change |
| CHTR | 2026-04-24 | -25.5% | -3.6% | Genuine: Q1 results |
| INTC | 2026-04-24 | +23.6% | +23.1% | Genuine: Q1 results |
| INTU | 2026-05-21 | -20.0% | -18.7% | Genuine: Q3 results and layoffs |
| CHTR | 2026-06-29 | +9.4% | +25.8% | Genuine: Reported SpaceX partnership talks |
| IBM | 2026-07-14 | -25.2% | -22.0% | Genuine: Preliminary Q2 shortfall |
| PLTR | 2026-08-04 | +29.5% | +15.5% | Genuine: Q2 results |
| CRM | 2026-08-27 | +22.6% | +11.9% | Genuine: Q2 results |

## H4: Oversold pullback in an uptrend, US large caps

| Period | Trades | Win rate | Avg win | Avg loss | Profit factor | Net per trade | t | Max drawdown | Sharpe |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Design 2016-2021 | 3545 | 64.7% | +1.80% | -2.85% | 1.16 | +0.159% | 3.17 | -119.1R | 0.58 |
| Holdout 2022-2026 | 2607 | 62.0% | +2.13% | -3.04% | 1.14 | +0.162% | 2.39 | -51.5R | 0.50 |
| All | 6152 | 63.5% | +1.94% | -2.94% | 1.15 | +0.161% | 3.93 | -119.1R | 0.54 |

Random baseline (random days with the same instruments, simultaneous entries kept together), holdout: +0.139% gross per trade vs +0.205% for the strategy; p = 0.215 (Holm-adjusted 0.431).

| # | Criterion | Value | Pass |
|---|---|---|---|
| 1 | At least 50 holdout trades | 2607 | yes |
| 2 | Win rate at least 50% | 62.0% | yes |
| 3 | Expectancy above 0 at base and 1.5x costs | +0.162% / +0.141% | yes |
| 4 | t-statistic at least 2.0 | 2.39 | yes |
| 5 | Beats random entries (Holm-adjusted p < 0.05) | 0.431 | **no** |
| 6 | Profit factor at least 1.3 | 1.14 | **no** |
| 7 | Avg loss at most 1.5x avg win; worst trade no worse than -3R | -3.04% vs +2.13%; worst -3.4R | **no** |
| 8 | Design-period expectancy also above 0 | +0.159% | yes |
| 9 | At least 70% of years (10+ trades) positive | 82% of 11 years | yes |
| 10 | 60%+ of stocks profitable; still positive without the top stock | 68% of 82 stocks; +0.143% without PLTR | yes |
| 11 | Cluster-robust t-statistic (signal weeks as clusters) at least 2.0 | 1.40 | **no** |

**Decision: REJECTED.**

By year (all trades, net of base costs):

| Year | Trades | Win rate | Net per trade |
|---|---:|---:|---:|
| 2016 | 559 | 66.5% | +0.372% |
| 2017 | 647 | 66.2% | +0.288% |
| 2018 | 565 | 55.0% | -0.565% |
| 2019 | 521 | 66.2% | +0.050% |
| 2020 | 498 | 62.4% | +0.047% |
| 2021 | 755 | 69.7% | +0.583% |
| 2022 | 346 | 52.3% | -0.720% |
| 2023 | 507 | 63.1% | +0.154% |
| 2024 | 757 | 63.8% | +0.380% |
| 2025 | 537 | 66.3% | +0.410% |
| 2026 | 460 | 60.0% | +0.187% |

## H5: Oversold pullback in an uptrend, Indian index ETFs

| Period | Trades | Win rate | Avg win | Avg loss | Profit factor | Net per trade | t | Max drawdown | Sharpe |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Design 2016-2021 | 173 | 68.8% | +1.46% | -2.25% | 1.43 | +0.305% | 1.84 | -4.2R | 0.58 |
| Holdout 2022-2026 | 143 | 54.5% | +1.34% | -1.73% | 0.93 | -0.057% | -0.34 | -12.2R | -0.10 |
| All | 316 | 62.3% | +1.41% | -1.97% | 1.19 | +0.141% | 1.19 | -15.5R | 0.28 |

Random baseline (random days with the same instruments, simultaneous entries kept together), holdout: +0.033% gross per trade vs +0.082% for the strategy; p = 0.385 (Holm-adjusted 0.431).

| # | Criterion | Value | Pass |
|---|---|---|---|
| 1 | At least 50 holdout trades | 143 | yes |
| 2 | Win rate at least 50% | 54.5% | yes |
| 3 | Expectancy above 0 at base and 1.5x costs | -0.057% / -0.126% | **no** |
| 4 | t-statistic at least 2.0 | -0.34 | **no** |
| 5 | Beats random entries (Holm-adjusted p < 0.05) | 0.431 | **no** |
| 6 | Profit factor at least 1.3 | 0.93 | **no** |
| 7 | Avg loss at most 1.5x avg win; worst trade no worse than -3R | -1.73% vs +1.34%; worst -1.7R | yes |
| 8 | Design-period expectancy also above 0 | +0.305% | yes |
| 9 | At least 70% of years (10+ trades) positive | 64% of 11 years | **no** |
| 10 | 60%+ of stocks profitable; still positive without the top stock | 75% of 4 stocks; +0.106% without ^CNXPHARMA | yes |
| 11 | Cluster-robust t-statistic (signal weeks as clusters) at least 2.0 | -0.30 | **no** |

**Decision: REJECTED.**

By year (all trades, net of base costs):

| Year | Trades | Win rate | Net per trade |
|---|---:|---:|---:|
| 2016 | 23 | 78.3% | +0.510% |
| 2017 | 24 | 70.8% | +0.533% |
| 2018 | 32 | 56.2% | +0.035% |
| 2019 | 21 | 61.9% | -0.133% |
| 2020 | 27 | 70.4% | +0.429% |
| 2021 | 46 | 73.9% | +0.397% |
| 2022 | 20 | 30.0% | -1.722% |
| 2023 | 30 | 43.3% | -0.298% |
| 2024 | 50 | 64.0% | +0.633% |
| 2025 | 24 | 66.7% | +0.213% |
| 2026 | 19 | 57.9% | -0.076% |

By instrument (all trades, net of base costs):

| Instrument | Trades | Win rate | Net per trade |
|---|---:|---:|---:|
| ^CNXPHARMA | 59 | 61.0% | +0.293% |
| ^CNXIT | 69 | 63.8% | +0.214% |
| ^NSMIDCP | 93 | 65.6% | +0.167% |
| ^NSEBANK | 95 | 58.9% | -0.031% |

## H6: Oversold pullback in an uptrend, US sector ETFs

| Period | Trades | Win rate | Avg win | Avg loss | Profit factor | Net per trade | t | Max drawdown | Sharpe |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Design 2016-2021 | 510 | 66.7% | +1.27% | -1.90% | 1.34 | +0.216% | 2.50 | -17.4R | 0.70 |
| Holdout 2022-2026 | 431 | 65.2% | +1.40% | -1.91% | 1.37 | +0.243% | 2.40 | -10.6R | 0.84 |
| All | 941 | 66.0% | +1.33% | -1.91% | 1.35 | +0.228% | 3.47 | -17.4R | 0.75 |

Random baseline (random days with the same instruments, simultaneous entries kept together), holdout: +0.134% gross per trade vs +0.286% for the strategy; p = 0.069 (Holm-adjusted 0.206).

| # | Criterion | Value | Pass |
|---|---|---|---|
| 1 | At least 50 holdout trades | 431 | yes |
| 2 | Win rate at least 50% | 65.2% | yes |
| 3 | Expectancy above 0 at base and 1.5x costs | +0.243% / +0.222% | yes |
| 4 | t-statistic at least 2.0 | 2.40 | yes |
| 5 | Beats random entries (Holm-adjusted p < 0.05) | 0.206 | **no** |
| 6 | Profit factor at least 1.3 | 1.37 | yes |
| 7 | Avg loss at most 1.5x avg win; worst trade no worse than -3R | -1.91% vs +1.40%; worst -1.2R | yes |
| 8 | Design-period expectancy also above 0 | +0.216% | yes |
| 9 | At least 70% of years (10+ trades) positive | 82% of 11 years | yes |
| 10 | 60%+ of stocks profitable; still positive without the top stock | 82% of 11 stocks; +0.183% without XLY | yes |
| 11 | Cluster-robust t-statistic (signal weeks as clusters) at least 2.0 | 1.86 | **no** |

**Decision: REJECTED.**

By year (all trades, net of base costs):

| Year | Trades | Win rate | Net per trade |
|---|---:|---:|---:|
| 2016 | 77 | 75.3% | +0.536% |
| 2017 | 86 | 66.3% | +0.232% |
| 2018 | 75 | 50.7% | -0.669% |
| 2019 | 83 | 72.3% | +0.473% |
| 2020 | 67 | 67.2% | +0.166% |
| 2021 | 122 | 67.2% | +0.398% |
| 2022 | 56 | 50.0% | -0.656% |
| 2023 | 73 | 64.4% | +0.268% |
| 2024 | 122 | 63.1% | +0.237% |
| 2025 | 92 | 73.9% | +0.610% |
| 2026 | 88 | 69.3% | +0.419% |

By instrument (all trades, net of base costs):

| Instrument | Trades | Win rate | Net per trade |
|---|---:|---:|---:|
| XLY | 102 | 78.4% | +0.604% |
| XLC | 70 | 75.7% | +0.529% |
| XLI | 99 | 67.7% | +0.365% |
| XLB | 91 | 64.8% | +0.328% |
| XLK | 81 | 65.4% | +0.276% |
| XLF | 87 | 66.7% | +0.204% |
| XLP | 88 | 67.0% | +0.176% |
| XLV | 94 | 63.8% | +0.063% |
| XLE | 81 | 55.6% | +0.059% |
| XLRE | 69 | 59.4% | -0.105% |
| XLU | 79 | 58.2% | -0.112% |

## Informational: the Phase 3 baseline (doesn't affect the decisions)

The same comparison with every random entry drawn independently, as in Phase 3:

| Hypothesis | p, simultaneous entries kept together | p, independent draws |
|---|---:|---:|
| H4 | 0.215 | 0.136 |
| H5 | 0.385 | 0.387 |
| H6 | 0.069 | 0.041 |
