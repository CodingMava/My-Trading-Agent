"""Round 9's evidence must not change when the code around it does. The decision was made by one stage-2 run on
14 Oct 2026 at 23:52 IST; this recomputes it, deterministically, without writing anything. Needs the frozen NSE panel
in data/round8/nse_eq (git-ignored); run with `pytest -m slow`."""
import pytest

from trader.research import round8, round9
from trader.research.nse_bhavcopy import PANEL_DIR

pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(not (PANEL_DIR / "manifest.json").exists(), reason="frozen NSE panel not present"),
]

# hypothesis: (trades, win %, net % per trade, t, raw p vs random, drawdown in R, failed criteria)
EXPECTED = {
    "L1": (795, 51.4465, 0.577226, 2.3647, 0.427429, 17.105, {5, 6, 9, 11, 12}),
    "L2": (795, 52.7044, 0.670624, 2.8536, 0.504375, 12.913, {5, 12}),
    "V2": (791, 45.8913, 2.067663, 3.5127, 0.000200, 30.408, {2, 9, 13}),
}


def test_round9_preregistration_still_matches_its_pin():
    assert round9.check_preregistration() == round9.PREREGISTRATION_SHA256


def test_round9_verdicts_and_key_numbers():
    sessions, secs, table = round8.load_inputs()
    table = round9.add_scores(table, secs)
    results = round9.evaluate(2, sessions, secs, table, with_informational=False)["results"]
    assert set(results) == set(EXPECTED)
    for key, (trades, win, net, t, p, depth, failed) in EXPECTED.items():
        stats = results[key]["stats"]
        assert stats["trades"] == trades, key
        assert 100 * stats["win_rate"] == pytest.approx(win, abs=1e-3), key
        assert 100 * stats["mean_net"] == pytest.approx(net, abs=1e-5), key
        assert stats["t"] == pytest.approx(t, abs=1e-3), key
        assert results[key]["raw_p"] == pytest.approx(p, abs=1e-6), key
        assert stats["max_drawdown_r"] == pytest.approx(depth, abs=1e-2), key
        assert {c.number for c in results[key]["checks"] if not c.passed} == failed, key
        assert results[key]["decision"] == "REJECTED", key
