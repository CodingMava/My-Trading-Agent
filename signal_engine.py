import pandas as pd
from data_engine import MarketTracker
from ta_engine import TechnicalAnalyzer
from universe import get_nifty_universe

# ✅ CORRECTED IMPORTS: Bring in the Alert and AI systems
from alert_engine import AlertSystem
from ai_engine import TradeAnalyzer



class SignalDetector:
    def __init__(self):
        self.tracker = MarketTracker(get_nifty_universe())
        self.ta = TechnicalAnalyzer()

    def scan_market(self):
        """
        Scans the universe of stocks and returns a list of actionable signals.
        """
        print(f"📡 Scanning {len(self.tracker.tickers)} stocks for setups...")
        market_data = self.tracker.fetch_latest_data(interval="5m", period="5d") 
        
        active_signals = []

        for ticker, df in market_data.items():
            analyzed_df = self.ta.apply_indicators(df)
            
            if analyzed_df.empty:
                continue
                
            latest = analyzed_df.iloc[-1]
            entry_price = latest['close']
            
            # Risk Management Math (Applied to all strategies)
            long_sl = entry_price * 0.99   # 1% below
            long_tp = entry_price * 1.02   # 2% above
            short_sl = entry_price * 1.01  # 1% above (for shorting)
            short_tp = entry_price * 0.98  # 2% below (for shorting)
            
            # STRATEGY A: Breakout + Volume Surge (Bullish)
            if latest['breakout_bullish'] and latest['vol_spike']:
                active_signals.append({
                    "ticker": ticker,
                    "signal": "BUY",
                    "strategy": "Volume Breakout",
                    "price": entry_price,
                    "stop_loss": round(long_sl, 2),
                    "target": round(long_tp, 2),
                    "rsi": round(latest['rsi_14'], 2)
                })

            # STRATEGY B: RSI Oversold + MACD Bullish Crossover
            elif latest['rsi_14'] < 30 and latest['macd'] > latest['macd_signal']:
                active_signals.append({
                    "ticker": ticker,
                    "signal": "BUY",
                    "strategy": "Oversold Reversal",
                    "price": entry_price,
                    "stop_loss": round(long_sl, 2),
                    "target": round(long_tp, 2),
                    "rsi": round(latest['rsi_14'], 2)
                })

            # STRATEGY C: Overbought + Bearish Breakout (Shorting Opportunity)
            elif latest['rsi_14'] > 70 and latest['breakout_bearish']:
                active_signals.append({
                    "ticker": ticker,
                    "signal": "SELL",
                    "strategy": "Overbought Breakdown",
                    "price": entry_price,
                    "stop_loss": round(short_sl, 2),
                    "target": round(short_tp, 2),
                    "rsi": round(latest['rsi_14'], 2)
                })

        return active_signals


    
from supabase import create_client

# Initialize Supabase
url = "https://cwuhxnlfvixaftgpkbdj.supabase.co"
key = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImN3dWh4bmxmdml4YWZ0Z3BrYmRqIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzUyODMzMzYsImV4cCI6MjA5MDg1OTMzNn0.1TWsC_w-SMBTOyn1kcjs2IEqaJXjneDE2Ww4E6ZTv9k"
supabase = create_client(url, key)


def log_signal_to_db(s, ai_verdict):
    data = {
        "ticker": s['ticker'],
        "signal": s['signal'],
        "price": s['price'],
        "confidence": ai_verdict['confidence']
    }
    supabase.table("signals").insert(data).execute()

if __name__ == "__main__":
    # Initialize our modules
    scanner = SignalDetector()
    
    # 🚨 ALWAYS KEEP THESE PRIVATE!
    TELEGRAM_TOKEN = "8375815740:AAENFzSV66W0qheHTSmeoWPsHVjnNesci_8"
    TELEGRAM_CHAT_ID = "6669851040"
    GEMINI_API_KEY = "AIzaSyAfWysvUdgnqjl46qwHgfrgd3wC7vg4BjU"
    
    alerter = AlertSystem(TELEGRAM_TOKEN, TELEGRAM_CHAT_ID)
    ai_analyzer = TradeAnalyzer(GEMINI_API_KEY)
    
    signals = scanner.scan_market()
    
    print("\n" + "="*40)
    print("🎯 ACTIVE TRADING SIGNALS 🎯")
    print("="*40)
    
    if not signals:
        print("No active setups found right now. Waiting for the next candle...")
    else:
        for s in signals:
            print(f"[{s['signal']}] {s['ticker']} | {s['strategy']} | Price: ₹{s['price']:.2f}")
            
            # --- PHASE 3: AI Sanity Check ---
            print(f"🤖 Asking AI to verify {s['ticker']} setup...")
            ai_verdict = ai_analyzer.analyze_signal(s)
            
            # --- PHASE 2: Format & Send Telegram Alert ---
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