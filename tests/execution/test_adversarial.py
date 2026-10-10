"""What reality will send (the audit's adversarial test layer): broken, partial or odd data must never crash
the daily run, stop the other instruments, or leave a held position unmanaged."""
from datetime import date, datetime

import numpy as np
import pandas as pd
import pytest

from tests.execution.test_paper_trader import IST, SIGNAL_DAY, UNIVERSE, bars, make_trader

SIX = {**UNIVERSE, **{f"{name}.NS": bars() for name in ("DDD", "EEE", "FFF")}}  # one bad instrument is under 20%


class AsIs:
    """A provider that hands back whatever it holds, unfiltered, and fails where told to."""
    name = "as-is"

    def __init__(self, frames, failing=()):
        self.frames, self.failing = frames, set(failing)

    def history(self, symbol, interval, start, end):
        if symbol in self.failing:
            raise ConnectionError("HTTP 500 from the data provider")
        return self.frames[symbol]


def run(tmp_path, frames, failing=(), db="paper.db"):
    trader = make_trader(tmp_path, frames=frames, db=db)
    trader.provider = AsIs(frames, failing)
    return trader, trader.run(until=date(2026, 8, 18), start=SIGNAL_DAY)


@pytest.mark.parametrize("broken", [
    pd.DataFrame(),  # nothing at all
    bars().iloc[:1],  # one old bar
    bars().assign(close=np.nan),  # no closes
    bars().drop(columns="volume"),  # a column missing
    bars().tz_localize(None),  # timestamps without a time zone
    bars().reset_index(drop=True),  # not even dates
], ids=["empty", "one-bar", "no-closes", "no-volume-column", "naive-times", "no-dates"])
def test_one_unusable_instrument_never_stops_the_others(tmp_path, broken):
    trader, summary = run(tmp_path, {**SIX, "DDD.NS": broken})
    assert not summary.halted and len(summary.sessions) == 7
    assert len(trader.store.trades()) == 3 and trader.store.reconcile() == []  # AAA, BBB, CCC as usual


def test_a_provider_error_for_one_instrument_is_contained(tmp_path):
    trader, summary = run(tmp_path, SIX, failing={"EEE.NS"})
    assert not summary.halted and len(trader.store.trades()) == 3


def test_repeated_and_shuffled_bars_change_nothing(tmp_path):
    messy = {s: pd.concat([f, f.iloc[[2, 5]]]).sample(frac=1, random_state=1) for s, f in UNIVERSE.items()}
    clean, _ = run(tmp_path, UNIVERSE, db="clean.db")
    trader, summary = run(tmp_path, messy, db="messy.db")
    assert not summary.halted
    pd.testing.assert_frame_equal(trader.store.trades().drop(columns="id"), clean.store.trades().drop(columns="id"))


def test_a_suspicious_jump_blocks_entries_but_the_stop_still_works(tmp_path):
    crash = {date(2026, 8, 13): {"open": 70.0, "high": 72.0, "low": 69.0, "close": 70.0}}  # -30% overnight
    trader = make_trader(tmp_path, frames={"AAA.NS": bars(crash, entries={SIGNAL_DAY})})
    trader.clock = lambda: datetime(2026, 8, 12, 20, 0, tzinfo=IST)
    trader.run(until=date(2026, 8, 12), start=SIGNAL_DAY)  # bought on the 11th
    trader.clock = lambda: datetime(2026, 8, 13, 20, 0, tzinfo=IST)
    trader.run(until=date(2026, 8, 13))  # the newest bar is the suspicious one
    trade = trader.store.trades().iloc[0]
    assert trade["reason"] == "Stop Loss (gapped through)" and trade["exit_price"] == 70.0
