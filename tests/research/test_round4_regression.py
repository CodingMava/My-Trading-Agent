"""The round 4 evidence must not change when the code around it does. Needs the frozen data in data/round4
(git-ignored); run with `pytest -m slow`."""
import pytest

from trader.research import round4
from trader.research.datasets import DATA_DIR

pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(not (DATA_DIR / "round4" / "us_spy_daily" / "manifest.json").exists(),
                       reason="frozen round 4 data not present"),
]

# hypothesis: (trades, win %, net % per trade, t, raw p vs random, decision)
EXPECTED = {
    "H9": (404, 57.67, 0.2288, 2.256, 0.0665, "REJECTED"),
    "H10": (225, 56.44, 0.2771, 1.645, 0.0165, "REJECTED"),
}


def test_round4_verdicts_and_key_numbers():
    results = round4.run(write=False)
    for key, (trades, win, net, t, p, decision) in EXPECTED.items():
        whole = results[key]["stats"]["all"]
        assert whole["trades"] == trades, key
        assert whole["win_pct"] == pytest.approx(win, abs=0.01), key
        assert whole["exp_net_pct"] == pytest.approx(net, abs=1e-4), key
        assert whole["t_stat"] == pytest.approx(t, abs=1e-3), key
        assert results[key]["raw_p"] == pytest.approx(p, abs=1e-4), key
        assert results[key]["decision"] == decision, key
    assert {c.number for c in results["H9"]["checks"] if not c.passed} == {5, 9}
    assert {c.number for c in results["H10"]["checks"] if not c.passed} == {4, 9, 11}
