"""Phase 8's dry run: the Kite request behind each paper-trading step (nothing is sent; no network)."""
import dataclasses
import json
from datetime import date

import numpy as np
import pytest

from tests.execution.test_paper_trader import SIGNAL_DAY, UNIVERSE, bars, make_trader
from trader.config import load_settings
from trader.core.models import Position
from trader.execution import broker
from trader.execution.store import PaperStore


def requests(store, purpose=None):
    rows = store.table("dry_run_orders")
    rows = rows if purpose is None else rows[rows["purpose"] == purpose]
    return [(r.session, r.send_at, r.purpose, r.symbol, json.loads(r.request)) for r in rows.itertuples()]


def test_each_paper_step_becomes_the_kite_request_that_would_carry_it_out(tmp_path):
    trader = make_trader(tmp_path)  # AAA is stopped out, BBB sold on an exit signal, CCC sold on time
    trader.run(until=date(2026, 8, 18), start=SIGNAL_DAY)
    store = trader.store
    steps = [(session, at, purpose, symbol) for session, at, purpose, symbol, _ in requests(store)]
    assert steps == [*[("2026-08-10", "18:00", "entry", s) for s in ("AAA.NS", "BBB.NS", "CCC.NS")],
                     *[("2026-08-11", "09:20", "stop", s) for s in ("AAA.NS", "BBB.NS", "CCC.NS")],
                     ("2026-08-14", "18:00", "exit", "BBB.NS"),  # AAA's stop needs nothing: its GTT sells
                     ("2026-08-17", "09:20", "cancel stop", "BBB.NS"),
                     ("2026-08-17", "15:15", "cancel stop", "CCC.NS"), ("2026-08-17", "15:15", "time exit", "CCC.NS")]
    rows = store.table("dry_run_orders")
    assert set(rows["problems"]) == {""} and rows["tag"].is_unique and set(rows["tag"].str.len()) == {20}

    entry = requests(store, "entry")[0][4]
    assert entry["method"] == "POST" and entry["path"] == "/orders/amo"
    assert {k: v for k, v in entry["params"].items() if k != "tag"} == {
        "exchange": "NSE", "tradingsymbol": "AAA", "transaction_type": "BUY", "order_type": "MARKET", "quantity": 1000,
        "product": "CNC", "validity": "DAY", "market_protection": -1}
    stop = requests(store, "stop")[0][4]
    assert stop["path"] == "/gtt/triggers" and stop["params"]["condition"]["trigger_values"] == [95.95]  # 101 less 5%
    assert stop["params"]["condition"]["last_price"] == 101.0 and stop["params"]["orders"][0]["price"] == 91.15
    stop_tag = rows.loc[(rows["purpose"] == "stop") & (rows["symbol"] == "CCC.NS"), "tag"].item()
    assert requests(store, "cancel stop")[1][4] == {"method": "DELETE", "path": f"/gtt/triggers/<GTT {stop_tag}>",
                                                    "params": {}}
    assert requests(store, "time exit")[0][4]["params"]["transaction_type"] == "SELL"

    assert broker.describe(store).splitlines()[0] == "Kite requests for the 2026-08-17 session (dry run: none was sent)"
    assert broker.describe(store, SIGNAL_DAY).count("POST /orders/amo") == 3
    assert broker.describe(store, date(2026, 8, 12)) == "No Kite requests for the 2026-08-12 session."


def test_a_gap_below_the_stops_limit_turns_its_triggered_sell_into_a_market_order(tmp_path):
    frames = {"AAA.NS": bars({date(2026, 8, 13): {"open": 85.0, "high": 86.0, "low": 84.0, "close": 85.5}},
                             entries={SIGNAL_DAY}),  # opens below the GTT's limit of 91.15
              "BBB.NS": bars({date(2026, 8, 13): {"open": 93.0, "high": 94.0, "low": 92.0, "close": 93.5}},
                             entries={SIGNAL_DAY})}  # opens below the stop, but above that limit: the GTT's sell fills
    trader = make_trader(tmp_path, frames=frames)
    trader.run(until=date(2026, 8, 13), start=SIGNAL_DAY)
    assert set(trader.store.trades()["reason"]) == {"Stop Loss (gapped through)"}
    rows = trader.store.table("dry_run_orders")
    stop_tag = rows.loc[(rows["purpose"] == "stop") & (rows["symbol"] == "AAA.NS"), "tag"].item()
    assert [r[1:] for r in requests(trader.store, "gap exit")] == [
        ("09:20", "gap exit", "AAA.NS", {"method": "PUT", "path": f"/orders/regular/<order from GTT {stop_tag}>",
                                         "params": {"order_type": "MARKET", "market_protection": -1}})]


def test_us_stocks_get_no_kite_request(tmp_path):
    trader = make_trader(tmp_path, frames={"AAA": UNIVERSE["AAA.NS"]}, market="US", currency="$")  # placed by hand
    trader.run(until=date(2026, 8, 18), start=SIGNAL_DAY)
    assert len(trader.store.trades()) == 1 and trader.store.table("dry_run_orders").empty


