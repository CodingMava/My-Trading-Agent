# Research round 5 results: a batch of documented monthly effects

Generated 2026-10-11 17:19 by `python -m trader.research.round5`, judged against [the pre-registration](round5-preregistration.md) (SHA-256 `2a2526fa940f65a3...`, unchanged since it was recorded before these rules ran on this data). Returns are per trade, net of costs, over each hypothesis's whole span.

## Verdict

| Hypothesis | Trades | Win rate | Net per trade | Profit factor | t | Cluster-robust t | p vs random (Holm) | Decision |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| H11: Turn of the month, Indian indices beyond the NIFTY 50 | 863 | 57.9% | +0.475% | 1.57 | 4.82 | 3.15 | 0.000 | **REJECTED** |
| H12: Turn of the month, 15 country ETFs | 4334 | 54.9% | +0.265% | 1.27 | 5.85 | 2.02 | 0.039 | **REJECTED** |
| H13: Momentum, top 3 of the 9 US sector SPDRs monthly | 960 | 59.0% | +0.858% | 1.53 | 5.04 | 3.54 | 0.355 | **REJECTED** |
| H14: Momentum, top 3 of 15 country ETFs monthly | 924 | 57.8% | +0.803% | 1.35 | 3.39 | 2.23 | 0.355 | **REJECTED** |

## Data and costs

- Daily bars from Yahoo (adjusted), frozen with checksums (`data/round5/`; the sector SPDRs from `data/round3/`), cut at 8 Oct 2026. Bars without prices and flat zero-volume placeholders were dropped.
- Round-trip costs: Indian ETFs 0.139%, country ETFs 0.103%, sector SPDRs 0.043%; stress test at 1.5x.

Every daily move above 20% in the data, classified before any strategy ran:

| Instrument | Date | Close to close | Open gap | Classification |
|---|---|---:|---:|---|
| EWH | 1997-10-28 | +20.2% | -6.0% | Genuine: Asian financial crisis, the rebound after the 27 Oct 1997 crash |
| EWY | 2008-09-19 | +5.5% | +22.3% | Genuine: US short-selling ban and bank rescue plan |
| XLF | 2008-09-19 | +12.9% | +22.1% | Genuine: US short-selling ban and bank rescue plan |
| EWA | 2008-10-13 | +20.7% | +10.5% | Genuine: coordinated bank rescues, worldwide rally |
| EWW | 2008-10-13 | +21.5% | +12.0% | Genuine: coordinated bank rescues, worldwide rally |
| EWY | 2008-10-13 | +22.4% | +12.7% | Genuine: coordinated bank rescues, worldwide rally |
| EWZ | 2008-10-13 | +25.6% | +13.4% | Genuine: coordinated bank rescues, worldwide rally |
| FXI | 2008-10-13 | +20.3% | +9.6% | Genuine: coordinated bank rescues, worldwide rally |
| EWY | 2008-10-28 | +20.8% | +10.5% | Genuine: worldwide rally (US stocks +11%) |
| FXI | 2008-10-28 | +20.0% | +9.6% | Genuine: worldwide rally (US stocks +11%) |
| EWY | 2008-10-30 | +22.1% | +16.0% | Genuine: Fed currency swap lines with Korea and others |
| XLE | 2020-03-09 | -20.1% | -17.5% | Genuine: COVID-19 crash (oil price war) |
| EWZ | 2020-03-16 | -23.1% | -16.1% | Genuine: COVID-19 crash |
| FXI | 2022-03-16 | +21.2% | +11.7% | Genuine: China's pledge to support its markets |
| MCHI | 2022-03-16 | +20.9% | +12.5% | Genuine: China's pledge to support its markets |

## H11: Turn of the month, Indian indices beyond the NIFTY 50

Traded as: BANKBEES, JUNIORBEES, ITBEES, PHARMABEES.

| Period | Trades | Win rate | Avg win | Avg loss | Profit factor | Net per trade | t | Max drawdown | Sharpe |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2008-2016 | 411 | 62.0% | +2.54% | -2.10% | 1.98 | +0.779% | 4.95 | -6.6R | 1.12 |
| 2017-2026 | 452 | 54.2% | +1.96% | -1.89% | 1.23 | +0.199% | 1.64 | -27.1R | 0.25 |
| All 2008-2026 | 863 | 57.9% | +2.26% | -1.98% | 1.57 | +0.475% | 4.82 | -27.1R | 0.68 |

