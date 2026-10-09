import pytest

from trader.registry import StrategyRecord, StrategyRegistry
from trader.research.legacy_rules import NAME


def test_every_legacy_rule_is_registered_and_none_may_trade():
    registry = StrategyRegistry.load()
    assert set(NAME.values()) <= {r.name for r in registry.records()}
    assert registry.live_strategies() == []
    assert {r.status for r in registry.records()} <= {"REJECTED", "DISABLED"}
    assert all(r.evidence for r in registry.records())


def test_partition_fails_closed():
    registry = StrategyRegistry([StrategyRecord("A", "Alpha", "LIVE_SMALL"),
                                 StrategyRecord("B", "Beta", "DISABLED"),
                                 StrategyRecord("C", "Gamma", "PAPER")])
    signals = [{"strategy": "Alpha"}, {"strategy": "Beta"}, {"strategy": "Gamma"}, {"strategy": "Unknown"}, {}]
    approved, rejected = registry.partition(signals)
    assert approved == [{"strategy": "Alpha"}]
    assert [r.status for r in rejected] == ["DISABLED", "PAPER", "UNREGISTERED", "UNREGISTERED"]
    assert "profitability gate" in rejected[0].reason


def test_invalid_registries_are_refused():
    with pytest.raises(ValueError):
        StrategyRegistry([StrategyRecord("A", "Alpha", "MAYBE")])
    with pytest.raises(ValueError):
        StrategyRegistry([StrategyRecord("A", "Alpha", "LIVE"), StrategyRecord("B", "Alpha", "LIVE")])
