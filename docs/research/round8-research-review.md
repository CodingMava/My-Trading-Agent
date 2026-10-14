# Strategy research review, October 2026

Written 14 Oct 2026 for the mission "find, research and validate the best suitable trading strategy". It covers the
sources read, the audit of the 23 hypotheses already tested, which strategy families are worth a test and which are
not, and round 8, the test that this review led to. Published findings are kept apart from this project's own tests.

## 1. What could and couldn't be read

- **The four books** (Chan, *Algorithmic Trading*, Wiley 2013; Aronson, *Evidence-Based Technical Analysis*, Wiley
  2006; López de Prado, *Advances in Financial Machine Learning*, Wiley 2018; Kaufman, *Trading Systems and Methods*,
  6th ed., Wiley 2019) were **not available in full**: Wiley Online Library and O'Reilly answered 403 without a
  subscription. Only tables of contents and publisher descriptions were read. Nothing here claims what the books say
  beyond that. Their methods are used through the authors' peer-reviewed papers instead: the deflated Sharpe ratio and
  the probability of backtest overfitting (López de Prado and co-authors), data-mining bias and multiple-testing
  correction (the method of Aronson's book, applied as Holm and Bonferroni corrections since round 6).
- **Papers:** abstracts, publisher and SSRN records, and summaries were read for every paper cited. Where only a
  summary was available, that is said. No paper's full tables were reproduced.
- **Official data and rules:** NSE's archive (bhavcopies, symbol changes, the equity list), SEBI's circular on the
  pre-open call auction and SEBI's 2024 study of intraday traders, Zerodha's charges page, Kite Connect's historical
  data documentation, the SEC's EDGAR API terms.

## 2. Sources

| Source | Venue, year | What it tests | Markets, horizon, period | Survives costs? | Reproduced? | Main limits | Use here |
|---|---|---|---|---|---|---|---|
| Jegadeesh & Titman, "Returns to buying winners and selling losers" | *J. Finance* 1993, doi 10.1111/j.1540-6261.1993.tb04702.x | Cross-sectional momentum | US stocks, 3-12 month holds, 1965-1989 | Long-short, before costs | Yes: Jegadeesh & Titman 2001 (US, later years); Rouwenhorst 1998, 1999; Asness et al. 2013 | Partial reversal after a year; crashes | Round 8's rule |
| Rouwenhorst, "Local return factors and turnover in emerging stock markets" | *J. Finance* 1999 | Momentum, size, value | 20 emerging markets, monthly | Before costs | — | Country detail not checked | Momentum exists in emerging markets |
| Asness, Moskowitz & Pedersen, "Value and momentum everywhere" | *J. Finance* 2013 | Value and momentum | 8 markets and asset classes | Before costs | — | Developed markets mostly | Breadth of the evidence |
| Agarwalla, Jacob & Varma, "Four factor model in Indian equities market" | IIMA WP 2013-09-05; data library updated to 2025 | Indian factors, survivorship-corrected | India, monthly, 1993-2012 (paper) | Long-short, before costs | Data library maintained by the authors | Long-short, includes small stocks | Momentum factor 21.2% a year in India |
| NSE Indices, Nifty200 Momentum 30 whitepaper | NSE 2020 | A long-only momentum index | Nifty 200, semi-annual, 2005-2020 | Index, no costs | Live since Aug 2020 | Back-test by the index provider | 18.6% vs 12.7% a year (back-test) |
| Daniel & Moskowitz, "Momentum crashes" | *JFE* 2016 | When momentum fails | US and international | — | — | Crashes come from the short side mostly | Why a long-only version, and why drawdown matters |
| Han, Zhou & Zhu, "Taming momentum crashes: a simple stop-loss strategy" | SSRN 2014/2016 | A 10% stop on momentum | US, 1926-2011 | — | — | Long-short; working paper; read through summaries | Round 8's stop |
| Cooper, Gutierrez & Hameed, "Market states and momentum" | *J. Finance* 2004 | Momentum after up vs down markets | US, 1929-1995 | — | Not found in the UK (Galariotis et al. 2014) | — | Not used: a filter would be a choice made with hindsight |
| Lesmond, Schill & Zhou, "The illusory nature of momentum profits" | *JFE* 2004 | Momentum after trading costs | US, 1980-1998 | **No**, at typical costs | Contested by Frazzini, Israel & Moskowitz (2018, AQR's own trades) | Cost estimates | Costs must be modelled; India's 0.2% STT matters |
| Moskowitz, Ooi & Pedersen, "Time series momentum" | *JFE* 2012, doi 10.1016/j.jfineco.2011.11.003 | Own-past-return trend | 58 futures, 1-12 months | Futures, low costs | Hurst, Ooi & Pedersen 2017 (a century) | Strongest when diversified across asset classes | Not tested: see families |
| Gao, Han, Li & Zhou, "Market intraday momentum" | *JFE* 2018 | First half hour predicts the last | SPY | — | Round 7 found nothing in NIFTYBEES | — | Already tested (I1-I3) |
| Martineau, "Rest in peace post-earnings announcement drift" | *Critical Finance Review* 2022 | Post-earnings drift | US | — | Disputed by two 2025 papers; Subrahmanyam (2025) finds t 1.43 without microcaps, 2001-2024 | — | Earnings drift is not a candidate in large caps |
| Gervais, Kaniel & Mingelgrin, "The high-volume return premium" | *J. Finance* 2001 | Volume shocks predict returns | US, 1-day/1-week shocks, ~1 month | Not established | Kaniel, Ozoguz & Starks, *JFE* 2012: 41 countries | India's own result not found | A future candidate on round 8's data |
| Bondarenko & Muravyev, "Market return around the clock" | *JFQA* 2023 | Overnight vs day returns | S&P 500 futures, 2004-2018 | The European-open window, after costs | — | US futures | Overnight family: see families |
| Gatev, Goetzmann & Rouwenhorst, "Pairs trading" | *RFS* 2006 | Pairs | US, 1962-2002 | Yes, then declining | Do & Faff, *FAJ* 2010: still declining | Needs shorting | Not a candidate in Indian cash equities |
| Zarattini & Aziz, "Can day trading really be profitable?" | SSRN 4416622, 2023 | 5-minute opening-range breakout | QQQ, 2016-2023 | Commissions only | A replication reports zero after spread and slippage | About a quarter of trades win | Ineligible under the 50% floor |
| Bailey, Borwein, López de Prado & Zhu, "The probability of backtest overfitting" | *J. Computational Finance* 2017 | Selection among backtests | — | — | — | Needs many configurations | Round 8 reports PBO across its variants |
| Bailey & López de Prado, "The deflated Sharpe ratio" | *J. Portfolio Management* 2014, SSRN 2460551 | Sharpe after selection and non-normality | — | — | — | Depends on counting trials honestly | Round 8 reports it with 25 trials |
| SEBI, "Analysis of intraday trading by individuals in the equity cash segment" | SEBI, July 2024 | Who wins at intraday trading | India, FY19-FY23 | — | — | Aggregate, not strategy-level | Over 70% of individual intraday traders lost money in FY23; loss-makers paid a further 57% of their losses in costs |
| CFA Institute, "Backtesting and simulation" | Refresher reading 2026 | Method | — | — | — | — | Rolling windows, scenario analysis, survivorship and look-ahead bias |
| QuantConnect, research guide | Online | Method | — | — | — | — | One hypothesis at a time; out-of-sample will be worse |

## 3. The 23 hypotheses already tested

| Group | Ids | What failed | Kind of failure | Status of the family |
|---|---|---|---|---|
| Original intraday rules (audit, 2026-10-08) | R1-R8S | All lost 0.10-0.20% a trade, 34-43% winners; none beat random entries | Weak rules, made worse by 0.14% costs | Exhausted. (R3 never fired: contradictory conditions, an implementation fault, but its idea is in the same family.) |
| Oversold pullback (RSI-2) | H1, H2, H4-H8 | H1 costs; H2 too few trades; H4, H6, H8 no better than random days; H5 decayed; H7 beat random but average loss 1.57x the win | Weak or unstable edge; India's delivery STT | **Retired** (round 3): no variant is tested again |
| Momentum, today's NIFTY 50 | H3 | Random picks from the same list did as well | Data-limited: survivorship bias, 4-year span | **Round 8 re-opens it on survivorship-free data** |
| Turn of the month | H9-H12 | H9 p 0.067; H10 t 1.65; H11 failed only "each third profitable" (lost money 2024-2026); H12 failed only profit factor (1.27) | Real but not steady enough | Forward test 1 (H11, H12) on new sessions; nothing before 2030 |
| Sector and country momentum | H13, H14 | Three random sectors or countries did as well | Market drift, not selection | Exhausted at ETF level |
| Chan's buy-on-gap | C1, C2 | Weak, lost money 2024-2025 (C1); flat (C2) | Weak edge | Exhausted (book rules from secondary sources) |
| Chan's opening gap | C3, C4 | Lost money before costs: gaps faded | No edge | Exhausted |
| Time-series momentum, one index | C5, C6 | No better than random months; lower CAGR than holding | Drift | Exhausted for a single index |
| Intraday momentum, NIFTYBEES | I1-I3 | No edge before costs; 0.12% costs | No edge | Exhausted |

What the record shows: 19 of the 23 failed to beat random entries (criterion 5). The four that beat them (H7, H10,
H11, H12) failed on the size of losses, on sample size and stability, on stability, and on profit factor. The most
common reason for failure is not costs or bad code; it is that the profit was what any entry in the same market at the
same times would have earned.

## 4. Strategy families: which to test now

| Family | Evidence | Fit with this project | Decision |
|---|---|---|---|
| **Cross-sectional stock momentum, India** | Strong, including survivorship-corrected Indian data | Kite delivery orders, monthly, 5 positions; the one family whose earlier test (H3) was data-limited; new data fixes that | **Tested: N1 (large), N2 (mid)** |
| Time-series momentum, diversified | Strong across asset classes (MOP 2012; a century, HOP 2017) | Single-index versions failed (C5, C6); a diversified long/flat ETF version rebalanced monthly can't beat random months at p < 0.002 in the ~18 years of ETF history (too few independent months), and trend rules' trade win rates in this project's audit were 36% (R4) | Not tested: low power; likely ineligible under the 50% floor |
| Short-term mean reversion | Strong historically, decays; costs bind | Retired family; India's 0.2% delivery STT | Not tested |
| Intraday range breakouts | ORB papers report ~a quarter of trades winning | Fails the 50% floor by construction; India intraday costs 0.12%; Kite minute data lacks delisted stocks | Not tested: **ineligible under current policy** |
| Sector rotation | Weak after drift (H13, H14) | Same family at ETF level | Not tested |
| High-volume return premium | Good cross-country evidence; India not confirmed | Fits round 8's data; needs weekly turnover against 0.35-0.45% delivery round trips | Not tested now; the natural next candidate on this data |
| Earnings drift, events | Gone in US large caps since about 2006 | No point-in-time event data: EDGAR needs a declared contact (your decision), India's results timestamps need NSE/BSE APIs | Not tested |
| Pairs, statistical arbitrage | Declining since the 1990s | Overnight shorts need F&O or stock lending; intraday pairs pay 0.24% a round trip | Not tested |
| Overnight drift, NIFTY | US evidence strong; Indian summaries show 64% of nights up | All its risk is the overnight gap, with no possible stop: on 23 Mar 2020 NIFTY opened about 9% lower, which breaks the -3R worst-trade rule at any risk unit below 3%; a round trip a day costs about 0.05-0.08% | Not tested: **structurally ineligible under current risk rules** |
| Low volatility | Mixed in India after beta | Its advantage is risk-adjusted; the gate compares raw returns with random picks | Not tested |

The US: free US stock data on Yahoo lacks delisted companies, so every US stock-level test is survivorship-biased and
could at best be UNPROVEN; ETF-level ideas were tested in rounds 2-6 (H6-H9, H12-H14, C2, C4, C6). No genuinely new,
adequately powered US hypothesis can be tested with the data the project can reach today. The US stays as it is: H12
(country ETFs) in forward test 1, and NO TRADE.

## 5. Market and timeframe

- **Intraday** (India): SEBI's study found over 70% of individual intraday traders in the cash segment lost money in
  FY23. Round 7 found NIFTYBEES' last half hour had no edge before 0.12% costs. Intraday tests need minute data for
  many stocks, which Kite has only for stocks still listed.
- **Swing** (days to weeks): rounds 1-6 covered it on daily data; India's delivery STT (0.1% each side) makes short
  holds in single stocks expensive.
- **Positional** (a month or more): costs matter least, and NSE's own files give a survivorship-free history back to
  2005. The risk rules (0.5% risk a position, five positions, a 10% kill switch) make the exposure small, so a
  strategy's edge per trade, in R, is what counts.

Round 8 is therefore positional, in India, executable through Kite delivery orders. India and the US are judged
separately; nothing is combined across markets.

## 6. Round 8: what was built, tested and found

Files: [pre-registration](round8-preregistration.md) (pinned 14 Oct 2026 01:38 IST), [stage 1](round8-stage1.md)
(development, 2006-2013, decides nothing), [results](round8-results.md) (the decision, 2013-2026, run once at 01:48 IST).

**The data, first.** 5,402 of NSE's daily files (January 2005 to 13 October 2026, delisted companies included) and
42,156 corporate-action records, frozen with checksums. The audit, made before any rule ran, caught three things that
would have corrupted any test:

- NSE's previous-close field is not adjusted for corporate actions: every split and bonus shows as a crash. Prices are
  now adjusted from NSE's own records (splits, bonuses, rights, special dividends, demergers), with a logged inference
  for 2005-2008 records that are missing.
- 25 weekend sessions (Muhurat, Budget days, disaster-recovery drills) were missing from a weekday download; they were
  found because previous closes stopped matching, and added.
- NSE files old records under companies' current symbols (Infosys's 2006 bonus is under INFY, not INFOSYSTCH), so
  matching by the symbol of the day missed them.

After the adjustments, every large one-day move since mid-2012 in a liquid stock is a real event (Yes Bank 2020, DHFL
2018, Jet Airways 2019 and the like), except one unexplained gap (Goodyear India, 20 Apr 2026), left as it is.

**The test.** At each month-end, NSE equity shares were ranked by liquidity; N1 took the 100 most liquid, N2 ranks
101-300. Each bought the 5 stocks with the best 12-1 month return at the next open, with a 10% stop, sold at the open
after the next month-end, paid Zerodha's delivery costs at the risk engine's position size (Rs 50,000, 0.35-0.45% a
round trip), and was compared with 5 random stocks from the same tier traded by the same rules.

| | N1: 100 most liquid | N2: ranks 101-300 |
|---|---:|---:|
| Trades (2013-2026) | 795 | 792 |
| Win rate (net of costs) | 48.6% | 43.9% |
| Average win / average loss | +10.0% / -8.6% | +16.3% / -9.6% |
| Median trade | -0.59% | -4.68% |
| Net per trade | +0.41% | +1.75% |
| Random picks, same tier and rules | +0.52% | +0.67% |
| p vs random (raw / Holm) | 0.64 / 0.64 | 0.0019 / 0.0038 |
| t / cluster-robust t | 1.00 / 0.72 | 2.92 / 2.21 |
| Profit factor | 1.09 | 1.32 |
| Calendar years profitable | 50% | 64% |
| Drawdown in R | 45.5R | 34.1R |
| At the engine's size (5 x 5% of equity) | CAGR 1.0%, drawdown 20-21%; kill switch Feb 2016 | CAGR 5.0%, drawdown 16-18%; kill switch Sep 2015 |
| Criteria failed | 2, 4, 5, 6, 8, 9, 10, 11, 12, 13 | 2 (win rate), 9 (years), 13 (drawdown) |
| Decision | **REJECTED** | **REJECTED** |

For comparison over the same months: the NIFTY 50 price index rose 12.8% a year; N2's tier, equally weighted and simply
held (no stops, no costs), 17.5% a year; N2 fully invested (5 x 20%), 16.5% a year with a 58% drawdown.

**What N2 shows, and what it doesn't.**

- It beat random picks from its own tier by about 1.1% a month, the second hypothesis in 25, after H11 (the turn of
  the month in India's sector indices), to clear the project's cross-round bar (p below 0.05 / 25 = 0.002). It passed
  that bar by a hair: p 0.0019.
- In all 12 parameter variants (lookback 6, 9 or 12 months; 5 or 10 picks; stop or none) it beat random picks, and the
  probability of backtest overfitting across them was 0.28. It stayed profitable at three times the costs.
- After the fact (not part of the decision), its significance depends on a few very large winners (p 0.07 without the
  best 5 of 792 trades, 0.32 without the best 10) and on 2020-2026 (first half: p 0.09). Momentum's returns are
  right-skewed, so this is expected, but it means a live version would depend on catching a handful of trades.
- It fails three of the project's rules, not one. Even without the 50% floor it would be REJECTED, on year-to-year
  stability and on drawdown. It is not "INELIGIBLE UNDER CURRENT POLICY" alone; it is rejected.
- Its deflated Sharpe ratio (25 trials) is 0.71, short of the 0.95 that would make selection luck an unlikely
  explanation.

N1 says something too: among India's 100 most liquid stocks, 12-1 momentum with a 10% stop had no edge over random picks
in 2013-2026, consistent with the evidence that momentum is weaker in large, well-covered stocks.

## 7. Decision

- **No candidate is PROVISIONALLY QUALIFIED.** The system stays in **NO TRADE**, in India and in the US.
- **N1: REJECTED.** **N2: REJECTED** under the current rules (criteria 2, 9 and 13).
- **The strongest leads the project has** are now two: H11 (turn of the month, Indian sector indices, failed only
  "each third of the span profitable", being judged on new sessions in forward test 1) and N2 (mid-cap momentum).
  Neither is ready for paper trading.

## 8. The win-rate floor, the stop and the drawdown limit: what round 8 shows

These are your policy settings; nothing here changes them.

- **Win rate.** N2 made money while winning 44% of its trades because its average win (+16.3%) was 1.7 times its
  average loss (-9.6%). That is the profile the 50% floor excludes. Without the stop (informational variants), the same
  picks won 51-54% of their trades, so the floor and the stop interact.
- **The stop.** The risk engine requires a stop and accepts up to 15% (`max_stop_distance`). At 10%, many momentum
  trades were stopped and later recovered: without the stop, N1's edge over random picks was +0.51% a month instead of
  -0.11%, and N2's +1.82% instead of +1.07%.
- **The drawdown limit.** At 0.5% of equity risked per position and five positions, 20R is a 10% fall in equity, the
  kill switch. Any long-only stock strategy will reach it in a broad market fall: N2 would have been stopped in
  September 2015, N1 in February 2016.
- **A possible review, for you to decide before new data is looked at:** whether a strategy whose losses are capped by
  a stop and whose wins are not should face the 50% floor, and whether momentum-type rules should be allowed the
  engine's full 15% stop. Either change would make new hypotheses, which could only be judged on data that doesn't
  exist yet.

## 9. What would move this forward (in order)

1. **Forward test 2 (needs your approval).** Pin N2's rules unchanged and judge them only on months after the pin, with
   NSE's daily files and corporate-action records collected automatically by a scheduled task (the code to read them
   exists now). Honest timeline: about 60 trades a year; confirming a +1% a month edge at the project's bar needs
   roughly 8-10 years, while a forward loss can retire it much sooner. A companion hypothesis with the engine's
   maximum 15% stop could be pinned at the same time, judged on the same future months and counted in the record.
2. **US:** nothing new can be tested on free data. Yahoo lacks delisted stocks; survivorship-free US data is paid (not
   bought); SEC EDGAR's event data needs a declared contact (a name and email in each request), your decision.
3. **Not recommended:** more rounds on the same daily data, intraday rules (SEBI's FY23 study, round 7, Kite's minute
   data without delisted stocks), and rules whose losses come mainly from overnight gaps (structurally ineligible
   under the -3R rule).
4. **Operations note (not caused by this work):** the news collector hasn't fetched since 00:15 on 14 Oct because the
   laptop slept through its 15-minute runs (result 0x800710E0); NSE's feed answers normally. The health check's warning
   is correct. Keeping the PC awake during market hours, or giving the task "run as soon as possible after a missed
   start", would fix it (re-running `scripts/register_tasks.ps1` needs your OK).

## 10. Project changes (all on branch `round8-research`, none committed or pushed)

- **New code:** `trader/research/nse_bhavcopy.py` (NSE daily files and corporate actions to a frozen, adjusted,
  survivorship-free panel; audit), `trader/research/round8.py` (the two-stage runner).
- **New tests:** `tests/research/test_round8.py` (26 tests on synthetic data, including the pin),
  `tests/research/test_round8_regression.py` (slow: reproduces stage 2 from the frozen data).
- **New documents:** `docs/research/round8-preregistration.md`, `round8-stage1.md` (with `round8-stage1-run1.md`, the
  first output), `round8-results.md`, this review; evidence `docs/research/evidence/N1.research.json` and
  `N2.research.json`.
- **Changed:** `config/strategies.toml` (N1 and N2 added as REJECTED; no other entry touched), `README.md` (status
  line, a round 8 section, commands, roadmap row 3i).
- **Data (git-ignored):** `data/round8/` (5,402 bhavcopies, 262 corporate-action files, NSE's symbol changes and equity
  list, the frozen panel). Not to be committed or redistributed.
- **Untouched:** order placement, the risk engine, the kill switch, Kite, live trading, the paper accounts, forward
  test 1, every earlier result. Nothing is at PAPER or above, so the daily run still records NO TRADE (it did on 14 Oct
  at 18:00, on this branch).

## 11. What is verified and what isn't

- **Verified:** the loader and runner on synthetic data; the stage-2 numbers reproduce exactly from the frozen data
  (slow regression); the registry loads with the new entries; the full fast test suite passes (see the final check
  below); the corporate-action treatment against known events (HDFC Bank 2019, Reliance 2024, Vodafone Idea 2019, Aster
  DM 2024, Adani Enterprises 2015).
- **Not verified or limited:**
  - the four books were not read (no legitimate full-text access); papers were read through abstracts, publisher
    records and summaries;
  - ordinary dividends are not in the returns (a bias of at most about 0.08% a month against the baseline);
  - before April 2013 opening prices could be stray first trades, and 2005-2008 corporate-action records are
    incomplete (stage 1 only);
  - rights issues are adjusted at the theoretical ex-rights price, an approximation;
  - the pin has no public timestamp: committing and pushing it needed your authorisation, which this mission withheld,
    so its time is recorded in the files and in this session's record only;
  - a strategy that passes software tests is not thereby shown to make money; none of these results is a forecast.
