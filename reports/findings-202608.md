# Findings — snapshot 202602 → 202608

_Generated 2026-08-16 01:45 UTC_

## Verdict: **PASS_WITH_WARNINGS**

**Reasons**
- 22 WARN-level anomalies (delisting/ticker_change/share_class_remap/value_drift)

## Coverage

- prior snapshot (202602): 100 rows
- new snapshot (202608): 100 rows
- delta: +0.00%

## Anomaly counts

| Category | Severity | Count |
|----------|----------|-------|
| coverage_drop | FAIL | 0 |
| delisting | WARN | 0 |
| figi_collision | FAIL | 0 |
| id_mapping_break | FAIL | 0 |
| new_addition | INFO | 0 |
| share_class_remap | WARN | 0 |
| split_unreconciled | FAIL | 0 |
| ticker_change | WARN | 0 |
| value_drift | WARN | 22 |

## Top anomalies (up to 20)

| Category | Sev | CIK | Ticker | Name | A → B | Evidence |
|----------|-----|-----|--------|------|-------|----------|
| value_drift | WARN | 2488 | AMD | ADVANCED MICRO DEVICES INC | 207.32000732421875 → 514.3900146484375 | price move of 148.11% between snapshots, no split recorded — investigate |
| value_drift | WARN | 6951 | AMAT | APPLIED MATERIALS INC /DE | 354.9100036621094 → 507.17999267578125 | price move of 42.9% between snapshots, no split recorded — investigate |
| value_drift | WARN | 50863 | INTC | INTEL CORP | 46.790000915527344 → 102.5 | price move of 119.06% between snapshots, no split recorded — investigate |
| value_drift | WARN | 319201 | KLAC | KLA CORP | 146.41299438476562 → 203.72000122070312 | price move of 39.14% between snapshots, no split recorded — investigate |
| value_drift | WARN | 707549 | LRCX | LAM RESEARCH CORP | 235.52999877929688 → 332.3599853515625 | price move of 41.11% between snapshots, no split recorded — investigate |
| value_drift | WARN | 731766 | UNH | UNITEDHEALTH GROUP INC | 293.19000244140625 → 401.7300109863281 | price move of 37.02% between snapshots, no split recorded — investigate |
| value_drift | WARN | 858877 | CSCO | CISCO SYSTEMS, INC. | 76.8499984741211 → 111.68000030517578 | price move of 45.32% between snapshots, no split recorded — investigate |
| value_drift | WARN | 937966 | ASML | ASML HOLDING NV | 1406.6099853515625 → 1844.0799560546875 | price move of 31.1% between snapshots, no split recorded — investigate |
| value_drift | WARN | 947263 | TD | TORONTO DOMINION BANK | 95.31999969482422 → 124.36000061035156 | price move of 30.47% between snapshots, no split recorded — investigate |
| value_drift | WARN | 1018724 | AMZN | AMAZON COM INC | 198.7899932861328 → 262.6499938964844 | price move of 32.12% between snapshots, no split recorded — investigate |
| value_drift | WARN | 1137789 | STX | Seagate Technology Holdings plc | 425.989990234375 → 973.4400024414062 | price move of 128.51% between snapshots, no split recorded — investigate |
| value_drift | WARN | 1321655 | PLTR | Palantir Technologies Inc. | 131.41000366210938 → 174.0399932861328 | price move of 32.44% between snapshots, no split recorded — investigate |
| value_drift | WARN | 1327567 | PANW | Palo Alto Networks Inc | 166.9499969482422 → 384.2699890136719 | price move of 130.17% between snapshots, no split recorded — investigate |
| value_drift | WARN | 1535527 | CRWD | CrowdStrike Holdings, Inc. | 107.41000366210938 → 216.9499969482422 | price move of 101.98% between snapshots, no split recorded — investigate |
| value_drift | WARN | 1571996 | DELL | Dell Technologies Inc. | 117.48999786376953 → 490.80999755859375 | price move of 317.75% between snapshots, no split recorded — investigate |
| value_drift | WARN | 1594805 | SHOP | SHOPIFY INC. | 112.69999694824219 → 154.32000732421875 | price move of 36.93% between snapshots, no split recorded — investigate |
| value_drift | WARN | 1596532 | ANET | Arista Networks, Inc. | 141.58999633789062 → 198.82000732421875 | price move of 40.42% between snapshots, no split recorded — investigate |
| value_drift | WARN | 1835632 | MRVL | Marvell Technology, Inc. | 78.61000061035156 → 222.02000427246094 | price move of 182.43% between snapshots, no split recorded — investigate |
| value_drift | WARN | 1973239 | ARM | ARM HOLDINGS PLC /UK | 125.27999877929688 → 279.44000244140625 | price move of 123.05% between snapshots, no split recorded — investigate |
| value_drift | WARN | 1996810 | GEV | GE Vernova Inc. | 802.1300048828125 → 1063.25 | price move of 32.55% between snapshots, no split recorded — investigate |

## How to reproduce

```bash
cd us-equity-dq
uv pip install -r requirements.txt   # or pip install
python src/run.py
```

Every anomaly row above carries CIK + ticker + both snapshot
values + a plain-English evidence string, so it can be re-run
against a fixed input for regression testing.
