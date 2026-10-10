from datetime import date

import pytest
from streamlit.testing.v1 import AppTest

from trader.config import ROOT
from trader.core.models import Position
from trader.execution.store import PaperStore
from trader.ops import console
from trader.registry import StrategyRegistry


def test_strategy_table_shows_each_status_with_its_research_verdict():
    table = console.strategy_table(StrategyRegistry.load()).set_index("Strategy")
    assert table.loc["H6", "Status"] == "REJECTED" and table.loc["H6", "Research verdict"] == "REJECTED"
    assert table.loc["H6", "Trades"] == 431 and table.loc["R1", "Research verdict"] == ""  # audit rules: no file


def test_account_views_of_a_paper_store(tmp_path):
    store = PaperStore(tmp_path / "p.db", 100_000)
    assert console.account(store)["equity"] == 100_000 and console.positions_table(store).empty
    store.save_position(Position("T1", "AAA.NS", 10, 100.0, 95.0, date(2026, 8, 11), last_price=110.0, entry_fees=1.0))
    store.record_session(date(2026, 8, 11), 101_099, 100_000 - 1_001)
    row = console.positions_table(store).iloc[0]
    assert row["P&L"] == pytest.approx(99.0) and console.account(store)["return"] == pytest.approx(0.01099)


def test_the_dashboard_renders_without_errors():
    app = AppTest.from_file(str(ROOT / "dashboard.py"), default_timeout=60).run()
    assert not app.exception
    assert app.title[0].value == "Trading agent"
