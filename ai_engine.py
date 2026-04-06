from google import genai

class TradeAnalyzer:
    def __init__(self, api_key):
        # The new SDK uses a Client object instead of a global configuration
        self.client = genai.Client(api_key=api_key)
        # Upgraded to the newest Flash model for maximum speed
        self.model_id = 'gemini-2.5-flash' 

    def analyze_signal(self, signal_data):
        """
        Passes the technical signal to Gemini for a rapid sanity check using the new SDK.
        """
        prompt = f"""
        You are an expert quantitative day trader and risk manager. 
        My algorithmic system just generated a trading signal based on the following data:
        
        - Stock: {signal_data['ticker']}
        - Signal Type: {signal_data['signal']}
        - Strategy Triggered: {signal_data['strategy']}
        - Current Price: ₹{signal_data['price']}
        - Calculated Stop Loss: ₹{signal_data['stop_loss']}
        - Calculated Target: ₹{signal_data['target']}
        - Current RSI (14): {signal_data['rsi']}
        
        Task:
        1. Briefly analyze this setup. Is the risk/reward logical? Does this strategy typically work well given the RSI context?
        2. Give me a 1 to 2 sentence explanation of the trade context.
        3. Assign a "Confidence Level" of either High, Medium, or Low.
        
        Format your response exactly like this:
        Explanation: [Your brief analysis]
        Confidence: [High/Medium/Low]
        """
        
        try:
            # The new syntax for generating content
            response = self.client.models.generate_content(
                model=self.model_id,
                contents=prompt,
            )
            text_response = response.text
            
            parts = text_response.split("Confidence:")
            explanation = parts[0].replace("Explanation:", "").strip()
            confidence = parts[1].strip() if len(parts) > 1 else "Unknown"
            
            return {
                "explanation": explanation,
                "confidence": confidence
            }
            
        except Exception as e:
            print(f"❌ AI Analysis Error: {e}")
            return {
                "explanation": "AI evaluation failed. Trade at your own risk based on technicals alone.",
                "confidence": "Unknown"
            }