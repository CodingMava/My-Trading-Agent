import pandas as pd
import pandas_ta as ta

class TechnicalAnalyzer:
    def __init__(self, volume_multiplier=2.0, breakout_window=20):
        self.vol_mult = volume_multiplier
        self.breakout_window = breakout_window

    def apply_indicators(self, df):
        """
        Takes a raw OHLCV dataframe and appends technical indicators.
        """
        # Ensure we have enough data to calculate long-term averages
        if df.empty or len(df) < 200:
            print("⚠️ Not enough data. Need at least 200 rows for the 200 SMA.")
            return df

        # 1. Simple Moving Averages (Trend)
        df['sma_20'] = ta.sma(df['close'], length=20)
        df['sma_50'] = ta.sma(df['close'], length=50)
        df['sma_200'] = ta.sma(df['close'], length=200)

        # 2. RSI (Momentum)
        df['rsi_14'] = ta.rsi(df['close'], length=14)

        # 3. MACD (Trend Strength)
        # MACD usually returns 3 columns: MACD line, Histogram, and Signal line.
        macd = ta.macd(df['close'], fast=12, slow=26, signal=9)
        if macd is not None:
            # Rename columns to be easier to use later
            macd.columns = ['macd', 'macd_histogram', 'macd_signal']
            df = pd.concat([df, macd], axis=1)

        # 4. Volume Spike Detection
        # Average volume over the last 20 periods
        df['vol_sma_20'] = ta.sma(df['volume'], length=20)
        # Boolean column: True if current volume is greater than our multiplier
        df['vol_spike'] = df['volume'] > (df['vol_sma_20'] * self.vol_mult)

        # 5. Breakout Detection (Support & Resistance)
        # Shift(1) ensures we are comparing TODAY'S close against YESTERDAY'S rolling high/low
        df['resistance'] = df['high'].rolling(window=self.breakout_window).max().shift(1)
        df['support'] = df['low'].rolling(window=self.breakout_window).min().shift(1)
        
        # Boolean columns: True if a breakout occurred
        df['breakout_bullish'] = df['close'] > df['resistance']
        df['breakout_bearish'] = df['close'] < df['support']

        # Drop the initial rows that have 'NaN' values due to the 200-period lookback
        df.dropna(inplace=True)

        return df

# --- Testing the Integration (Connecting Step 1 and Step 2) ---
if __name__ == "__main__":
    # Import the data tracker we built in Step 1
    # Ensure data_engine.py is in the same folder
    from data_engine import MarketTracker
    
    symbols = ["RELIANCE.NS"]
    tracker = MarketTracker(symbols)
    
    print("⏳ Fetching data...")
    # Fetching 1 month of 5-min data to ensure we have >200 candles
    market_data = tracker.fetch_latest_data(interval="5m", period="1mo")
    
    if "RELIANCE.NS" in market_data:
        df = market_data["RELIANCE.NS"]
        
        print("⚙️ Applying Technical Analysis...")
        analyzer = TechnicalAnalyzer()
        analyzed_df = analyzer.apply_indicators(df)
        
        # Display the specific columns we care about for the last 3 candles
        columns_to_show = ['close', 'sma_20', 'rsi_14', 'macd', 'vol_spike', 'breakout_bullish']
        print("\n📊 Latest 3 Candles with Indicators:")
        print(analyzed_df[columns_to_show].tail(3))