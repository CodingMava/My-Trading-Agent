from datetime import date

import numpy as np
import pytest

from tests.helpers import daily_session_bars
from trader.research.datasets import load_dataset, main, period_days, save_dataset, text_sha256

DAYS = [date(2026, 8, d) for d in (3, 4, 5, 6, 7)]


def test_round_trip_and_tamper_detection(tmp_path):
    frames = {"A.NS": daily_session_bars(DAYS, seed=1), "B.NS": daily_session_bars(DAYS, seed=2)}
    out = save_dataset(frames, tmp_path / "dataset", interval="1d")
    loaded = load_dataset(out)
    assert list(loaded) == ["A.NS", "B.NS"] and np.allclose(loaded["A.NS"]["close"], frames["A.NS"]["close"])
    (out / "A.NS.parquet").write_bytes(b"tampered")
    with pytest.raises(ValueError, match="checksum"):
        load_dataset(out)


def test_period_days():
    assert (period_days("60d"), period_days("6mo"), period_days("10y")) == (60, 186, 3660)
    with pytest.raises(ValueError):
        period_days("ten years")


def test_validate_command_reports_gaps(tmp_path, capsys):
    frames = {f"S{i}.NS": daily_session_bars(DAYS, seed=i) for i in range(4)}
    frames["GAP.NS"] = daily_session_bars([d for d in DAYS if d != date(2026, 8, 5)])
    out = save_dataset(frames, tmp_path / "dataset", interval="1d")
    main(["validate", str(out)])
    printed = capsys.readouterr().out
    assert "GAP.NS" in printed and "most other NSE instruments traded" in printed


def test_a_text_pin_ignores_windows_line_endings(tmp_path):
    lf, crlf = tmp_path / "lf.md", tmp_path / "crlf.md"
    lf.write_bytes(b"# Hypotheses\nH1: one\n")
    crlf.write_bytes(b"# Hypotheses\r\nH1: one\r\n")
    assert text_sha256(lf) == text_sha256(crlf) == "2e49b7ebe7b008f9c68c77432dbbbfb9a2a8581685f9048cadeee4248e5b0b99"
