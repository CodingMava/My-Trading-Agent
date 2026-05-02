# universe.py

def get_nifty_universe():
    """
    Returns a list of highly liquid Indian stocks (yfinance format).
    You can expand this to the full Nifty 50 or F&O 200 later.
    """
    return [
        "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS", "ICICIBANK.NS", 
        "SBIN.NS", "BHARTIARTL.NS", "ITC.NS", "HINDUNILVR.NS", "LT.NS",
        "BAJFINANCE.NS", "AXISBANK.NS", "MARUTI.NS", 
        "SUNPHARMA.NS", "KOTAKBANK.NS", "TITAN.NS", "ASIANPAINT.NS", 
        "TATASTEEL.NS", "ADANIENT.NS","ADANIPOWER.NS","ATHERENERG.NS"
    ]