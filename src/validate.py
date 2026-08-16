"""
Validation protocol: compare snapshot B (current delivery) against
snapshot A (prior accepted baseline). Every check runs against 100% of
rows in DuckDB SQL, then anomalies get materialised into a single
long-format `anomalies` table so downstream reports/sheets have one
source of truth.

Anomaly categories in this framework:
  A. coverage_drop        — well-covered CIK in A missing/thin in B
  B. new_addition         — CIK in B not in A (IPO, new listing, re-listing)
  C. delisting            — CIK in A not in B (delisted, acquired, merged)
  D. ticker_change        — same CIK in both, different ticker
  E. share_class_remap    — same CIK+composite_figi, share_class_figi changed
  F. id_mapping_break     — CIK missing composite_figi in B (had it in A)
  G. value_drift          — price move > threshold σ without matching split
  H. split_unreconciled   — split observed but price move doesn't match ratio
  I. figi_collision       — two different CIKs sharing a composite_figi

Every anomaly row carries reproducible evidence: exact CIK, ticker, both
snapshot values, and a brief `evidence` string an operator can paste into
a bug tracker.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import duckdb

from config import TOLERANCES


@dataclass
class ValidationResult:
    snap_a: str  # "202607"
    snap_b: str  # "202608"
    coverage_a: int
    coverage_b: int
    coverage_drop_pct: float
    anomaly_counts: dict[str, int]
    verdict: str  # "PASS" | "PASS_WITH_WARNINGS" | "FAIL"
    verdict_reasons: list[str]


ANOMALY_SCHEMA = """
    CREATE TABLE anomalies (
        category VARCHAR,        -- one of the letters above
        severity VARCHAR,        -- INFO / WARN / FAIL
        cik BIGINT,
        ticker VARCHAR,
        name VARCHAR,
        snap_a_value VARCHAR,
        snap_b_value VARCHAR,
        evidence VARCHAR
    )
