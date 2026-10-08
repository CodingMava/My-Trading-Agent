"""Frozen datasets: market data saved once, with checksums, so every backtest can be reproduced.

    python -m trader.research.datasets fetch --name nse_daily_10y --interval 1d --period 10y --universe nifty
    python -m trader.research.datasets fetch --name us_daily_10y --interval 1d --period 10y AAPL MSFT
    python -m trader.research.datasets info data/nse_daily_10y

Data lives under data/, which is git-ignored: Yahoo Finance data is for personal research only and
must not be committed or redistributed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from trader.config import ROOT

DATA_DIR = ROOT / "data"
MANIFEST = "manifest.json"
OHLCV = ["open", "high", "low", "close", "volume"]
log = logging.getLogger(__name__)


def _filename(ticker: str) -> str:
    return re.sub(r'[<>:"/\\|?*]', "_", ticker) + ".parquet"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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


def fetch_yahoo(tickers: list[str], interval: str = "1d", period: str = "10y") -> dict[str, pd.DataFrame]:
    """Split- and dividend-adjusted OHLCV from Yahoo Finance (research only; not for live decisions)."""
    import yfinance as yf

    frames = {}
    for ticker in tickers:
        try:
            frame = yf.Ticker(ticker).history(interval=interval, period=period)
        except Exception as exc:  # one bad ticker shouldn't stop the download
            log.warning("%s: download failed: %s", ticker, exc)
            continue
        if frame.empty:
            log.warning("%s: no data returned", ticker)
            continue
        frame.columns = [str(col).lower() for col in frame.columns]
        frames[ticker] = frame[OHLCV]
    return frames


def main(argv: list[str] | None = None) -> None:
    from trader.logging_setup import make_console_utf8

    make_console_utf8()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Fetch and freeze research datasets.")
    sub = parser.add_subparsers(dest="command", required=True)
    fetch = sub.add_parser("fetch", help="download from Yahoo Finance and freeze under data/<name>")
    fetch.add_argument("--name", required=True)
    fetch.add_argument("--interval", default="1d")
    fetch.add_argument("--period", default="10y")
    fetch.add_argument("--universe", choices=["nifty"], help="use the tickers in universe.py")
    fetch.add_argument("tickers", nargs="*")
    info = sub.add_parser("info", help="show a frozen dataset's manifest")
    info.add_argument("directory")
    args = parser.parse_args(argv)

    if args.command == "info":
        manifest = load_manifest(Path(args.directory))
        print(json.dumps({k: v for k, v in manifest.items() if k != "files"}, indent=2))
        for ticker in manifest["tickers"]:
            entry = manifest["files"][ticker]
            print(f"  {ticker:15s} {entry['rows']:>7d} rows  {entry['first']} -> {entry['last']}")
        return

    tickers = list(args.tickers)
    if args.universe == "nifty":
        from universe import get_nifty_universe
        tickers += get_nifty_universe()
    if not tickers:
        parser.error("give tickers or --universe")
    frames = fetch_yahoo(tickers, args.interval, args.period)
    out = save_dataset(frames, DATA_DIR / args.name, source="Yahoo Finance via yfinance (adjusted)",
                       interval=args.interval, period=args.period)
    print(f"Saved {len(frames)}/{len(tickers)} tickers to {out}")


if __name__ == "__main__":
    main()
