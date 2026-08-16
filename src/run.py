"""
End-to-end demo run.

  1. Ingest two monthly snapshots (2026-07-31 and 2026-08-15).
  2. Build the point-in-time entity mapping across both.
  3. Run the validation protocol.
  4. Emit findings markdown/JSON and the Google Sheet CSVs.

Everything lives in a single DuckDB file so a stranger can open it later
and re-run any SQL cited in the report.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import duckdb

from config import DATA
from ingest import build_snapshot
from entity_mapping import build_entity_mapping
from validate import run_validation
from report import emit


REPO_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = REPO_ROOT / "data" / "dq.duckdb"
REPORTS = REPO_ROOT / "reports"
SHEETS = REPO_ROOT / "sheets"


def main() -> None:
    DB_PATH.parent.mkdir(exist_ok=True, parents=True)
    if DB_PATH.exists():
        DB_PATH.unlink()   # fresh run every time — reproducible

    conn = duckdb.connect(str(DB_PATH))

    # Two snapshots spanning 6 months so real corporate actions (splits,
    # ticker changes, delistings) surface naturally in the demo. Production
    # runs would compare two consecutive month-ends.
    snap_a_date = date(2026, 2, 15)
    snap_b_date = date(2026, 8, 15)

    build_snapshot(conn, snap_a_date, DATA.universe_size)
    build_snapshot(conn, snap_b_date, DATA.universe_size)

    build_entity_mapping(
        conn,
        snapshot_dates_by_tag={
            snap_a_date.strftime("%Y%m"): snap_a_date.isoformat(),
            snap_b_date.strftime("%Y%m"): snap_b_date.isoformat(),
        },
    )

    result = run_validation(conn, snap_a_date.strftime("%Y%m"), snap_b_date.strftime("%Y%m"))

    emit(conn, result, REPORTS, SHEETS)

    conn.close()

    print()
    print("=" * 60)
    print(f"VERDICT: {result.verdict}")
    print(f"Coverage: {result.coverage_a} → {result.coverage_b} "
          f"({result.coverage_drop_pct:+.2f}%)")
    print(f"Anomalies: {sum(result.anomaly_counts.values())} total")
    for cat, n in sorted(result.anomaly_counts.items()):
        if n > 0:
            print(f"  · {cat}: {n}")
    print("=" * 60)


if __name__ == "__main__":
    main()
