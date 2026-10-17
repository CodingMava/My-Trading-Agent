"""Round 10's evidence must not change when the code around it does. The decision was made by one stage-2 run on
17 Oct 2026; this recomputes it, deterministically, without writing anything. Needs the frozen NSE panel and round 10's
board-meeting and insider data (git-ignored); run with `pytest -m slow`."""
import pytest

from trader.research import round10
from trader.research.nse_bhavcopy import PANEL_DIR

pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(not (PANEL_DIR / "manifest.json").exists() or not round10.BOARD_MANIFEST.exists()
                       or not round10.PIT_MANIFEST.exists(), reason="frozen round 10 data not present"),
]

# hypothesis: (trades, win %, net % per trade, t, raw p vs random, drawdown in R, failed criteria)
EXPECTED = {
    "E2": (313, 54.9521, 2.328918, 2.6542, 0.029649, 17.283, {5, 12}),
    "Q": (230, 50.0000, 1.332842, 1.3017, 0.309485, 17.107, {4, 5, 6, 8, 9, 11, 12}),
    "M": (288, 53.8194, 1.880639, 2.0837, 0.180091, 15.442, {5, 11, 12}),
}


def test_round10_verdicts_and_key_numbers():
    sessions, secs, universe, events, candidates = round10.load_everything()
    results = round10.evaluate(2, sessions, secs, universe, candidates, with_informational=False)["results"]
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
