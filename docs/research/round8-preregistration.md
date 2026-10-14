# Research round 8 pre-registration: stock momentum on a survivorship-free NSE universe

> **Pinned on 14 Oct 2026 at 01:38 IST, before any trade or return was computed and before any signal was looked at.**
> The only results seen from the data are the data-quality and universe checks in "Data audit" (a dry run of the
> loader also computed the scores, which were not printed or inspected). This file's SHA-256 (LF line endings) is
> recorded in `trader/research/round8.py`, which refuses to run if the file changes. It was not committed or pushed:
> this session had no authorisation to commit, so there is no public timestamp (see "Protocol").

## Why this round

- **23 hypotheses failed** (H1-H14, C1-C6, I1-I3). The project's own rule for restarting research was new data, and it
  named the most important gap: "a NIFTY universe as it was at each date, instead of today's members".
- **New data that closes that gap.** NSE's daily capital-market bhavcopies, downloaded from the exchange's archive:
  every security quoted on every session from January 2005 to October 2026, including companies later delisted,
  merged or suspended. A universe chosen from them at each month-end, by liquidity, has no survivorship bias.
- **The effect: cross-sectional momentum.** Stocks with the highest returns over the past year, skipping the latest
  month, have tended to keep outperforming for the next months.
  - Jegadeesh and Titman, *Journal of Finance* 1993 (US, 1965-1989); Rouwenhorst, *Journal of Finance* 1998 (12
    European countries) and 1999 (20 emerging markets); Asness, Moskowitz and Pedersen, *Journal of Finance* 2013
    (eight markets and asset classes).
  - India, corrected for survivorship: Agarwalla, Jacob and Varma (IIMA working paper 2013-09-05) report a momentum
    factor averaging 21.2% a year in 1993-2012, long-short, with illiquid stocks excluded.
  - NSE's own Nifty200 Momentum 30 index (launched August 2020): 18.6% against 12.7% a year for the Nifty 200 from
    April 2005 to 2020, but that history is a back-test published by the index provider, not live returns.
- **Why it may fail.** Momentum crashes in sharp market rebounds (Daniel and Moskowitz, *Journal of Financial
  Economics* 2016), its profits shrink after trading costs (Lesmond, Schill and Zhou, *JFE* 2004), and India's
  long-only momentum indices lost heavily from late 2024. US post-earnings drift, a related under-reaction effect, has
  disappeared in large stocks (Martineau, *Critical Finance Review* 2022).
