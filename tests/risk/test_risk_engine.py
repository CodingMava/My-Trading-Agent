from datetime import date

import numpy as np
import pandas as pd
import pytest

from trader.core.models import PortfolioState, Position, TradeIntent
from trader.portfolio.exposure import correlation, load_sectors, most_correlated, sector_of
from trader.portfolio.sizing import position_size
from trader.risk import killswitch
from trader.risk.engine import RiskEngine
from trader.risk.killswitch import KillSwitch
from trader.risk.limits import RiskLimits, load_limits

LIMITS = RiskLimits()
DAY = date(2026, 10, 9)


def intent(symbol="AAA.NS", price=1000.0, stop=0.05, sector="Tech", adv=None):
    return TradeIntent("S1", symbol, DAY, price, stop, sector, adv)


def held(symbol, quantity, price, sector="Tech"):
    return Position("S1", symbol, quantity, price, price * 0.95, DAY, sector, last_price=price)


def account(cash=1_000_000.0, positions=(), peak=None, day_start=None):
    state = PortfolioState(cash=cash, positions={p.symbol: p for p in positions})
    state.peak_equity = state.equity if peak is None else peak
    state.day_start_equity = state.equity if day_start is None else day_start
    return state


def engine(tmp_path, limits=LIMITS):
    return RiskEngine(limits, KillSwitch(tmp_path / "KILL_SWITCH"))


def failed(decision):
    return [c.name for c in decision.checks if not c.passed]


def test_sizing_spends_the_risk_budget_within_every_cap():
    size = position_size(1_000_000, 1_000_000, 1000, 0.05, LIMITS)
    assert (size.quantity, size.binding) == (100, "risk per trade")  # Rs 5,000 risk / Rs 50 per share
    assert position_size(1_000_000, 1_000_000, 1000, 0.01, LIMITS).binding == "max position"  # 200 shares
    assert position_size(1_000_000, 50_000, 1000, 0.05, LIMITS).quantity == 50  # cash
    assert position_size(1_000_000, 1_000_000, 1000, 0.05, LIMITS, avg_traded_value=4_000_000).quantity == 40
    assert position_size(1_000_000, 1_000_000, 1000, 0.05, LIMITS, lot_size=30).quantity == 90
    assert position_size(1_000_000, 1_000_000, 1000, 0.05, LIMITS, room={"sector limit": 30_000}).quantity == 30
    assert position_size(1_000_000, 1_000_000, 1000, float("nan"), LIMITS).quantity == 0


def test_an_ordinary_trade_is_approved(tmp_path):
    decision = engine(tmp_path).evaluate(intent(), account())
    assert decision.approved and decision.quantity == 100 and decision.reason == "approved"


def test_account_level_brakes(tmp_path):
    risk = engine(tmp_path)
    risk.kill_switch.engage("test")
    assert failed(risk.evaluate(intent(), account()))[0] == "kill switch"
    risk.kill_switch.release()
    assert "daily loss" in failed(risk.evaluate(intent(), account(day_start=1_030_000)))  # down 2.9% today
    decision = risk.evaluate(intent(), account(peak=1_200_000))  # 16.7% below the peak
    assert "drawdown" in failed(decision) and risk.kill_switch.engaged and "drawdown" in risk.kill_switch.reason
    assert not risk.evaluate(intent(), account()).approved  # stays blocked until a person releases it


def test_per_trade_limits(tmp_path):
    risk = engine(tmp_path)
    assert failed(risk.evaluate(intent(stop=0.0), account())) == ["stop", "size"]
    assert "stop" in failed(risk.evaluate(intent(stop=0.2), account()))
    assert failed(risk.evaluate(intent(), account(positions=[held("AAA.NS", 10, 1000)]))) == ["one position per stock"]
    five = [held(f"S{i}.NS", 10, 1000, sector=f"Sector{i}") for i in range(5)]
    assert failed(risk.evaluate(intent(), account(positions=five))) == ["position count"]
    assert failed(risk.evaluate(intent(), account(cash=100_000))) == ["size"]  # Rs 10,000 is below the minimum


def test_sector_and_gross_limits_shrink_or_block_the_trade(tmp_path):
    risk = engine(tmp_path)
    tech = held("BBB.NS", 350, 1000, sector="Tech")  # Rs 3.5 lakh of Rs 10 lakh equity
    decision = risk.evaluate(intent(), account(cash=650_000, positions=[tech]))
    assert decision.approved and decision.quantity == 50  # only 5% room left in Tech
    full = held("BBB.NS", 380, 1000, sector="Tech")
    assert "size" in failed(risk.evaluate(intent(), account(cash=620_000, positions=[full])))  # Rs 20,000 room
    invested = [held(f"S{i}.NS", 245, 1000, sector=f"Sector{i}") for i in range(4)]  # 98% invested
    assert "size" in failed(risk.evaluate(intent(sector="Other"), account(cash=20_000, positions=invested)))