Random baseline (the same four-day hold and stop entered on random days, simultaneous entries kept together): +0.077% gross per trade vs +0.614% for the strategy; p = 0.000 (Holm-adjusted 0.000).

| # | Criterion | Value | Pass |
|---|---|---|---|
| 1 | At least 50 trades | 863 | yes |
| 2 | Win rate at least 50% | 57.9% | yes |
| 3 | Expectancy above 0 at base and 1.5x costs | +0.475% / +0.406% | yes |
| 4 | t-statistic at least 2.0 | 4.82 | yes |
| 5 | Beats random entries (Holm-adjusted p < 0.05) | 0.000 | yes |
| 6 | Profit factor at least 1.3 | 1.57 | yes |
| 7 | Avg loss at most 1.5x avg win; worst trade no worse than -3R | -1.98% vs +2.26%; worst -1.8R | yes |
| 8 | Expectancy above 0 in each half of the span | +0.779% / +0.199% | yes |
| 9 | Expectancy above 0 in each third of the span | +1.023% / -0.019% / +0.489% | **no** |
| 10 | 60%+ of instruments profitable; still positive without the top instrument | 100% of 4 instruments; +0.397% without ^NSMIDCP | yes |
| 11 | Cluster-robust t-statistic (signal weeks as clusters) at least 2.0 | 3.15 | yes |

**Decision: REJECTED.**

Informational: 74% of years (10+ trades) were profitable, the measure rounds 1-4 required to be at least 70%.

By year (net of base costs):

| Year | Trades | Win rate | Net per trade |
|---|---:|---:|---:|
| 2008 | 36 | 58.3% | +1.050% |
| 2009 | 36 | 66.7% | +1.926% |
| 2010 | 36 | 77.8% | +1.683% |
| 2011 | 47 | 55.3% | +0.448% |
| 2012 | 48 | 70.8% | +0.929% |
| 2013 | 48 | 68.8% | +0.619% |
| 2014 | 48 | 70.8% | +0.833% |
| 2015 | 48 | 45.8% | +0.211% |
| 2016 | 48 | 47.9% | +0.195% |
| 2017 | 48 | 60.4% | +0.017% |
| 2018 | 48 | 35.4% | -0.878% |
| 2019 | 48 | 41.7% | -0.570% |
| 2020 | 48 | 60.4% | +0.974% |
| 2021 | 48 | 79.2% | +1.590% |
| 2022 | 48 | 56.2% | +0.432% |
| 2023 | 48 | 66.7% | +0.752% |
| 2024 | 48 | 56.2% | -0.006% |
| 2025 | 48 | 39.6% | -0.159% |
| 2026 | 36 | 47.2% | -0.437% |

By instrument (net of base costs):

| Instrument | Trades | Win rate | Net per trade |
|---|---:|---:|---:|
| ^NSMIDCP | 225 | 63.6% | +0.697% |
| ^NSEBANK | 225 | 52.9% | +0.433% |
| ^CNXIT | 225 | 56.0% | +0.391% |
| ^CNXPHARMA | 188 | 59.6% | +0.361% |

## H12: Turn of the month, 15 country ETFs

Traded as: the ETFs themselves.

| Period | Trades | Win rate | Avg win | Avg loss | Profit factor | Net per trade | t | Max drawdown | Sharpe |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2001-2012 | 2009 | 56.4% | +2.53% | -2.49% | 1.32 | +0.346% | 4.67 | -54.6R | 0.55 |
| 2013-2026 | 2325 | 53.6% | +2.03% | -1.92% | 1.22 | +0.195% | 3.54 | -73.6R | 0.27 |
| All 2001-2026 | 4334 | 54.9% | +2.27% | -2.18% | 1.27 | +0.265% | 5.85 | -100.9R | 0.40 |

Random baseline (the same four-day hold and stop entered on random days, simultaneous entries kept together): +0.111% gross per trade vs +0.368% for the strategy; p = 0.013 (Holm-adjusted 0.039).

