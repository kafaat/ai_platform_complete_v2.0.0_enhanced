# CDSE future-failure diagnostics evidence — 2026-10-14

Source commit: `33616dbb5f20c7b56b62f3799fadc2d667803962` on `codex/cdse-diagnostics`, based on `53652e02b3c80fa5747a0ad0e7c6f7ed9c408d4b`.
No PR number existed when this evidence was prepared. This is source and offline-test evidence, not a deployment receipt.

- `open_c_resume.json` pins four reviewed source/test hashes and 103 related tests (no skipped cases); `cdse_resume_tests.xml`/`.log` are raw results.
- `cdse_verify_b_initial_witness.json` retains all four original reproduced defects; `cdse_verify_b_repaired_witness.json` replays them against repaired hashes. `verify_b_resume.json` includes that independent review (and separately scoped Qdrant review, not a CDSE test count).
- `cdse_privacy_review_final.json` and its raw run/log/XML record 6 independent privacy checks, including forced interleaving of simultaneous tenant requests.
- Reproduction/test Python files are preserved as `.py.txt` evidence (only surplus blank lines at EOF are normalized), including their original analysis paths. They are not new CI entrypoints. Review their paths and run against the referenced source before reuse.

## Scope and limits

The historical `CDSE-EMPTY-SCENE-HAS-NO-ATTRIBUTABLE-CAUSE-01` remains **open**. These diagnostics cannot recover missing historical rasters or provider responses. They do not fix the separate catalogue-outage/no-scenes ambiguity.

Receipts preserve allowlisted fields, hashes and sensitive bbox coordinates. Unkeyed identifier hashes are not anonymization. No receipt read/list HTTP route is added. New directory/files use 0700/0600, an OS-user boundary; existing directory permissions are not rewritten and processes sharing a UID/volume share access. This review does not claim every pre-existing service log is secret-free.

The rolling window is shared across tenants: 256 JSON receipts after successful rotation, at most 257 after an interrupted commit/rotation; the next writer reconciles excess before append. No per-tenant retention or time expiry is guaranteed. New-file fsync and directory fsync precede deleting old evidence; cleanup failure still closes the write-lock descriptor. Failed persistence is reported as unconfirmed. Fault tests and a fresh-interpreter read demonstrate local behavior, not production volume persistence or backup recovery.

No live CDSE provider, database, secrets, Railway deployment or mount validation was used in these checks. Full generated-artifact/preflight gates are a later root-owned step. Actual deployment watch paths and operational freeze must be evaluated before merge; successful build does not establish running behavior.

Raw JSON/XML evidence and reproduction sources use synthetic fixtures and injected errors; no live credentials/provider bodies were captured. `SHA256SUMS` covers copied evidence and this README, not itself. Original raw reports retain their pre-commit source hashes and time-of-test status; the source commit above is the later provenance binding.

## Root-suite source contract correction

Full C-locale validation exposed an existing source-contract test that split
on the obsolete log prose `CDSE returned an empty raster`. The reviewed runtime
now accurately uses `CDSE raster rejected` with an outcome distinguishing zero
observed pixels, rejected shape and failed inspection. The root test retains
all six request fields, adds the outcome and requires the attempted receipt,
request log and byte cleanup in that order in the same rejected branch.

`cdse_log_contract_repair_witness.json` binds the updated test hash to the
unchanged reviewed runtime hash: valid source passes and nine defective
temporary-source mutants fail. `verify_b_cdse_log_contract_review.json` records
independent approval without weakening. The four original runtime/source-test
hashes and source commit above remain unchanged. The earlier normal-unit log
ended without a summary and cannot be attributed to the stale-literal failure;
that incomplete run is retained separately from the concrete C-locale failure.
This test correction does not close the historical CDSE gap, establish the
historical cause, prove deployment or replace final-head CI.
