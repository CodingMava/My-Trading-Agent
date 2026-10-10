"""Ops console for the trading agent: health, the paper account, decisions, strategies and runs.
Read-only: nothing on this page can trade or change a setting.

    streamlit run dashboard.py
"""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from trader.config import ROOT, load_settings
from trader.data.providers import YahooProvider
from trader.execution.store import PaperStore
from trader.features.indicators import sma
from trader.gate import load_gate_config
from trader.markets.calendar import load_calendars
from trader.ops import console
from trader.ops.health import ACTIVE, ALERT, WARN, health_checks
from trader.registry import StrategyRegistry
from trader.risk.killswitch import KillSwitch
from trader.strategies.catalog import load_universes

IST = ZoneInfo("Asia/Kolkata")
st.set_page_config(page_title="Trading agent", layout="wide")

settings = load_settings()
database = ROOT / settings.paper_database
store = PaperStore(database, settings.paper_starting_capital) if database.exists() else None
registry = StrategyRegistry.load()
now = datetime.now(IST)
checks = health_checks(store, load_calendars()["NSE"], registry, KillSwitch(), settings, now,
                       load_gate_config().max_evidence_age_days, backup_dir=database.parent / "backups")
active = [r.id for r in registry.records() if r.status in ACTIVE]

st.title("Trading agent")
mode = f"Paper trading: {', '.join(active)}" if active else "NO TRADE: no strategy has the evidence to trade"
st.caption(f"{mode} · {now:%d %b %Y %H:%M} IST · read-only")
alerts = [c for c in checks if c.level == ALERT]
warnings = [c for c in checks if c.level == WARN]
if alerts:
    st.error("Needs attention: " + "; ".join(f"{c.name}: {c.detail}" for c in alerts))
elif warnings:
    st.warning("; ".join(f"{c.name}: {c.detail}" for c in warnings))
else:
    st.success("All health checks pass.")

account_tab, decisions_tab, strategies_tab, health_tab, chart_tab = st.tabs(
    ["Account", "Decisions", "Strategies", "Health and runs", "Chart"])
NO_RECORDS = "No paper-trading records yet: the first daily run creates them (python -m trader.execution.eod)."

with account_tab:
    if store is None:
        st.info(NO_RECORDS)
    else:
        numbers = console.account(store)
        equity, cash, held, last = st.columns(4)
        equity.metric("Equity", f"₹{numbers['equity']:,.0f}", f"{numbers['return']:+.2%} since the start")
        cash.metric("Cash", f"₹{numbers['cash']:,.0f}")
        held.metric("Open positions", numbers["positions"])
        last.metric("Last session", str(numbers["last_session"] or "-"))
        history = store.equity_history()
        if len(history) > 1:
            st.line_chart(history.rename("Equity"))
        st.subheader("Open positions")
        st.dataframe(console.positions_table(store), hide_index=True)
        st.subheader("Closed trades")
        st.dataframe(console.newest_first(store.trades()), hide_index=True)

with decisions_tab:
    if store is None:
        st.info(NO_RECORDS)
    else:
        st.caption("Every signal the engine saw and what it did, including each NO TRADE and its reason.")
        st.dataframe(console.newest_first(store.table("decisions")), hide_index=True)

with strategies_tab:
    st.caption("A status is only kept if its evidence in docs/research/evidence supports it.")
    st.dataframe(console.strategy_table(registry), hide_index=True)

with health_tab:
    st.dataframe(pd.DataFrame([{"Check": c.name, "Level": c.level.upper(), "Detail": c.detail} for c in checks]),
                 hide_index=True)
    if store is not None:
        st.subheader("Runs")
        st.dataframe(store.runs(limit=100), hide_index=True)


@st.cache_data(ttl=3600, show_spinner=False)
def daily_bars(symbol: str) -> pd.DataFrame:
    end = datetime.now(IST)
    return YahooProvider().history(symbol, "1d", end - timedelta(days=550), end)


with chart_tab:
    symbols = sorted({s for listed in load_universes().values() for s in listed} | set(store.positions() if store else {}))
    choice = st.selectbox("Instrument (daily bars from Yahoo)", ["-", *symbols])
    if choice != "-":
        bars = daily_bars(choice)
        if bars.empty:
            st.error(f"No data for {choice}.")
        else:
            fig = go.Figure([go.Candlestick(x=bars.index, open=bars["open"], high=bars["high"], low=bars["low"],
                                            close=bars["close"], name=choice),
                             go.Scatter(x=bars.index, y=sma(bars["close"], 200), name="200-day average")])
            trades = store.trades() if store is not None else pd.DataFrame()
            trades = trades[trades["symbol"] == choice] if len(trades) else trades
            for column, price, label, symbol in (("entry_session", "entry_price", "Paper entry", "triangle-up"),
                                                 ("exit_session", "exit_price", "Paper exit", "triangle-down")):
                if len(trades):
                    fig.add_trace(go.Scatter(x=pd.to_datetime(trades[column]), y=trades[price], mode="markers",
                                             marker_symbol=symbol, marker_size=12, name=label))
            fig.update_layout(height=560, xaxis_rangeslider_visible=False, margin=dict(t=30))
            st.plotly_chart(fig, use_container_width=True)
