"""Trade records for tax and reporting: each round trip's dates, quantities, prices, charges and holding period,
classified by its country's rule and grouped by tax year. They are for checking against the broker's statement
(for Zerodha, the tax P&L in Console), which is the one to file from.

    python -m trader.execution.records live 2026     # live trades: India's FY 2026-27, the US's 2026
    python -m trader.execution.records paper 2026    # paper trades, the same way

Writes state/reports/<account>-<year>.csv (git-ignored) and prints the totals. India: a buy and sale on the
same day is intraday (speculative business income); listed shares held for more than 12 months are long-term
(LTCG), anything else short-term (STCG); the year runs from 1 April. US: more than a year is long-term; the
year is the calendar year. Charges are the cost model's estimates; the contract notes have the exact ones.
"""
from __future__ import annotations

import argparse
from collections import deque
from datetime import date

import pandas as pd

from trader.config import ROOT, load_settings
from trader.execution.eod import market_of
from trader.execution.oms import LiveStore
from trader.execution.store import PaperStore
from trader.research.costs import ZERODHA_DELIVERY, CostModel
from trader.strategies.catalog import CATALOG

COLUMNS = ["market", "symbol", "quantity", "buy_date", "buy_price", "buy_value", "sell_date", "sell_price",
           "sell_value", "charges", "gain", "held_days", "term"]


def one_year_later(day: date) -> date:
    try:
        return day.replace(year=day.year + 1)
    except ValueError:  # 29 February
        return day.replace(year=day.year + 1, day=28)


def term(market: str, bought: date, sold: date) -> str:
    if market != "US" and bought == sold:
        return "intraday"
    return "long-term" if sold > one_year_later(bought) else "short-term"


def tax_year(market: str, sold: date) -> int:
    """The year a sale belongs to: India's financial year (named by the year it starts) or the US calendar year."""
    return sold.year - 1 if market != "US" and sold.month < 4 else sold.year


def _row(symbol: str, quantity: int, bought: date, buy_price: float, sold: date, sell_price: float, charges: float) -> dict:
    market = market_of(symbol)
    buy_value, sell_value = quantity * buy_price, quantity * sell_price
    return {"market": market, "symbol": symbol, "quantity": quantity, "buy_date": bought, "buy_price": buy_price,
            "buy_value": buy_value, "sell_date": sold, "sell_price": sell_price, "sell_value": sell_value,
            "charges": charges, "gain": sell_value - buy_value - charges, "held_days": (sold - bought).days,
            "term": term(market, bought, sold)}


def from_paper(trades: pd.DataFrame) -> pd.DataFrame:
    """Paper round trips, as the paper engine closed them (charges are what it charged)."""
    rows = [_row(t.symbol, int(t.quantity), date.fromisoformat(t.entry_session), float(t.entry_price),
                 date.fromisoformat(t.exit_session), float(t.exit_price), float(t.fees)) for t in trades.itertuples()]
    return pd.DataFrame(rows, columns=COLUMNS)


def from_fills(fills: pd.DataFrame, costs: dict[str, CostModel] | None = None) -> pd.DataFrame:
    """Live round trips: each sale matched with the earliest unsold buys of the same stock (first in, first out),
    with charges estimated by the strategy's cost model. A sale with no buy to match raises: the records are
    wrong and must not be filed."""
    costs = costs if costs is not None else {key: spec.costs for key, spec in CATALOG.items()}
    lots: dict[str, deque] = {}
    rows = []
    for fill in fills.sort_values("id").itertuples():
        day, model = date.fromisoformat(fill.session), costs.get(fill.strategy_id, ZERODHA_DELIVERY)
        if fill.side == "buy":
            lots.setdefault(fill.symbol, deque()).append([int(fill.quantity), float(fill.price), day, model])
            continue
        remaining = int(fill.quantity)
        while remaining:
            if not lots.get(fill.symbol):
                raise ValueError(f"{fill.symbol}: a sale of {remaining} share(s) on {day} with no buy to match")
            lot = lots[fill.symbol][0]
            quantity = min(remaining, lot[0])
            charges = lot[3].one_side(quantity * lot[1], "buy") + model.one_side(quantity * float(fill.price), "sell")
            rows.append(_row(fill.symbol, quantity, lot[2], lot[1], day, float(fill.price), charges))
            lot[0] -= quantity
            remaining -= quantity
            if lot[0] == 0:
                lots[fill.symbol].popleft()
    return pd.DataFrame(rows, columns=COLUMNS)


def for_year(trips: pd.DataFrame, year: int) -> pd.DataFrame:
    if trips.empty:
        return trips
    return trips[[tax_year(m, d) == year for m, d in zip(trips["market"], trips["sell_date"])]].reset_index(drop=True)


def totals(trips: pd.DataFrame) -> pd.DataFrame:
    """Gains by country and term."""
    if trips.empty:
        return pd.DataFrame(columns=["market", "term", "trades", "gain"])
    return (trips.groupby(["market", "term"]).agg(trades=("gain", "size"), gain=("gain", "sum")).reset_index())


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Trade records for tax and reporting.")
    parser.add_argument("account", choices=["live", "paper", "paper-us"])
    parser.add_argument("year", type=int, help="India's financial year starting in April of this year; the US calendar year")
    args = parser.parse_args(argv)
    settings = load_settings()
    database = ROOT / {"live": settings.live_database, "paper": settings.paper_database,
                       "paper-us": settings.paper_us_database}[args.account]
    if not database.exists():
        raise SystemExit(f"No {args.account} records yet.")
    trips = (from_fills(LiveStore(database).table("live_fills")) if args.account == "live"
             else from_paper(PaperStore(database, settings.paper_starting_capital).trades()))
    trips = for_year(trips, args.year)
    target = ROOT / "state" / "reports" / f"{args.account}-{args.year}.csv"
    target.parent.mkdir(parents=True, exist_ok=True)
    trips.to_csv(target, index=False)
    print(f"{len(trips)} round trip(s) in India's FY {args.year}-{(args.year + 1) % 100:02d} and the US's {args.year}, "
          f"written to {target}")
    print(totals(trips).to_string(index=False) if len(trips) else "Nothing to report.")


if __name__ == "__main__":
    main()