- **How it relates to H3.** H3 (top 5 of today's NIFTY 50 by 12-1 momentum, 2022-2026) failed only one criterion: five
  random stocks from the same list did nearly as well. Its universe had survivorship bias and its span was four years.
  This round is the same family on different data: a point-in-time universe of 300 stocks, a 13-year decision span,
  a protective stop that the risk engine requires, and costs at the engine's position size. It is counted as two new
  hypotheses in the project's multiple-testing record, and its kinship with H3 is stated here so it can't be presented
  as a new discovery.

## Stated before the test: the most likely outcome is failure

- **Power.** Each hypothesis holds 5 stocks a month for about 158 decision months. If a month's 5-stock average beats a
  random 5-stock pick from its tier by d, with a monthly standard deviation of about 4% (large) or 5% (mid caps), the
  smallest d that criterion 12 (p below 0.002) can detect is about 0.92% (N1) or 1.14% (N2) a month. If the true edge is
  0.6% a month, criterion 12 passes with probability about 16% (N1) or 9% (N2).
- **Drawdown.** At 0.5% of equity risked per position and 5 positions, 20R is a 10% fall in equity, the kill switch.
  A month in which all five positions are stopped costs 5R. A long-only stock strategy with no market filter can
  reach 20R in one bad quarter.
- **Win rate.** A 10% stop cuts losing trades at about -1R but also stops some trades that would have recovered. The
  50% floor may bind.
- Nothing will be changed if this happens. The outcome is reported as it is.

## Data

- **Raw files** (git-ignored, unchanged, downloaded from NSE on 14 Oct 2026):
  - `data/round8/bhavcopy_raw/<year>/`: 5,402 daily capital-market bhavcopies from nsearchives.nseindia.com, 3 Jan 2005
    to 13 Oct 2026. The old format (`cmDDMONYYYYbhav.csv.zip`) runs to 5 Jul 2024, the UDiFF format
    (`BhavCopy_NSE_CM_0_0_0_YYYYMMDD_F_0000.csv.zip`) after. Weekdays without a file were holidays (NSE answered 404);
    25 weekend sessions (Muhurat, Budget-day and disaster-recovery sessions) were found by the audit and added.
  - `data/round8/corporate_actions/`: NSE's corporate-action records for equities (nseindia.com/api), one JSON file per
    month, 262 files, 42,156 records.
  - `data/round8/symbolchange.csv`: NSE's 1,066 symbol changes (SHA-256 `3467c4ca...`).
- **Frozen table:** `python -m trader.research.nse_bhavcopy build` writes `data/round8/nse_eq/panel.parquet`: series EQ,
  BE and BZ only, 8,620,050 rows, 4,029 securities, SHA-256
  `afb79ad2ce778f187059302864576fba478c9d5a59ae5853cf909007cfb0fb01`. Its manifest (SHA-256
  `d05a44fe666a454d148f0ba4a510f28c1eebbfa9b60c402276e01e3da735be2f`) records every raw file's SHA-256. `isins.csv`
  (SHA-256 `d29b000d...`) holds each symbol's ISINs.
- **Renames:** a renamed company's histories are joined under its latest symbol only where the new symbol's first
  previous close is within 2% of the old symbol's last close. 671 of the 1,066 renames were joined; 383 involved a symbol
  outside these series; 12 were refused (dates overlap, or prices don't continue). TISCO-TATASTEEL, UTIBANK-AXISBANK,
  INFOSYSTCH-INFY, MOTHERSUMI-MOTHERSON and ZOMATO-ETERNAL are among those joined.

### Corporate actions: what the audit found, and the treatment

NSE's previous close in these files is **not** adjusted for corporate actions: a 2:1 split shows as a 50% fall on its
ex-date (HDFCBANK 19 Sep 2019; RELIANCE's bonus on 28 Oct 2024). The first draft of this file assumed otherwise; the
audit caught it before any rule ran. Each security's prices are therefore adjusted by a factor on each ex-date, built in
`trader/research/nse_bhavcopy.py` from NSE's own records, matched by the security's latest symbol (as NSE files them):

| Action | Factor on the ex-date | Rows |
|---|---|---:|
| Split (old to new face value), bonus a:b, or both | new / old face value, times b / (a + b). A record whose ex-date doesn't match the price change moves to the session within 5 that does, or isn't applied | 1,369 applied; 5 not |
| Rights a:b at subscription price S | the theoretical ex-rights price, (P + nS) / ((1 + n) P) with n = a / b, when the opening gap agrees within 15% | 232 applied; 15 not |
| Dividend of at least 5% of the previous close (special dividends) | 1 - dividend / previous close, if the open fell by at least half of it | 504 records |
| Demerger, scheme of arrangement, capital reduction, bonus debentures or preference shares | the ex-date's close / previous close, when it fell more than 3%. The close, because on demerger days the opening print came from a special price-discovery session and was often far off (Adani Enterprises 3 Jun 2015, Sintex 25 May 2017) | 197 applied |
| A split or bonus missing from the records (mostly 2005-2008) | inferred when the open fell more than 40%, to within 6% of a standard split or bonus ratio | 377 |
| Reliance Industries, 18 Jan 2006: the demerger of four ADA companies, with no record | the ex-date's close / previous close | 1 |

Ordinary dividends under 5% are not adjusted: returns are price returns, for the strategy and the random picks alike.

### Data audit (14 Oct 2026, before any rule ran; no returns, signals or trades were computed)

- Sessions per year: 242-252 (2026: 193, to 13 Oct). One gap over 5 days (1-7 Oct 2014, holidays). Equity rows per
  session: 578 to 2,696. No duplicate security-days; no missing, zero or negative prices; no high below low; no open or
  close outside the day's range.
- The previous close continues the previous row's close on 99.997% of rows; the rest are corporate-action days. Before
  the weekend sessions were added, 25 sessions showed most previous closes jumping: that is how they were found.
- Every move of more than 25% in a stock whose 126-session median traded value exceeded Rs 2 crore was listed. Since
  June 2012 (everything the decision span's scores and trades can touch), 35 remain after the adjustments:
  - real events: Educomp 2013, Financial Technologies (NSEL) 2013, Unitech 2015, Amtek Auto 2015, Indiabulls Real
    Estate 2017, the PSU bank recapitalisation (25 Oct 2017), RCOM, PC Jeweller 2018, DHFL 2018, Infibeam 2018, Jet
    Airways 2019, Vodafone Idea, Yes Bank (March 2020), IndusInd and Bandhan Bank (26 Mar 2020), ZEEL 2021, Force Motors
    2024, Policybazaar 2026, and circuit-limit days;
  - demerger days whose close-based factor leaves the day's opening print far off (Future Retail 21 Jun 2013, Adani
    Enterprises 3 Jun 2015, Sintex 25 May 2017): only a trade entering or exiting at that day's open, or stopped that
    day, would be affected; any such trade is listed in the results;
  - unexplained: Goodyear India opened 37% lower on 20 Apr 2026, with no record. It is left as a price move.
- Before June 2012 (stage 1 only) some adjustments are less reliable: records are incomplete in 2005-2008, demerger
  opening prints were erratic (Indiabulls 2 Jan 2007, Zee News 15 Apr 2010, Triveni 3 May 2011), and a few 1:2 bonuses
  (factor 0.67) fall short of the inference threshold (Orchid Chemicals 15 Sep 2005). Stage 1 is replication only.
- **The universe** (eligibility and liquidity only): eligible stocks per month-end rose from 641 (2006) to 1,820
  (2026); the first month-end with 300 eligible was 28 Feb 2006. The 300th stock's median daily traded value was at
  least Rs 0.75 crore in every month of the decision span, so a Rs 50,000 position is within the risk engine's 1%
  liquidity limit throughout (in 2009 the floor fell to Rs 0.33 crore: stage 1 only).
- No exchange-traded fund is among the securities without an ISIN that ever reached Rs 2 crore a day (all 112 are
  companies, mostly under old symbols), so Appendix A is empty.

### What the data can't do, and how that is met

- **Price returns.** Ordinary dividends (under 5%) are missing for the strategy and the random picks alike. A momentum
  rule's picks tend to pay lower dividends than the average stock, which favours the strategy slightly against its
  baseline: about 1% a year of dividend yield on the average stock makes the baseline at most about 0.08% a month too
  low. The results report this bound next to the excess return.
- **Fills at the open.** Since 1 April 2013 every equity stock's official open comes from NSE's pre-open call auction
  (SEBI circular CIR/MRD/DP/6/2013; NIFTY stocks since 18 October 2010), so the decision span's opens are auction prices,
  at which a market order placed in the pre-open window fills. Before that, most opens in stage 1 are first trades.
  Slippage is added on top (below).
- **Daily bars can't show the order of prices within a day.** A rule with a stop and no target never needs it.
- **No order book.** Upper-circuit locks are approximated (below); partial fills are not modelled.
- **Corporate actions inside a trade** are neutral: trades are valued in adjusted prices, so a split, bonus, rights
  issue or special dividend during a holding doesn't move its return. A demerged company's new shares are not followed
  after the ex-date: the parent's factor removes their value, so the trade's return is the parent's alone.

## Definitions

- **Sessions:** the dates that have a bhavcopy file, in order. s-k is the k-th session before s.
- **Signal date:** the last session of each calendar month.
- **Equity share:** a security any of whose symbols carries an ISIN beginning `INE` in the files. Securities that never
  carry an ISIN (NSE added ISINs to the file in 2011) count as equity shares unless their symbol is in Appendix A. A
  security with an ISIN beginning `INF` (a fund) is never an equity share.
- **Adjusted price:** raw price x `adj`, the product of every later corporate-action factor of the security.
- **Eligible at signal date s** (all known at s's close):
  1. an equity share, quoted in series EQ on s;
  2. raw close on s at least Rs 10;
  3. at least 273 rows up to s, and rows on at least 227 of the 252 sessions ending at s (not dormant or suspended);
  4. a momentum score (below).
- **Liquidity:** the median of the daily traded value over the 126 sessions ending at s, counting a session without a
  row as zero.
- **Tiers** (ranked by liquidity among the eligible, highest first; ties by symbol): **N1** = ranks 1-100; **N2** =
  ranks 101-300.
- **Momentum score:** adjusted close at s-21 / adjusted close at s-252 - 1. At a session without a row, the latest
  earlier row's adjusted close is used; if that row is more than 10 sessions earlier, the score is undefined.
- **Selection:** the 5 highest scores in the tier (ties by symbol).

## The trade

| When | What happens | Uses only |
|---|---|---|
| Signal date s, after the close | Eligibility, liquidity tiers, scores, the 5 picks per tier | Bhavcopies up to s |
| Session s+1, open | Buy each pick at the official open | The open; that the stock has a row on s+1 |
| s+1 to s' (the next signal date) | The stop is watched every session: a session whose low reaches the stop exits there | Each session's open and low |
| s'+1, open | Exit at the official open if not stopped | The open |

- **Not bought** (the slot stays in cash for the month): no row on s+1, or an open of 0, or the stock locked at its
  upper band all day on s+1 (raw open = high = low = close, and the open above the previous close).
- **Stop:** 10% below the entry price (the stop level of Han, Zhou and Zhu, "Taming momentum crashes", 2016; the risk
  engine refuses positions without a stop). It is watched from the entry session itself (its low comes after the
  open) through s'. A session whose low reaches it fills at the stop, or at that session's open if the open was
  already below it. After a stop, the slot stays in cash until the next month's entries.
- **Exit:** at the open of s'+1. If the stock has no row that session (suspended), at the open of its next session with
  a row. If it never trades again in the data (delisted), at its last close; every such trade is listed in the
  results, with a sensitivity of -30% on that close.
- **One trade per stock per month.** A stock picked again the next month is a new trade with full costs (as H3): the
  gross return is the same as holding through, and the costs are conservative. The informational section reports the
  costs if retained stocks were not re-traded.
- **R:** 10% of the entry price. Gross return = exit / entry - 1 in adjusted prices.

## Costs, size and risk limits

- **Charges** (zerodha.com/charges, checked 14 Oct 2026, delivery CNC): brokerage 0; STT 0.1% on the buy and on the
  sell; NSE transaction charge 0.00307% a side; SEBI Rs 10 a crore a side; stamp duty 0.015% on the buy; GST 18% on the
  transaction and SEBI charges; DP charge Rs 15.34 a sale.
- **Size:** the risk engine's: 0.5% of equity at risk with a 10% stop is a position of 5% of equity, Rs 50,000 on the
  Rs 10,00,000 paper account; five positions are 25% of equity. The DP charge is 0.031% of that.
- **Slippage:** 0.05% a side for N1, 0.10% a side for N2 (wider spreads in mid caps), and once more on a stop's exit.
- **Round trip:** N1 0.3532%, N2 0.4532% (a stopped trade adds 0.05% or 0.10%).
- **Risk limits as the engine applies them:** at most 5 positions; 5% of equity each (below the 20% cap); a position at
  most 1% of the stock's average daily traded value (Rs 50,000 needs Rs 50 lakh a day; the liquidity floors of both tiers
  are reported); no new entries after a 2% daily loss; the kill switch at a 10% drawdown. The per-trade test doesn't
  apply the daily-loss rule or the kill switch; the informational portfolio replay does.

## The random baseline, precisely

- **The question:** does picking the 5 highest scores beat picking 5 stocks at random from the same tier in the same
  months, with the same entry, stop and exit?
- **The pools:** for each signal month in the span and each tier, every tier member that could be bought on s+1 (by
  the rule above), traded by the same rules, net of the same costs.
- **The draws:** 20,000 draws from numpy's `default_rng(8)`. In each draw, for every month in which the hypothesis
  entered k trades, k distinct members are drawn from that month's pool without replacement. A draw's statistic is the
  mean net return over all its trades.
- **The p-value:** p = (k + 1) / (20,000 + 1), with k the number of draws whose statistic is at least the hypothesis's
  own mean net return.

## Multiple testing

- **Within the round (criterion 5):** the two raw p-values are Holm-corrected together: the smaller is doubled, the
  larger kept (never below the doubled smaller).
- **Across the project (criterion 12):** each raw p must be below 0.05 / 25 = 0.002. The 25 hypotheses tested on
  historical data are H1-H14, C1-C6, I1-I3 and N1-N2. Forward test 1 is not counted.

## Two stages, in order

1. **Stage 1, development and replication:** signals from the first month-end with eligible stocks (early 2006)
   through 31 May 2013. It overlaps the period of the published Indian evidence, so it checks the implementation on
   real data and whether this rule reproduces that evidence. It decides nothing. It writes
   `docs/research/round8-stage1.md`.
   - Allowed after stage 1: fixing a bug, documented with both outputs.
   - Not allowed: changing any rule, parameter, cost, criterion or span.
2. **Stage 2, the decision:** signals from 28 Jun 2013 (the last session of June 2013) through 31 Aug 2026 (the last
   trade exits at the open of 1 Oct 2026). Run once, only after stage 1's results exist. It writes
   `docs/research/round8-results.md` and the evidence for N1 and N2.

## Pass criteria (stage 2, each hypothesis on its own; every criterion must pass)

| # | Criterion | What it guards against |
|---|---|---|
| 1 | At least 50 trades | Too little evidence |
| 2 | Win rate at least 50% (a trade wins if its net return is above 0) | Strategies that lose most of the time (your rule) |
| 3 | Expectancy above zero at base costs and at 1.5x costs | Profits that costs, or worse costs, would erase |
| 4 | t-statistic at least 2.0 | Profit indistinguishable from noise |
| 5 | Holm-adjusted random-baseline p below 0.05 | Picks no better than random stocks from the same tier |
| 6 | Profit factor at least 1.3 | Thin profits |
| 7 | Average loss at most 1.5x the average win; no trade worse than -3R | Small wins paid for by rare large losses |
| 8 | Expectancy above zero in each half of the span (split at the midpoint date) | Profits from one period only |
| 9 | At least 70% of calendar years with 10+ trades profitable | Instability from year to year |
| 10 | At least 60% of stocks with 5+ trades profitable, and expectancy above zero without the stock that contributed most | Profits from one stock |
| 11 | Cluster-robust t-statistic at least 2.0, trades clustered by signal month | Five trades a month that are really one bet |
| 12 | Raw random-baseline p below 0.05 / 25 = 0.002 | Luck across every hypothesis this project has tried |
| 13 | Drawdown no deeper than 20R: cumulative R, trades in exit order | Losses the decay rule and the kill switch wouldn't tolerate |

## The 50% win-rate floor

Your rule, kept. A momentum strategy with a stop has right-skewed trades: losses are cut near -1R, a few winners run
to several R. Such a strategy can make money with fewer than half its trades winning. If N1 or N2 passes every
criterion except 2, it is REJECTED under the current rules and labelled INELIGIBLE UNDER CURRENT POLICY in the report.
The floor isn't changed here; a change would be your decision, made before new data is looked at.

## Decisions

| Outcome | Decision |
|---|---|
| Every criterion passes | Candidate for PAPER, once you approve. Before paper trading: a daily bhavcopy feed for the point-in-time universe, the monthly rule in `trader/strategies`, and the Level 5 paper stage. Live trading stays locked. |
| Only criterion 1 fails | Inconclusive (RESEARCH) |
| Anything else | REJECTED |

## Informational (stage 2; no effect on the decisions)

- **Benchmarks:** the tier's equal-weighted average (what a random pick earns), the NIFTY 50 price index (^NSEI,
  `data/round4/nse_nifty_daily`), both over the same months.
- **Portfolio views,** monthly: at the engine's size (5 x 5% of equity, the rest in cash earning nothing) and fully
  invested (5 x 20%). CAGR, volatility, Sharpe, Sortino, maximum drawdown.
- **The risk engine replayed:** the Rs 10,00,000 account at the engine's size, marked to market every session: its
  deepest drawdown, and the first session on which the 10% kill switch would have engaged.
- **Uncertainty:** Wilson 95% interval for the win rate; month-clustered bootstrap 95% intervals for expectancy and for
  the monthly excess over random picks (stationary block bootstrap over months, mean block 6, 10,000 resamples,
  seed 9); a deflated Sharpe ratio (Bailey and López de Prado 2014) for the monthly excess, with 25 trials.
- **Costs** at 0x, 1x, 1.5x, 2x and 3x; and without re-trading retained stocks.
- **Parameter sensitivity** (never used to choose): lookback 6-1, 9-1 and 12-1 months; 5 or 10 picks; a 10% stop or
  none: 12 variants per tier. The probability of backtest overfitting (Bailey, Borwein, López de Prado and Zhu 2017,
  combinatorially symmetric cross-validation over 16 blocks of months) across those 12 variants.
- **Regimes:** NIFTY 50 above or below its 200-session average at the signal date; India VIX above or below its
  250-session median (`data/round6/aux_daily`); each calendar year.
- **Delisted and suspended holdings,** listed one by one.

Patterns seen in these reports are hypotheses for future data, not findings.

## Protocol

1. This file is completed with the data audit, then pinned: its SHA-256 and the frozen panel's are recorded in the
   runner, with the time. (The project's usual step, committing and pushing the pin for a public timestamp, needs your
   authorisation, which this session doesn't have; the pin time is recorded in the runner and in the results instead,
   and the runner's own SHA-256 is written into each results file.)
2. `trader/research/round8.py` is written and tested on synthetic data only.
3. Stage 1 runs. Then stage 2 runs once. The runner refuses stage 2 if this file or the frozen panel changed, or if
   stage 2's results already exist.
4. Results are reported whatever they show.

## Appendix A: exchange-traded funds without an ISIN in the data

None found (see the audit).
