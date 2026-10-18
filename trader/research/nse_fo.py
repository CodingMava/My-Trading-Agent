"""NSE's daily futures-and-options files (F&O bhavcopies), for research on derivatives-based signals.

    python -m trader.research.nse_fo download      # every session's file since 2008 into NSE_RAW/fo (outside OneDrive)
    python -m trader.research.nse_fo download --month-ends   # only each month's last session (monthly signals)
    python -m trader.research.nse_fo compact       # stock futures and near-expiry stock options, per year, into NSE_RAW/fo_compact

The raw files are large (about 2-3 GB for 2008-2026), so they live outside the project folder (which OneDrive syncs):
in the folder named by the environment variable NSE_RAW, by default C:/Users/11231/nse_raw. Each file is kept unchanged
and its SHA-256 recorded in fo_manifest.json beside it. Only stock contracts are extracted: every stock future, and the
stock options of the two nearest expiries with strikes within 30% of the nearest future's settlement price. Contracts
that didn't trade keep their row but are marked (contracts = 0): their close is stale and their settlement price is
NSE's own model, so research must not read prices from them.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import time
import zipfile
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import requests

from trader.logging_setup import make_console_utf8
from trader.research import nse_bhavcopy as nb

RAW_ROOT = Path(os.environ.get("NSE_RAW", "C:/Users/11231/nse_raw"))
FO_RAW, COMPACT = RAW_ROOT / "fo", RAW_ROOT / "fo_compact"
MANIFEST = FO_RAW / "fo_manifest.json"
FIRST = date(2008, 1, 1)
OLD_URL = "https://nsearchives.nseindia.com/content/historical/DERIVATIVES/{y}/{mon}/fo{d:02d}{mon}{y}bhav.csv.zip"
NEW_URL = "https://nsearchives.nseindia.com/content/fo/BhavCopy_NSE_FO_0_0_0_{ymd}_F_0000.csv.zip"
STRIKE_BAND = 0.30
COLUMNS = ["date", "kind", "symbol", "expiry", "strike", "open", "high", "low", "close", "settle", "contracts", "oi",
           "chg_oi", "underlying"]


def fo_url(day: date) -> str:
    if day >= nb.UDIFF_FROM:
        return NEW_URL.format(ymd=f"{day:%Y%m%d}")
    return OLD_URL.format(y=day.year, mon=f"{day:%b}".upper(), d=day.day)


def raw_path(day: date) -> Path:
    return FO_RAW / str(day.year) / f"fo_{day:%Y%m%d}.csv.zip"


def fetch(day: date, http=requests) -> str:
    """One session's file, saved unchanged. "saved", "have" (already there) or "absent" (NSE answered 404)."""
    path = raw_path(day)
    if path.exists():
        return "have"
    response = http.get(fo_url(day), headers=nb.RESEARCH_HEADERS, timeout=60)
    if response.status_code == 404:
        return "absent"
    response.raise_for_status()
    zipfile.ZipFile(io.BytesIO(response.content)).testzip()  # a damaged answer raises here, before it is kept
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(response.content)
    return "saved"


def sessions_since(first: date = FIRST) -> list[date]:
    """The cash market's sessions (round 8's archive and forward test 2's new files): F&O trades on the same days."""
    days = sorted({nb.file_date(p) for p in nb.raw_files([nb.RAW_DIR, nb.ROOT8.parent / "forward2" / "bhavcopy_raw"])})
    return [d for d in days if d >= first]


def month_end_sessions(days: list[date]) -> list[date]:
    """The last session of each calendar month among `days` (the newest month only once a later month has begun)."""
    out = [a for a, b in zip(days, days[1:]) if (a.year, a.month) != (b.year, b.month)]
    return out


def download(pause: float = 0.4, month_ends: bool = False) -> dict:
    counts = {"saved": 0, "have": 0, "absent": 0, "failed": 0}
    days = sessions_since()
    for day in (month_end_sessions(days) if month_ends else days):
        try:
            status = fetch(day)
        except (requests.RequestException, zipfile.BadZipFile, OSError) as exc:
            counts["failed"] += 1
            print(f"{day}: {type(exc).__name__}: {exc}", flush=True)
            time.sleep(5)
            continue
        counts[status] += 1
        if status == "saved":
            time.sleep(pause)
    write_manifest()
    return counts


def write_manifest() -> None:
    entries = {str(p.relative_to(FO_RAW)).replace("\\", "/"): hashlib.sha256(p.read_bytes()).hexdigest()
               for p in sorted(FO_RAW.glob("*/fo_*.csv.zip"))}
    MANIFEST.write_text(json.dumps(entries, indent=1), encoding="utf-8")


