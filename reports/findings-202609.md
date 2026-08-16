# Findings — snapshot 202608 → 202609

_Generated 2026-08-16 01:46 UTC_

## Verdict: **FAIL**

**Reasons**
- 1 id_mapping_break rows (> 0 threshold)
- 2 figi_collision rows
- 1 split_unreconciled rows

## Coverage

- prior snapshot (202608): 100 rows
- new snapshot (202609): 100 rows
- delta: +0.00%

## Anomaly counts

| Category | Severity | Count |
|----------|----------|-------|
| coverage_drop | FAIL | 2 |
| delisting | WARN | 1 |
| figi_collision | FAIL | 2 |
| id_mapping_break | FAIL | 1 |
| new_addition | INFO | 1 |
| share_class_remap | WARN | 1 |
| split_unreconciled | FAIL | 1 |
| ticker_change | WARN | 1 |
| value_drift | WARN | 0 |

## Top anomalies (up to 20)

| Category | Sev | CIK | Ticker | Name | A → B | Evidence |
|----------|-----|-----|--------|------|-------|----------|
| coverage_drop | FAIL | 320193 | AAPL | Apple Inc. | 29 → 0 | well-covered in A (>=3 rows), silent in B — likely ticker change or vendor drop |
| coverage_drop | FAIL | 1318605 | TSLA | Tesla, Inc. | 29 → ABSENT | well-covered in A (>=3 rows), silent in B — likely ticker change or vendor drop |
| figi_collision | FAIL | 1018724 | AMZN | AMAZON COM INC | CIK 1018724 → BBG000BVPV84 | composite_figi collides across 2 CIKs in this snapshot — bad mapping |
| figi_collision | FAIL | 1045810 | NVDA | NVIDIA CORP | CIK 1045810 → BBG000BVPV84 | composite_figi collides across 2 CIKs in this snapshot — bad mapping |
| id_mapping_break | FAIL | 789019 | MSFT | MICROSOFT CORP | BBG000BPH459 → NULL | composite_figi disappeared for a known-good CIK. Chase vendor bug |
| split_unreconciled | FAIL | 1045810 | NVDA | NVIDIA CORP | 225.16000366210938 → 225.16000366210938 → 4.0:1 | split ratio 4.0:1 but observed price ratio 1.0 — verify split date/ratio |
| delisting | WARN | 1318605 | TSLA | Tesla, Inc. | 29 → ABSENT | CIK present in A, absent in B. Verify against SEC delisting notices |
| share_class_remap | WARN | 1652044 | GOOGL | Alphabet Inc. | BBG009S39JY5 → BBG_SIMULATED_REMAP_1652044 | CIK+composite_figi same, share_class_figi remapped. Confirm vs vendor notice |
| ticker_change | WARN | 1326801 | META → METAX | Meta Platforms, Inc. | META → METAX | Same CIK, ticker changed. Update entity mapping valid_to/valid_from |
| new_addition | INFO | 9999999 | IPOX | Fictional New Listing Corp | ABSENT → 5 | CIK not in A. Expected on new listings — flag only if unexpected |

## How to reproduce

```bash
cd us-equity-dq
uv pip install -r requirements.txt   # or pip install
python src/run.py
```

Every anomaly row above carries CIK + ticker + both snapshot
values + a plain-English evidence string, so it can be re-run
against a fixed input for regression testing.
