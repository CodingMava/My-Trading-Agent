"""The research copy of the audited legacy rules must not peek at future bars."""
import numpy as np

from tests.helpers import synthetic_intraday
from trader.research.legacy_rules import RULE_IDS, legacy_features, legacy_masks


def test_synthetic_data_exercises_the_rules():
    masks = legacy_masks(legacy_features(synthetic_intraday(sessions=12, seed=42)))
    fired = {rule for rule in RULE_IDS if masks[rule].any()}
    assert len(fired) >= 4, f"synthetic data only exercises {sorted(fired)}"


def test_rule_masks_do_not_use_future_bars():
    bars = synthetic_intraday(sessions=12, seed=7)
    full = legacy_masks(legacy_features(bars))
    for cut in (400, 600, 800):
        part = legacy_masks(legacy_features(bars.iloc[:cut]))
        for rule in RULE_IDS:
            assert np.array_equal(part[rule], full[rule][:len(part[rule])]), (rule, cut)


def test_short_history_yields_no_features():
    assert legacy_features(synthetic_intraday(sessions=2)).empty  # 150 bars < the 200-bar warm-up
