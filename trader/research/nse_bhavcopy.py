"""NSE's daily capital-market bhavcopies: the exchange's own end-of-day file for every listed security, including
companies that were later delisted, so a universe built from them, date by date, has no survivorship bias.

    python -m trader.research.nse_bhavcopy build     # raw files -> one frozen, adjusted table, with checksums
    python -m trader.research.nse_bhavcopy audit     # the data-quality report (no returns a strategy would earn)

Inputs, all under data/round8/ (git-ignored) and kept unchanged:

* bhavcopy_raw/<year>/*.zip: the old format (cmDDMONYYYYbhav.csv.zip) up to 5 Jul 2024, UDiFF after;
* corporate_actions/<YYYY-MM>.json: NSE's corporate-action records (nseindia.com/api/corporates-corporateActions);
* symbolchange.csv: NSE's list of symbol changes.

Corporate actions. NSE's previous close (PREVCLOSE) is the raw previous close: a split or bonus shows up as a fall
of half or more on its ex-date. So corporate actions are applied from NSE's own records, as a factor on the ex-date:

* split: new face value / old; bonus a:b: b / (a + b). A record whose ex-date doesn't match the price change is
  moved to the session within 5 that does, or, with no such session, not applied (both reported);
* rights a:b at subscription price S (face value + premium): the theoretical ex-rights price, (P + n S) / (1 + n) / P
  with n = a / b, when the opening gap agrees within 15%;
* a dividend of at least 5% of the previous close: 1 - dividend / previous close;
* distributions without a ratio (demergers, schemes of arrangement, capital reductions, bonus debentures or
  preference shares): the ex-date's close / previous close, when it fell more than 3%;
* splits and bonuses missing from the records (mostly 2005-2008): inferred when the open fell more than 40% to within
  6% of a standard ratio; and the one distribution the audit found with no record (MANUAL_DISTRIBUTIONS).

Ordinary dividends (under 5%) are not adjusted: returns are price returns.

Each security keeps one history under its latest symbol: NSE's renames are joined where the new symbol's first
previous close continues the old symbol's last close.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import zipfile
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from trader.research.datasets import DATA_DIR

ROOT8 = DATA_DIR / "round8"
RAW_DIR = ROOT8 / "bhavcopy_raw"
CA_DIR = ROOT8 / "corporate_actions"
SYMBOL_CHANGES = ROOT8 / "symbolchange.csv"
PANEL_DIR = ROOT8 / "nse_eq"
SERIES = ("EQ", "BE", "BZ")  # equity shares: normal, trade-for-trade, trade-for-trade for non-compliant companies
SERIES_RANK = {"EQ": 0, "BE": 1, "BZ": 2}  # a security quoted in two equity series on one day keeps the first
PRICES = ["open", "high", "low", "close", "prevclose", "value"]
OLD = {"SYMBOL": "symbol", "SERIES": "series", "OPEN": "open", "HIGH": "high", "LOW": "low", "CLOSE": "close",
       "PREVCLOSE": "prevclose", "TOTTRDVAL": "value", "TIMESTAMP": "stated", "ISIN": "isin"}
NEW = {"TckrSymb": "symbol", "SctySrs": "series", "OpnPric": "open", "HghPric": "high", "LwPric": "low",
       "ClsPric": "close", "PrvsClsgPric": "prevclose", "TtlTrfVal": "value", "TradDt": "stated", "ISIN": "isin"}
DISTRIBUTION = re.compile(r"demerger|arrangement|arangement|capital reduction|reduction of capital|"
                          r"bonus\s*[-:]?\s*(?:issue of\s*)?(?:debenture|deb\b|deb\d|ncrps|ncd|pref|dvr|\d+\s*dvr)", re.I)
DISTRIBUTION_GAP = 0.97  # a distribution is applied only when the open fell below this x the previous close
EX_DATE_WINDOW = 5  # sessions searched either side when a record's ex-date doesn't match the price change
INFER_GAP = 0.60  # an opening fall of more than 40% ...
INFER_TOLERANCE = 0.06  # ... within 6% of a standard split or bonus ratio, with the close within 30%, is inferred
LARGE_DIVIDEND = 0.05  # dividends of at least this share of the previous close are adjusted (special dividends)
# Distributions the audit found with no record at all, applied as their opening gap.
MANUAL_DISTRIBUTIONS = [("RELIANCE", "2006-01-18", "Demerger of the four Reliance ADA companies: a 37.5% opening gap "
                                                   "with no record in NSE's corporate-action history")]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def raw_files(raw_dir: Path = RAW_DIR) -> list[Path]:
    return sorted(raw_dir.glob("*/*.zip"), key=file_date)


def file_date(path: Path) -> date:
    name = path.name
    if name.startswith("cm"):
        return datetime.strptime(name[2:11], "%d%b%Y").date()
    return datetime.strptime(name.split("_")[6], "%Y%m%d").date()


def parse(path: Path) -> pd.DataFrame:
    """One raw file -> its equity-series rows: date, symbol, series, isin, prices and traded value."""
    with zipfile.ZipFile(path) as zf:
        text = zf.read(zf.namelist()[0]).decode("latin-1")
    frame = pd.read_csv(io.StringIO(text), dtype=str, skipinitialspace=True)
    frame.columns = [c.strip() for c in frame.columns]
    frame = frame.rename(columns=OLD if "SYMBOL" in frame.columns else NEW)
    if "isin" not in frame.columns:
        frame["isin"] = pd.NA
    for column in ("symbol", "series", "isin"):
        frame[column] = frame[column].astype("string").str.strip()
    frame = frame[frame["series"].isin(SERIES)].copy()
    session = file_date(path)
    stated = pd.to_datetime(frame["stated"].astype(str).str.strip(), format="mixed").dt.date
    if len(frame) and not (stated == session).all():
        raise ValueError(f"{path.name}: rows dated {sorted(set(stated) - {session})[:3]}, not {session}")
    out = pd.DataFrame({"date": pd.Timestamp(session), "symbol": frame["symbol"].to_numpy(),
                        "series": frame["series"].to_numpy(), "isin": frame["isin"].to_numpy()})
    for column in PRICES:
        out[column] = pd.to_numeric(frame[column], errors="coerce").to_numpy(dtype="float64")
    return out


# --------------------------------------------------------------------------------- corporate actions
def parse_ratio(subject: str) -> tuple[float, list[str]]:
    """A record's split and bonus factor (1.0 if none) and what was found, e.g. (0.25, ['bonus 1:1', 'split 2->1'])."""
    s = subject.lower().replace("re.", "rs.").replace("re ", "rs ")
    s = re.sub(r"(\d)\s*to\s*r[se]\.?\s*(\d)", r"\1 to rs \2", s)  # "Rs10tors5", "Rs.5tors.2", "Rs10tore1"
    q, kinds = 1.0, []
    pattern = (r"\bbon(?:us)?\b\s*[-:]?\s*(?:issue\s*|shares in the ratio of\s*)?"
               r"(?!debenture|deb\b|ncrps|ncd|pref|redeemable|non)(\d+)\s*:\s*(\d+)(?!\s*eq)")
    for m in re.finditer(pattern, s):
        a, b = float(m.group(1)), float(m.group(2))
        if a > 0 and b > 0 and not re.search(r"dvr|debenture|ncrps|pref", s[m.start():m.end() + 12]):
            q *= b / (a + b)
            kinds.append(f"bonus {m.group(1)}:{m.group(2)}")
    m = re.search(r"(split|sub-?\s?division|\bspl\b\.?\s*-?\s*(?=(?:rs\.?\s*)?\d+\s*/?-?\s*to\b))(.*)", s)
    if m:
        clause = re.split(r"/(?=\s*(?:bon|div|agm|annual|rd\b|record|int|purpose|rights|spl div|final))|\bbon(?:us)?\b",
                          m.group(2))[0]
        nums = re.findall(r"(\d+(?:\.\d+)?)", clause)
        if len(nums) >= 2:
            old, new = float(nums[0]), float(nums[1])
            if 0 < new < old:
                q *= new / old
                kinds.append(f"split {old:g}->{new:g}")
    return q, kinds


