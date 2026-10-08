"""Frozen datasets: market data saved once, with checksums and a validation report, so every
backtest can be reproduced and its data problems are known up front.

    python -m trader.research.datasets fetch --name nse_daily_10y --interval 1d --period 10y --universe nifty
    python -m trader.research.datasets fetch --name us_daily_10y --interval 1d --period 10y AAPL MSFT
    python -m trader.research.datasets fetch --name nse_daily_kite --provider kite --period 5y --universe nifty
    python -m trader.research.datasets validate data/nse_daily_10y
    python -m trader.research.datasets info data/nse_daily_10y

Data lives under data/, which is git-ignored: Yahoo Finance data is for personal research only and
must not be committed or redistributed. Yahoo's 5-minute history reaches back about 60 days.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from trader.config import ROOT

DATA_DIR = ROOT / "data"
MANIFEST = "manifest.json"
_PERIOD_DAYS = {"d": 1, "wk": 7, "mo": 31, "y": 366}


def _filename(ticker: str) -> str:
    return re.sub(r'[<>:"/\\|?*]', "_", ticker) + ".parquet"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def period_days(period: str) -> int:
    """"60d", "6mo", "10y" -> a number of calendar days (rounded up)."""
    match = re.fullmatch(r"(\d+)(d|wk|mo|y)", period)
    if not match:
        raise ValueError(f"period must look like 60d, 6mo or 10y; got {period!r}")
    return int(match[1]) * _PERIOD_DAYS[match[2]]


def save_dataset(frames: dict[str, pd.DataFrame], directory: Path, **meta) -> Path:
    """Write one Parquet file per ticker plus a manifest (ticker order, row counts, checksums)."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    files = {}
    for ticker, frame in frames.items():
        path = directory / _filename(ticker)
        frame.to_parquet(path)
        files[ticker] = {"file": path.name, "rows": len(frame), "sha256": _sha256(path),
                         "first": str(frame.index[0]) if len(frame) else None,
                         "last": str(frame.index[-1]) if len(frame) else None}
    manifest = {"saved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "tickers": list(frames), "files": files, **meta}
    (directory / MANIFEST).write_text(json.dumps(manifest, indent=2, default=str), encoding="utf-8")
    return directory


def load_manifest(directory: Path) -> dict:
    return json.loads((Path(directory) / MANIFEST).read_text(encoding="utf-8"))


def load_dataset(directory: Path, verify: bool = True) -> dict[str, pd.DataFrame]:
    """Load a frozen dataset in its saved ticker order; refuses files whose checksum changed."""
    directory = Path(directory)
    manifest = load_manifest(directory)
    frames = {}
    for ticker in manifest["tickers"]:
        entry = manifest["files"][ticker]
        path = directory / entry["file"]
        if verify and _sha256(path) != entry["sha256"]:
            raise ValueError(f"{path} does not match its checksum: the frozen dataset was modified")
        frames[ticker] = pd.read_parquet(path)
    return frames


def validation_summary(frames: dict[str, pd.DataFrame], interval: str) -> tuple[pd.DataFrame, dict]:
    """(table for printing, dict for the manifest) from validate_dataset()."""
    from trader.data.validate import report_table, validate_dataset
    from trader.markets.calendar import load_calendars

    reports = validate_dataset(frames, interval, load_calendars())
    return report_table(reports), {symbol: report.as_dict() for symbol, report in reports.items()}


def main(argv: list[str] | None = None) -> None:
    from trader.logging_setup import make_console_utf8

    make_console_utf8()
    pd.set_option("display.width", 250)
    pd.set_option("display.max_colwidth", 160)
    parser = argparse.ArgumentParser(description="Fetch, freeze and validate research datasets.")
    sub = parser.add_subparsers(dest="command", required=True)
    fetch = sub.add_parser("fetch", help="download and freeze under data/<name>, with a validation report")
    fetch.add_argument("--name", required=True)
    fetch.add_argument("--provider", choices=["yahoo", "kite"], default="yahoo")
    fetch.add_argument("--interval", default="1d")
    fetch.add_argument("--period", default="10y", help="how far back, e.g. 59d, 6mo, 10y")
    fetch.add_argument("--universe", choices=["nifty"], help="add the tickers in universe.py")
    fetch.add_argument("tickers", nargs="*")
    validate = sub.add_parser("validate", help="re-check a frozen dataset and print the report")
    validate.add_argument("directory")
    info = sub.add_parser("info", help="show a frozen dataset's manifest")
    info.add_argument("directory")
    args = parser.parse_args(argv)

    if args.command == "info":
        manifest = load_manifest(Path(args.directory))
        print(json.dumps({k: v for k, v in manifest.items() if k not in ("files", "validation")}, indent=2))
        for ticker in manifest["tickers"]:
            entry = manifest["files"][ticker]
            print(f"  {ticker:15s} {entry['rows']:>7d} rows  {entry['first']} -> {entry['last']}")
        return

    if args.command == "validate":
        directory = Path(args.directory)
        table, _ = validation_summary(load_dataset(directory), load_manifest(directory)["interval"])
        print(table.to_string(index=False))
        return

    from trader.config import load_settings
    from trader.data.providers import YahooProvider, fetch_many

    tickers = list(args.tickers)
    if args.universe == "nifty":
        from universe import get_nifty_universe
        tickers += get_nifty_universe()
    if not tickers:
        parser.error("give tickers or --universe")
    if args.provider == "kite":
        from trader.data.kite import provider_from_settings
        provider = provider_from_settings(load_settings())
    else:
        provider = YahooProvider()
    end = datetime.now(timezone.utc)
    frames, failures = fetch_many(provider, tickers, args.interval, end - timedelta(days=period_days(args.period)), end)
    for ticker, reason in failures.items():
        print(f"  {ticker}: {reason}")
    table, validation = validation_summary(frames, args.interval)
    out = save_dataset(frames, DATA_DIR / args.name, source=provider.name, interval=args.interval,
                       period=args.period, validation=validation)
    print(table.to_string(index=False))
    print(f"Saved {len(frames)}/{len(tickers)} tickers to {out}")


if __name__ == "__main__":
    main()
