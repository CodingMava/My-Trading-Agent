import streamlit as st
import plotly.graph_objects as go
import pandas as pd
from data_engine import MarketTracker
from ta_engine import TechnicalAnalyzer
from signal_engine import SignalDetector
from universe import get_nifty_universe

# --- Page Configuration ---
st.set_page_config(page_title="AI Trading Command Center", layout="wide")
st.title("📈 AI Quantitative Trading Dashboard")

# --- Initialize Engines (Cached for speed) ---
@st.cache_resource
def get_detector():
    return SignalDetector()

@st.cache_resource
def get_tracker():
    return MarketTracker(get_nifty_universe())

detector = get_detector()
tracker = get_tracker()

# --- Sidebar Controls ---
st.sidebar.header("Control Panel")
if st.sidebar.button("🔄 Scan Market for Signals"):
    with st.spinner("Scanning universe and calculating technicals..."):
        # We only run the detector, NOT the Telegram/AI alerts here
        signals = detector.scan_market()
        if signals:
            st.session_state['latest_signals'] = signals
            st.sidebar.success(f"Found {len(signals)} setups!")
        else:
            st.session_state['latest_signals'] = []
            st.sidebar.warning("No active setups found.")

# --- Main Dashboard Area ---
col1, col2 = st.columns([1, 2]) # Split screen: 1/3 for signals, 2/3 for charts

# Left Column: Live Signals
with col1:
    st.subheader("🚨 Active Setups")
    
    if 'latest_signals' in st.session_state and st.session_state['latest_signals']:
        for s in st.session_state['latest_signals']:
            # Create a nice visual card for each signal
            with st.expander(f"{s['signal']} | {s['ticker']}", expanded=True):
                st.write(f"**Strategy:** {s['strategy']}")
                st.write(f"**Entry Price:** ₹{s['price']:.2f}")
                st.write(f"**Target:** ₹{s['target']} 🎯")
                st.write(f"**Stop Loss:** ₹{s['stop_loss']} 🛑")
                st.write(f"**RSI:** {s['rsi']}")
    else:
        st.info("Click 'Scan Market' in the sidebar to hunt for trades.")

# Right Column: Interactive Charting
with col2:
    st.subheader("📊 Chart Analysis")
    
    # Let the user pick a stock from our universe
    selected_ticker = st.selectbox("Select a stock to analyze:", get_nifty_universe())
    
    with st.spinner(f"Fetching latest chart data for {selected_ticker}..."):
        # Fetch 1 month of 15-minute data for a cleaner chart
        chart_data_dict = tracker.fetch_latest_data(interval="15m", period="1mo")
        
        if selected_ticker in chart_data_dict:
            df = chart_data_dict[selected_ticker]
            
            # Apply technical indicators to the chart data
            ta = TechnicalAnalyzer()
            df = ta.apply_indicators(df)
            
            # Build the interactive Plotly Candlestick chart
            fig = go.Figure()
            
            # Add Candlesticks
            fig.add_trace(go.Candlestick(
                x=df.index,
                open=df['open'], high=df['high'], low=df['low'], close=df['close'],
                name="Price"
            ))
            
            # Add 20 SMA
            fig.add_trace(go.Scatter(
                x=df.index, y=df['sma_20'], 
                line=dict(color='orange', width=1.5), name="20 SMA"
            ))
            
            # Add 50 SMA
            fig.add_trace(go.Scatter(
                x=df.index, y=df['sma_50'], 
                line=dict(color='blue', width=1.5), name="50 SMA"
            ))

            fig.update_layout(
                title=f"{selected_ticker} Intraday Chart",
                yaxis_title="Price (₹)",
                xaxis_rangeslider_visible=False,
                height=600,
                template="plotly_dark" # Gives it a professional trading terminal look
            )
            
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.error("Could not fetch data for charting.")