| # | Criterion | Value | Pass |
|---|---|---|---|
| 1 | At least 50 trades | 4334 | yes |
| 2 | Win rate at least 50% | 54.9% | yes |
| 3 | Expectancy above 0 at base and 1.5x costs | +0.265% / +0.214% | yes |
| 4 | t-statistic at least 2.0 | 5.85 | yes |
| 5 | Beats random entries (Holm-adjusted p < 0.05) | 0.039 | yes |
| 6 | Profit factor at least 1.3 | 1.27 | **no** |
| 7 | Avg loss at most 1.5x avg win; worst trade no worse than -3R | -2.18% vs +2.27%; worst -2.3R | yes |
| 8 | Expectancy above 0 in each half of the span | +0.346% / +0.195% | yes |
| 9 | Expectancy above 0 in each third of the span | +0.369% / +0.053% / +0.384% | yes |
| 10 | 60%+ of instruments profitable; still positive without the top instrument | 100% of 15 instruments; +0.246% without EWZ | yes |
| 11 | Cluster-robust t-statistic (signal weeks as clusters) at least 2.0 | 2.02 | yes |

**Decision: REJECTED.**

Informational: 69% of years (10+ trades) were profitable, the measure rounds 1-4 required to be at least 70%.

By year (net of base costs):

| Year | Trades | Win rate | Net per trade |
|---|---:|---:|---:|
| 2001 | 144 | 54.9% | +0.746% |
| 2002 | 144 | 45.1% | -0.549% |
| 2003 | 144 | 75.7% | +1.627% |
| 2004 | 147 | 59.2% | +0.224% |
| 2005 | 156 | 64.1% | +1.192% |
| 2006 | 156 | 51.9% | +0.146% |
| 2007 | 156 | 54.5% | -0.692% |
| 2008 | 156 | 40.4% | -0.572% |
| 2009 | 156 | 58.3% | +1.149% |
| 2010 | 156 | 80.8% | +1.848% |
| 2011 | 165 | 47.9% | -0.761% |
| 2012 | 179 | 55.3% | +0.304% |
| 2013 | 180 | 40.0% | -0.410% |
| 2014 | 180 | 35.0% | -0.557% |
| 2015 | 180 | 46.1% | +0.002% |
| 2016 | 180 | 50.0% | +0.188% |
| 2017 | 180 | 60.6% | +0.390% |
| 2018 | 180 | 33.3% | -0.716% |
| 2019 | 180 | 68.3% | +0.432% |
| 2020 | 180 | 73.3% | +1.898% |
| 2021 | 180 | 63.9% | +0.293% |
| 2022 | 180 | 53.9% | +0.223% |
| 2023 | 180 | 39.4% | -0.338% |
| 2024 | 180 | 55.6% | +0.000% |
| 2025 | 180 | 71.1% | +0.923% |
| 2026 | 135 | 54.8% | +0.192% |

By instrument (net of base costs):

| Instrument | Trades | Win rate | Net per trade |
|---|---:|---:|---:|
| EWZ | 309 | 53.1% | +0.512% |
| EWY | 309 | 55.0% | +0.480% |
| EWW | 309 | 55.3% | +0.425% |
| EWT | 309 | 58.3% | +0.385% |
| FXI | 264 | 53.4% | +0.324% |
| INDA | 176 | 59.1% | +0.302% |
| EWA | 309 | 57.3% | +0.301% |
| EWH | 309 | 55.0% | +0.264% |
| EWS | 309 | 53.4% | +0.242% |
| EWC | 309 | 57.0% | +0.208% |
| EWU | 309 | 57.0% | +0.173% |
| MCHI | 186 | 48.9% | +0.155% |
| EWJ | 309 | 52.8% | +0.103% |
| EWG | 309 | 52.4% | +0.072% |
| EWL | 309 | 55.3% | +0.010% |

## H13: Momentum, top 3 of the 9 US sector SPDRs monthly

Traded as: the ETFs themselves.

| Period | Trades | Win rate | Avg win | Avg loss | Profit factor | Net per trade | t | Max drawdown | Sharpe |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2000-2012 | 480 | 57.1% | +4.27% | -4.23% | 1.34 | +0.623% | 2.50 | -145.9% | 0.45 |
| 2013-2026 | 480 | 60.8% | +4.17% | -3.68% | 1.76 | +1.093% | 4.71 | -59.5% | 0.91 |
| All 2000-2026 | 960 | 59.0% | +4.22% | -3.97% | 1.53 | +0.858% | 5.04 | -145.9% | 0.67 |

