"""Trade records for tax and reporting."""
from datetime import date

import pytest

from tests.execution.test_paper_trader import SIGNAL_DAY, make_trader
from trader.execution import records
from trader.execution.oms import LiveStore
from trader.research.costs import ZERODHA_DELIVERY


def test_each_countrys_rules():
    assert records.term("NSE", date(2026, 8, 11), date(2026, 8, 11)) == "intraday"
    assert records.term("NSE", date(2025, 8, 11), date(2026, 8, 11)) == "short-term"  # 12 months is not more than 12
    assert records.term("NSE", date(2025, 8, 11), date(2026, 8, 12)) == "long-term"
    assert records.term("NSE", date(2024, 2, 29), date(2025, 2, 28)) == "short-term"
    assert records.term("NSE", date(2024, 2, 29), date(2025, 3, 1)) == "long-term"
    assert records.term("US", date(2026, 8, 11), date(2026, 8, 11)) == "short-term"  # no intraday class there
    assert records.tax_year("NSE", date(2027, 3, 31)) == 2026 and records.tax_year("NSE", date(2027, 4, 1)) == 2027
    assert records.tax_year("US", date(2027, 3, 31)) == 2027


def test_paper_round_trips(tmp_path):
    trader = make_trader(tmp_path)
    trader.run(until=date(2026, 8, 18), start=SIGNAL_DAY)
    trips = records.from_paper(trader.store.trades())
    assert len(trips) == 3 and set(trips["term"]) == {"short-term"} and set(trips["market"]) == {"NSE"}
    assert trips["gain"].sum() == pytest.approx(trader.store.trades()["net_pnl"].sum())
    assert len(records.for_year(trips, 2026)) == 3 and records.for_year(trips, 2025).empty
    assert records.totals(trips).to_dict("records") == [{"market": "NSE", "term": "short-term", "trades": 3,
                                                         "gain": pytest.approx(trips["gain"].sum())}]
    assert records.totals(trips.iloc[0:0]).empty


def test_live_round_trips_match_each_sale_to_the_earliest_buys(tmp_path):
    store = LiveStore(tmp_path / "live.db")
    store.add_fill(date(2026, 8, 11), "E1", "T1", "INFY.NS", "buy", 10, 100.0)
    store.add_fill(date(2026, 8, 12), "E2", "T1", "INFY.NS", "buy", 5, 110.0)
    store.add_fill(date(2026, 8, 13), "X1", "T1", "INFY.NS", "sell", 12, 120.0)  # the first lot and 2 of the second
    store.add_fill(date(2026, 8, 13), "E3", "T1", "TCS.NS", "buy", 3, 50.0)
    store.add_fill(date(2026, 8, 13), "X2", "T1", "TCS.NS", "sell", 3, 49.0)
    trips = records.from_fills(store.table("live_fills"), costs={"T1": ZERODHA_DELIVERY})
    assert list(zip(trips["symbol"], trips["quantity"], trips["buy_price"], trips["term"])) == [
        ("INFY.NS", 10, 100.0, "short-term"), ("INFY.NS", 2, 110.0, "short-term"), ("TCS.NS", 3, 50.0, "intraday")]
    charges = ZERODHA_DELIVERY.one_side(1000.0, "buy") + ZERODHA_DELIVERY.one_side(1200.0, "sell")
    assert trips.loc[0, "charges"] == pytest.approx(charges) and trips.loc[0, "gain"] == pytest.approx(200.0 - charges)
    store.add_fill(date(2026, 8, 14), "X3", "T1", "TCS.NS", "sell", 1, 49.0)
    with pytest.raises(ValueError, match="no buy to match"):  # wrong records must not reach a tax return
        records.from_fills(store.table("live_fills"))


def test_the_command_writes_the_years_records(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(records, "ROOT", tmp_path)
    with pytest.raises(SystemExit, match="No paper records yet"):
        records.main(["paper", "2026"])
    trader = make_trader(tmp_path / "state")  # the repository's settings keep paper records in state/paper.db
    trader.run(until=date(2026, 8, 18), start=SIGNAL_DAY)
    trader.store.close()
    records.main(["paper", "2026"])
    assert "3 round trip(s) in India's FY 2026-27" in capsys.readouterr().out
    assert (tmp_path / "state" / "reports" / "paper-2026.csv").read_text().count("\n") == 4
    records.main(["paper", "2025"])
    assert "Nothing to report." in capsys.readouterr().out
    with pytest.raises(SystemExit, match="No live records yet"):
        records.main(["live", "2026"])
