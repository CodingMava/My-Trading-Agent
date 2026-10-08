import argparse
import logging
import time
from datetime import datetime, timedelta

from alert_engine import AlertSystem
from ta_engine import TechnicalAnalyzer
from trader.config import load_settings
from trader.data.kite import session_secrets
from trader.data.providers import YahooProvider, fetch_many, make_provider
from trader.data.validate import drop_incomplete_bars, validate_bars
from trader.logging_setup import configure_logging
from trader.markets.calendar import CalendarCoverageError, load_calendars
from trader.registry import StrategyRegistry
from universe import get_nifty_universe

log = logging.getLogger("signal_engine")

INTERVAL = "5m"
LOOKBACK = timedelta(days=10)  # of 5-minute bars: enough for the 200-bar warm-up even across holidays
# apply_indicators() drops the SMA-200 warm-up rows. After that, the rules need Bollinger(20) and
# the shifted 20-bar Turtle channel on the latest row, i.e. at least 21 remaining rows.
MIN_ROWS_AFTER_WARMUP = 21


def nse_calendar():
    return load_calendars()["NSE"]


def is_market_open(now=None, calendar=None):
    """Is NSE in session? Holiday-aware; raises CalendarCoverageError for a year with no holiday list."""
    calendar = calendar or nse_calendar()
    return calendar.is_open(now or datetime.now(calendar.tz))


def market_state(calendar, now):
    """("open" | "closed" | "unknown", reason). "unknown" means the calendar can't tell: NO TRADE."""
    try:
        return ("open", "") if calendar.is_open(now) else ("closed", "")
    except CalendarCoverageError as exc:
        return "unknown", str(exc)


def warn_if_calendar_ends_soon(calendar, today):
    if today.month == 12 and today.year + 1 not in calendar.years:
        log.warning("The %s calendar has no holidays for %d yet. Add them to config/market_calendars.toml "
                    "before 1 January, or every scan will end in NO TRADE.", calendar.name, today.year + 1)


def evaluate_latest(ticker, analyzed_df):
    """The original 8-strategy if/elif block, unchanged: returns one candidate signal for the latest
    bar, or None. The 2026-10-08 audit rejected or disabled every rule; the registry decides whether a
    candidate may be used, and tests/research/test_legacy_rules.py keeps this in sync with the research copy."""
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

    # --- THE 8 STRATEGIES (all rejected or disabled by the 2026-10-08 audit) ---

    # 1. ORIGINAL: Volume Breakout (Bullish)
    if latest['breakout_bullish'] and latest['vol_spike']:
        return {"ticker": ticker, "signal": "BUY", "strategy": "Volume Breakout", "price": entry_price, "stop_loss": round(long_sl, 2), "target": round(long_tp, 2), "rsi": round(latest['rsi_14'], 2)}

    # 2. ORIGINAL: Oversold Reversal (Bullish)
    elif latest['rsi_14'] < 30 and latest['macd'] > latest['macd_signal']:
        return {"ticker": ticker, "signal": "BUY", "strategy": "Oversold Reversal", "price": entry_price, "stop_loss": round(long_sl, 2), "target": round(long_tp, 2), "rsi": round(latest['rsi_14'], 2)}

    # 3. ORIGINAL: Overbought Breakdown (Bearish)
    elif latest['rsi_14'] > 70 and latest['breakout_bearish']:
        return {"ticker": ticker, "signal": "SELL", "strategy": "Overbought Breakdown", "price": entry_price, "stop_loss": round(short_sl, 2), "target": round(short_tp, 2), "rsi": round(latest['rsi_14'], 2)}

    # 4. NEW: Turtle Trend Follower (Commodities/Crypto logic adapted for Equities)
    elif latest['close'] > latest['turtle_high'] and latest['sma_50'] > latest['sma_200']:
        return {"ticker": ticker, "signal": "BUY", "strategy": "Turtle Trend Breakout", "price": entry_price, "stop_loss": round(long_sl, 2), "target": round(long_tp, 2), "rsi": round(latest['rsi_14'], 2)}

    # 5. NEW: Tudor Jones Macro Filter (Indices/Blue Chips)
    # Logic: Price crosses above 20 SMA, but ONLY if price is above the 200 SMA.
    elif prev['close'] < prev['sma_20'] and latest['close'] > latest['sma_20'] and latest['close'] > latest['sma_200']:
        return {"ticker": ticker, "signal": "BUY", "strategy": "Tudor Jones Macro Filter", "price": entry_price, "stop_loss": round(long_sl, 2), "target": round(long_tp, 2), "rsi": round(latest['rsi_14'], 2)}

    # 6. NEW: Minervini Momentum (Growth Stocks)
    # Logic: Price > 20 SMA > 50 SMA > 200 SMA (Perfect alignment) + Volume Spike
    elif latest['close'] > latest['sma_20'] > latest['sma_50'] > latest['sma_200'] and latest['vol_spike']:
        return {"ticker": ticker, "signal": "BUY", "strategy": "Minervini Momentum Stacking", "price": entry_price, "stop_loss": round(long_sl, 2), "target": round(long_tp, 2), "rsi": round(latest['rsi_14'], 2)}

    # 7. NEW: Stat-Arb Mean Reversion (Forex/Pairs logic adapted for single stock)
    # Logic: Price pierces the extreme lower Bollinger Band while RSI is crushed.
    elif latest['close'] < latest['bb_lower'] and latest['rsi_14'] < 25:
        return {"ticker": ticker, "signal": "BUY", "strategy": "Stat-Arb Mean Reversion", "price": entry_price, "stop_loss": round(long_sl, 2), "target": round(long_tp, 2), "rsi": round(latest['rsi_14'], 2)}

    # 8. NEW: Crabel Intraday Volatility Breakout
    # Logic: Inside Bar (contraction) followed by an immediate price breakout (expansion).
    else:
        is_inside_bar = (prev['high'] < prev2['high']) and (prev['low'] > prev2['low'])
        if is_inside_bar and latest['close'] > prev['high']:
            return {"ticker": ticker, "signal": "BUY", "strategy": "Crabel Intraday Expansion", "price": entry_price, "stop_loss": round(long_sl, 2), "target": round(long_tp, 2), "rsi": round(latest['rsi_14'], 2)}
        elif is_inside_bar and latest['close'] < prev['low']:
            return {"ticker": ticker, "signal": "SELL", "strategy": "Crabel Intraday Breakdown", "price": entry_price, "stop_loss": round(short_sl, 2), "target": round(short_tp, 2), "rsi": round(latest['rsi_14'], 2)}

    return None


