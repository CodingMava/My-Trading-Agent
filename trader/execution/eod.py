"""End-of-day paper trading for swing strategies. No real orders are ever placed.

    python -m trader.execution.eod                        # every completed NSE session not yet processed
    python -m trader.execution.eod --start 2026-10-01     # first run only: replay from this session

For each session, in order, with the same fill rules as the backtester:
  1. orders decided at the previous close fill at this session's open (sells first, then buys);
  2. stops are checked against the day's range, then time exits happen at the close;
  3. what remains is valued at the close and the session is recorded;
  4. exit signals at the close queue sells for the next open;
  5. entry signals from strategies whose evidence supports PAPER pass the risk engine, and approved ones
     queue buys for the next open.
Every run also fetches and validates NIFTYBEES, the market check: the data path is exercised every day, so
a data source that breaks halts the run and alerts long before a strategy depends on it.
Alongside, every step for an NSE stock records the exact Zerodha Kite request that would carry it out with
real shares (trader/execution/broker.py: Phase 8's dry run; nothing is sent).
Each session is one database transaction. Telegram messages are queued inside it and sent only after it
commits; anything unsent is retried on the next run. If a session's market data is broadly missing, the
run stops before that session and alerts, rather than recording a day it couldn't see. Every run is
recorded for monitoring (python -m trader.ops.health), and a failed run sends an alert.
"""
from __future__ import annotations

import argparse
import logging
import math
import sqlite3
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import requests

from trader.config import ROOT, load_settings
from trader.core.models import PortfolioState, Position, TradeIntent
from trader.data.kite import session_secrets
from trader.data.providers import fetch_many, make_provider
from trader.data.validate import COLUMNS, DAILY_SETTLE, drop_incomplete_bars, placeholder_bars, validate_bars
from trader.execution import broker
from trader.execution.store import PaperStore
from trader.gate import EVIDENCE_DIR, DecayThresholds, decay_check, load_evidence, load_gate_config
from trader.logging_setup import configure_logging, redact
from trader.markets.calendar import load_calendars
from trader.notify import templates
from trader.notify.telegram import notifier_from_settings
from trader.ops.health import UNATTENDED_TARGET, clean_sessions
from trader.portfolio.exposure import load_sectors, sector_of
from trader.registry import StrategyRegistry
from trader.research.costs import ZERODHA_DELIVERY
from trader.risk.engine import RiskEngine
from trader.risk.killswitch import KillSwitch
from trader.risk.limits import load_limits
from trader.strategies.catalog import CATALOG, StrategySpec, load_universes

log = logging.getLogger(__name__)
IST = ZoneInfo("Asia/Kolkata")
LOOKBACK_DAYS = 420  # calendar days of history: a 200-day average plus a margin
CASH_BUFFER = 1.02  # cash set aside per pending buy, in case the next open gaps up
BUY_COST_HEADROOM = 1.005  # leave room for buy-side charges when sizing a fill to the cash available
ADV_DAYS = 20
MIN_DATA_COVERAGE = 0.8  # share of instruments that must have a session's bar before that session is processed
ACTIVE_STATUSES = ("PAPER", "LIVE_SMALL", "LIVE")  # a strategy earning live money keeps paper trading too
MARKET_CHECK = ("NIFTYBEES.NS",)  # fetched on every run, even when nothing trades


@dataclass
class RunSummary:
    sessions: list = field(default_factory=list)
    orders: int = 0
    fills: int = 0
    trades: int = 0
    messages_sent: int = 0
    notes: list = field(default_factory=list)
    halted: str = ""  # why the run stopped before the latest session, if it did


def market_of(symbol: str) -> str:
    return "NSE" if symbol.endswith(".NS") else "BSE" if symbol.endswith(".BO") else "US"


