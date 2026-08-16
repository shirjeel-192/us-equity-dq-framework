# Submission bundle — Data Quality Specialist for US Equity

Everything you need to submit is in this repo. Do the three actions below (~15 min total) and paste the resulting links into your Upwork proposal.

---

## Action 1 — Upload workbook to Google Drive + share

1. Open Google Drive → drag `reports/us-equity-dq-workbook.xlsx` into a folder
2. Right-click the uploaded file → **Open with → Google Sheets**
3. Google converts it automatically. Save it (File → Save).
4. Top-right **Share** button → **General access** → **Anyone with the link — Viewer**
5. Copy the link

Paste that link into the Upwork proposal (`{SHEET_LINK}` placeholder).

---

## Action 2 — Record a 2-minute Loom

**Tabs to have open before recording:**
- Tab 1 — GitHub repo: https://github.com/shirjeel-192/us-equity-dq-framework
- Tab 2 — The Google Sheet you just created
- Tab 3 — Terminal in the repo root

**Script (target ~90 seconds):**

### [0:00–0:15] Landing on GitHub README

> "Hi, I'm Shirjeel. I built a US equity monthly-delivery data-quality framework end-to-end over the last day to prove the shape of the work I'd do here, since I don't have prior equity domain experience. Everything's on GitHub and in a shared Google Sheet — walking you through both in 90 seconds."

### [0:15–0:40] GitHub — scroll through README

Point at the 9-detector table.

> "Nine anomaly detectors covering coverage drops, silent dropouts, ticker changes, share-class remaps, ID mapping breaks, value drift, unreconciled splits, FIGI collisions, and new additions. Every check runs against 100% of rows in DuckDB SQL — no eyeballing. Every anomaly row carries CIK, ticker, both snapshot values, and a plain-English evidence string that pastes straight into a bug tracker."

### [0:40–1:10] Switch to Google Sheet → "03 Anomalies — real" tab

Point at the AMD row.

> "This is the real-data run. 100 US equities from SEC EDGAR mapped to FIGIs via OpenFIGI, prices from Yahoo, comparing February 2026 to August 2026. Twenty-two real value-drift anomalies — AMD moved 148%, Palo Alto Networks 130%, Dell 318%. The framework doesn't care those are real market moves — that's the point. A move that big without a matching corporate action gets a human eye by design."

### [1:10–1:40] Switch to "07 Anomalies — controlled" tab

Point at the FAIL verdict.

> "This is the controlled test — I take a copy of the August snapshot and inject known-bad issues, one per detector category. Every injection gets caught. AAPL silently dropped. TSLA delisted. META retickered to METAX. MSFT's composite FIGI disappeared. NVDA got a fake 4:1 split with the price left unchanged. All flagged. This is the golden-fixture test that proves the validators work — regressions surface here before they surface in production."

### [1:40–1:55] Back to GitHub — scroll to Assumptions doc

> "The `docs/ASSUMPTIONS.md` file lists every judgment call I made and every equity-specific gotcha I know I'd need to learn — spin-off cost basis, share-class renames that look like ticker changes, delisting variance by exchange. I don't oversell what I know. Happy to walk through more on a call."

*End recording.*

---

## Action 3 — Post the Loom link

Once Loom finishes rendering:
1. Share → **Anyone with link — Viewer**
2. Copy the URL
3. Paste into proposal (`{LOOM_LINK}` placeholder)

---

## Final proposal to paste into Upwork

**Cover letter:**

Have to open honestly. I don't have prior US equity domain experience in production — no CUSIP, ISIN, or FIGI work on my resume before this week. Applied anyway because the shape of the work — automated checks against 100% of rows, PASS/FAIL cycles per delivery, root-causing every anomaly, codified numeric tolerances, findings report a stranger could pick up — is what I run on every pipeline I own.

Built the framework end-to-end over the last day. Public repo, working code, real US equity data:

- **Repo:** https://github.com/shirjeel-192/us-equity-dq-framework
- **Sheet (verdict, anomalies, entity mapping, controlled test):** {SHEET_LINK}
- **90-sec walkthrough:** {LOOM_LINK}

What's in the framework:

- Ingestion from SEC EDGAR (CIK ↔ ticker), OpenFIGI (composite + share-class FIGI), and Yahoo Finance (prices + corporate actions).
- Point-in-time entity mapping with `valid_from`/`valid_to` windows so historical queries resolve to the right identifier for any as-of date.
- **Nine anomaly detectors** running against 100% of rows in DuckDB SQL: coverage drop, silent dropout, delisting, ticker change, share-class remap, ID mapping break, value drift, unreconciled split, FIGI collision.
- **PASS / PASS_WITH_WARNINGS / FAIL verdict** with a written reasons list.
- **Findings report** in markdown + JSON per run — one anomaly per row with reproducible evidence (CIK, ticker, both snapshot values, plain-English hint).
- **Controlled golden-fixture test** — mutates a real snapshot with deliberate issues, proves every detector fires. Regressions caught before production.

