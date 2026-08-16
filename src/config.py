"""
Central config for the US-equity data-quality framework.

Every tolerance, threshold, and verdict rule lives here — the whole point of
this file is that changing "what does PASS mean this month" is a single edit,
not a scavenger hunt through the validators.
"""
from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class Tolerances:
    # % coverage drop from prior snapshot to current before we FAIL
    max_coverage_drop_pct: float = 0.5

    # % of well-covered securities that can silently drop before we FAIL
    max_silent_dropout_share: float = 0.02  # 2%

    # Unexplained value-drift outliers (single-day move beyond X σ w/o corp action)
    max_unexplained_drift_outliers: int = 5
    drift_sigma_threshold: float = 3.0  # 3σ move flagged if no matching action

    # ID-mapping breaks (CIK missing FIGI, duplicate FIGIs across CIKs)
    max_id_mapping_breaks: int = 0  # zero tolerance — every one gets chased

    # "Well-covered" means: had ≥ N valid measure rows in the prior snapshot
    well_covered_min_rows: int = 3


@dataclass(frozen=True)
class DataConfig:
    # Universe size for the demo run. 100 companies keeps the unauthenticated
    # OpenFIGI throttling (5 req/min) manageable and still surfaces real
    # cross-snapshot change. In production, an API key raises this to 25/min
    # and the same code path handles ~2,500 companies per snapshot.
    universe_size: int = 100

    # SEC requires a User-Agent identifying you and giving a contact email.
    sec_user_agent: str = "US-Equity DQ Framework Shirjeel shirjeel@getrevdup.com"

    # OpenFIGI free-tier (no API key) allows 10 mappings per POST and
    # 5 POSTs per minute. With a free API key it's 25 per POST and 25/min.
    # We stay unauthenticated so the demo runs with zero setup.
    openfigi_batch_size: int = 10
    openfigi_sleep_seconds: float = 12.5   # 60s / 5 req = 12s + safety margin


# Live singleton — every module imports these
TOLERANCES = Tolerances()
DATA = DataConfig()
