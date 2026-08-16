"""
Ingest US equity data from three public sources and land it in DuckDB.

1. SEC EDGAR   → CIK ↔ ticker ↔ company_name  (canonical company universe)
2. OpenFIGI    → ticker → composite_figi + share_class_figi
3. Yahoo       → historical prices + splits + dividends

The three feeds get cross-joined into a per-snapshot entity table with
point-in-time validity. Every field carries its source so a later dispute
about "which vendor said what on this date" resolves in one query.

Rate limits respected:
  - SEC: 10 req/sec cap, we do 1 req total (company_tickers.json is a bulk file)
  - OpenFIGI: 25 mappings per request, 25 req/min (batched below cap)
  - Yahoo: yfinance handles its own throttling
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta

import duckdb
import httpx
import yfinance as yf

from config import DATA


SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
OPENFIGI_URL = "https://api.openfigi.com/v3/mapping"


@dataclass
class Company:
    cik: int
    ticker: str
    name: str


# ------------------------------------------------------------------
# SEC EDGAR — canonical company universe
# ------------------------------------------------------------------

def fetch_sec_universe(limit: int) -> list[Company]:
    """
    company_tickers.json is a single file listing every reporting entity's
    CIK, primary ticker, and title, ordered roughly by prominence (largest
    market caps first). We take the first `limit` for the demo.
    """
    headers = {"User-Agent": DATA.sec_user_agent}
    r = httpx.get(SEC_TICKERS_URL, headers=headers, timeout=30)
    r.raise_for_status()
    data = r.json()  # {"0": {"cik_str": ..., "ticker": ..., "title": ...}, ...}

    out: list[Company] = []
    seen_tickers: set[str] = set()
    for _, row in data.items():
        t = row["ticker"].upper().strip()
        if t in seen_tickers:
            continue
        seen_tickers.add(t)
        out.append(Company(cik=int(row["cik_str"]), ticker=t, name=row["title"]))
        if len(out) >= limit:
            break
    return out


# ------------------------------------------------------------------
# OpenFIGI — ticker → FIGI mapping
# ------------------------------------------------------------------

def fetch_figi_mapping(companies: list[Company]) -> dict[str, dict]:
    """
    Returns {ticker: {"composite_figi": str, "share_class_figi": str,
                       "security_type": str, "name": str}}.

    OpenFIGI is authoritative for Bloomberg IDs and is FREE. Not every US
    ticker resolves — thinly-traded or dual-listed names sometimes come back
    empty. Those get None values and are flagged as ID-mapping breaks
    downstream by the validator.
    """
    out: dict[str, dict] = {}
    batch_size = DATA.openfigi_batch_size

    for i in range(0, len(companies), batch_size):
        batch = companies[i : i + batch_size]
        body = [
            {"idType": "TICKER", "idValue": c.ticker, "exchCode": "US"}
            for c in batch
        ]
        r = httpx.post(
            OPENFIGI_URL,
            json=body,
            headers={"Content-Type": "application/json"},
            timeout=30,
        )
        r.raise_for_status()
        results = r.json()  # list aligned with `body`

        for c, res in zip(batch, results):
            if "data" not in res or not res["data"]:
                out[c.ticker] = {
                    "composite_figi": None,
                    "share_class_figi": None,
                    "security_type": None,
                    "figi_name": None,
                }
                continue
            hit = res["data"][0]  # primary match
            out[c.ticker] = {
                "composite_figi": hit.get("compositeFIGI"),
                "share_class_figi": hit.get("shareClassFIGI"),
                "security_type": hit.get("securityType"),
                "figi_name": hit.get("name"),
            }
        # Stay under OpenFIGI's 5-req/min free-tier cap.
        time.sleep(DATA.openfigi_sleep_seconds)
    return out


# ------------------------------------------------------------------
# Yahoo Finance — price + corporate actions at a specific snapshot date
# ------------------------------------------------------------------

def fetch_month_end_measures(
    companies: list[Company], snapshot_date: date
) -> dict[str, dict]:
    """
    For a given snapshot cutoff (typically month-end), return a per-ticker
    dict of last observed measures and any corporate actions that fell in
    the trailing 30-day window ending on the snapshot date.

    We fetch a 40-day window rather than exactly 30, so a Friday-Monday
    weekend on the boundary doesn't leave us empty-handed.
    """
    end = datetime.combine(snapshot_date, datetime.min.time()) + timedelta(days=1)
    start = end - timedelta(days=40)

    out: dict[str, dict] = {}
    for c in companies:
        row: dict = {
            "last_close": None,
            "last_volume": None,
            "trading_days_in_window": 0,
            "split_ratio_in_window": None,
            "split_date": None,
            "dividend_in_window": None,
            "dividend_date": None,
        }
        try:
            hist = yf.download(
                c.ticker,
                start=start.strftime("%Y-%m-%d"),
                end=end.strftime("%Y-%m-%d"),
                progress=False,
                auto_adjust=False,
                actions=True,
                threads=False,
            )
        except Exception as e:
            row["fetch_error"] = str(e)
            out[c.ticker] = row
            continue

        if hist is None or len(hist) == 0:
            row["fetch_error"] = "no data returned"
            out[c.ticker] = row
            continue

        # yfinance sometimes returns a MultiIndex column even for a single ticker
        if hasattr(hist.columns, "get_level_values"):
            try:
                hist.columns = hist.columns.get_level_values(0)
            except Exception:
                pass

        row["trading_days_in_window"] = len(hist)
        if "Close" in hist.columns:
            close_series = hist["Close"].dropna()
            if len(close_series) > 0:
                row["last_close"] = float(close_series.iloc[-1])
        if "Volume" in hist.columns:
            vol_series = hist["Volume"].dropna()
            if len(vol_series) > 0:
                row["last_volume"] = int(vol_series.iloc[-1])

        # Split events — yfinance returns 0.0 for non-split days
        if "Stock Splits" in hist.columns:
            splits = hist[hist["Stock Splits"] > 0]["Stock Splits"]
            if len(splits) > 0:
                row["split_ratio_in_window"] = float(splits.iloc[-1])
                row["split_date"] = splits.index[-1].date().isoformat()

        # Dividend events
        if "Dividends" in hist.columns:
            divs = hist[hist["Dividends"] > 0]["Dividends"]
            if len(divs) > 0:
                row["dividend_in_window"] = float(divs.iloc[-1])
                row["dividend_date"] = divs.index[-1].date().isoformat()

        out[c.ticker] = row

    return out


# ------------------------------------------------------------------
# Snapshot builder
# ------------------------------------------------------------------

def build_snapshot(
    conn: duckdb.DuckDBPyConnection,
    snapshot_date: date,
    limit: int,
) -> None:
    """
    Materialise a full monthly snapshot table into DuckDB:
      snapshot_<yyyymm>(cik, ticker, name, composite_figi, share_class_figi,
                        security_type, last_close, last_volume,
                        trading_days_in_window, split_ratio_in_window,
                        split_date, dividend_in_window, dividend_date,
                        snapshot_date)

    Rebuilt (DROP + CREATE) every call so a re-run always reflects the
    current source-of-truth state, not stale data.
    """
    print(f"[ingest] snapshot={snapshot_date.isoformat()} universe_size={limit}")
    companies = fetch_sec_universe(limit)
    print(f"[ingest]   SEC universe: {len(companies)} companies")

    figi_map = fetch_figi_mapping(companies)
    figi_hit = sum(1 for v in figi_map.values() if v["composite_figi"])
    print(f"[ingest]   OpenFIGI: {figi_hit}/{len(companies)} resolved")

    measures = fetch_month_end_measures(companies, snapshot_date)
    with_close = sum(1 for v in measures.values() if v["last_close"] is not None)
    print(f"[ingest]   Yahoo: {with_close}/{len(companies)} have last_close")

    rows = []
    for c in companies:
        fig = figi_map.get(c.ticker, {})
        m = measures.get(c.ticker, {})
        rows.append(
            {
                "cik": c.cik,
                "ticker": c.ticker,
                "name": c.name,
                "composite_figi": fig.get("composite_figi"),
                "share_class_figi": fig.get("share_class_figi"),
                "security_type": fig.get("security_type"),
                "last_close": m.get("last_close"),
                "last_volume": m.get("last_volume"),
                "trading_days_in_window": m.get("trading_days_in_window", 0),
                "split_ratio_in_window": m.get("split_ratio_in_window"),
                "split_date": m.get("split_date"),
                "dividend_in_window": m.get("dividend_in_window"),
                "dividend_date": m.get("dividend_date"),
                "fetch_error": m.get("fetch_error"),
                "snapshot_date": snapshot_date.isoformat(),
            }
        )

    tag = snapshot_date.strftime("%Y%m")
    table = f"snapshot_{tag}"
    conn.execute(f"DROP TABLE IF EXISTS {table}")
    conn.execute(
        f"""
        CREATE TABLE {table} (
            cik BIGINT,
            ticker VARCHAR,
            name VARCHAR,
            composite_figi VARCHAR,
            share_class_figi VARCHAR,
            security_type VARCHAR,
            last_close DOUBLE,
            last_volume BIGINT,
            trading_days_in_window INTEGER,
            split_ratio_in_window DOUBLE,
            split_date VARCHAR,
            dividend_in_window DOUBLE,
            dividend_date VARCHAR,
            fetch_error VARCHAR,
            snapshot_date VARCHAR
        )
        """
    )
    conn.executemany(
        f"""
        INSERT INTO {table} VALUES (
            $cik, $ticker, $name, $composite_figi, $share_class_figi,
            $security_type, $last_close, $last_volume, $trading_days_in_window,
            $split_ratio_in_window, $split_date, $dividend_in_window,
            $dividend_date, $fetch_error, $snapshot_date
        )
        """,
        rows,
    )
    print(f"[ingest]   wrote {table} ({len(rows)} rows)")
