# Raster PostgreSQL 15 and 16 historical local proof — 2026-11-21

This directory preserves **historical local development evidence** from one measured
source revision. It does not certify a later final candidate, hosted GitHub CI, merge,
deployment, restored-production upgrade, or field acceptance. No tests were rerun
while preparing this evidence directory.

## Bound source and results

- Repository: `kafaat/ai_platform_complete_v2.0.0_enhanced`.
- Measured commit: `3339d31844579809156160db5502727bc1f6478e`.
- Measured tree: `abbe1a9b8e49b12d5f1273d97c19165a4a8441a4`.
- PostgreSQL 15.20 with PostGIS 3.7.0: **7 collected, 7 passed, 0 failed, 0 skipped**.
- PostgreSQL 16.16 with PostGIS 3.7.0: **7 collected, 7 passed, 0 failed, 0 skipped**.
- Each isolated database received all **275 canonical migrations in manifest order**.
- Both cleanup queries reported `0|0|0` for raster jobs, run items and runs.
- Both owned local servers were stopped after the run.

The seven cases cover the unprivileged application connection, expired-lease recovery
and fencing, job-id reuse rejection, competing lease claims with two and eight workers,
and competing single-scene enqueues with two and eight workers. Each version's exact
JUnit identities agree with its certification receipt. The schema contract hashes are
those at the measured revision and must not be rewritten for a later revision.

[PG15 JUnit](pg15/certification.xml) · [PG15 certificate](pg15/certification.evidence.json)

[PG16 JUnit](pg16/certification.xml) · [PG16 certificate](pg16/certification.evidence.json)

## Provenance and preservation

[provenance-manifest.json](provenance-manifest.json) records original and saved byte
hashes, the measured source and schema hashes, workflow-selected command strings,
the native wrapper hash, supporting log hashes, and verified log facts. The workflow
commands were selected by the retained `run_pg.py` wrapper and executed locally with
`bash -euo pipefail -c`; no hosted workflow run is implied. The full process argv was
not recovered. Fixture credentials, DSNs and machine-specific paths are omitted.

The XML is byte-identical to the original output. The JSON has exactly one reversible
representation change per file: the inherited literal U+200F in a diagnostic comment
is represented as the ASCII JSON escape `\u200f`, following the repository convention.
Decoded JSON values are unchanged. Restoring that one escape reproduces the original
byte hash. The unedited originals are retained separately outside the repository.

The local versions do not prove parity with hosted CI container images. The certificate
reports direct role attributes; do not infer a general role-membership closure from
that field. A later commit or changed schema comment needs its own final-head evidence.
The 123-case related-unit result is not included in or added to these live-case counts.