Random baseline (three ETFs picked at random from the same month's eligible list): +0.816% gross per trade vs +0.901% for the strategy; p = 0.202 (Holm-adjusted 0.355).

| # | Criterion | Value | Pass |
|---|---|---|---|
| 1 | At least 50 trades | 960 | yes |
| 2 | Win rate at least 50% | 59.0% | yes |
| 3 | Expectancy above 0 at base and 1.5x costs | +0.858% / +0.837% | yes |
| 4 | t-statistic at least 2.0 | 5.04 | yes |
| 5 | Beats random entries (Holm-adjusted p < 0.05) | 0.355 | **no** |
| 6 | Profit factor at least 1.3 | 1.53 | yes |
| 7 | Avg loss at most 1.5x avg win | -3.97% vs +4.22% | yes |
| 8 | Expectancy above 0 in each half of the span | +0.623% / +1.093% | yes |
| 9 | Expectancy above 0 in each third of the span | +0.312% / +1.053% / +1.214% | yes |
| 10 | 60%+ of instruments profitable; still positive without the top instrument | 100% of 9 instruments; +0.795% without XLK | yes |
| 11 | Cluster-robust t-statistic (signal weeks as clusters) at least 2.0 | 3.54 | yes |

**Decision: REJECTED.**

Informational: 78% of years (10+ trades) were profitable, the measure rounds 1-4 required to be at least 70%.

By year (net of base costs):

| Year | Trades | Win rate | Net per trade |
|---|---:|---:|---:|
| 2000 | 36 | 36.1% | -0.106% |
| 2001 | 36 | 50.0% | -0.114% |
| 2002 | 36 | 38.9% | -1.426% |
| 2003 | 36 | 69.4% | +2.788% |
| 2004 | 36 | 63.9% | +1.229% |
| 2005 | 36 | 61.1% | +1.885% |
| 2006 | 36 | 52.8% | +0.128% |
| 2007 | 36 | 52.8% | +0.338% |
| 2008 | 36 | 41.7% | -2.299% |
| 2009 | 36 | 66.7% | +1.408% |
| 2010 | 36 | 69.4% | +2.214% |
| 2011 | 36 | 55.6% | +0.153% |
| 2012 | 36 | 77.8% | +1.218% |
| 2013 | 36 | 72.2% | +1.838% |
| 2014 | 36 | 66.7% | +1.116% |
| 2015 | 36 | 52.8% | -0.308% |
| 2016 | 36 | 52.8% | +0.955% |
| 2017 | 36 | 69.4% | +1.491% |
| 2018 | 36 | 55.6% | -0.476% |
| 2019 | 36 | 69.4% | +1.686% |
| 2020 | 36 | 55.6% | +1.537% |
| 2021 | 36 | 66.7% | +2.116% |
| 2022 | 36 | 52.8% | +0.536% |
| 2023 | 36 | 58.3% | +0.979% |
| 2024 | 36 | 61.1% | +1.353% |
| 2025 | 36 | 69.4% | +1.121% |
| 2026 | 24 | 50.0% | +2.299% |

By instrument (net of base costs):

| Instrument | Trades | Win rate | Net per trade |
|---|---:|---:|---:|
| XLY | 125 | 61.6% | +1.293% |
| XLI | 94 | 67.0% | +1.285% |
| XLK | 141 | 60.3% | +1.226% |
| XLE | 109 | 55.0% | +1.158% |
| XLF | 94 | 53.2% | +0.740% |
| XLV | 101 | 61.4% | +0.699% |
| XLB | 102 | 55.9% | +0.592% |
| XLP | 80 | 57.5% | +0.230% |
| XLU | 114 | 57.9% | +0.206% |

## H14: Momentum, top 3 of 15 country ETFs monthly

Traded as: the ETFs themselves.

| Period | Trades | Win rate | Avg win | Avg loss | Profit factor | Net per trade | t | Max drawdown | Sharpe |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2001-2012 | 462 | 57.1% | +6.24% | -6.08% | 1.37 | +0.959% | 2.57 | -299.2% | 0.45 |
| 2013-2026 | 462 | 58.4% | +4.46% | -4.72% | 1.33 | +0.648% | 2.22 | -105.5% | 0.43 |
| All 2001-2026 | 924 | 57.8% | +5.34% | -5.41% | 1.35 | +0.803% | 3.39 | -299.2% | 0.44 |

Random baseline (three ETFs picked at random from the same month's eligible list): +0.797% gross per trade vs +0.906% for the strategy; p = 0.177 (Holm-adjusted 0.355).

| # | Criterion | Value | Pass |
|---|---|---|---|
| 1 | At least 50 trades | 924 | yes |
| 2 | Win rate at least 50% | 57.8% | yes |
| 3 | Expectancy above 0 at base and 1.5x costs | +0.803% / +0.752% | yes |
| 4 | t-statistic at least 2.0 | 3.39 | yes |
| 5 | Beats random entries (Holm-adjusted p < 0.05) | 0.355 | **no** |
| 6 | Profit factor at least 1.3 | 1.35 | yes |
| 7 | Avg loss at most 1.5x avg win | -5.41% vs +5.34% | yes |
| 8 | Expectancy above 0 in each half of the span | +0.959% / +0.648% | yes |
| 9 | Expectancy above 0 in each third of the span | +0.965% / +0.557% / +0.888% | yes |
| 10 | 60%+ of instruments profitable; still positive without the top instrument | 67% of 15 instruments; +0.682% without EWY | yes |
| 11 | Cluster-robust t-statistic (signal weeks as clusters) at least 2.0 | 2.23 | yes |

**Decision: REJECTED.**

Informational: 62% of years (10+ trades) were profitable, the measure rounds 1-4 required to be at least 70%.

By year (net of base costs):

| Year | Trades | Win rate | Net per trade |
|---|---:|---:|---:|
| 2001 | 36 | 47.2% | -0.252% |
| 2002 | 36 | 44.4% | -1.196% |
| 2003 | 36 | 72.2% | +3.290% |
| 2004 | 36 | 61.1% | +1.517% |
| 2005 | 36 | 66.7% | +4.351% |
| 2006 | 36 | 66.7% | +1.872% |
| 2007 | 36 | 52.8% | +2.235% |
| 2008 | 36 | 25.0% | -5.589% |
| 2009 | 36 | 66.7% | +2.704% |
| 2010 | 36 | 58.3% | +2.318% |
| 2011 | 36 | 52.8% | -1.038% |
| 2012 | 36 | 75.0% | +1.729% |
| 2013 | 36 | 52.8% | +0.110% |
| 2014 | 36 | 58.3% | +0.342% |
| 2015 | 36 | 36.1% | -1.833% |
| 2016 | 36 | 75.0% | +1.518% |
| 2017 | 36 | 72.2% | +1.576% |
| 2018 | 36 | 36.1% | -1.848% |
| 2019 | 36 | 61.1% | +0.912% |
| 2020 | 36 | 80.6% | +2.982% |
| 2021 | 36 | 47.2% | -0.040% |
| 2022 | 36 | 52.8% | -0.349% |
| 2023 | 36 | 47.2% | -0.781% |
| 2024 | 36 | 55.6% | -0.007% |
| 2025 | 36 | 75.0% | +3.255% |
| 2026 | 24 | 66.7% | +4.259% |

By instrument (net of base costs):

| Instrument | Trades | Win rate | Net per trade |
|---|---:|---:|---:|
| FXI | 55 | 63.6% | +1.970% |
| EWY | 88 | 55.7% | +1.951% |
| EWS | 50 | 58.0% | +1.473% |
| MCHI | 44 | 59.1% | +1.301% |
| EWT | 79 | 63.3% | +1.293% |
| EWZ | 106 | 53.8% | +1.103% |
| EWW | 113 | 58.4% | +0.965% |
| EWL | 65 | 63.1% | +0.535% |
| EWA | 70 | 64.3% | +0.477% |
| EWC | 49 | 59.2% | +0.178% |
| EWU | 33 | 63.6% | -0.029% |
| EWH | 38 | 47.4% | -0.049% |
| EWJ | 50 | 52.0% | -0.112% |
| INDA | 39 | 53.8% | -0.447% |
| EWG | 45 | 46.7% | -1.065% |
