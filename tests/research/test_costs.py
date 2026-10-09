import pytest

from trader.research.costs import (AUDIT_2026_10_08, US_COMMISSION_FREE, ZERODHA_DELIVERY, ZERODHA_INTRADAY,
                                   CostModel)


def test_zerodha_intraday_matches_a_hand_calculation():
    costs = ZERODHA_INTRADAY.with_slippage(0).breakdown(100_000)
    assert costs["brokerage"] == pytest.approx(40.0)  # Rs 20 cap per order (0.03% would be Rs 30)
    assert costs["stt"] == pytest.approx(25.0)  # 0.025% on the sell side
    assert costs["exchange"] == pytest.approx(5.94)
    assert costs["sebi"] == pytest.approx(0.20)
    assert costs["gst"] == pytest.approx(0.18 * (40 + 5.94 + 0.20))
    assert costs["stamp"] == pytest.approx(3.0)
    assert sum(costs.values()) == pytest.approx(82.4452)


def test_brokerage_cap_only_binds_on_large_orders():
    assert ZERODHA_INTRADAY.breakdown(10_000)["brokerage"] == pytest.approx(6.0)  # 0.03% = Rs 3 per order


def test_delivery_round_trip_and_the_fixed_dp_charge():
    large = ZERODHA_DELIVERY.round_trip(100_000)
    small = ZERODHA_DELIVERY.round_trip(10_000)
    assert large == pytest.approx(0.002975852)
    assert small - large == pytest.approx(15.34 / 10_000 - 15.34 / 100_000)  # small positions pay more


def test_itemised_models_agree_with_the_audit_constants():
    assert ZERODHA_INTRADAY.round_trip(100_000) == pytest.approx(AUDIT_2026_10_08["india_intraday"]["base"], abs=1e-6)
    assert US_COMMISSION_FREE.round_trip(10_000) == pytest.approx(AUDIT_2026_10_08["us_intraday"]["base"], abs=1e-5)


def test_one_side_costs_add_up_to_the_round_trip():
    for model in (ZERODHA_INTRADAY, ZERODHA_DELIVERY, US_COMMISSION_FREE):
        for notional in (10_000, 100_000, 1_000_000):
            both = model.one_side(notional, "buy") + model.one_side(notional, "sell")
            assert both == pytest.approx(sum(model.breakdown(notional).values()))
    assert ZERODHA_DELIVERY.one_side(100_000, "sell") > ZERODHA_DELIVERY.one_side(100_000, "buy")  # DP charge
    with pytest.raises(ValueError):
        ZERODHA_DELIVERY.one_side(100_000, "short")


def test_notional_must_be_positive():
    with pytest.raises(ValueError):
        CostModel("x").round_trip(0)