class PaperTrader:
    def __init__(self, *, store: PaperStore, provider, calendar, registry: StrategyRegistry, risk: RiskEngine,
                 notifier, catalog: dict[str, StrategySpec] | None = None, universes: dict | None = None,
                 sectors: dict | None = None, decay: DecayThresholds | None = None, evidence_dir: Path = EVIDENCE_DIR,
                 send_no_trade: bool = False, paper: bool = True, clock=None, market_check: tuple[str, ...] = ()):
        self.store, self.provider, self.calendar = store, provider, calendar
        self.registry, self.risk, self.notifier = registry, risk, notifier
        self.catalog = CATALOG if catalog is None else catalog
        self.universes = load_universes() if universes is None else universes
        self.sectors = load_sectors() if sectors is None else sectors
        self.decay = decay or DecayThresholds()
        self.evidence_dir, self.send_no_trade, self.paper = evidence_dir, send_no_trade, paper
        self.market_check = tuple(market_check)
        self.clock = clock or (lambda: datetime.now(IST))
        self._rows: dict[str, dict[date, int]] = {}
        self._signals: dict[tuple[str, str], object] = {}

    # --- what to run -----------------------------------------------------------------------------
    def active_strategies(self) -> list[StrategySpec]:
        """Catalog strategies whose evidence-checked status is PAPER or above and that aren't suspended. One that
        trades live keeps paper trading alongside, so live results can be held to the paper ones."""
        suspended = self.store.suspended()
        return [spec for spec in self.catalog.values()
                if (record := self.registry.get_by_id(spec.id)) is not None and record.status in ACTIVE_STATUSES
                and spec.id not in suspended]

    def sessions_to_process(self, until: date, start: date | None) -> list[date]:
        last = self.store.last_session()
        if last is not None:
            return [] if until <= last else self.calendar.trading_days(last + timedelta(days=1), until)
        return self.calendar.trading_days(start or until, until)

    def load_bars(self, symbols: list[str], first_session: date, now: datetime):
        """Validated daily bars. As in research, repeated timestamps keep their first bar, and bars without
        prices and holiday placeholders are dropped (that day then simply has no bar). A frame that isn't
        usable at all only rules out its own instrument. Exits may use a stock whose latest bar jumped
        suspiciously (a stop must still work); new entries may not. Returns (bars for exits, bars for
        entries, problems)."""
        start = datetime.combine(first_session - timedelta(days=LOOKBACK_DAYS), time(0), IST)
        frames, problems = fetch_many(self.provider, symbols, "1d", start, now)
        for_exits, for_entries = {}, {}
        for symbol, frame in frames.items():
            if (any(c not in frame.columns for c in COLUMNS) or not isinstance(frame.index, pd.DatetimeIndex)
                    or frame.index.tz is None):
                problems[symbol] = validate_bars(frame, symbol, "1d").summary()  # names what is wrong
                continue
            frame = frame[~frame.index.duplicated(keep="first")].sort_index()
            priced = frame[["open", "high", "low", "close"]].notna().all(axis=1)
            frame = drop_incomplete_bars(frame[priced & ~placeholder_bars(frame)], "1d", now, self.calendar)
            report = validate_bars(frame, symbol, "1d", calendar=self.calendar)
            blocking = [i.message for i in report.errors if i.check != "large_move"]
            if blocking:
                problems[symbol] = "; ".join(blocking)
                continue
            for_exits[symbol] = frame
            if report.ok:
                for_entries[symbol] = frame
            else:
                problems[symbol] = "; ".join(i.message for i in report.errors)
            self._rows[symbol] = {stamp.date(): i for i, stamp in enumerate(frame.index)}
        return for_exits, for_entries, problems

    def _row(self, symbol: str, session: date) -> int | None:
        return self._rows.get(symbol, {}).get(session)

    def _not_yet_available(self, symbol: str, session: date) -> bool:
        """No bar on or after `session` yet: the data may still arrive. (A gap with later bars after it is
        a hole in the history that no later run can fill; that session goes ahead with a stale-data alert.)"""
        days = self._rows.get(symbol)
        return not days or max(days) < session

    def signals_for(self, strategy_id: str, symbol: str, frames: dict):
        """A strategy's signals on one stock's bars, computed once per run (indicators are causal, so the
        values at a session only use bars up to that session)."""
        key = (strategy_id, symbol)
        if key not in self._signals:
            spec = self.catalog.get(strategy_id)
            self._signals[key] = spec.signals(frames[symbol]) if spec is not None and symbol in frames else None
        return self._signals[key]

    # --- the run -----------------------------------------------------------------------------------
    def run(self, until: date | None = None, start: date | None = None) -> RunSummary:
        now = self.clock()
        until = until or self.calendar.last_completed_session(now - DAILY_SETTLE)
        sessions = self.sessions_to_process(until, start)
        summary = RunSummary()
        if not sessions:
            summary.notes.append(f"{until} is already processed")
        else:
            strategies = self.active_strategies()
            if not strategies:
                summary.notes.append("no strategy is approved for paper trading: NO TRADE")
            held = set(self.store.positions()) | {o.symbol for o in self.store.pending_orders()}
            symbols = sorted({s for spec in strategies for s in self.universes.get(spec.universe, [])} | held
                             | set(self.market_check))
            self._record = clean_sessions(self.store, now)  # the unattended record before this run
            self._rows, self._signals = {}, {}
            for_exits, for_entries, problems = self.load_bars(symbols, sessions[0], now) if symbols else ({}, {}, {})
            for session in sessions:
                missing = [symbol for symbol in symbols if self._not_yet_available(symbol, session)]
                if len(missing) > (1 - MIN_DATA_COVERAGE) * len(symbols):
                    examples = ", ".join(missing[:3]) + (", ..." if len(missing) > 3 else "")
                    summary.halted = (f"no {session} market data yet for {len(missing)} of {len(symbols)} instruments "
                                      f"({examples}); stopped before that session, and the next run will retry it")
                    with self.store.transaction():
                        self.store.queue_message(session, self._alert("Market data missing", summary.halted))
                    break
                with self.store.transaction():
                    self.process_session(session, for_exits, for_entries, strategies, problems, summary,
                                         final=session == sessions[-1])
                summary.sessions.append(session)
        summary.messages_sent = self.flush_outbox()
        return summary

    def process_session(self, s: date, for_exits, for_entries, strategies, problems, summary: RunSummary,
                        final: bool) -> None:
        store, messages = self.store, []
        cash, positions = store.cash, store.positions()
        history = store.equity_history()
        day_start = float(history.iloc[-1]) if len(history) else store.starting_capital
        exited_today: set[str] = set()

        def bar(symbol: str):
            row = self._row(symbol, s)
            return None if row is None or symbol not in for_exits else for_exits[symbol].iloc[row]

        def close(position: Position, price: float, reason: str, order_id: int | None = None) -> None:
            nonlocal cash
            cash = self._close(position, float(price), s, reason, cash, messages, order_id)
            positions.pop(position.symbol, None)
            exited_today.add(position.symbol)
            summary.fills += 1
            summary.trades += 1

        # 1. Sells decided at the previous close fill at this open.
        for order in store.pending_orders("sell"):
            position = positions.get(order.symbol)
            if position is None:
                store.set_order_status(order.id, "CANCELLED", s, "no open position")
            elif (b := bar(order.symbol)) is None:
                messages.append(self._alert("Stale data", f"No {s} price for {order.symbol}; its sell waits for the next session."))
            else:
                close(position, b["open"], order.note or "Strategy Exit", order.id)

        # 2. Buys decided at the previous close fill at this open, if the cash is there.
        for order in store.pending_orders("buy"):
            spec, b = self.catalog.get(order.strategy_id), bar(order.symbol)
            if spec is None or b is None or order.symbol in positions:
                why = ("strategy no longer known" if spec is None else f"no {s} price to fill at" if b is None
                       else "already holding it")
                store.set_order_status(order.id, "CANCELLED", s, why)
                messages.append(self._alert("Rejected order", f"{order.symbol} buy cancelled: {why}."))
                continue
            price = float(b["open"])
            quantity = min(order.quantity, math.floor(cash / (price * BUY_COST_HEADROOM)))
            while quantity > 0 and quantity * price + spec.costs.one_side(quantity * price, "buy") > cash:
                quantity -= 1
            if quantity < 1 or quantity * price < self.risk.limits.min_notional:
                store.set_order_status(order.id, "CANCELLED", s, "not enough cash at the open")
                messages.append(self._alert("Rejected order", f"{order.symbol} buy cancelled: not enough cash at the open."))
                continue
            fees = spec.costs.one_side(quantity * price, "buy")
            cash -= quantity * price + fees
            position = Position(order.strategy_id, order.symbol, quantity, price, price * (1 - order.stop_distance), s,
                                sector_of(order.symbol, self.sectors), last_price=price, max_hold_days=spec.max_hold_days,
                                entry_fees=fees)
            positions[order.symbol] = position
            store.save_position(position)
            store.set_order_status(order.id, "FILLED", s)
            store.add_fill(s, order.id, order.strategy_id, order.symbol, "buy", quantity, price, fees, "Entry")
            self._dry_run(s, broker.stop_order(position), messages)
            summary.fills += 1
            messages.append(templates.buy_executed(symbol=order.symbol, price=price, quantity=quantity,
                                                   stop=position.stop_price, strategy=self._name(order.strategy_id),
                                                   exit_note=spec.exit_note, paper=self.paper))

        # 3. Stops against the day's range, then time exits at the close; value the rest at the close.
        for symbol in sorted(positions):
            position, b = positions[symbol], bar(symbol)
            if b is None:
                messages.append(self._alert("Stale data", f"No {s} price for held {symbol} "
                                            f"({problems.get(symbol, 'missing bar')}); its stop wasn't checked today."))
                continue
            if position.entry_date != s and b["open"] <= position.stop_price:
                close(position, b["open"], "Stop Loss (gapped through)")
                continue
            if b["low"] <= position.stop_price:
                close(position, position.stop_price, "Stop Loss")
                continue
            position.bars_held += 1
            if position.max_hold_days and position.bars_held >= position.max_hold_days:
                close(position, b["close"], "Time Exit")
                continue
            position.last_price = float(b["close"])
            store.save_position(position)

        # 4. Exit signals at the close: sell at the next open.
        for symbol, position in sorted(positions.items()):
            signals, row = self.signals_for(position.strategy_id, symbol, for_exits), self._row(symbol, s)
            if signals is not None and row is not None and signals.exit[row]:
                key = f"{position.strategy_id}:{symbol}:{s}:sell"
                if store.add_order(key, position.strategy_id, symbol, "sell", position.quantity, s, position.price, 0.0,
                                   "Strategy Exit"):
                    self._dry_run(s, broker.exit_order(key, symbol, position.quantity), messages)
                    summary.orders += 1
                    store.add_decision(s, position.strategy_id, symbol, "EXIT_SIGNAL", "exit rule met: sell at the next open")

        # 5. Record the session.
        equity = cash + sum(p.market_value for p in positions.values())
        store.set_cash(cash)
        store.record_session(s, equity, cash)
        peak = max([store.starting_capital, equity, *history.tolist()])
        state = PortfolioState(cash=cash, positions=dict(positions), peak_equity=peak, day_start_equity=day_start)
        was_engaged = self.risk.kill_switch.engaged
        brakes = {c.name: c for c in self.risk.account_checks(state)}
        if not brakes["daily loss"].passed:
            messages.append(self._alert("Daily loss limit", brakes["daily loss"].detail + "; no new entries today."))

        # 6. New entries, through the risk engine (not from a strategy suspended earlier in this run).
        reserved, suspended = 0.0, store.suspended()
        for spec in strategies:
            if spec.id in suspended:
                continue
            evidence = load_evidence(spec.id, "research", self.evidence_dir)
            stats = (evidence.stats or {}) if evidence else {}
            for symbol in self.universes.get(spec.universe, []):
                if symbol not in for_entries:
                    continue
                signals, row = self.signals_for(spec.id, symbol, for_exits), self._row(symbol, s)
                if signals is None or row is None or not signals.entry[row]:
                    continue
                if symbol in exited_today:
                    store.add_decision(s, spec.id, symbol, "NO_TRADE", "exited today, so no re-entry from today's close")
                    continue
                frame = for_entries[symbol]
                traded = float((frame["close"] * frame["volume"]).iloc[max(0, row - ADV_DAYS + 1):row + 1].mean())
                if not traded > 0:  # no usable volume, so the liquidity limit can't be checked
                    store.add_decision(s, spec.id, symbol, "NO_TRADE", "no volume data to check liquidity")
                    continue
                intent = TradeIntent(spec.id, symbol, s, float(frame["close"].iloc[row]), float(signals.stop[row]),
                                     sector_of(symbol, self.sectors), traded, spec.max_hold_days)
                state.cash = cash - reserved
                decision = self.risk.evaluate(intent, state)
                if not decision.approved:
                    store.add_decision(s, spec.id, symbol, "NO_TRADE", decision.reason)
                    if self.send_no_trade:
                        messages.append(templates.no_trade(symbol=symbol, strategy=self._name(spec.id),
                                                           reason=decision.reason, paper=self.paper))
                    continue
                key = f"{spec.id}:{symbol}:{s}:buy"
                if not store.add_order(key, spec.id, symbol, "buy", decision.quantity, s, intent.reference_price,
                                       intent.stop_distance, "Entry"):
                    store.add_decision(s, spec.id, symbol, "NO_TRADE", "duplicate order prevented")
                    messages.append(self._alert("Duplicate order prevented", f"{spec.id} {symbol} {s} buy already exists."))
                    continue
                self._dry_run(s, broker.entry_order(key, symbol, decision.quantity), messages)
                summary.orders += 1
                reserved += decision.quantity * intent.reference_price * CASH_BUFFER
                # The pending buy counts as a position worth the cash set aside for it, so equity (and the
                # size of the next order) is unchanged; its exposure is overstated by the buffer, not under.
                state.positions[symbol] = Position(spec.id, symbol, decision.quantity, intent.reference_price,
                                                   intent.reference_price * (1 - intent.stop_distance), s, intent.sector,
                                                   last_price=intent.reference_price * CASH_BUFFER)
                store.add_decision(s, spec.id, symbol, "BUY_SIGNAL", f"{decision.quantity} shares; exits on {spec.exit_note}")
                messages.append(templates.buy_signal(
                    symbol=symbol, market=market_of(symbol), last_close=intent.reference_price,
                    stop_distance=intent.stop_distance, quantity=decision.quantity, strategy=self._name(spec.id),
                    exit_note=spec.exit_note, win_rate=stats.get("holdout_win_rate"),
                    expectancy=stats.get("holdout_mean_net"), reason=f"{spec.id} entry rule met at the {s} close",
                    paper=self.paper))
        if self.risk.kill_switch.engaged and not was_engaged:
            messages.append(self._alert("Kill switch", self.risk.kill_switch.reason))

        # 7. Watch each strategy's paper results for decay.
        for spec in strategies:
            trades = store.trades(spec.id)
            evidence = load_evidence(spec.id, "research", self.evidence_dir)
            win_rate = (evidence.stats or {}).get("holdout_win_rate", 0.5) if evidence else 0.5
            action, why = decay_check(trades["r_multiple"].to_numpy(float), win_rate, self.decay)
            if action != "keep" and spec.id not in store.suspended():
                store.suspend(spec.id, s, f"{action}: {why}")
                messages.append(self._alert("Strategy suspended", f"{spec.id} ({action}): {why}. Review it before "
                                            "changing its status in config/strategies.toml."))

        # 8. Rebuild cash and holdings from the fills; any mismatch stops new trading.
        mismatches = store.reconcile()
        if mismatches:
            self.risk.kill_switch.engage("reconciliation failed: " + mismatches[0])
            messages.append(self._alert("Reconciliation failed", "; ".join(mismatches)))

        if final:
            checked = [f"{symbol} closed at {templates.rupees(b['close'])}" if (b := bar(symbol)) is not None
                       else f"{symbol}: no price today" for symbol in self.market_check]
            record = self._record + len(summary.sessions) + 1
            messages.append(templates.daily_summary(
                session=s.isoformat(), equity=equity, day_change=equity / day_start - 1 if day_start else 0.0,
                cash=cash, positions=[(p.symbol, p.quantity, p.price) for p in positions.values()],
                strategies=len({spec.id for spec in strategies} - set(store.suspended())), paper=self.paper,
                market=checked, record=f"{record} of {UNATTENDED_TARGET} clean sessions in a row before live trading"))
        for text in messages:
            store.queue_message(s, text)

    def _close(self, position: Position, price: float, s: date, reason: str, cash: float, messages: list,
               order_id: int | None) -> float:
        spec = self.catalog.get(position.strategy_id)
        costs = spec.costs if spec else ZERODHA_DELIVERY
        notional = position.quantity * price
        fees = costs.one_side(notional, "sell")
        entry_notional = position.quantity * position.entry_price
        pnl = notional - entry_notional - fees - position.entry_fees
        risk_amount = entry_notional * position.stop_distance
        self.store.add_fill(s, order_id, position.strategy_id, position.symbol, "sell", position.quantity, price, fees, reason)
        if order_id is not None:
            self.store.set_order_status(order_id, "FILLED", s)
        self.store.add_trade(position.strategy_id, position.symbol, position.quantity, position.entry_date,
                             position.entry_price, s, price, reason, fees + position.entry_fees, pnl,
                             pnl / entry_notional, pnl / risk_amount if risk_amount > 0 else float("nan"))
        self.store.delete_position(position.symbol)
        if order_id is not None:  # its after-market sell filled at the open, so the stop's GTT goes
            self._dry_run(s, broker.cancel_stop(position, broker.AFTER_OPEN), messages)
        elif reason == "Time Exit":
            self._dry_run(s, broker.cancel_stop(position, broker.BEFORE_CLOSE), messages)
            self._dry_run(s, broker.time_exit(position), messages)
        elif price < broker.stop_limit(position.stop_price):  # opened below the GTT's limit: that sell can't fill
            self._dry_run(s, broker.gap_exit(position), messages)
        messages.append(templates.sell_executed(symbol=position.symbol, price=price, quantity=position.quantity,
                                                pnl=pnl, net_return=pnl / entry_notional, reason=reason, paper=self.paper))
        return cash + notional - fees

    def _dry_run(self, s: date, request: broker.KiteRequest, messages: list) -> None:
        """Record the Kite request a live system would send for this step (never sent). US stocks are traded
        by hand, so only NSE stocks get one."""
        if market_of(request.symbol) != "NSE":
            return
        problems = "; ".join(broker.problems(request))
        self.store.add_dry_run_order(s, request.tag, request.symbol, request.purpose, request.send_at, request.json(),
                                     problems)
        if problems:
            messages.append(self._alert("Dry-run order invalid", f"Kite would refuse the {request.purpose} for "
                                        f"{request.symbol}: {problems}. Fix this before any live trading."))

    def _name(self, strategy_id: str) -> str:
        record = self.registry.get_by_id(strategy_id)
        return record.name if record else strategy_id

    def _alert(self, title: str, detail: str) -> str:
        return templates.risk_alert(title=title, detail=detail, paper=self.paper)

    def flush_outbox(self) -> int:
        """Send queued messages in order; stop at the first failure and retry on the next run."""
        sent = 0
        for message_id, text in self.store.unsent_messages():
            if not self.notifier.send(text):
                break
            self.store.mark_sent(message_id)
            sent += 1
        return sent


