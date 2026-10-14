"""Round 8's evidence must not change when the code around it does. The decision was made by one stage-2 run on
14 Oct 2026; this recomputes it, deterministically, without writing anything. Needs the frozen NSE panel in
data/round8/nse_eq (git-ignored); run with `pytest -m slow`."""
import pytest

from trader.research import round8
from trader.research.nse_bhavcopy import PANEL_DIR

pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(not (PANEL_DIR / "manifest.json").exists(), reason="frozen NSE panel not present"),
]

# hypothesis: (trades, win %, net % per trade, t, raw p vs random, drawdown in R, failed criteria)
EXPECTED = {
    "N1": (795, 48.5535, 0.413114, 1.0031, 0.638468, 45.464, {2, 4, 5, 6, 8, 9, 10, 11, 12, 13}),
    "N2": (792, 43.9394, 1.751471, 2.9160, 0.001900, 34.064, {2, 9, 13}),
}


def test_round8_verdicts_and_key_numbers():
    sessions, secs, table = round8.load_inputs()
    results = round8.evaluate(2, sessions, secs, table, with_informational=False)["results"]
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