Real-data run of 100 companies over a 6-month gap surfaced 22 real market-move anomalies (AMD +148%, Palo Alto Networks +130%, Dell +318%, Marvell +182%). Controlled test caught all 8 non-drift categories on injected inputs.

**About me.** Director of Engineering at RevdUp (YC W20 backed). Own the ingestion + AI layer that connects seven external platforms (HubSpot, Salesforce, Stripe, Gong, Fathom, Five9, Vapi) into a canonical Postgres schema with per-source coercion, orphan-key detection, and PASS/FAIL audit outputs. Before RevdUp I migrated 1000+ employee payroll records across three fiscal years at Tajir (also YC W20 backed) with ID drift and dedup edge cases. Also finishing an MSc in Geoinformatics and Spatial Data Science at Uni Münster in parallel.

**Honest gap.** The domain layer — spin-off cost basis handling, share-class renames that look like ticker changes, delisting variance across exchanges, vendor-specific ID quirks — I would need to learn in the first month. `docs/ASSUMPTIONS.md` in the repo lists every judgment call I made and every gotcha I know I don't yet know.

**Stack.** Python 3.13, DuckDB, httpx, yfinance, Polars. Comfortable moving snapshots to Postgres or parquet at 7M-row scale, keeping DuckDB as the query engine.

**Availability.** 30+ hrs/week starting immediately. Germany-based, good US overlap. Rate is $45/hr — priced against the domain ramp-up cost you'd carry in month one.

**Two questions upfront** to make the first call useful:

1. What does the current toolkit look like? (I built mine to demonstrate the shape — I'd expect to adapt to whatever you have.)
2. Is there a written scope for the first sprint, or does month 1 include triaging a running month-over-month findings backlog?

Best,
Shirjeel

---

**Q1 answer (Describe your exact experience with historical ID mapping process for US Stocks):**

Direct answer. Prior to this week I had no production US equity ID mapping experience. Over the last day I built a working framework end-to-end, using SEC EDGAR as the CIK anchor and OpenFIGI as the vendor-agnostic secondary key, with point-in-time validity windows so any as-of date resolves to the correct identifier. Public repo linked in the cover letter.

Where my transferable ID-reconciliation experience comes from:

- **Tajir (2021–2022) — payroll ID reconciliation.** 1000+ employees across 6 monthly spreadsheets over 3 fiscal years. Employee IDs drifted after name changes. Some employees appeared 3+ times with slight variants. Solution was a canonical employee table with a versioned overrides CSV so re-runs stayed deterministic, roughly 12% of records requiring documented manual overrides. Same shape as ticker-change / share-class-remap handling in an equity dataset.

- **RevdUp CRM ingestion — canonical entity across 7 providers.** HubSpot, Salesforce, Stripe, Gong, Fathom, Five9, Vapi. Each has different auth, rate limits, and schema quirks. Provider abstraction with per-source parsers projecting raw JSON into a canonical shape. Raw payload always stored in JSONB alongside so we can re-project if the vendor drifts a schema.

The pattern I applied to US equity in the repo:

- **Canonical anchor:** SEC CIK. Regulator's own record, stable across ticker changes and share-class remaps.
- **Vendor-agnostic secondary:** OpenFIGI compositeFIGI. Stays stable across venues; the sub-instrument `figi` and `shareClassFIGI` can move separately and each move is a different anomaly category.
- **Point-in-time validity:** every mapping row has `valid_from`/`valid_to`. Historical corrections close prior windows rather than overwriting them — the survivorship-bias-free property the JD asks for.
- **Detection contract:** every anomaly emits CIK, both snapshot values, and reproducible evidence. Regression tests run against the same anomalies.

What I would need to learn in the first month:

- Spin-off cost basis handling (varies by vendor)
- Share-class renames that read like ticker changes but aren't
- Delisting variance across NYSE, Nasdaq, and OTC
- Vendor-specific quirks (LSEG PermID vs Bloomberg BBGID vs FIGI vs S&P PayPortal)

Framework in `github.com/shirjeel-192/us-equity-dq-framework`. Controlled test in `src/controlled_test.py` proves every detector fires on known-bad input. Being upfront about the gap so you can decide before booking a call.

---

## Rate

**Bid $45/hr** on Upwork. Below the $100 top, meaningfully above the $35 low, priced to account for domain ramp-up cost in month one.

---

## Post-submit

- If they respond: assess seriousness via the two questions in the cover letter
- If they don't: connects spent were a good bet — this repo demonstrates transferable data-quality discipline for any future data-eng role, not just equity

## Cleanup after submit

- Delete duplicate repo on shirjeel-revdup account (needs manual delete_repo scope on gh)
- Keep the shirjeel-192/us-equity-dq-framework repo as portfolio
- Keep the Google Sheet as a shareable portfolio artefact
