"""The round 5 evidence must not change when the code around it does. Needs the frozen data in data/round5
and data/round3 (git-ignored); run with `pytest -m slow`."""
import pytest

from trader.research import round5
from trader.research.datasets import DATA_DIR

pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(not (DATA_DIR / "round5" / "country_etfs_daily" / "manifest.json").exists(),
                       reason="frozen round 5 data not present"),
]

# hypothesis: (trades, win %, net % per trade, t, raw p vs random, failed criteria)
EXPECTED = {
    "H11": (863, 57.94, 0.4751, 4.823, 0.0, {9}),
    "H12": (4334, 54.94, 0.2650, 5.851, 0.013, {6}),
    "H13": (960, 58.96, 0.8585, 5.035, 0.202, {5}),
    "H14": (924, 57.79, 0.8032, 3.388, 0.1775, {5}),
}


def test_round5_verdicts_and_key_numbers():
    results = round5.run(write=False)
    for key, (trades, win, net, t, p, failed) in EXPECTED.items():
        whole = results[key]["stats"]["all"]
        assert whole["trades"] == trades, key
        assert whole["win_pct"] == pytest.approx(win, abs=0.01), key
        assert whole["exp_net_pct"] == pytest.approx(net, abs=1e-4), key
        assert whole["t_stat"] == pytest.approx(t, abs=1e-3), key
        assert results[key]["raw_p"] == pytest.approx(p, abs=1e-4), key
        assert {c.number for c in results[key]["checks"] if not c.passed} == failed, key
        assert results[key]["decision"] == "REJECTED", key