def parse_rights(subject: str, face_value: float) -> tuple[float, float] | None:
    """(new shares per held share, subscription price) of a rights issue "Rights a:b @ Premium Rs P", or None. The
    subscription price is the face value plus the premium."""
    s = subject.lower()
    m = re.search(r"rights?(?:\s*issue)?\s*[-:]?\s*(\d+)\s*:\s*(\d+)\s*@?\s*(?:a\s*)?(premium|price)?[^\d]*(\d+(?:\.\d+)?)?", s)
    if not m or not np.isfinite(face_value):
        return None
    a, b = float(m.group(1)), float(m.group(2))
    if a <= 0 or b <= 0:
        return None
    amount = float(m.group(4)) if m.group(4) else 0.0
    price = amount if m.group(3) == "price" else face_value + amount
    return a / b, price


def parse_dividend(subject: str, face_value: float) -> float:
    """Rupees per share of the dividends named in a record (amounts in Rs, or a percentage of the face value)."""
    s = subject.lower().replace("re.", "rs.").replace("re ", "rs ")
    total = 0.0
    for part in re.split(r"[/|]", s):
        if "div" not in part:
            continue
        rupees = re.findall(r"rs\.?\s*(\d+(?:\.\d+)?)", part)
        if rupees:
            total += sum(float(x) for x in rupees)
        elif np.isfinite(face_value):
            total += sum(float(x) for x in re.findall(r"(\d+(?:\.\d+)?)\s*%", part)) * face_value / 100
    return total


