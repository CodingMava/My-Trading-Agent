# Kite minute data: what is available (investigated 13 Oct 2026)

Checked before buying anything or starting new research, with the day's Kite session and read-only
requests (`python -m trader.data.kite check NIFTYBEES.NS --interval 1m --days 5`, and single-day probes).
Nothing was bought, saved or traded.

## Access and cost

- This account's Kite Connect app already has historical data: 1-minute bars came back for the last three
  sessions (1,125 bars, all valid). Nothing needs to be bought.
- Zerodha's prices since 2025: the data APIs (live and historical) cost Rs 500 a month, cut from Rs 2,000
  in March 2025; historical data has had no add-on fee since 8 Feb 2025; the order and account APIs are
  free. A static IP is needed only for placing orders.
- Limits: 3 historical requests a second, and at most 60 days of 1-minute bars per request (the client asks
  for 30). One stock's full history is about 140 requests, under a minute; all fifty NIFTY stocks about 40
  minutes, well within one day's session (sessions expire at 06:00 IST).

## Depth and quality

- 1-minute bars start around 1 Feb 2015 (none on 15 Jan 2015): about 11.7 years, 375 bars on a full day.
- Adjusted for corporate actions: RELIANCE's 2016 prices already reflect its later bonuses, and TRENT shows
  no jump at its 1 Jan 2026 bonus, which Yahoo's daily data got wrong.
- NIFTYBEES and RELIANCE, Feb 2015 to Oct 2026: about 1.08 million bars each on 2,896 days, no duplicate
  timestamps, 96-99% of days complete each year. A few short days a year are special sessions (Muhurat
  trading); about 575 bars in all fall outside 09:15-15:29.
- NIFTYBEES was thinly traded before 2020: 17,000-44,000 minutes a year without a trade in 2015-2019, almost
  none since. Intraday tests on it are realistic only from 2020.

## Two limits that shape any intraday research

- **Survivorship.** Kite's instrument list holds only what is listed today: HDFC Ltd (merged into HDFC Bank
  in 2023) and the old TATAMOTORS are missing, so their history can't be fetched. A stock-picking test on
  Kite data alone would still leave out the stocks that dropped out, which flatters rules that buy falling
  stocks. Index instruments (the NIFTY 50 index, NIFTYBEES) don't have this problem. A stock universe needs
  to be rebuilt as it was at each date, from NSE's index-change notices.
- **NSE's closing auction, from 3 Aug 2026.** In F&O stocks, which include every NIFTY 50 stock, continuous
  trading now ends at 15:15 and the closing price is set by an auction from 15:15 to 15:35. Instruments
  outside F&O, such as NIFTYBEES, still trade to 15:30. Their minute bars stop at 15:14 (RELIANCE has had
  360 bars a day since 3 Aug 2026), so a rule that exits "at the close" must use the auction price, and the
  last 15 minutes of the history differ before and after that date. The live system's 15:15 time exits
  must be re-checked against the auction before any real order ([runbook](../runbook.md), "Before the first
  real order").

## What an honest intraday test needs

- Entries at the open of the minute after the signal's bar, plus slippage; never at the opening print
  itself (round 6's gap rules filled at the open, which flattered them).
- Zerodha's intraday (MIS) charges, a minimum trade size, and no trades in a stock at its price band or
  under exchange surveillance (ASM/GSM).
- Exits by 15:10 in F&O stocks, before the auction, or at the auction price modelled as such.
- An intraday paper-trading path: today's engine is end-of-day only.
- The project's standards, unchanged: at least a 50% win rate, positive expectancy after all costs, a
  limited drawdown, better than random entries, out of sample, and corrected for the twenty hypotheses
  already tested.

## The frozen dataset (13 Oct 2026)

`data/kite_minute/nifty_1m` (git-ignored: Kite's data is for this account's own use), with checksums and a
validation report in its manifest. 1-minute bars of NIFTYBEES and the NIFTY 50 index (^NSEI), 1 Jan 2020
to 12 Oct 2026: 628,692 and 628,721 bars on the same 1,684 sessions, no duplicate timestamps, no
validation errors. Only completeness and data errors were examined: no returns, signals or patterns, which
belong after a pre-registration.

- **Complete:** 96-100% of each year's sessions have all 375 minutes; the rest are a few special sessions
  (Muhurat trading, about an hour in the evening) and short days.
- **NIFTYBEES' opening prints are unreliable in 2020-2022:** 117 of its 118 bar-to-bar jumps above 5% are
  at the 09:15 bar, and 115 of those snap back the next minute (5 Mar 2020: a 119.40 close, then a
  142.95 "open" in a bar that closed at 120.30). None since 2023. A test must never fill at the 09:15
  bar's open. NIFTYBEES also had 541 minutes without a trade in 2020, almost none since.
- **The index:** no volume, by nature. Its few moves above 5% in a minute are all genuine: the March
  2020 crash (opening gaps, and the rebound after the 13 Mar circuit-breaker halt) and the 7 Apr 2025
  opening gap. Since NSE's closing auction began on 3 Aug 2026, 686 of its 735 bars from 15:15
  are flat: its stocks stop trading continuously at 15:15, so the index only moves again at the auction.
  NIFTYBEES (not an F&O instrument) trades normally to 15:29.
- **Loading it:** the research loaders' filter for Yahoo's holiday placeholders (flat bars with no
  volume) would drop 539 real NIFTYBEES minutes and 828 index minutes. Don't apply it to minute data.
- **The Budget-day session of Sunday 1 Feb 2026** is in Kite's bars but missing from Yahoo's, and was
  missing from `config/market_calendars.toml` too; it has been added there as a special session.

## Next step (to approve first)

Pre-register an intraday round on this frozen dataset: rules, costs and criteria pinned before any rule
runs on the data, with the realistic execution above and the project's standards.
