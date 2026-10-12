"""The round 6 evidence must not change when the code around it does. Needs the frozen data in data/phase3,
data/round2, data/round4 and data/round6 (git-ignored); run with `pytest -m slow`."""
import pytest

from trader.research import round6
from trader.research.datasets import DATA_DIR

pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(not (DATA_DIR / "round6" / "aux_daily" / "manifest.json").exists(),
                       reason="frozen round 6 data not present"),
]

# hypothesis: (trades, win %, net % per trade, t, raw p vs random, failed criteria)
EXPECTED = {
    "C1": (111, 54.0541, 0.154035, 0.725025, 0.0145, {4, 5, 6, 9, 10, 11, 12}),
    "C2": (355, 50.9859, 0.006596, 0.056109, 0.1695, {3, 4, 5, 6, 8, 9, 10, 11, 12}),
    "C3": (1055, 40.9479, -0.158952, -6.413801, 0.8125, {2, 3, 4, 5, 6, 8, 9, 11, 12}),
    "C4": (1066, 47.9362, -0.056245, -2.337428, 0.703, {2, 3, 4, 5, 6, 8, 9, 11, 12}),
    "C5": (127, 55.1181, 0.504949, 1.295817, 0.8575, {4, 5, 11, 12}),
    "C6": (141, 70.2128, 0.996988, 3.009899, 0.6975, {5, 12}),
}


def test_round6_verdicts_and_key_numbers():
    results = round6.run(write=False)
    for key, (trades, win, net, t, p, failed) in EXPECTED.items():
        stats = results[key]["stats"]
        assert stats["trades"] == trades, key
        assert stats["win_pct"] == pytest.approx(win, abs=1e-3), key
        assert stats["exp_net_pct"] == pytest.approx(net, abs=1e-5), key
        assert stats["t_stat"] == pytest.approx(t, abs=1e-5), key
        assert results[key]["raw_p"] == pytest.approx(p, abs=1e-4), key
        assert {c.number for c in results[key]["checks"] if not c.passed} == failed, key
        assert results[key]["decision"] == "REJECTED", key