def standard_ratios() -> dict[float, str]:
    """The price factors of common splits and bonuses, and of one of each together, for the splits and bonuses missing
    from NSE's records (mostly 2005-2008)."""
    splits = {1.0: "", 0.5: "split 2:1", 0.4: "split 5:2", 0.2: "split 5:1", 0.1: "split 10:1"}
    bonuses = {1.0: ""}
    for a in range(1, 5):
        for b in range(1, 5):
            if np.gcd(a, b) == 1:
                bonuses[b / (a + b)] = f"bonus {a}:{b}"
    out = {}
    for qs, s in splits.items():
        for qb, b in bonuses.items():
            q = qs * qb
            if q < 1.0:
                out.setdefault(round(q, 6), " with ".join(x for x in (s, b) if x))
    return out


def load_corporate_actions(ca_dir: Path = CA_DIR) -> pd.DataFrame:
    """Every equity record: symbol, isin, ex_date, subject, ratio (split and bonus factor), distribution (bool)."""
    rows = []
    for path in sorted(ca_dir.glob("*.json")):
        for r in json.loads(path.read_text(encoding="utf-8")):
            ex = pd.to_datetime(r.get("exDate"), format="%d-%b-%Y", errors="coerce")
            if pd.isna(ex):
                continue
            subject = (r.get("subject") or "").strip()
            ratio, kinds = parse_ratio(subject)
            face_value = pd.to_numeric(str(r.get("faceVal") or "").strip(), errors="coerce")
            rights = parse_rights(subject, face_value) if "right" in subject.lower() else None
            rows.append({"symbol": (r.get("symbol") or "").strip(), "isin": (r.get("isin") or "").strip(),
                         "ex_date": ex, "subject": subject, "ratio": ratio, "kinds": "; ".join(kinds),
                         "distribution": bool(DISTRIBUTION.search(subject)) and not kinds,
                         "rights_per_share": rights[0] if rights else np.nan,
                         "rights_price": rights[1] if rights else np.nan,
                         "dividend": parse_dividend(subject, face_value) if "div" in subject.lower() else 0.0})
    frame = pd.DataFrame(rows).drop_duplicates(["symbol", "ex_date", "subject"])
    # the same split or bonus filed twice (e.g. a revised purpose) is one action
    ratio = frame[frame["ratio"] != 1.0].drop_duplicates(["symbol", "ex_date", "kinds"])
    return pd.concat([ratio, frame[frame["ratio"] == 1.0]]).sort_values(["ex_date", "symbol"]).reset_index(drop=True)


def load_symbol_changes(path: Path = SYMBOL_CHANGES) -> pd.DataFrame:
    frame = pd.read_csv(path, dtype=str, encoding="latin-1")
    frame.columns = [c.strip() for c in frame.columns]
    frame = frame.rename(columns={"OLD SYMBOL": "old", "NEW SYMBOL": "new", "EFFECTIVE DATE": "effective"})
    frame["old"], frame["new"] = frame["old"].str.strip(), frame["new"].str.strip()
    frame["effective"] = pd.to_datetime(frame["effective"].str.strip(), format="%d-%b-%Y")
    return frame[["old", "new", "effective"]].dropna().sort_values("effective").reset_index(drop=True)