"""


def run_validation(
    conn: duckdb.DuckDBPyConnection,
    snap_a: str,
    snap_b: str,
) -> ValidationResult:
    print(f"[validate] snapshot_{snap_a} → snapshot_{snap_b}")

    conn.execute("DROP TABLE IF EXISTS anomalies")
    conn.execute(ANOMALY_SCHEMA)

    ta = f"snapshot_{snap_a}"
    tb = f"snapshot_{snap_b}"

    coverage_a = conn.execute(f"SELECT COUNT(*) FROM {ta}").fetchone()[0]
    coverage_b = conn.execute(f"SELECT COUNT(*) FROM {tb}").fetchone()[0]
    coverage_drop_pct = (
        (coverage_a - coverage_b) / coverage_a * 100 if coverage_a > 0 else 0.0
    )
    print(f"[validate]   coverage: {coverage_a} → {coverage_b} ({coverage_drop_pct:+.2f}%)")

    # ---- A. Coverage drop on well-covered CIKs -----------------------
    # "Well covered" in A means trading_days_in_window >= min. Then in B
    # the same CIK is either missing OR shows no valid last_close.
    conn.execute(
        f"""
        INSERT INTO anomalies
        SELECT
            'coverage_drop' AS category,
            'FAIL' AS severity,
            a.cik, a.ticker, a.name,
            CAST(a.trading_days_in_window AS VARCHAR) AS snap_a_value,
            CASE WHEN b.cik IS NULL THEN 'ABSENT' ELSE CAST(b.trading_days_in_window AS VARCHAR) END AS snap_b_value,
            'well-covered in A (>=' || CAST({TOLERANCES.well_covered_min_rows} AS VARCHAR)
              || ' rows), silent in B — likely ticker change or vendor drop' AS evidence
        FROM {ta} a
        LEFT JOIN {tb} b USING (cik)
        WHERE a.trading_days_in_window >= {TOLERANCES.well_covered_min_rows}
          AND (b.cik IS NULL OR b.last_close IS NULL)
        """
    )

    # ---- B. New additions in B (IPO / new listing / re-listing) ------
    conn.execute(
        f"""
        INSERT INTO anomalies
        SELECT
            'new_addition', 'INFO',
            b.cik, b.ticker, b.name,
            'ABSENT', CAST(b.trading_days_in_window AS VARCHAR),
            'CIK not in A. Expected on new listings — flag only if unexpected'
        FROM {tb} b
        LEFT JOIN {ta} a USING (cik)
        WHERE a.cik IS NULL
        """
    )

    # ---- C. Delistings (CIK in A not in B) --------------------------
    conn.execute(
        f"""
        INSERT INTO anomalies
        SELECT
            'delisting', 'WARN',
            a.cik, a.ticker, a.name,
            CAST(a.trading_days_in_window AS VARCHAR), 'ABSENT',
            'CIK present in A, absent in B. Verify against SEC delisting notices'
        FROM {ta} a
        LEFT JOIN {tb} b USING (cik)
        WHERE b.cik IS NULL
        """
    )

    # ---- D. Ticker change (same CIK, different ticker) --------------
    conn.execute(
        f"""
        INSERT INTO anomalies
        SELECT
            'ticker_change', 'WARN',
            a.cik, a.ticker || ' → ' || b.ticker, a.name,
            a.ticker, b.ticker,
            'Same CIK, ticker changed. Update entity mapping valid_to/valid_from'
        FROM {ta} a
        JOIN {tb} b USING (cik)
        WHERE a.ticker <> b.ticker
        """
    )

    # ---- E. Share-class remap (composite same, share_class changed) --
    conn.execute(
        f"""
        INSERT INTO anomalies
        SELECT
            'share_class_remap', 'WARN',
            a.cik, a.ticker, a.name,
            a.share_class_figi, b.share_class_figi,
            'CIK+composite_figi same, share_class_figi remapped. Confirm vs vendor notice'
        FROM {ta} a
        JOIN {tb} b USING (cik)
        WHERE a.composite_figi IS NOT NULL
          AND a.composite_figi = b.composite_figi
          AND a.share_class_figi <> b.share_class_figi
        """
    )

    # ---- F. ID mapping break (had composite_figi in A, missing in B) --
    conn.execute(
        f"""
        INSERT INTO anomalies
        SELECT
            'id_mapping_break', 'FAIL',
            a.cik, a.ticker, a.name,
            a.composite_figi, 'NULL',
            'composite_figi disappeared for a known-good CIK. Chase vendor bug'
        FROM {ta} a
        JOIN {tb} b USING (cik)
        WHERE a.composite_figi IS NOT NULL
          AND b.composite_figi IS NULL
        """
    )

    # ---- G. Value drift beyond σ threshold w/o matching split -------
    # We approximate drift as |Δpct| between snap_a.last_close and snap_b.last_close.
    # A split in the between-snapshot window explains a large move.
    conn.execute(
        f"""
        INSERT INTO anomalies
        SELECT
            'value_drift', 'WARN',
            a.cik, a.ticker, a.name,
            CAST(a.last_close AS VARCHAR), CAST(b.last_close AS VARCHAR),
            'price move of ' || CAST(ROUND((b.last_close - a.last_close) / a.last_close * 100, 2) AS VARCHAR)
              || '% between snapshots, no split recorded — investigate'
        FROM {ta} a
        JOIN {tb} b USING (cik)
        WHERE a.last_close IS NOT NULL AND b.last_close IS NOT NULL
          AND a.last_close > 0
          AND ABS((b.last_close - a.last_close) / a.last_close) > 0.30
          AND (b.split_ratio_in_window IS NULL OR b.split_ratio_in_window = 0)
        """
    )

    # ---- H. Split unreconciled (split observed but move doesn't match) -
    # A 2-for-1 split should drop price ~50%. Tolerance ± 5% around the
    # expected post-split price gap.
    conn.execute(
        f"""
        INSERT INTO anomalies
        SELECT
            'split_unreconciled', 'FAIL',
            a.cik, a.ticker, a.name,
            CAST(a.last_close AS VARCHAR) || ' → ' || CAST(b.last_close AS VARCHAR),
            CAST(b.split_ratio_in_window AS VARCHAR) || ':1',
            'split ratio ' || CAST(b.split_ratio_in_window AS VARCHAR)
              || ':1 but observed price ratio '
              || CAST(ROUND(a.last_close / NULLIF(b.last_close, 0), 3) AS VARCHAR)
              || ' — verify split date/ratio'
        FROM {ta} a
        JOIN {tb} b USING (cik)
        WHERE b.split_ratio_in_window IS NOT NULL AND b.split_ratio_in_window > 1
          AND a.last_close IS NOT NULL AND b.last_close IS NOT NULL
          AND b.last_close > 0
          AND ABS((a.last_close / b.last_close) - b.split_ratio_in_window)
                / b.split_ratio_in_window > 0.05
        """
    )

    # ---- I. FIGI collision (two CIKs sharing composite_figi in B) ----
    conn.execute(
        f"""
        INSERT INTO anomalies
        SELECT
            'figi_collision', 'FAIL',
            b.cik, b.ticker, b.name,
            'CIK ' || CAST(b.cik AS VARCHAR),
            b.composite_figi,
            'composite_figi collides across ' || CAST(dup.n AS VARCHAR)
              || ' CIKs in this snapshot — bad mapping'
        FROM {tb} b
        JOIN (
            SELECT composite_figi, COUNT(DISTINCT cik) AS n
            FROM {tb}
            WHERE composite_figi IS NOT NULL
            GROUP BY composite_figi
            HAVING COUNT(DISTINCT cik) > 1
        ) dup USING (composite_figi)
        """
    )

    # ------------------------------------------------------------------
    # Roll up per-category counts
    # ------------------------------------------------------------------
    counts_rows = conn.execute(
        "SELECT category, COUNT(*) FROM anomalies GROUP BY category ORDER BY category"
    ).fetchall()
    counts = {c: n for c, n in counts_rows}
    for cat in [
        "coverage_drop", "new_addition", "delisting", "ticker_change",
        "share_class_remap", "id_mapping_break", "value_drift",
        "split_unreconciled", "figi_collision",
    ]:
        counts.setdefault(cat, 0)

    # ------------------------------------------------------------------
    # Verdict logic
    # ------------------------------------------------------------------
    reasons: list[str] = []
    verdict = "PASS"

    # Coverage drop threshold (positive = drop, negative = growth)
    if coverage_drop_pct > TOLERANCES.max_coverage_drop_pct:
        reasons.append(
            f"coverage dropped {coverage_drop_pct:.2f}% "
            f"(> {TOLERANCES.max_coverage_drop_pct}% threshold)"
        )
        verdict = "FAIL"

    # Silent dropout share
    well_covered_a = conn.execute(
        f"""
        SELECT COUNT(*) FROM {ta}
        WHERE trading_days_in_window >= {TOLERANCES.well_covered_min_rows}
        """
    ).fetchone()[0]
    silent_share = (
        counts["coverage_drop"] / well_covered_a if well_covered_a > 0 else 0.0
    )
    if silent_share > TOLERANCES.max_silent_dropout_share:
        reasons.append(
            f"silent dropouts on {silent_share*100:.2f}% of well-covered CIKs "
            f"(> {TOLERANCES.max_silent_dropout_share*100}% threshold)"
        )
        verdict = "FAIL"

    # ID-mapping breaks
    if counts["id_mapping_break"] > TOLERANCES.max_id_mapping_breaks:
        reasons.append(
            f"{counts['id_mapping_break']} id_mapping_break rows "
            f"(> {TOLERANCES.max_id_mapping_breaks} threshold)"
        )
        verdict = "FAIL"

    # FIGI collisions and unreconciled splits are always FAIL — data integrity
    if counts["figi_collision"] > 0:
        reasons.append(f"{counts['figi_collision']} figi_collision rows")
        verdict = "FAIL"
    if counts["split_unreconciled"] > 0:
        reasons.append(f"{counts['split_unreconciled']} split_unreconciled rows")
        verdict = "FAIL"

    # WARN-only items (upgrade PASS → PASS_WITH_WARNINGS but never FAIL alone)
    if verdict == "PASS":
        warn_categories = [
            "delisting", "ticker_change", "share_class_remap", "value_drift",
        ]
        warn_total = sum(counts[c] for c in warn_categories)
        if warn_total > 0:
            verdict = "PASS_WITH_WARNINGS"
            reasons.append(
                f"{warn_total} WARN-level anomalies "
                f"(delisting/ticker_change/share_class_remap/value_drift)"
            )

    print(f"[validate]   verdict={verdict}")
    for r in reasons:
        print(f"[validate]     · {r}")

    return ValidationResult(
        snap_a=snap_a,
        snap_b=snap_b,
        coverage_a=coverage_a,
        coverage_b=coverage_b,
        coverage_drop_pct=coverage_drop_pct,
        anomaly_counts=counts,
        verdict=verdict,
        verdict_reasons=reasons,
    )
