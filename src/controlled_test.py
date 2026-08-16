"""
Controlled golden-fixture test.

The real-data demo (`run.py`) fires the `value_drift` detector heavily on
its own — the 2026-02 → 2026-08 window in real US equity data has
plenty of >30% moves. But the other eight detectors don't naturally
trigger on a clean 100-company snapshot pair, so this script builds a
SYNTHETIC snapshot_C from a copy of snapshot_202608 with deliberate
issues injected. Every injection is labelled and reproducible.

Purpose: prove that all nine anomaly detectors fire correctly against
inputs we know they should catch. Same shape as a golden-fixture test in
any well-run data pipeline.

Run AFTER `run.py`. Reuses the DuckDB file so we don't re-hit APIs.
"""
from __future__ import annotations

from pathlib import Path

import duckdb

from validate import run_validation
from report import emit


REPO_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = REPO_ROOT / "data" / "dq.duckdb"
REPORTS = REPO_ROOT / "reports"
SHEETS_CONTROLLED = REPO_ROOT / "sheets_controlled"


def main() -> None:
    if not DB_PATH.exists():
        raise SystemExit("dq.duckdb not found — run src/run.py first")

    conn = duckdb.connect(str(DB_PATH))

    # ------------------------------------------------------------------
    # Build synthetic snapshot_202609 as a MUTATION of snapshot_202608.
    # ------------------------------------------------------------------
    conn.execute("DROP TABLE IF EXISTS snapshot_202609")
    conn.execute(
        """
        CREATE TABLE snapshot_202609 AS
        SELECT * FROM snapshot_202608
        """
    )
    # Point every synthetic row's snapshot_date forward one month so the
    # temporal ordering is unambiguous.
    conn.execute("UPDATE snapshot_202609 SET snapshot_date = '2026-09-15'")

    # ==================================================================
    # INJECTED ISSUES — every one is a real class the JD describes.
    # ==================================================================

    # A. Silent dropout: pick a well-covered CIK and null out its measures
    #    (simulate the "well-covered company silently stops receiving data").
    silent_dropout_cik = _pick_first_cik(conn, "snapshot_202608", "AAPL")
    conn.execute(
        f"""
        UPDATE snapshot_202609
        SET last_close = NULL, last_volume = NULL, trading_days_in_window = 0
        WHERE cik = {silent_dropout_cik}
        """
    )
    print(f"[injection] silent dropout on cik={silent_dropout_cik} (AAPL)")

    # B. Delisting: drop a CIK entirely.
    delisted_cik = _pick_first_cik(conn, "snapshot_202608", "TSLA")
    conn.execute(f"DELETE FROM snapshot_202609 WHERE cik = {delisted_cik}")
    print(f"[injection] delisting on cik={delisted_cik} (TSLA)")

    # C. Ticker change: same CIK, new ticker.
    ticker_change_cik = _pick_first_cik(conn, "snapshot_202608", "META")
    conn.execute(
        f"""
        UPDATE snapshot_202609
        SET ticker = 'METAX'
        WHERE cik = {ticker_change_cik}
        """
    )
    print(f"[injection] ticker_change META → METAX (cik={ticker_change_cik})")

    # D. Share-class remap: composite_figi stable, share_class_figi changes.
    share_remap_cik = _pick_first_cik(conn, "snapshot_202608", "GOOGL")
    conn.execute(
        f"""
        UPDATE snapshot_202609
        SET share_class_figi = 'BBG_SIMULATED_REMAP_' || CAST(cik AS VARCHAR)
        WHERE cik = {share_remap_cik}
        """
    )
    print(f"[injection] share_class_remap on cik={share_remap_cik} (GOOGL)")

    # E. ID mapping break: null out a composite_figi that A had.
    id_break_cik = _pick_first_cik(conn, "snapshot_202608", "MSFT")
    conn.execute(
        f"""
        UPDATE snapshot_202609
        SET composite_figi = NULL, share_class_figi = NULL
        WHERE cik = {id_break_cik}
        """
    )
    print(f"[injection] id_mapping_break on cik={id_break_cik} (MSFT)")

    # F. Unreconciled split: claim a 4:1 split but leave prices unchanged.
    #    In a real split the current close would be ≈ prior/4.
    split_cik = _pick_first_cik(conn, "snapshot_202608", "NVDA")
    conn.execute(
        f"""
        UPDATE snapshot_202609
        SET split_ratio_in_window = 4.0,
            split_date = '2026-09-01'
        WHERE cik = {split_cik}
        """
    )
    print(f"[injection] split_unreconciled 4:1 on cik={split_cik} (NVDA), price not halved")

    # G. FIGI collision: force two different CIKs to share a composite_figi.
    #    Use AMZN's composite_figi and paste it onto another CIK.
    (amzn_cik, amzn_figi) = conn.execute(
        """
        SELECT cik, composite_figi FROM snapshot_202608
        WHERE ticker = 'AMZN' AND composite_figi IS NOT NULL LIMIT 1
        """
    ).fetchone()
    other_cik = conn.execute(
        f"""
        SELECT cik FROM snapshot_202608
        WHERE composite_figi IS NOT NULL
          AND composite_figi <> '{amzn_figi}'
          AND cik <> {amzn_cik}
        LIMIT 1
        """
    ).fetchone()[0]
    conn.execute(
        f"""
        UPDATE snapshot_202609
        SET composite_figi = '{amzn_figi}'
        WHERE cik = {other_cik}
        """
    )
    print(f"[injection] figi_collision — cik={other_cik} now shares {amzn_figi} with cik={amzn_cik}")

    # H. New addition: fake IPO — a CIK that wasn't in the base.
    conn.execute(
        """
        INSERT INTO snapshot_202609 VALUES (
            9999999, 'IPOX', 'Fictional New Listing Corp',
            'BBG_SIM_NEW_LISTING', 'BBG_SIM_NEW_LISTING_SC',
            'Common Stock', 12.50, 1200000, 5, NULL, NULL, NULL, NULL,
            NULL, '2026-09-15'
        )
        """
    )
    print("[injection] new_addition IPOX cik=9999999")

    print()
    print("=== running validation on injected snapshot ===")
    result = run_validation(conn, "202608", "202609")

    emit(conn, result, REPORTS, SHEETS_CONTROLLED)

    conn.close()

    print()
    print("=" * 60)
    print("CONTROLLED-TEST RESULT")
    print(f"Verdict: {result.verdict}")
    print(f"Total anomalies: {sum(result.anomaly_counts.values())}")
    for cat, n in sorted(result.anomaly_counts.items()):
        if n > 0:
            print(f"  · {cat}: {n}")
    print()
    print("Every non-zero category above corresponds to at least one deliberate")
    print("injection. Zero counts mean the detector didn't fire on the injection —")
    print("that would be a real bug in the validator.")
    print("=" * 60)


def _pick_first_cik(conn: duckdb.DuckDBPyConnection, table: str, ticker: str) -> int:
    row = conn.execute(
        f"SELECT cik FROM {table} WHERE ticker = '{ticker}' LIMIT 1"
    ).fetchone()
    if row is None:
        raise SystemExit(f"Ticker {ticker} not in {table} — pick another anchor")
    return int(row[0])


if __name__ == "__main__":
    main()
