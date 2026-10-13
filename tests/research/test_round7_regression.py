"""Round 7's evidence must not change when the code around it does. The decision was made by one run on
13 Oct 2026 (commit 0e604d1); this recomputes it, deterministically, without writing anything. Needs the
frozen minute data in data/kite_minute (git-ignored); run with `pytest -m slow`."""
import pytest

from trader.research import round7

pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(not (round7.DATA / "manifest.json").exists(), reason="frozen minute data not present"),
]

# hypothesis: (trades, win %, net % per trade, t, raw p vs random, drawdown in R, failed criteria)
EXPECTED = {
    "I1": (959, 24.4004, -0.110599, -16.8311, 0.419279, 212.153, {2, 3, 4, 5, 6, 8, 9, 11, 12, 13}),
    "I2": (714, 23.5294, -0.128057, -15.3592, 0.564922, 182.866, {2, 3, 4, 5, 6, 8, 9, 11, 12, 13}),
    "I3": (279, 26.8817, -0.122992, -9.5559, 0.595970, 68.629, {2, 3, 4, 5, 6, 7, 8, 9, 11, 12, 13}),
}


def test_round7_verdicts_and_key_numbers():
    results = round7.run()["results"]
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
