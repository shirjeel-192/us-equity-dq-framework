# Architecture

## One-diagram summary

```
             ┌───────────────┐   ┌───────────────┐   ┌────────────────┐
             │  SEC EDGAR    │   │   OpenFIGI    │   │ Yahoo Finance  │
             │  company_     │   │   v3/mapping  │   │  (yfinance)    │
             │  tickers.json │   │               │   │                │
             └──────┬────────┘   └───────┬───────┘   └───────┬────────┘
                    │                    │                   │
                    └────────────────────┴───────────────────┘
                                         │
                             ┌───────────▼─────────────┐
                             │      ingest.py          │
                             │  build_snapshot(date)   │
                             └───────────┬─────────────┘
                                         │
                                         ▼
                        ┌──────────────────────────────┐
                        │   snapshot_<YYYYMM>          │  ← one per delivery
                        │   (raw entities + measures)  │
                        └──────────────┬───────────────┘
                                       │
                                       ▼
                        ┌──────────────────────────────┐
                        │    entity_mapping.py         │
                        │  build across snapshots →    │
                        │  point-in-time table w/      │
                        │  valid_from / valid_to       │
                        └──────────────┬───────────────┘
                                       │
                                       ▼
                        ┌──────────────────────────────┐
                        │       validate.py            │
                        │  9 checks × 100% of rows,    │
                        │  materialised into           │
                        │  `anomalies` table           │
                        └──────────────┬───────────────┘
                                       │
                                       ▼
                        ┌──────────────────────────────┐
                        │        report.py             │
                        │  emits:                      │
                        │   - findings.md              │
                        │   - findings.json            │
                        │   - sheets/*.csv (one per    │
                        │     Google Sheet tab)        │
                        └──────────────────────────────┘
```

## Why DuckDB

The whole thing runs in a single DuckDB file. Reasons:

- **SQL for the validation logic.** Every check is a SQL insert into the `anomalies` table. That means: the check IS the audit — an operator can paste the exact query into DuckDB and reproduce the anomaly count in one command.
- **Fast enough at scale.** DuckDB scans 7M rows in a couple seconds locally. For the demo's 100 CIKs it's overkill, but the same code path handles the client's real volume without changes.
- **No infra.** No Postgres to spin up, no schema migrations to manage during the assessment. `pip install duckdb` is the deployment story.

At production scale you'd probably move the persistent tables to Postgres or a warehouse and keep DuckDB as the query engine over parquet extracts. Same SQL, different physical layer.

## Why materialise anomalies into a table

You could compute anomaly counts in memory. The framework materialises them into a `anomalies` table because:

1. **Every downstream artefact reads from the same source.** The markdown report, the JSON log, and the Google Sheet CSVs all read from the same table. No risk of one saying "22 anomalies" and another saying "23."
2. **A stranger can query it.** Six months from now when someone asks "why did that value_drift fire?", they open the DuckDB file and `SELECT * FROM anomalies WHERE ticker = 'AMD'`.
3. **The verdict logic reads it.** Verdict is a straightforward SELECT with a WHERE. Changing the verdict rule doesn't require re-running the detectors — just re-reading their output.

## Idempotency

- Every run starts by **deleting** `data/dq.duckdb`. No cross-run state contamination.
- Every `snapshot_<yyyymm>` table is **DROP + CREATE**. Same input, same output.
- Every `anomalies` insert is a full replace. No partial rows leaking through.
- API pulls are deterministic per date (SEC EDGAR is a static file; OpenFIGI is idempotent; Yahoo is date-anchored).

Two runs with the same date bounds produce byte-identical outputs (allowing for Yahoo occasionally revising a stale price bar).

## What's split into modules and why

| Module | Owns | Talks to |
|--------|------|----------|
| `config.py` | Every tolerance, threshold, and data-source constant | Nothing — read-only imports |
| `ingest.py` | API fetches, raw snapshot table writes | External HTTP + DuckDB |
| `entity_mapping.py` | Point-in-time mapping build | DuckDB only |
| `validate.py` | The 9 checks + verdict struct | DuckDB only |
| `report.py` | Markdown / JSON / CSV emission | DuckDB + filesystem |
| `run.py` | End-to-end demo entrypoint | All of the above |
| `controlled_test.py` | Golden-fixture injection test | `validate.py` + `report.py` |

If a business rule changes (say, coverage tolerance moves from 0.5% to 0.25%), one edit in `config.py` and every downstream consumer respects it. If a new check gets added, it's a single INSERT INTO anomalies + a single line in the severity map in `report.py`.

## Error handling philosophy

**Loud on real errors, quiet on expected drift.**

- Yahoo failing on a single ticker → captured as `fetch_error` on that row, run continues.
- OpenFIGI 413 → framework fails loud (rate limit mismatch means the config is wrong, not the run).
- DuckDB constraint violation → framework fails loud (schema drift is the operator's problem).
- Anomalies discovered → NOT an error, they're the output.

The distinction matters: an anomaly in the data does not mean the framework failed. It means the framework succeeded in finding something worth investigating.

## What I would add on day 30

- **Real corporate action feed** (SEC Form 8-K, exchange notices) for ground-truth split reconciliation. Right now the framework infers splits from Yahoo, which lags reality by a day or two.
- **Historical ratio tolerances** (tolerances change month-to-month based on rolling stddev per security, not fixed thresholds).
- **Diff-style change reports** so operators see "what's new since last run" without scanning the full findings.
- **Postgres materialisation** of the persistent tables (snapshots, entity_mapping), keeping DuckDB as the query engine.
- **Slack/PagerDuty routing** for FAIL verdicts so no delivery gets promoted silently.
