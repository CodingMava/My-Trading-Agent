import time
from datetime import datetime
import pytz
import pandas as pd
from data_engine import MarketTracker
from ta_engine import TechnicalAnalyzer
from universe import get_nifty_universe
from alert_engine import AlertSystem
from ai_engine import TradeAnalyzer

def is_market_open():
    """Checks if the Indian Stock Market is currently open (9:15 AM to 3:30 PM IST)."""
    tz = pytz.timezone('Asia/Kolkata')
    now = datetime.now(tz)
    
    # 1. Check if it's a weekend (5 = Saturday, 6 = Sunday)
    if now.weekday() >= 5:
        return False
        
    # 2. Check if the time is between 9:15 AM and 3:30 PM
    market_start = now.replace(hour=9, minute=15, second=0, microsecond=0)
    market_end = now.replace(hour=15, minute=30, second=0, microsecond=0)
    
    return market_start <= now <= market_end

class SignalDetector:
    def __init__(self):
        self.tracker = MarketTracker(get_nifty_universe())
        self.ta = TechnicalAnalyzer()

    def scan_market(self):
        """Scans the universe of stocks and returns actionable signals based on 8 strategies."""
        market_data = self.tracker.fetch_latest_data(interval="5m", period="5d") 
        active_signals = []

        for ticker, df in market_data.items():
            analyzed_df = self.ta.apply_indicators(df)
            
            # Need enough data for 200 SMA and historical lookbacks
            if analyzed_df.empty or len(analyzed_df) < 200:
                continue
                
            # --- ADVANCED INDICATOR MATH (Added dynamically for the new strategies) ---
            # 1. Bollinger Bands (For Stat-Arb Mean Reversion)
            analyzed_df['bb_mid'] = analyzed_df['close'].rolling(20).mean()
            analyzed_df['bb_std'] = analyzed_df['close'].rolling(20).std()
            analyzed_df['bb_upper'] = analyzed_df['bb_mid'] + (2 * analyzed_df['bb_std'])
            analyzed_df['bb_lower'] = analyzed_df['bb_mid'] - (2 * analyzed_df['bb_std'])
            
            # 2. Turtle Channels (20-period highest high / lowest low)
            analyzed_df['turtle_high'] = analyzed_df['high'].rolling(20).max().shift(1)
            analyzed_df['turtle_low'] = analyzed_df['low'].rolling(20).min().shift(1)

            # --- CANDLE DATA EXTRACTION ---
            latest = analyzed_df.iloc[-1]
            prev = analyzed_df.iloc[-2]
            prev2 = analyzed_df.iloc[-3]
            entry_price = latest['close']
            
            # Risk Management Math
            long_sl = entry_price * 0.99   # 1% below
            long_tp = entry_price * 1.02   # 2% above
            short_sl = entry_price * 1.01  # 1% above
            short_tp = entry_price * 0.98  # 2% below
            
            # --- 🚀 THE 8 QUANTITATIVE STRATEGIES 🚀 ---
            
            # 1. ORIGINAL: Volume Breakout (Bullish)
            if latest['breakout_bullish'] and latest['vol_spike']:
                active_signals.append({"ticker": ticker, "signal": "BUY", "strategy": "Volume Breakout", "price": entry_price, "stop_loss": round(long_sl, 2), "target": round(long_tp, 2), "rsi": round(latest['rsi_14'], 2)})

            # 2. ORIGINAL: Oversold Reversal (Bullish)
            elif latest['rsi_14'] < 30 and latest['macd'] > latest['macd_signal']:
                active_signals.append({"ticker": ticker, "signal": "BUY", "strategy": "Oversold Reversal", "price": entry_price, "stop_loss": round(long_sl, 2), "target": round(long_tp, 2), "rsi": round(latest['rsi_14'], 2)})

            # 3. ORIGINAL: Overbought Breakdown (Bearish)
            elif latest['rsi_14'] > 70 and latest['breakout_bearish']:
                active_signals.append({"ticker": ticker, "signal": "SELL", "strategy": "Overbought Breakdown", "price": entry_price, "stop_loss": round(short_sl, 2), "target": round(short_tp, 2), "rsi": round(latest['rsi_14'], 2)})

            # 4. NEW: Turtle Trend Follower (Commodities/Crypto logic adapted for Equities)
            elif latest['close'] > latest['turtle_high'] and latest['sma_50'] > latest['sma_200']:
                active_signals.append({"ticker": ticker, "signal": "BUY", "strategy": "Turtle Trend Breakout", "price": entry_price, "stop_loss": round(long_sl, 2), "target": round(long_tp, 2), "rsi": round(latest['rsi_14'], 2)})

            # 5. NEW: Tudor Jones Macro Filter (Indices/Blue Chips)
            # Logic: Price crosses above 20 SMA, but ONLY if the 200 SMA is trending upward (Price > 200 SMA).
            elif prev['close'] < prev['sma_20'] and latest['close'] > latest['sma_20'] and latest['close'] > latest['sma_200']:
                active_signals.append({"ticker": ticker, "signal": "BUY", "strategy": "Tudor Jones Macro Filter", "price": entry_price, "stop_loss": round(long_sl, 2), "target": round(long_tp, 2), "rsi": round(latest['rsi_14'], 2)})

            # 6. NEW: Minervini Momentum (Growth Stocks)
            # Logic: Price > 20 SMA > 50 SMA > 200 SMA (Perfect alignment) + Volume Spike
            elif latest['close'] > latest['sma_20'] > latest['sma_50'] > latest['sma_200'] and latest['vol_spike']:
                active_signals.append({"ticker": ticker, "signal": "BUY", "strategy": "Minervini Momentum Stacking", "price": entry_price, "stop_loss": round(long_sl, 2), "target": round(long_tp, 2), "rsi": round(latest['rsi_14'], 2)})

            # 7. NEW: Stat-Arb Mean Reversion (Forex/Pairs logic adapted for single stock)
            # Logic: Price pierces the extreme lower Bollinger Band while RSI is crushed.
            elif latest['close'] < latest['bb_lower'] and latest['rsi_14'] < 25:
                active_signals.append({"ticker": ticker, "signal": "BUY", "strategy": "Stat-Arb Mean Reversion", "price": entry_price, "stop_loss": round(long_sl, 2), "target": round(long_tp, 2), "rsi": round(latest['rsi_14'], 2)})

            # 8. NEW: Crabel Intraday Volatility Breakout
            # Logic: Inside Bar (contraction) followed by an immediate price breakout (expansion).
            else:
                is_inside_bar = (prev['high'] < prev2['high']) and (prev['low'] > prev2['low'])
                if is_inside_bar and latest['close'] > prev['high']:
                    active_signals.append({"ticker": ticker, "signal": "BUY", "strategy": "Crabel Intraday Expansion", "price": entry_price, "stop_loss": round(long_sl, 2), "target": round(long_tp, 2), "rsi": round(latest['rsi_14'], 2)})
                elif is_inside_bar and latest['close'] < prev['low']:
                    active_signals.append({"ticker": ticker, "signal": "SELL", "strategy": "Crabel Intraday Breakdown", "price": entry_price, "stop_loss": round(short_sl, 2), "target": round(short_tp, 2), "rsi": round(latest['rsi_14'], 2)})

        return active_signals

