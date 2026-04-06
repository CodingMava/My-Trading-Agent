import yfinance as yf
import pandas as pd

class MarketTracker:
    def __init__(self, tickers):
        """
        Initialize with a list of stock tickers.
        Note: For Indian stocks on yfinance, append '.NS' for NSE or '.BO' for BSE.
        """
        self.tickers = tickers

    def fetch_latest_data(self, interval="5m", period="1d"):
        """
        Fetches the latest intraday data.
        interval: 1m, 5m, 15m, 30m, 1h
        period: 1d, 5d, 1mo
        """
        market_data = {}
        for ticker in self.tickers:
            try:
                # FIX: Using yf.Ticker().history() instead of yf.download()
                stock = yf.Ticker(ticker)
                df = stock.history(interval=interval, period=period)
                
                if not df.empty:
                    # Clean up column names safely
                    df.columns = [str(col).lower() for col in df.columns]
                    
                    # Filter only the OHLCV columns we need for our TA Engine
                    if all(col in df.columns for col in ['open', 'high', 'low', 'close', 'volume']):
                        df = df[['open', 'high', 'low', 'close', 'volume']]
                        
                    market_data[ticker] = df
                    print(f"✅ Fetched {len(df)} candles for {ticker}")
                else:
                    print(f"⚠️ No data found for {ticker}. Market might be closed or ticker is wrong.")
                    
            except Exception as e:
                print(f"❌ Error fetching {ticker}: {e}")
                
        return market_data

# --- Testing the Data Engine ---
if __name__ == "__main__":
    # Example NSE Stocks: Reliance, Tata Consultancy Services, HDFC Bank
    symbols = ["RELIANCE.NS", "TCS.NS", "HDFCBANK.NS"]
    
    print("🚀 Initializing Market Tracker...")
    tracker = MarketTracker(symbols)
    
    # Fetch 5-minute candle data for today
    data = tracker.fetch_latest_data(interval="5m", period="1d")
    
    # Display the last 3 candles for Reliance
    if "RELIANCE.NS" in data:
        print("\nLatest 3 candles for RELIANCE.NS:")
        print(data["RELIANCE.NS"].tail(3))