class SignalDetector:
    def __init__(self, registry=None, provider=None, calendar=None, max_delay=timedelta(minutes=20)):
        self.symbols = get_nifty_universe()
        self.provider = provider if provider is not None else YahooProvider()
        self.calendar = calendar if calendar is not None else nse_calendar()
        self.max_delay = max_delay
        self.ta = TechnicalAnalyzer()
        self.registry = registry if registry is not None else StrategyRegistry.load()
        self.last_rejected = []  # candidates the registry blocked (NO TRADE decisions)
        self.last_skipped = []   # (ticker, reason) pairs that could not be evaluated

    def scan_market(self, now=None):
        """Scans the universe and returns only signals from strategies approved for live use in
        config/strategies.toml. Only complete, fresh, validated bars are evaluated. Blocked candidates
        go to last_rejected, unusable tickers to last_skipped."""
        now = now or datetime.now(self.calendar.tz)
        market_data, failures = fetch_many(self.provider, self.symbols, INTERVAL, now - LOOKBACK,
                                           now + timedelta(minutes=1))
        candidates = []
        skipped = [(ticker, f"no data ({reason})") for ticker, reason in failures.items()]

        for ticker, df in market_data.items():
            try:
                df = drop_incomplete_bars(df, INTERVAL, now, self.calendar)  # Yahoo includes the forming candle
                report = validate_bars(df, ticker, INTERVAL, calendar=self.calendar, now=now,
                                       max_delay=self.max_delay)
                if not report.ok:
                    skipped.append((ticker, "unusable data: " + "; ".join(f"{i.check}: {i.message}" for i in report.errors)))
                    continue
                analyzed_df = self.ta.apply_indicators(df)
                if analyzed_df.empty or 'sma_200' not in analyzed_df.columns or len(analyzed_df) < MIN_ROWS_AFTER_WARMUP:
                    skipped.append((ticker, f"insufficient history ({len(df)} complete bars)"))
                    continue
                candidate = evaluate_latest(ticker, analyzed_df)
            except Exception as exc:  # one bad ticker must not abort the whole scan
                skipped.append((ticker, f"evaluation error: {exc}"))
                continue
            if candidate:
                candidates.append(candidate)

        approved, self.last_rejected = self.registry.partition(candidates)
        self.last_skipped = skipped
        return approved


