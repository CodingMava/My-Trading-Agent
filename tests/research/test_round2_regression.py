"""The round 2 evidence must not change when the code around it does. Needs the frozen data in
data/round2 (git-ignored); run with `pytest -m slow`."""
import pytest

from trader.research import round2
from trader.research.datasets import DATA_DIR

pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(not (DATA_DIR / "round2" / "us_stocks_daily" / "manifest.json").exists(),
                       reason="frozen round 2 data not present"),
]

# hypothesis: (holdout trades, holdout win %, holdout net % per trade, holdout t, clustered t, raw p vs random, decision)
EXPECTED = {
    "H4": (2607, 62.0, 0.162, 2.39, 1.40, 0.2155, "REJECTED"),
    "H5": (143, 54.5, -0.057, -0.34, -0.30, 0.3845, "REJECTED"),
    "H6": (431, 65.2, 0.243, 2.40, 1.86, 0.0685, "REJECTED"),
}


def test_round2_verdicts_and_key_numbers():
    results = round2.run(write=False)
    for key, (trades, win, net, t, t_week, p, decision) in EXPECTED.items():
        holdout = results[key]["stats"]["holdout"]
        assert holdout["trades"] == trades, key
        assert holdout["win_pct"] == pytest.approx(win, abs=0.06), key
        assert holdout["exp_net_pct"] == pytest.approx(net, abs=6e-4), key
        assert holdout["t_stat"] == pytest.approx(t, abs=6e-3), key
        assert results[key]["t_week"] == pytest.approx(t_week, abs=6e-3), key
        assert results[key]["raw_p"] == pytest.approx(p, abs=1e-4), key
        assert results[key]["decision"] == decision, key
