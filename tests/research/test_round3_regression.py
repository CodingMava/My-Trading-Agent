"""The round 3 evidence must not change when the code around it does. Needs the frozen data in
data/round3 and data/round2 (git-ignored); run with `pytest -m slow`."""
import pytest

from trader.research import round3
from trader.research.datasets import DATA_DIR

pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(not (DATA_DIR / "round3" / "sector_spdrs_daily" / "manifest.json").exists(),
                       reason="frozen round 3 data not present"),
]

# hypothesis: (trades, win %, net % per trade, t, clustered t, raw p vs random, decision)
EXPECTED = {
    "H7": (1085, 71.1, 0.323, 5.30, 3.48, 0.006, "REJECTED"),
    "H8": (1154, 61.6, 0.072, 1.16, 0.76, 0.191, "REJECTED"),
}


def test_round3_verdicts_and_key_numbers():
    results = round3.run(write=False)
    for key, (trades, win, net, t, t_week, p, decision) in EXPECTED.items():
        whole = results[key]["stats"]["all"]
        assert whole["trades"] == trades, key
        assert whole["win_pct"] == pytest.approx(win, abs=0.06), key
        assert whole["exp_net_pct"] == pytest.approx(net, abs=6e-4), key
        assert whole["t_stat"] == pytest.approx(t, abs=6e-3), key
        assert results[key]["t_week"] == pytest.approx(t_week, abs=6e-3), key
        assert results[key]["raw_p"] == pytest.approx(p, abs=1e-3), key
        assert results[key]["decision"] == decision, key
    failed = {c.number for c in results["H7"]["checks"] if not c.passed}
    assert failed == {7, 12}  # H7 failed only the loss-size limit and the both-must-pass rule
