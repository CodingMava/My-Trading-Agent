import requests

class AlertSystem:
    def __init__(self, bot_token, chat_id):
        self.bot_token = bot_token
        self.chat_id = chat_id
        # This is the official Telegram API endpoint for sending messages
        self.base_url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"

    def send_telegram_alert(self, message):
        """
        Sends a formatted text message to your Telegram app.
        """
        try:
            payload = {
                "chat_id": self.chat_id,
                "text": message,
                "parse_mode": "Markdown" # This allows us to use bolding and emojis!
            }
            response = requests.post(self.base_url, json=payload)
            
            if response.status_code == 200:
                print("✅ Telegram alert sent to your phone!")
            else:
                print(f"⚠️ Failed to send alert. Telegram said: {response.text}")
                
        except Exception as e:
            print(f"❌ Alert System Error: {e}")

# --- Testing the Alert Engine ---
if __name__ == "__main__":
    # 🚨 REPLACE THESE WITH YOUR ACTUAL KEYS FROM STEP 1 🚨
    TOKEN = "8375815740:AAENFzSV66W0qheHTSmeoWPsHVjnNesci_8"
    CHAT_ID = "6669851040"
    
    print("Connecting to Telegram...")
    alerter = AlertSystem(TOKEN, CHAT_ID)
    
    test_message = "🚀 *AI Trading Agent Online*\nSystem is connected and ready to hunt for setups!"
    alerter.send_telegram_alert(test_message)

    # TELEGRAM_TOKEN = "8375815740:AAENFzSV66W0qheHTSmeoWPsHVjnNesci_8"
    # TELEGRAM_CHAT_ID = "6669851040"
    # GEMINI_API_KEY = "AIzaSyAfWysvUdgnqjl46qwHgfrgd3wC7vg4BjU"