def test_correlated_positions_are_refused(tmp_path):
    rng = np.random.default_rng(0)
    base = pd.Series(rng.normal(0, 0.01, 100), index=pd.bdate_range("2026-05-01", periods=100))
    returns = {"AAA.NS": base, "BBB.NS": base + rng.normal(0, 0.001, 100), "CCC.NS": pd.Series(
        rng.normal(0, 0.01, 100), index=base.index)}
    risk = engine(tmp_path)
    twin = account(cash=900_000, positions=[held("BBB.NS", 100, 1000, sector="Other")])
    assert "correlation" in failed(risk.evaluate(intent(), twin, returns))
    unrelated = account(cash=900_000, positions=[held("CCC.NS", 100, 1000, sector="Other")])
    assert risk.evaluate(intent(), unrelated, returns).approved


def test_no_approved_trade_ever_breaks_a_limit(tmp_path):
    rng = np.random.default_rng(42)
    risk, approvals = engine(tmp_path), 0
    for case in range(500):
        positions = [held(f"P{i}.NS", int(rng.integers(1, 300)), float(rng.uniform(100, 3000)),
                          sector=f"Sector{rng.integers(0, 4)}") for i in range(int(rng.integers(0, 7)))]
        state = account(cash=float(rng.uniform(0, 1_500_000)), positions=positions)
        state.peak_equity = state.equity * float(rng.uniform(1.0, 1.15))
        state.day_start_equity = state.equity * float(rng.uniform(0.97, 1.03))
        idea = intent(symbol=f"N{case}.NS", price=float(rng.uniform(50, 5000)), stop=float(rng.uniform(0.0, 0.2)),
                      sector=f"Sector{rng.integers(0, 4)}", adv=float(rng.uniform(1e6, 1e9)) if rng.random() < 0.5 else None)
        decision = risk.evaluate(idea, state)
        risk.kill_switch.release()
        if not decision.approved:
            assert decision.quantity == 0
            continue
        approvals += 1
        q, p, e = decision.quantity, idea.reference_price, state.equity
        assert q >= 1 and q * p >= LIMITS.min_notional
        assert q * p * idea.stop_distance <= e * LIMITS.risk_per_trade + 1e-6
        assert q * p <= min(e * LIMITS.max_position, state.cash) + 1e-6
        assert state.sector_value(idea.sector) + q * p <= e * LIMITS.max_sector_exposure + 1e-6
        assert state.invested + q * p <= e * LIMITS.max_gross_exposure + 1e-6
        assert len(state.positions) < LIMITS.max_positions
        assert state.equity / state.peak_equity - 1 > -LIMITS.max_drawdown
        assert state.equity / state.day_start_equity - 1 > -LIMITS.max_daily_loss
    assert approvals > 50  # the cases exercise approvals, not just rejections


def test_limits_config():
    assert load_limits() == RiskLimits()
    with pytest.raises(ValueError):
        RiskLimits(risk_per_trade=0.05)
    with pytest.raises(ValueError):
        RiskLimits(max_positions=0)


def test_sectors_and_correlation_helpers():
    sectors = load_sectors()
    assert sector_of("RELIANCE.NS", sectors) == "Oil, Gas & Consumable Fuels"
    assert sector_of("UNLISTED.NS", sectors) == "UNKNOWN"
    index = pd.bdate_range("2026-01-01", periods=80)
    a = pd.Series(np.random.default_rng(1).normal(0, 0.01, 80), index=index)
    assert correlation(a, a * 2) == pytest.approx(1.0)
    assert np.isnan(correlation(a.iloc[:30], a.iloc[:30]))  # too little shared history
    assert most_correlated(a, {"X": -a, "Y": a * 3}) == ("Y", pytest.approx(1.0))
    # a weaker match found later, or a holding with too little shared history, never replaces the strongest
    assert most_correlated(a, {"Y": a * 3, "X": -a, "Z": a.iloc[:30]}) == ("Y", pytest.approx(1.0))
    best, value = most_correlated(a, {"Z": a.iloc[:30]})
    assert best is None and np.isnan(value)


def test_kill_switch_command(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(killswitch, "KILL_FILE", tmp_path / "KILL_SWITCH")
    killswitch.main(["engage", "manual test"])
    assert "ENGAGED" in capsys.readouterr().out and (tmp_path / "KILL_SWITCH").exists()
    killswitch.main(["release"])
    assert "released" in capsys.readouterr().out and not (tmp_path / "KILL_SWITCH").exists()
    killswitch.main(["status"])
    assert "released" in capsys.readouterr().out


def test_engaging_again_keeps_the_original_reason(tmp_path):
    switch = KillSwitch(tmp_path / "KILL_SWITCH")
    switch.engage("drawdown 10.4% breached the 10% limit")
    switch.engage("engaged by hand")  # e.g. a later alert or a person, while it is already engaged
    assert "drawdown 10.4%" in switch.reason and "by hand" not in switch.reason
