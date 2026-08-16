"""
Point-in-time entity mapping across snapshots.

The insight this module encodes: an entity's identity is stable at the CIK
level, but every OTHER attribute (ticker, share class FIGI, name) can change
over time. The mapping table captures those changes with explicit validity
windows so any historical query can resolve to the correct identifier for
the query date.

Emitted table shape:
    entity_mapping(
        cik BIGINT,
        ticker VARCHAR,
        composite_figi VARCHAR,
        share_class_figi VARCHAR,
        name VARCHAR,
        valid_from DATE,
        valid_to DATE,             -- NULL means "still valid at latest snapshot"
        source_snapshot VARCHAR    -- the snapshot the row was first observed in
    )
"""
from __future__ import annotations

import duckdb


def build_entity_mapping(
    conn: duckdb.DuckDBPyConnection,
    snapshot_dates_by_tag: dict[str, str],  # {"202607": "2026-07-31", ...}
) -> None:
    """
    Build a mapping table by walking snapshots in chronological order, closing
    a validity window whenever any of (ticker, composite_figi, share_class_figi,
    name) changes for a given CIK.
    """
    tags = sorted(snapshot_dates_by_tag.keys())
    print(f"[mapping] building over snapshots: {tags}")

    # Union all snapshots into one long table so we can window over CIK.
    union_sql_parts = []
    for tag in tags:
        d = snapshot_dates_by_tag[tag]
        union_sql_parts.append(
            f"""
            SELECT cik, ticker, composite_figi, share_class_figi, name,
                   DATE '{d}' AS observed_on,
                   '{tag}' AS source_snapshot
            FROM snapshot_{tag}
            """
        )
    union_sql = " UNION ALL ".join(union_sql_parts)

    conn.execute("DROP TABLE IF EXISTS entity_mapping")
    conn.execute(
        f"""
        CREATE TABLE entity_mapping AS
        WITH all_obs AS ({union_sql}),
        -- Compact consecutive identical states per CIK so we only emit rows
        -- when something actually changed.
        change_flags AS (
            SELECT
                cik, ticker, composite_figi, share_class_figi, name,
                observed_on, source_snapshot,
                LAG(ticker) OVER w AS prev_ticker,
                LAG(composite_figi) OVER w AS prev_composite,
                LAG(share_class_figi) OVER w AS prev_share_class,
                LAG(name) OVER w AS prev_name
            FROM all_obs
            WINDOW w AS (PARTITION BY cik ORDER BY observed_on)
        ),
        starts AS (
            SELECT * FROM change_flags
            WHERE prev_ticker IS NULL          -- first observation for this CIK
               OR ticker <> prev_ticker
               OR COALESCE(composite_figi, '') <> COALESCE(prev_composite, '')
               OR COALESCE(share_class_figi, '') <> COALESCE(prev_share_class, '')
               OR COALESCE(name, '') <> COALESCE(prev_name, '')
        ),
        with_end AS (
            SELECT
                *,
                LEAD(observed_on) OVER (PARTITION BY cik ORDER BY observed_on) AS next_change
            FROM starts
        )
        SELECT
            cik, ticker, composite_figi, share_class_figi, name,
            observed_on AS valid_from,
            next_change AS valid_to,
            source_snapshot
        FROM with_end
        ORDER BY cik, valid_from
        """
    )

    n = conn.execute("SELECT COUNT(*) FROM entity_mapping").fetchone()[0]
    changes = conn.execute(
        "SELECT COUNT(*) FROM entity_mapping WHERE valid_to IS NOT NULL"
    ).fetchone()[0]
    print(f"[mapping]   entity_mapping: {n} rows total, {changes} closed windows")