def test_a_request_kite_would_refuse_is_recorded_and_alerted(tmp_path, monkeypatch):
    real = broker.problems
    monkeypatch.setattr(broker, "problems", lambda request: ["test refusal"] if request.purpose == "stop" else real(request))
    trader = make_trader(tmp_path)
    trader.run(until=date(2026, 8, 11), start=SIGNAL_DAY)
    rows = trader.store.table("dry_run_orders")
    assert set(rows.loc[rows["purpose"] == "stop", "problems"]) == {"test refusal"}
    assert set(rows.loc[rows["purpose"] == "entry", "problems"]) == {""}
    alerts = [text for text in trader.notifier.sent if "Dry-run order invalid" in text]
    assert len(alerts) == 3 and "Kite would refuse the stop for AAA.NS: test refusal" in alerts[0]
    assert "Kite would refuse it: test refusal" in broker.describe(trader.store)


def test_nse_tick_sizes():
    prices = (249.99, 250, 1000, 1000.05, 5000, 5000.5, 10000, 10001, 20000, 20005)
    assert [broker.tick_size(p) for p in prices] == [0.01, 0.05, 0.05, 0.10, 0.10, 0.50, 0.50, 1.00, 1.00, 5.00]
    assert broker.to_tick(95.953) == 95.95 and broker.to_tick(1234.56) == 1234.6 and broker.to_tick(1234.56, down=True) == 1234.5
    assert broker.on_tick(1234.5) and not broker.on_tick(1234.55)
    assert broker.to_tick(900.03) == 900.0 and broker.on_tick(900.0)  # rounds as if in the Rs 1,000-5,000 band
    assert broker.to_tick(180.07) == 180.05  # as if Rs 250-1,000: still a valid Rs 0.01 price
    assert broker.stop_limit(95.95) == 91.15 and broker.stop_limit(2000.0) == 1900.0  # 5% under the stop, on a tick


def test_requests_kite_would_refuse_are_caught():
    held = Position("T1", "AAA.NS", 10, 101.0, 95.95, date(2026, 8, 11))
    made = [broker.entry_order("k", "M&M.NS", 5), broker.exit_order("k", "BAJAJ-AUTO.NS", 5), broker.stop_order(held),
            broker.cancel_stop(held, broker.AFTER_OPEN), broker.gap_exit(held), broker.time_exit(held)]
    assert [broker.problems(request) for request in made] == [[]] * len(made)

    entry, stop = made[0], made[2]

    def order(**changes):
        return dataclasses.replace(entry, params={**entry.params, **changes})

    def gtt(condition=(), leg=(), **changes):
        params = {**stop.params, **changes}
        params["condition"] = {**stop.params["condition"], **dict(condition)}
        params["orders"] = [{**stop.params["orders"][0], **dict(leg)}]
        return dataclasses.replace(stop, params=params)

    refused = {
        "market protection": order(market_protection=0), "quantity": order(quantity=0),
        "whole number": order(quantity=np.int64(5)), "has no price": order(price=101.0), "CNC": order(product="MIS"),
        "tick": order(order_type="LIMIT", price=101.003), "order type": order(order_type="SL-M"),
        "transaction type": order(transaction_type="SHORT"), "isn't an NSE stock": order(exchange="BSE"),
        "carry its tag": order(tag="Eother"),
        "letters and digits": dataclasses.replace(entry, tag="E" * 21, params={**entry.params, "tag": "E" * 21}),
        "isn't a request": dataclasses.replace(entry, method="GET"),
        "turns the order into MARKET": dataclasses.replace(made[4], params={"order_type": "LIMIT", "market_protection": -1}),
        "fires at once": gtt(condition={"trigger_values": [102.0]}),
        "one trigger, one order": gtt(condition={"trigger_values": [95.95, 90.0]}),
        "above the trigger": gtt(leg={"price": 96.0}),
        "LIMIT sell of the same stock": gtt(leg={"tradingsymbol": "BBB"}),
        "trigger 95.953": gtt(condition={"trigger_values": [95.953]}),
        "single GTT": gtt(type="two-leg"),
    }
    for expected, request in refused.items():
        assert any(expected in problem for problem in broker.problems(request)), (expected, broker.problems(request))


def test_the_command_shows_the_latest_requests(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(broker, "ROOT", tmp_path)
    with pytest.raises(SystemExit, match="No paper records yet"):
        broker.main([])
    store = PaperStore(tmp_path / load_settings().paper_database, 1_000_000)
    assert broker.describe(store) == "No Kite requests prepared yet."
    request = broker.entry_order("T1:AAA.NS:2026-08-10:buy", "AAA.NS", 10)
    store.add_dry_run_order(SIGNAL_DAY, request.tag, request.symbol, request.purpose, request.send_at, request.json())
    store.close()
    broker.main([])
    assert "18:00  entry        AAA.NS         POST /orders/amo" in capsys.readouterr().out