def parse(path: Path) -> pd.DataFrame:
    """One file's stock contracts in one shape, old format or UDiFF."""
    with zipfile.ZipFile(path) as z:
        frame = pd.read_csv(z.open(z.namelist()[0]), low_memory=False)
    frame.columns = [c.strip() for c in frame.columns]
    frame = frame.rename(columns={"OPTIONTYPE": "OPTION_TYP"})  # one 2008 file spells it so
    if "INSTRUMENT" in frame:
        f = frame[frame["INSTRUMENT"].astype(str).str.strip().isin(["FUTSTK", "OPTSTK"])]
        # stock options were American (CA, PA) until 2011, then European (CE, PE): one label for each side
        side = f["OPTION_TYP"].astype(str).str.strip().replace({"CA": "CE", "PA": "PE"})
        kind = np.where(f["INSTRUMENT"].str.strip() == "FUTSTK", "FUT", side)
        out = pd.DataFrame({"date": pd.to_datetime(f["TIMESTAMP"], format="%d-%b-%Y", errors="coerce"), "kind": kind,
                            "symbol": f["SYMBOL"].astype(str).str.strip(),
                            "expiry": pd.to_datetime(f["EXPIRY_DT"], format="%d-%b-%Y", errors="coerce"),
                            "strike": f["STRIKE_PR"], "open": f["OPEN"], "high": f["HIGH"], "low": f["LOW"],
                            "close": f["CLOSE"], "settle": f["SETTLE_PR"], "contracts": f["CONTRACTS"],
                            "oi": f["OPEN_INT"], "chg_oi": f["CHG_IN_OI"], "underlying": np.nan})
    else:
        f = frame[frame["FinInstrmTp"].astype(str).str.strip().isin(["STF", "STO"])]
        kind = np.where(f["FinInstrmTp"].str.strip() == "STF", "FUT", f["OptnTp"].astype(str).str.strip())
        out = pd.DataFrame({"date": pd.to_datetime(f["TradDt"], errors="coerce"), "kind": kind,
                            "symbol": f["TckrSymb"].astype(str).str.strip(),
                            "expiry": pd.to_datetime(f["XpryDt"], errors="coerce"), "strike": f["StrkPric"],
                            "open": f["OpnPric"], "high": f["HghPric"], "low": f["LwPric"], "close": f["ClsPric"],
                            "settle": f["SttlmPric"], "contracts": f["TtlTradgVol"], "oi": f["OpnIntrst"],
                            "chg_oi": f["ChngInOpnIntrst"], "underlying": f["UndrlygPric"]})
    out["strike"] = out["strike"].where(out["kind"] != "FUT", np.nan)
    return out[COLUMNS].reset_index(drop=True)


def compact_day(frame: pd.DataFrame) -> pd.DataFrame:
    """Every stock future; the options of the two nearest expiries, strikes within 30% of the nearest future's settle."""
    fut = frame[frame["kind"] == "FUT"]
    near = fut.sort_values("expiry").groupby("symbol").head(1).set_index("symbol")["settle"]
    opts = frame[frame["kind"].isin(["CE", "PE"])]
    expiries = opts.groupby("symbol")["expiry"].apply(lambda s: set(sorted(s.unique())[:2]))
    keep = pd.Series([e in expiries.get(s, set()) for s, e in zip(opts["symbol"], opts["expiry"])], index=opts.index,
                     dtype=bool)
    opts = opts[keep]
    ref = opts["symbol"].map(near)
    opts = opts[(ref.notna()) & ((opts["strike"] / ref - 1).abs() <= STRIKE_BAND)]
    return pd.concat([fut, opts], ignore_index=True)


def compact() -> dict:
    COMPACT.mkdir(parents=True, exist_ok=True)
    years = {}
    for path in sorted(FO_RAW.glob("*/fo_*.csv.zip")):
        years.setdefault(path.parent.name, []).append(path)
    rows = {}
    for year, paths in years.items():
        frames = [compact_day(parse(p)) for p in paths]
        table = pd.concat(frames, ignore_index=True)
        table.to_parquet(COMPACT / f"fo_{year}.parquet", index=False)
        rows[year] = len(table)
    return rows


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="NSE's daily F&O files for research (stored outside OneDrive).")
    parser.add_argument("command", choices=["download", "compact"])
    parser.add_argument("--month-ends", action="store_true", help="download: only each month's last session")
    args = parser.parse_args(argv)
    make_console_utf8()
    print(download(month_ends=args.month_ends) if args.command == "download" else compact())


if __name__ == "__main__":
    main()