def ping_heartbeat(url: str, http=requests) -> bool:
    """Tell an external dead man's switch (e.g. healthchecks.io) that the run succeeded: if the pings stop,
    it alerts you even when this computer is off. Never raises, and never logs the URL (it is a secret)."""
    try:
        response = http.get(url, timeout=10)
    except requests.RequestException as exc:
        log.warning("Heartbeat ping failed (%s)", type(exc).__name__)
        return False
    if response.status_code >= 400:
        log.warning("Heartbeat ping failed (HTTP %s)", response.status_code)
        return False
    return True


def daily(store: PaperStore, notifier, build, until: date | None = None, start: date | None = None,
          heartbeat: str = "", secrets=(), http=requests, clock=None, backup_dir: Path | None = None) -> int:
    """One unattended run, recorded in the store's runs table. `build()` makes the PaperTrader, so setup
    failures (a broken config, no Kite login) count as failed runs too. A failure sends an alert with
    every secret masked; a halt for missing data has queued its own alert. After a run that didn't fail,
    the records are backed up to `backup_dir` (one copy per day), and only a clean run pings the
    heartbeat. Returns the process exit code: 0 ok, 1 failed, 2 halted."""
    clock = clock or (lambda: datetime.now(IST))
    run_id = store.start_run(clock())
    try:
        trader = build()
        summary = trader.run(until, start)
    except Exception as exc:  # every failure is recorded and reported, never swallowed
        detail = redact(f"{type(exc).__name__}: {exc}", secrets)[:500]
        log.error("Daily run failed: %s", detail, exc_info=True)
        store.finish_run(run_id, "failed", clock(), 0, detail)
        notifier.send(templates.risk_alert(title="Daily run failed", detail=f"{detail}. Nothing after the last "
                                           "processed session was recorded; fix the cause and run it again."))
        return 1
    status = "halted" if summary.halted else "ok"
    store.finish_run(run_id, status, clock(), len(summary.sessions), summary.halted or "; ".join(summary.notes))
    for note in summary.notes:
        log.info(note)
    if summary.halted:
        log.warning("Stopped early: %s", summary.halted)
    history = store.equity_history()
    log.info("Paper trading: %d session(s) processed (%s), %d order(s), %d fill(s), %d closed trade(s), "
             "%d message(s) sent; equity %s", len(summary.sessions),
             ", ".join(map(str, summary.sessions)) or "none", summary.orders, summary.fills, summary.trades,
             summary.messages_sent, f"{history.iloc[-1]:,.2f}" if len(history) else "n/a")
    if backup_dir is not None:
        try:
            log.info("Backed up the paper records to %s", store.backup(backup_dir, clock().date()))
        except (OSError, sqlite3.Error) as exc:  # the health check reports a stale backup
            log.warning("Backup failed: %s: %s", type(exc).__name__, exc)
    if status == "ok" and heartbeat:
        ping_heartbeat(heartbeat, http)
    return 0 if status == "ok" else 2


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="End-of-day paper trading. Never places a real order.")
    parser.add_argument("--until", type=date.fromisoformat, help="last session to process (default: latest completed)")
    parser.add_argument("--start", type=date.fromisoformat, help="first run only: replay from this session")
    args = parser.parse_args(argv)

    settings = load_settings()
    secrets = settings.secret_values() + session_secrets()
    configure_logging(secrets=secrets)
    for warning in settings.warnings:
        log.warning(warning)
    database = ROOT / settings.paper_database
    store = PaperStore(database, settings.paper_starting_capital)
    notifier = notifier_from_settings(settings)

    def build() -> PaperTrader:
        registry = StrategyRegistry.load()
        for problem in registry.problems:
            log.warning("Registry: %s", problem)
        return PaperTrader(store=store, provider=make_provider(settings), calendar=load_calendars()["NSE"],
                           registry=registry, risk=RiskEngine(load_limits(), KillSwitch()), notifier=notifier,
                           decay=load_gate_config().decay, send_no_trade=settings.paper_send_no_trade,
                           market_check=MARKET_CHECK)

    try:
        code = daily(store, notifier, build, args.until, args.start, settings.heartbeat_url.reveal(), secrets,
                     backup_dir=database.parent / "backups")
    except Exception:  # the run record itself failed (e.g. a locked database): log it, with secrets masked
        log.exception("The daily run could not be recorded")
        code = 1
    raise SystemExit(code)


if __name__ == "__main__":
    main()
