# Assumptions

Every judgment call I made and why. All of these are places where a domain expert (which I'm not yet) could reasonably override me. Flagged so a reviewer can decide before we book a call.

## Data sources

### 1. SEC EDGAR is authoritative for CIK ↔ current-ticker
`company_tickers.json` reflects the primary ticker for the most-recent quarterly filing. If a ticker changed intra-month, EDGAR might not reflect it yet. Production would layer in the exchange listing feeds (NYSE + Nasdaq daily change files) for tighter recency.

### 2. OpenFIGI's `compositeFIGI` is the identity key, not `figi`
FIGI (the specific instrument) can change across venues for the same security. `compositeFIGI` is the security-level identifier that stays stable across venues. If you use `figi` as the join key, you'll get spurious "share_class_remap" alerts every time a dual-listed name gets traded on a different venue.

### 3. Yahoo Finance splits/dividends are lagged and occasionally wrong
Yahoo backfills corporate actions on a delay and sometimes revises the ratio. Production would use SEC 8-K filings or an exchange corporate-action feed as ground truth. Yahoo is fine for the demo because I only need to prove the reconciliation math, not the source.

### 4. The 100-company demo universe is the SEC EDGAR list order
That's roughly-by-prominence but not exactly market-cap-ranked. Production would sort by shares × price or use a fixed universe (S&P 500 constituents, Russell 3000, whatever your dataset defines).

## Tolerances

### 5. Coverage-drop threshold is 0.5%
On a 3,600-CIK universe, 0.5% = 18 CIKs. That's the level where a coordinated data-quality issue starts to matter and individual delistings still pass. For your specific dataset this number should be calibrated against 12+ months of historical monthly coverage variance.

### 6. Silent-dropout threshold is 2% of well-covered CIKs
"Well-covered" here means ≥3 trading days of data in the prior snapshot. Two things this catches: vendor coverage genuinely dropped, or the well-covered baseline itself is drifting.

### 7. Value-drift threshold is 30% between snapshots
Chosen for the demo's 6-month window. For actual month-over-month snapshots I'd expect this to drop to ~15% with a matching increase in the required σ multiple (real σ-based drift not just absolute pct move).

### 8. Split reconciliation tolerance is ±5%
A 2:1 split should drop price by exactly 50%, but the real observed move is confounded by 30 days of trading either side of the ex-date. 5% is loose enough to accept genuine splits and tight enough to flag a mis-recorded ratio.

## Framework design

### 9. Snapshot tables are DROP + CREATE, not INSERT
Every run produces a fresh snapshot table. Advantages: full reproducibility, no accidental cross-run contamination. Downside: no history within the DuckDB file. Historical snapshots would be persisted to parquet or Postgres in production.

### 10. `entity_mapping` uses valid_to = NULL for "still current"
Common pattern. An alternative is `valid_to = 9999-12-31`. NULL is more explicit about "no known end" versus "far-future placeholder we forgot to update." Every downstream query has to remember the NULL check.

### 11. Composite FIGI is the identity for FIGI collision checks
A collision (2 CIKs → same composite_figi) is always a data-integrity issue in the vendor's output. Distinct securities never legitimately share a compositeFIGI. If your dataset has known exceptions (say, ADR + underlying), the exception list would move into `config.py`.

### 12. Point-in-time as-of queries use `valid_from <= d AND (valid_to IS NULL OR valid_to > d)`
Half-open intervals. `valid_to` is exclusive: the row is valid up to but NOT including `valid_to`. If your convention is closed intervals (`valid_to` inclusive), one line in `entity_mapping.py` changes.

## What I'd learn in month 1 (honest gaps)

### 13. Spin-off cost basis handling
When a company spins off a subsidiary, the parent's historical price adjusts for the value of the distributed shares. Vendor treatments vary. I don't yet know your dataset's convention.

### 14. Share-class renames that look like ticker changes
When a company reclassifies its share structure (Google Class A/B/C history), the ticker looks like it changed but the underlying entity is the same. My current detector flags these as `ticker_change` — a domain-experienced eye would want a separate category.

### 15. Delisting behaviour varies by exchange
NYSE, Nasdaq, and OTC all have different delisting notification patterns. Some post ahead, some post the day of, some are only discoverable via SEC 8-K. The framework treats "absent from snapshot B" as evidence of delisting; production would cross-check against the actual delisting notice feeds.

### 16. Point-in-time joins in the return-testing pipeline
The dataset is tested against equity returns. Right-censoring and delisting bias in the return calculation are subtle. I would need to see your return calculation code before claiming I could safely modify it.

### 17. Vendor-specific ID quirks
LSEG PermID, S&P PayPortal ID, Bloomberg BBGID (not the same as FIGI), CRSP PERMNO. Each has its own gotchas. My framework's approach is CIK-anchored with FIGI as the vendor-agnostic secondary key — but this is a choice, not the only right answer.

## What would change in production

- `Ingest` module gets 4 more source adapters (your vendor + backup vendor + SEC 8-K corporate actions + exchange delisting feeds).
- `Tolerances` gets re-calibrated against 12+ months of historical monthly variance.
- `Verdict` logic gets an escalation gate (FAIL → Slack + PagerDuty).
- `Entity_mapping` moves from DuckDB → Postgres for durability.
- Snapshot tables get partitioned by month and pushed to parquet.
- The controlled test grows to cover every anomaly class my dataset has ever produced (regression suite).
