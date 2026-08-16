"""
Emit three artefacts per run:

1. reports/findings-<snap_b>.md   → human-readable summary, top anomalies
2. reports/findings-<snap_b>.json → machine-readable full anomaly log
3. sheets/*.csv                   → tabular exports for the Google Sheet

The Google Sheet has one tab per CSV. The stranger-picks-it-up test:
open the sheet, read verdict tab, scan anomalies tab, sanity-check the
mapping tab — done in under two minutes.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import duckdb

from validate import ValidationResult


def emit(
    conn: duckdb.DuckDBPyConnection,
    result: ValidationResult,
    reports_dir: Path,
    sheets_dir: Path,
) -> None:
    reports_dir.mkdir(exist_ok=True, parents=True)
    sheets_dir.mkdir(exist_ok=True, parents=True)

    _write_markdown(conn, result, reports_dir)
    _write_json(conn, result, reports_dir)
    _write_sheet_csvs(conn, result, sheets_dir)


# ------------------------------------------------------------------
# Markdown findings report
# ------------------------------------------------------------------

def _write_markdown(
    conn: duckdb.DuckDBPyConnection,
    result: ValidationResult,
    out_dir: Path,
) -> None:
    p = out_dir / f"findings-{result.snap_b}.md"
    run_stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    lines: list[str] = []
    lines.append(f"# Findings — snapshot {result.snap_a} → {result.snap_b}")
    lines.append("")
    lines.append(f"_Generated {run_stamp}_")
    lines.append("")
    lines.append(f"## Verdict: **{result.verdict}**")
    lines.append("")
    if result.verdict_reasons:
        lines.append("**Reasons**")
        for r in result.verdict_reasons:
            lines.append(f"- {r}")
    else:
        lines.append("_No verdict-affecting anomalies triggered._")
    lines.append("")

    lines.append("## Coverage")
    lines.append("")
    lines.append(f"- prior snapshot ({result.snap_a}): {result.coverage_a} rows")
    lines.append(f"- new snapshot ({result.snap_b}): {result.coverage_b} rows")
    lines.append(f"- delta: {result.coverage_drop_pct:+.2f}%")
    lines.append("")

    lines.append("## Anomaly counts")
    lines.append("")
    lines.append("| Category | Severity | Count |")
    lines.append("|----------|----------|-------|")
    severities = {
        "coverage_drop": "FAIL",
        "new_addition": "INFO",
        "delisting": "WARN",
        "ticker_change": "WARN",
        "share_class_remap": "WARN",
        "id_mapping_break": "FAIL",
        "value_drift": "WARN",
        "split_unreconciled": "FAIL",
        "figi_collision": "FAIL",
    }
    for cat, n in sorted(result.anomaly_counts.items()):
        lines.append(f"| {cat} | {severities.get(cat,'?')} | {n} |")
    lines.append("")

    lines.append("## Top anomalies (up to 20)")
    lines.append("")
    top = conn.execute(
        """
        SELECT category, severity, cik, ticker, name, snap_a_value,
               snap_b_value, evidence
        FROM anomalies
        ORDER BY CASE severity WHEN 'FAIL' THEN 0 WHEN 'WARN' THEN 1 ELSE 2 END,
                 category, cik
        LIMIT 20
        """
    ).fetchall()
    if not top:
        lines.append("_No anomalies raised. Sanity check the tolerances._")
    else:
        lines.append("| Category | Sev | CIK | Ticker | Name | A → B | Evidence |")
        lines.append("|----------|-----|-----|--------|------|-------|----------|")
        for r in top:
            cat, sev, cik, tic, name, a, b, ev = r
            name = (name or "")[:40]
            ev = (ev or "")[:100]
            lines.append(f"| {cat} | {sev} | {cik} | {tic} | {name} | {a} → {b} | {ev} |")
    lines.append("")

    lines.append("## How to reproduce")
    lines.append("")
    lines.append("```bash")
    lines.append("cd us-equity-dq")
    lines.append("uv pip install -r requirements.txt   # or pip install")
    lines.append("python src/run.py")
    lines.append("```")
    lines.append("")
    lines.append("Every anomaly row above carries CIK + ticker + both snapshot")
    lines.append("values + a plain-English evidence string, so it can be re-run")
    lines.append("against a fixed input for regression testing.")
    lines.append("")

    p.write_text("\n".join(lines))
    print(f"[report] wrote {p}")


# ------------------------------------------------------------------
# JSON findings log
# ------------------------------------------------------------------

def _write_json(
    conn: duckdb.DuckDBPyConnection,
    result: ValidationResult,
    out_dir: Path,
) -> None:
    p = out_dir / f"findings-{result.snap_b}.json"
    rows = conn.execute(
        """
        SELECT category, severity, cik, ticker, name,
               snap_a_value, snap_b_value, evidence
        FROM anomalies
        ORDER BY category, cik
        """
    ).fetchall()
    payload = {
        "snap_a": result.snap_a,
        "snap_b": result.snap_b,
        "coverage_a": result.coverage_a,
        "coverage_b": result.coverage_b,
        "coverage_drop_pct": result.coverage_drop_pct,
        "verdict": result.verdict,
        "verdict_reasons": result.verdict_reasons,
        "anomaly_counts": result.anomaly_counts,
        "anomalies": [
            {
                "category": c, "severity": sev, "cik": cik, "ticker": tic,
                "name": name, "snap_a_value": a, "snap_b_value": b,
                "evidence": ev,
            }
            for (c, sev, cik, tic, name, a, b, ev) in rows
        ],
    }
    p.write_text(json.dumps(payload, indent=2, default=str))
    print(f"[report] wrote {p}")


# ------------------------------------------------------------------
# Sheet CSVs — one per tab
# ------------------------------------------------------------------

def _write_sheet_csvs(
    conn: duckdb.DuckDBPyConnection,
    result: ValidationResult,
    out_dir: Path,
) -> None:
    # verdict_summary.csv
    _copy_query_to_csv(
        conn,
        f"""
        SELECT
            '{result.snap_a}' AS snap_a,
            '{result.snap_b}' AS snap_b,
            {result.coverage_a} AS coverage_a,
            {result.coverage_b} AS coverage_b,
            {result.coverage_drop_pct} AS coverage_drop_pct,
            '{result.verdict}' AS verdict,
            '{" | ".join(result.verdict_reasons).replace("'", "''")}' AS reasons
        """,
        out_dir / "01_verdict_summary.csv",
    )

    # anomaly_counts.csv
    _copy_query_to_csv(
        conn,
        """
        SELECT category, severity, COUNT(*) AS count
        FROM anomalies
        GROUP BY category, severity
        ORDER BY CASE severity WHEN 'FAIL' THEN 0 WHEN 'WARN' THEN 1 ELSE 2 END,
                 category
        """,
        out_dir / "02_anomaly_counts.csv",
    )

    # anomalies_full.csv
    _copy_query_to_csv(
        conn,
        """
        SELECT category, severity, cik, ticker, name,
               snap_a_value, snap_b_value, evidence
        FROM anomalies
        ORDER BY CASE severity WHEN 'FAIL' THEN 0 WHEN 'WARN' THEN 1 ELSE 2 END,
                 category, cik
        """,
        out_dir / "03_anomalies_full.csv",
    )

    # entity_mapping_current.csv (latest state per CIK)
    _copy_query_to_csv(
        conn,
        """
        SELECT cik, ticker, composite_figi, share_class_figi, name,
               valid_from, valid_to, source_snapshot
        FROM entity_mapping
        WHERE valid_to IS NULL
        ORDER BY cik
        """,
        out_dir / "04_entity_mapping_current.csv",
    )

    # entity_mapping_history.csv (only rows that closed, i.e., real changes)
    _copy_query_to_csv(
        conn,
        """
        SELECT cik, ticker, composite_figi, share_class_figi, name,
               valid_from, valid_to, source_snapshot
        FROM entity_mapping
        WHERE valid_to IS NOT NULL
        ORDER BY cik, valid_from
        """,
        out_dir / "05_entity_mapping_history.csv",
    )


def _copy_query_to_csv(
    conn: duckdb.DuckDBPyConnection, query: str, out: Path
) -> None:
    # DuckDB's COPY does header + quoting correctly out of the box.
    conn.execute(
        f"COPY ({query}) TO '{out}' (HEADER, DELIMITER ',', QUOTE '\"')"
    )
    print(f"[report] wrote {out}")
