import pytest

from trader.registry import StrategyRecord, StrategyRegistry
from trader.research.legacy_rules import NAME


def test_every_legacy_rule_is_registered_and_none_may_trade():
    registry = StrategyRegistry.load()
    assert set(NAME.values()) <= {r.name for r in registry.records()}
    assert registry.live_strategies() == []
    assert {r.status for r in registry.records()} <= {"REJECTED", "DISABLED"}
    assert all(r.evidence for r in registry.records())


def test_invalid_registries_are_refused():
    with pytest.raises(ValueError):
        StrategyRegistry([StrategyRecord("A", "Alpha", "MAYBE")])
    with pytest.raises(ValueError):
        StrategyRegistry([StrategyRecord("A", "Alpha", "LIVE"), StrategyRecord("B", "Alpha", "LIVE")])
