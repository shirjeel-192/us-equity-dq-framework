# US Equity Data-Quality Framework

Reference implementation of the monthly validation protocol described in the Data Quality Specialist job posting. Built end-to-end in a couple of days by someone (me) who does not have prior equity domain experience — the point being that the shape of the work is systems + discipline, and the equity gotchas layer on top.

**What it does:** ingests two "monthly" snapshots of a US equity universe from public sources, builds a point-in-time entity mapping across market IDs, runs a full-coverage validation protocol, and emits a PASS / PASS_WITH_WARNINGS / FAIL verdict with a findings report a stranger can pick up.

**What runs in production if you hire me:** exactly this pattern, wired to your actual monthly vendor files. The demo swaps public sources (SEC EDGAR, OpenFIGI, Yahoo Finance) for what would be the real vendor feed on your side.

---

## Quick start

```bash
pip install -r requirements.txt
python src/run.py
```

Everything runs offline after the initial API pulls. Fresh DuckDB file every run, so re-runs are deterministic.

Outputs:
- `reports/findings-<snap>.md` — human-readable summary
- `reports/findings-<snap>.json` — machine-readable full anomaly log
- `sheets/*.csv` — one per Google Sheet tab

---

## Data sources (why these three)

| Source | What it gives us | Why it's here |
|--------|------------------|---------------|
| **SEC EDGAR** `company_tickers.json` | CIK ↔ current ticker ↔ registered name | The regulator's own record of who's public. Canonical primary key. |
| **OpenFIGI** `v3/mapping` | ticker → composite FIGI + share class FIGI + security type | Bloomberg's own open ID service. Free, no key required for the demo. |
| **Yahoo Finance** (via yfinance) | historical prices, splits, dividends | Free daily bars + corporate actions. Enough to demonstrate value drift + split reconciliation logic. |

In production these would be replaced by your paid vendor feed (LSEG, S&P, Bloomberg terminal, etc.) but the framework contract stays the same: rows come in with CIK, ticker, FIGI, name, and measures, and rows go out through the same validation graph.

---

## What the framework guarantees

Every row that gets a PASS verdict has cleared all nine of these checks against 100% of the data, not a sample:

| # | Check | Severity | What it catches |
|---|-------|----------|------------------|
| A | Coverage drop on well-covered CIKs | FAIL | The "silent dropout" case from the JD. Company had ≥N observations in prior snapshot, disappeared or went thin this month. |
| B | New additions | INFO | IPOs, new listings, re-listings. Never FAILs — surfaced so a human can confirm expected. |
| C | Delistings | WARN | CIK present prior, absent now. Cross-checked against SEC delisting notices. |
| D | Ticker change | WARN | Same CIK, ticker moved (e.g., FB → META class historical case). |
| E | Share-class remap | WARN | Composite FIGI stable but share_class FIGI moved. Vendor's silent remap of a share class. |
| F | ID mapping break | FAIL | CIK had a composite_figi, this snapshot dropped it. Chase the vendor. |
| G | Value drift | WARN | Price move > 30% between snapshots with no recorded split. Investigate. |
| H | Split unreconciled | FAIL | Split was recorded but observed price move doesn't match the reported ratio ± 5%. |
| I | FIGI collision | FAIL | Two different CIKs pointing at the same composite_figi in the same snapshot. Bad mapping. |

Every anomaly row carries: CIK, ticker, company name, both snapshot values, and a plain-English `evidence` string an operator can paste into a bug tracker.

---

## Verdict logic

Configured in `src/config.py::Tolerances`. Change one number, whole framework respects it.

- **FAIL** if any of:
  - coverage drop > 0.5%
  - silent-dropout share > 2% of well-covered CIKs from prior snapshot
  - any `id_mapping_break` rows
  - any `figi_collision` rows
  - any `split_unreconciled` rows

- **PASS_WITH_WARNINGS** if any of:
  - delisting / ticker_change / share_class_remap / value_drift rows > 0

- **PASS** otherwise.

Every rule change goes through the same tolerances object — no scattered magic numbers.

---

## Entity mapping — point-in-time

`entity_mapping` is built by walking snapshots in chronological order and emitting one row per (CIK, distinct combination of ticker/FIGI/name). Each row has `valid_from` and `valid_to`. Query at any date `d` and get the correct identifier by:

```sql
SELECT * FROM entity_mapping
WHERE cik = 320193
  AND valid_from <= DATE '2026-05-01'
  AND (valid_to IS NULL OR valid_to > DATE '2026-05-01');
```

This is the survivorship-bias-free / no-silent-revision property the JD asks for. Historical corrections do not overwrite prior windows — they close them and open new ones.

---

## Directory layout

```
us-equity-dq/
├── README.md                    (this)
├── requirements.txt
├── src/
│   ├── config.py                Tolerances + data-source config (single source of truth)
│   ├── ingest.py                SEC + OpenFIGI + Yahoo pulls
│   ├── entity_mapping.py        Point-in-time mapping builder
│   ├── validate.py              The 9 checks + verdict
│   ├── report.py                Markdown + JSON + CSV emitters
│   └── run.py                   End-to-end demo entrypoint
├── data/dq.duckdb               (generated) - the SQL playground
├── reports/                     (generated)
└── sheets/                      (generated) - one CSV per Google Sheet tab
```

---

## Honesty section (what I would not claim to know yet)

I have zero prior US equity domain experience in production. The design decisions above are informed by:
- ID-reconciliation patterns from a payroll migration at Tajir (1000+ employees across 6 monthly files, name drift, dedup edge cases)
- Multi-source data ingestion at RevdUp (HubSpot, Salesforce, Stripe, Gong, Fathom, Five9, Vapi → canonical Postgres)
- Live audit-log + tolerance-gated production systems (Margin Maximizer bidder for four ad-tech tenants, `check_bid_down_safety.py` gate)

What I would specifically learn in the first month:
- Corporate action edge cases: spin-off cost basis, share class renames that look like ticker changes, delisting behavior variance across NYSE / Nasdaq / OTC
- Vendor-specific quirks in the ID mapping data (LSEG PermID, Bloomberg BBGID vs FIGI, S&P PayPortal, etc.)
- Point-in-time gotchas that only surface when comparing against equity returns (as-of-date joins, right-censoring, delisting bias in return calculations)

This repo is the shape of the discipline. The equity layer would sit on top of it.

---

## What would change moving to production

- **Ingestion.** Replace SEC EDGAR + OpenFIGI + Yahoo with your monthly vendor drop (parquet/CSV, whatever format).
- **Snapshot cadence.** Two snapshot dates get replaced by month-end anchor logic (last business day per month, holiday-adjusted).
- **Universe.** From 100 demo CIKs → your ~3,600 companies. Framework contract does not change.
- **Tolerances.** Values in `config.py` get set against your historical baseline, not the demo defaults.
- **Corporate action ground truth.** Layer in a corporate-action feed (SEC Form 8-K, exchange notices) rather than inferring from price gaps alone.
- **Storage.** DuckDB is fine for demo scale. At 7M-row scale you probably want Postgres or a warehouse, with DuckDB kept as a query layer.
