"""The research copy of the legacy rules must match the live code, and must not peek at future bars."""
import numpy as np

from signal_engine import evaluate_latest
from ta_engine import TechnicalAnalyzer
from tests.helpers import synthetic_intraday
from trader.research.legacy_rules import NAME, RULE_IDS, chain_choice, legacy_features, legacy_masks


def test_research_copy_matches_the_live_code_bar_by_bar():
    bars = synthetic_intraday(sessions=12, seed=42)
    masks = legacy_masks(legacy_features(bars))
    fired = {rule for rule in RULE_IDS if masks[rule].any()}
    assert len(fired) >= 4, f"synthetic data only exercises {sorted(fired)}"

    analyzer = TechnicalAnalyzer()
    offset = len(bars) - len(masks["R1"])  # warm-up rows dropped by apply_indicators
    checked = 0
    for end in range(offset + 25, len(bars) + 1, 3):
        live = evaluate_latest("TEST", analyzer.apply_indicators(bars.iloc[:end].copy()))
        expected = chain_choice(masks, end - 1 - offset)
        assert (live["strategy"] if live else None) == (NAME[expected] if expected else None), f"bar {end - 1}"
        checked += 1
    assert checked > 100


def test_rule_masks_do_not_use_future_bars():
    bars = synthetic_intraday(sessions=12, seed=7)
    full = legacy_masks(legacy_features(bars))
    for cut in (400, 600, 800):
        part = legacy_masks(legacy_features(bars.iloc[:cut]))
        for rule in RULE_IDS:
            assert np.array_equal(part[rule], full[rule][:len(part[rule])]), (rule, cut)


def test_short_history_yields_no_features():
    assert legacy_features(synthetic_intraday(sessions=2)).empty  # 150 bars < the 200-bar warm-up