# ------------------------------------------------------------------------------------------ assembly
def join_renames(panel: pd.DataFrame, changes: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Give each security one id, its latest symbol. A rename joins two histories only if the old symbol's rows all
    come before the effective date, the new symbol's all on or after it, and the new symbol's first previous close is
    within 2% of the old symbol's last close. Returns the panel with `sid`, and every rename with the outcome."""
    order = panel.sort_values("date")
    spans = order.groupby("symbol", observed=True)["date"].agg(["min", "max"])
    first_prev = order.groupby("symbol", observed=True)["prevclose"].first()
    last_close = order.groupby("symbol", observed=True)["close"].last()
    report, links = [], {}
    for old, new, eff in changes.itertuples(index=False):
        row = {"old": old, "new": new, "effective": eff.date(), "joined": False, "ratio": np.nan, "why": ""}
        if old not in spans.index or new not in spans.index:
            row["why"] = "not both in the data"
        elif spans.loc[old, "max"] >= eff or spans.loc[new, "min"] < eff:
            row["why"] = f"dates overlap (old to {spans.loc[old, 'max'].date()}, new from {spans.loc[new, 'min'].date()})"
        else:
            ratio = first_prev[new] / last_close[old] if last_close[old] > 0 else np.nan
            row["ratio"] = ratio
            if np.isfinite(ratio) and abs(ratio - 1) < 0.02:
                row["joined"] = True
                links[old] = new
            else:
                row["why"] = "previous close does not continue"
        report.append(row)

    def final(symbol: str) -> str:
        seen = set()
        while symbol in links and symbol not in seen:
            seen.add(symbol)
            symbol = links[symbol]
        return symbol

    mapping = {s: final(s) for s in links}
    panel["sid"] = panel["symbol"].map(lambda s: mapping.get(s, s)).astype("string")
    return panel, pd.DataFrame(report)


def one_row_per_day(panel: pd.DataFrame) -> pd.DataFrame:
    rank = panel["series"].map(SERIES_RANK).astype("int8")
    panel = panel.assign(_rank=rank).sort_values(["sid", "date", "_rank"], kind="stable")
    return panel.drop_duplicates(["sid", "date"], keep="first").drop(columns="_rank").reset_index(drop=True)


def corporate_action_factors(panel: pd.DataFrame, actions: pd.DataFrame) -> tuple[pd.Series, pd.DataFrame]:
    """The factor for every row (1.0 unless a corporate action goes ex), and a log of every action: applied from a
    record, shifted to the session where its price change happened, not applied (no matching price change), applied
    as a distribution's opening gap, or inferred (a standard split or bonus ratio missing from the records).

    `panel` must be sorted by sid and date and carry `prev_row_close`. NSE's records name a company by its current
    symbol, so they are matched to a security's latest symbol (sid) first, then to the symbol it traded under."""
    factor = pd.Series(1.0, index=panel.index)
    log = []
    by_sid = {s: g for s, g in panel.groupby("sid", observed=True)}
    by_symbol = {s: g for s, g in panel.groupby("symbol", observed=True)}

    def rows_for(symbol: str, ex_date) -> pd.DataFrame | None:
        for table in (by_sid, by_symbol):
            rows = table.get(symbol)
            if rows is not None:
                after = rows[rows["date"] >= ex_date]
                if len(after) and (after["date"].iloc[0] - ex_date).days <= 10:
                    return rows
        return None

    ratios = actions[actions["ratio"] != 1.0]
    for (symbol, ex_date), recs in ratios.groupby(["symbol", "ex_date"], sort=True):
        q, kinds, subject = float(np.prod(recs["ratio"])), "; ".join(recs["kinds"]), " | ".join(recs["subject"])
        entry = {"symbol": symbol, "ex_date": ex_date.date(), "subject": subject, "kind": kinds, "factor": q}
        rows = rows_for(symbol, ex_date)
        if rows is None:
            log.append({**entry, "applied": False, "why": "no row near the ex-date"})
            continue
        first = rows.index.get_loc(rows[rows["date"] >= ex_date].index[0])
        lo = max(0, first - EX_DATE_WINDOW)
        window = rows.iloc[lo: first + EX_DATE_WINDOW + 1]
        gaps = (window["open"] / window["prev_row_close"]).to_numpy()
        here = first - lo
        if np.isfinite(gaps[here]) and abs(gaps[here] / q - 1) < 0.30:
            target, why = window.index[here], "applied"
        else:
            near = np.flatnonzero(np.isfinite(gaps) & (np.abs(gaps / q - 1) < 0.15))
            if not len(near):
                log.append({**entry, "applied": False, "why": "no matching price change within 5 sessions"})
                continue
            target, why = window.index[near[np.argmin(np.abs(near - here))]], "shifted to the price change"
        factor[target] *= q
        log.append({**entry, "applied": True, "why": why, "session": panel.at[target, "date"].date(),
                    "sid": panel.at[target, "sid"]})

    for rec in actions[actions["distribution"]].itertuples(index=False):
        rows = rows_for(rec.symbol, rec.ex_date)
        entry = {"symbol": rec.symbol, "ex_date": rec.ex_date.date(), "subject": rec.subject, "kind": "distribution"}
        if rows is None:
            log.append({**entry, "applied": False, "why": "no row near the ex-date"})
            continue
        target = rows[rows["date"] >= rec.ex_date].index[0]
        # the ex-date's close, not its open: on demerger days the opening print comes from a special price-discovery
        # session and was often far from where the stock traded (Adani Enterprises 2015, Sintex 2017)
        fall = panel.at[target, "close"] / panel.at[target, "prev_row_close"]
        applied = bool(np.isfinite(fall) and fall < DISTRIBUTION_GAP and panel.at[target, "date"] == rec.ex_date
                       and factor[target] == 1.0)
        if applied:
            factor[target] *= fall
        log.append({**entry, "applied": applied, "factor": fall if applied else 1.0,
                    "why": "the ex-date's fall" if applied else "no fall of 3% on the ex-date",
                    "session": panel.at[target, "date"].date(), "sid": panel.at[target, "sid"]})

    # rights issues: the theoretical ex-rights price, (P + n x S) / (1 + n) for n new shares per share at price S,
    # applied when the opening gap agrees with it (a holder keeps the value as the rights or the new shares)
    rights = actions[actions["rights_per_share"].notna()]
    for rec in rights.itertuples(index=False):
        rows = rows_for(rec.symbol, rec.ex_date)
        entry = {"symbol": rec.symbol, "ex_date": rec.ex_date.date(), "subject": rec.subject, "kind": "rights"}
        if rows is None:
            continue
        target = rows[rows["date"] >= rec.ex_date].index[0]
        prev, n, price = panel.at[target, "prev_row_close"], rec.rights_per_share, rec.rights_price
        terp = (prev + n * price) / (1 + n) / prev if prev > 0 else np.nan
        gap = panel.at[target, "open"] / prev if prev > 0 else np.nan
        applied = bool(np.isfinite(terp) and terp < DISTRIBUTION_GAP and abs(gap / terp - 1) < 0.15
                       and factor[target] == 1.0 and panel.at[target, "date"] == rec.ex_date)
        if applied:
            factor[target] *= terp
        if np.isfinite(terp) and terp < DISTRIBUTION_GAP:
            log.append({**entry, "applied": applied, "factor": terp,
                        "why": "theoretical ex-rights price" if applied else "opening gap disagrees",
                        "session": panel.at[target, "date"].date(), "sid": panel.at[target, "sid"]})

    # dividends of at least 5% of the price (special dividends): the price falls by the dividend
    big = actions[actions["dividend"] > 0]
    for rec in big.itertuples(index=False):
        rows = rows_for(rec.symbol, rec.ex_date)
        if rows is None:
            continue
        target = rows[rows["date"] >= rec.ex_date].index[0]
        prev = panel.at[target, "prev_row_close"]
        share = rec.dividend / prev if prev > 0 else np.nan
        if not (np.isfinite(share) and LARGE_DIVIDEND <= share < 1) or panel.at[target, "date"] != rec.ex_date:
            continue
        gap = panel.at[target, "open"] / prev
        applied = bool(factor[target] == 1.0 and gap <= 1 - share / 2)  # the open fell by at least half the dividend
        if applied:
            factor[target] *= 1 - share
        log.append({"symbol": rec.symbol, "ex_date": rec.ex_date.date(), "subject": rec.subject, "kind": "large dividend",
                    "factor": 1 - share, "applied": applied, "why": "dividend of 5% or more",
                    "session": panel.at[target, "date"].date(), "sid": panel.at[target, "sid"]})

    for symbol, day, why in MANUAL_DISTRIBUTIONS:
        rows = by_sid.get(symbol)
        hit = rows[rows["date"] == pd.Timestamp(day)] if rows is not None else None
        if hit is not None and len(hit) and factor[hit.index[0]] == 1.0:
            idx = hit.index[0]
            factor[idx] = panel.at[idx, "close"] / panel.at[idx, "prev_row_close"]
            log.append({"symbol": symbol, "ex_date": pd.Timestamp(day).date(), "subject": why, "kind": "manual",
                        "factor": factor[idx], "applied": True, "why": "missing from the records (audit)",
                        "session": pd.Timestamp(day).date(), "sid": symbol})

    # splits and bonuses missing from the records: an opening fall of over 40% at a standard ratio
    gap = panel["open"] / panel["prev_row_close"]
    close_ratio = panel["close"] / panel["prev_row_close"]
    candidates = panel.index[(factor == 1.0) & (gap < INFER_GAP)]
    ratios = standard_ratios()
    for idx in candidates:
        q, what = min(ratios.items(), key=lambda kv: abs(gap[idx] / kv[0] - 1))
        if abs(gap[idx] / q - 1) < INFER_TOLERANCE and abs(close_ratio[idx] / q - 1) < 0.30:
            factor[idx] = q
            log.append({"symbol": panel.at[idx, "symbol"], "ex_date": panel.at[idx, "date"].date(), "subject": "",
                        "kind": f"inferred: factor {q:.4f} ({what})", "factor": q, "applied": True,
                        "why": "inferred from the price change", "session": panel.at[idx, "date"].date(),
                        "sid": panel.at[idx, "sid"]})
    return factor, pd.DataFrame(log)


def build(raw_dir: Path = RAW_DIR, out_dir: Path = PANEL_DIR, ca_dir: Path = CA_DIR,
          changes_path: Path = SYMBOL_CHANGES) -> Path:
    files = raw_files(raw_dir)
    frames, inventory = [], {}
    for path in files:
        frames.append(parse(path))
        inventory[path.relative_to(raw_dir).as_posix()] = sha256(path)
    panel = pd.concat(frames, ignore_index=True)
    del frames
    isins = (panel.dropna(subset=["isin"]).groupby("symbol", observed=True)["isin"]
             .agg(lambda s: ";".join(sorted(set(s)))))
    panel = panel.drop(columns="isin")
    panel["series"] = panel["series"].astype("category")
    panel, renames = join_renames(panel, load_symbol_changes(changes_path))
    panel = one_row_per_day(panel)
    same = panel["sid"].eq(panel["sid"].shift(1))
    panel["prev_row_close"] = panel["close"].shift(1).where(same)
    actions = load_corporate_actions(ca_dir)
    factor, ca_log = corporate_action_factors(panel, actions)
    panel["factor"] = factor.to_numpy()
    # adj_t = product of the factors of every later row of the same security (prices in today's shares)
    log_f = np.log(panel["factor"].to_numpy())
    rev = pd.Series(log_f[::-1]).groupby(panel["sid"].to_numpy()[::-1]).cumsum().to_numpy()[::-1]
    panel["adj"] = np.exp(rev - log_f)
    for column in ["open", "high", "low", "close", "prevclose", "prev_row_close"]:
        panel[column] = panel[column].astype("float64")
    out_dir.mkdir(parents=True, exist_ok=True)
    panel_path = out_dir / "panel.parquet"
    panel.to_parquet(panel_path, index=False)
    isins.rename("isins").to_frame().to_csv(out_dir / "isins.csv")
    renames.to_csv(out_dir / "renames.csv", index=False)
    ca_log.to_csv(out_dir / "corporate_actions_applied.csv", index=False)
    sessions = sorted({file_date(p) for p in files})
    manifest = {"saved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "source": "NSE capital-market bhavcopies and corporate-action records (nseindia.com)",
                "raw_files": len(files), "sessions": len(sessions), "first": str(sessions[0]), "last": str(sessions[-1]),
                "rows": len(panel), "securities": int(panel["sid"].nunique()),
                "panel_sha256": sha256(panel_path), "isins_sha256": sha256(out_dir / "isins.csv"),
                "symbol_changes_sha256": sha256(changes_path),
                "corporate_actions_sha256": {p.name: sha256(p) for p in sorted(ca_dir.glob("*.json"))},
                "raw": inventory}
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    return panel_path


def load_panel(out_dir: Path = PANEL_DIR, expected_sha256: str | None = None, columns: list[str] | None = None) -> pd.DataFrame:
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    path = out_dir / "panel.parquet"
    digest = sha256(path)
    if digest != manifest["panel_sha256"] or (expected_sha256 and digest != expected_sha256):
        raise ValueError(f"{path} does not match its pinned checksum: the frozen panel changed")
    return pd.read_parquet(path, columns=columns)


def load_isins(out_dir: Path = PANEL_DIR) -> dict[str, str]:
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    path = out_dir / "isins.csv"
    if sha256(path) != manifest["isins_sha256"]:
        raise ValueError(f"{path} does not match its checksum")
    frame = pd.read_csv(path, dtype=str, keep_default_na=False)
    return dict(zip(frame["symbol"], frame["isins"]))


# ------------------------------------------------------------------------------------------------- audit
def audit(panel: pd.DataFrame, out_dir: Path = PANEL_DIR) -> dict:
    """Data-quality facts only: coverage, duplicates, broken prices, previous-close continuity, corporate actions
    applied, renames, and every large one-day move left after the adjustments. Nothing about returns a strategy
    would earn."""
    out = {}
    sessions = pd.Series(sorted(panel["date"].unique()))
    out["sessions_per_year"] = {int(k): int(v) for k, v in sessions.dt.year.value_counts().sort_index().items()}
    gaps = [(a.date(), b.date()) for a, b in zip(sessions, sessions[1:]) if (b - a).days > 5]
    out["gaps_over_5_days"] = [(str(a), str(b)) for a, b in gaps]
    out["weekend_sessions"] = [str(d.date()) for d in sessions if d.weekday() >= 5]
    eq = panel[panel["series"] == "EQ"].groupby("date").size()
    out["eq_rows_per_session"] = {"min": int(eq.min()), "median": int(eq.median()), "max": int(eq.max())}
    out["duplicates_sid_date"] = int(panel.duplicated(["sid", "date"]).sum())
    prices = panel[["open", "high", "low", "close"]]
    bad = (prices <= 0).any(axis=1) | prices.isna().any(axis=1)
    out["rows_missing_or_nonpositive_price"] = int(bad.sum())
    p = panel[~bad]
    out["rows_high_below_low"] = int((p["high"] < p["low"]).sum())
    out["rows_open_or_close_outside_range"] = int(((p["open"] > p["high"] * 1.0001) | (p["open"] < p["low"] * 0.9999)
                                                    | (p["close"] > p["high"] * 1.0001) | (p["close"] < p["low"] * 0.9999)).sum())
    has_prev = panel["prev_row_close"].notna()
    continues = (panel["prevclose"] / panel["prev_row_close"] - 1).abs() < 1e-4
    out["prevclose_continues_previous_close"] = float(continues[has_prev].mean())
    share = (~continues[has_prev]).groupby(panel.loc[has_prev, "date"]).mean()
    out["sessions_where_over_20pct_of_prevcloses_jump"] = {str(d.date()): round(float(v), 3) for d, v in share[share > 0.2].items()}
    out["factor_rows"] = int((panel["factor"] != 1.0).sum())
    log_path = out_dir / "corporate_actions_applied.csv"
    if log_path.exists():
        log = pd.read_csv(log_path)
        out["corporate_actions"] = {f"{kind} / {why}": int(n) for (kind, why), n in
                                    log.assign(kind=log["kind"].astype(str).str.split(":").str[0].str.replace(r"^(bonus|split).*", "split or bonus", regex=True))
                                    .groupby(["kind", "why"]).size().items()}
    renames = out_dir / "renames.csv"
    if renames.exists():
        r = pd.read_csv(renames)
        out["renames"] = {"in_file": int(len(r)), "joined": int(r["joined"].sum())}
    return out


def big_moves(panel: pd.DataFrame, threshold: float = 0.25) -> pd.DataFrame:
    """Every row whose adjusted close moved more than `threshold` from the adjusted previous close."""
    prev_adj = panel["prev_row_close"] * panel["adj"] * panel["factor"]  # the previous row's adj is adj x factor
    move = panel["close"] * panel["adj"] / prev_adj - 1
    gap = panel["open"] * panel["adj"] / prev_adj - 1
    rows = panel.assign(move=move, gap=gap)
    return rows[rows["move"].abs() > threshold][["date", "sid", "symbol", "series", "prev_row_close", "open", "close",
                                                  "factor", "move", "gap", "value"]]


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="NSE bhavcopies: build the frozen equity panel, or audit it.")
    parser.add_argument("command", choices=["build", "audit"])
    args = parser.parse_args(argv)
    if args.command == "build":
        print(build())
    else:
        print(json.dumps(audit(load_panel()), indent=1, default=str))


if __name__ == "__main__":
    main()