if __name__ == "__main__":
    # 🚨 INSERT YOUR KEYS HERE
    TELEGRAM_TOKEN = "8375815740:AAENFzSV66W0qheHTSmeoWPsHVjnNesci_8"
    TELEGRAM_CHAT_ID = "6669851040"
    GEMINI_API_KEY = "AIzaSyAfWysvUdgnqjl46qwHgfrgd3wC7vg4BjU"
    
    alerter = AlertSystem(TELEGRAM_TOKEN, TELEGRAM_CHAT_ID)
    ai_analyzer = TradeAnalyzer(GEMINI_API_KEY)
    scanner = SignalDetector()
    
    print("🚀 Advanced 8-Strategy Quant Bot Initialized. Entering monitoring loop...")
    
    while True:
        try:
            if is_market_open():
                print(f"\n[{datetime.now().strftime('%H:%M:%S')}] 🟢 Market Open. Scanning {len(scanner.tracker.tickers)} stocks...")
                signals = scanner.scan_market()
                
                if not signals:
                    print("No setups found across all 8 strategies. Waiting for next candle...")
                else:
                    for s in signals:
                        print(f"🎯 [{s['signal']}] {s['ticker']} detected via {s['strategy']}! Verifying with AI...")
                        
                        ai_verdict = ai_analyzer.analyze_signal(s)
                        
                        msg = f"🚨 *{s['signal']} SIGNAL DETECTED* 🚨\n\n"
                        msg += f"📈 *Stock:* {s['ticker']}\n"
                        msg += f"🧠 *Strategy:* {s['strategy']}\n"
                        msg += f"💰 *Entry:* ₹{s['price']:.2f}\n"
                        msg += f"🛑 *Stop Loss:* ₹{s['stop_loss']}\n"
                        msg += f"🎯 *Target:* ₹{s['target']}\n"
                        msg += f"📊 *RSI:* {s['rsi']}\n\n"
                        msg += f"🤖 *AI Analysis ({ai_verdict['confidence']} Confidence):*\n"
                        msg += f"_{ai_verdict['explanation']}_"
                        
                        alerter.send_telegram_alert(msg)
                
                # Sleep for 5 minutes (300 seconds)
                time.sleep(300)
                
            else:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] 🔴 Market Closed. Sleeping...")
                time.sleep(60)
                
        except KeyboardInterrupt:
            print("\n🛑 Bot manually stopped by user.")
            break
        except Exception as e:
            print(f"\n⚠️ Unexpected Error: {e}")
            print("Restarting loop in 60 seconds...")
            time.sleep(60)