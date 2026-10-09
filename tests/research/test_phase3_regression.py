"""The Phase 3 evidence must not change when the code around it does. Needs the frozen data in
data/phase3 (git-ignored); run with `pytest -m slow`."""
import pytest

from trader.research import phase3
from trader.research.datasets import DATA_DIR

pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(not (DATA_DIR / "phase3" / "nse_nifty50_daily" / "manifest.json").exists(),
                       reason="frozen Phase 3 data not present"),
]

# hypothesis: (holdout trades, holdout win %, holdout net % per trade, holdout t, raw p vs random, decision)
EXPECTED = {
    "H1": (1771, 60.2, -0.050, -0.67, 0.040, "REJECTED"),
    "H2": (46, 63.0, 0.122, 0.60, 0.154, "REJECTED"),
    "H3": (280, 55.7, 1.180, 2.12, 0.287, "REJECTED"),
}


def test_phase3_verdicts_and_key_numbers():
    results = phase3.run(write=False)
    for key, (trades, win, net, t, p, decision) in EXPECTED.items():
        holdout = results[key]["stats"]["holdout"]
        assert holdout["trades"] == trades, key
        assert holdout["win_pct"] == pytest.approx(win, abs=0.06), key
        assert holdout["exp_net_pct"] == pytest.approx(net, abs=6e-4), key
        assert holdout["t_stat"] == pytest.approx(t, abs=6e-3), key
        assert results[key]["raw_p"] == pytest.approx(p, abs=1e-3), key
        assert results[key]["decision"] == decision, key