def format_signal_message(s, ai_verdict=None):
    msg = f"🚨 *{s['signal']} SIGNAL DETECTED* 🚨\n\n"
    msg += f"📈 *Stock:* {s['ticker']}\n"
    msg += f"🧠 *Strategy:* {s['strategy']}\n"
    msg += f"💰 *Entry:* ₹{s['price']:.2f}\n"
    msg += f"🛑 *Stop Loss:* ₹{s['stop_loss']}\n"
    msg += f"🎯 *Target:* ₹{s['target']}\n"
    msg += f"📊 *RSI:* {s['rsi']}\n"
    if ai_verdict:
        msg += f"\n🤖 *AI Analysis ({ai_verdict['confidence']} Confidence):*\n"
        msg += f"_{ai_verdict['explanation']}_"
    return msg


def log_scan(scanner, signals):
    for rejection in scanner.last_rejected:
        s = rejection.signal
        log.info("NO TRADE | %s | %s (%s) | %s: %s", s['ticker'], s['strategy'], rejection.strategy_id or "?",
                 rejection.status, rejection.reason)
    for ticker, reason in scanner.last_skipped:
        log.warning("SKIPPED | %s | %s", ticker, reason)
    if not signals:
        log.info("NO TRADE this scan | %d candidate(s) blocked by the registry, %d ticker(s) skipped",
                 len(scanner.last_rejected), len(scanner.last_skipped))


def run_scan(scanner, alerter, ai_analyzer):
    signals = scanner.scan_market()
    log_scan(scanner, signals)
    for s in signals:
        log.info("SIGNAL | %s %s | %s | entry %.2f, stop %s, target %s",
                 s['signal'], s['ticker'], s['strategy'], s['price'], s['stop_loss'], s['target'])
        ai_verdict = ai_analyzer.analyze_signal(s) if ai_analyzer else None
        if alerter:
            alerter.send_telegram_alert(format_signal_message(s, ai_verdict))
    return signals


def main(argv=None):
    parser = argparse.ArgumentParser(description="NSE signal scanner. Sends alerts only; it never places orders.")
    parser.add_argument("--once", action="store_true", help="run one scan now (even outside market hours) and exit")
    args = parser.parse_args(argv)

    settings = load_settings()
    configure_logging(secrets=settings.secret_values() + session_secrets())
    for warning in settings.warnings:
        log.warning(warning)
    try:
        provider = make_provider(settings)
    except Exception as exc:  # e.g. Kite selected but nobody logged in today
        log.error("No market data source: %s", exc)
        raise SystemExit(1)
    calendar = nse_calendar()

    registry = StrategyRegistry.load()
    live = registry.live_strategies()
    alerter = None
    if settings.telegram_enabled:
        alerter = AlertSystem(settings.telegram_bot_token.reveal(), settings.telegram_chat_id,
                              timeout_s=settings.telegram_timeout_seconds)
    ai_analyzer = None
    if settings.ai_enabled:
        from ai_engine import TradeAnalyzer
        ai_analyzer = TradeAnalyzer(settings.gemini_api_key.reveal(), model_id=settings.ai_model,
                                    timeout_s=settings.ai_timeout_seconds)
    scanner = SignalDetector(registry, provider=provider, calendar=calendar,
                             max_delay=timedelta(minutes=settings.max_data_delay_minutes))

    log.info("Scanner started | %d stocks | data: %s | live strategies: %s | telegram: %s | ai: %s",
             len(scanner.symbols), provider.name, ", ".join(r.name for r in live) or "none",
             "on" if alerter else "off", "on" if ai_analyzer else "off")
    if not live:
        log.warning("No strategy is approved for live signals (config/strategies.toml): every scan ends in NO TRADE.")

    if args.once:
        now = datetime.now(calendar.tz)
        warn_if_calendar_ends_soon(calendar, now.date())
        state, reason = market_state(calendar, now)
        if state == "unknown":
            log.error("Market calendar: %s. NO TRADE.", reason)
        elif state == "closed":
            log.info("Outside market hours: evaluating the most recent session's data.")
        run_scan(scanner, alerter, ai_analyzer)
        return

    last_state, last_day = None, None
    while True:
        try:
            now = datetime.now(calendar.tz)
            if now.date() != last_day:
                warn_if_calendar_ends_soon(calendar, now.date())
                last_day = now.date()
            state, reason = market_state(calendar, now)
            if state != last_state:
                if state == "unknown":
                    log.error("Market calendar: %s. NO TRADE until it is fixed.", reason)
                else:
                    log.info("Market %s.", "open: scanning every 5 minutes" if state == "open" else "closed: waiting")
                last_state = state
            if state == "open":
                run_scan(scanner, alerter, ai_analyzer)
                time.sleep(300)
            else:
                time.sleep(60)
        except KeyboardInterrupt:
            log.info("Stopped by user.")
            break
        except Exception:
            log.exception("Unexpected error; retrying in 60 seconds.")
            time.sleep(60)


if __name__ == "__main__":
    main()
