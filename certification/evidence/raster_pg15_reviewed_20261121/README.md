# Raster PostgreSQL evidence after concurrency review — 2026-11-21

This is retained **local development evidence**, not GitHub CI or deployment acceptance.
The preceding six-case receipt remains unchanged in `../raster_pg15_20261121/`.

## Source and measured execution

The native run used local HEAD `a2d9d0e14626e0f5d42be974fcedb191dafc9ec5`
plus the seven tracked file edits listed in [development-receipt.json](development-receipt.json).
The complete binary Git diff SHA256 was
`90ed5a63d04a8121cb84af2d18f9facde7d206fb021857bd62f2cf997fa489f0`.
The receipt verifies the source and working diff stayed unchanged during execution.
These identities describe the measured development tree, not the later documentation
or generated commit. Final candidate checks and GitHub CI must bind their own source.

- PostgreSQL 15.20, PostGIS 3.7.0, loopback-only owned fixture.
- A new database received the canonical 275 migrations, then all 275 were reapplied in order.
- The actual application connection used the restricted role, with no unsafe role flags,
  no role memberships and no owned relations. The test also checks table ownership.
- The workflow-selected command collected and executed **seven cases: seven passed,
  zero failed, zero skipped**. The server was stopped afterward.
- The focused certification, lab-step and schema-guard suite executed **105 cases:
  105 passed, zero failed, zero skipped**.

[JUnit](certification.xml) · [live database evidence](live_pg_evidence.json) ·
[required-case catalog](catalog.json) · [workflow binding](workflow-binding.json) ·
[focused contracts](focused-contracts.xml).

## What the reviewed tests prove

The single-scene test uses two and eight separate real asyncpg connections. Each must
finish the initial absent-item SELECT before any can insert a run. It observes N real
run inserts and N item attempts, one winning insert, N-1 `ON CONFLICT` losses, and
N-1 successful deletes. An independent database read checks the surviving run and item,
zero orphan runs, and convergence of every caller on the same run and item.

Lease races separately run with two and eight workers; the remaining cases check
restricted-role attributes, expired-lease fencing and job-id uniqueness.
The JUnit adapter rejects missing, duplicate, failed and skipped mandatory cases.

CI now retains the raster report directory with an always-run pinned artifact upload.
The lab permits only that exact reporting contract; its reserved name cannot be replaced
by a different reporting command. Coverage reporting accepts one known argv prefix and
rejects shell composition, expansion and extra command lines. Negative contract tests
cover those rejection paths.

## Preservation and limits

JSON copies use escaped Unicode; [source-bindings.json](source-bindings.json) records
original and saved byte hashes, and all decoded JSON values match the original receipts.
The XML copies are byte-identical. These files contain synthetic test identities only.

The local PostGIS version does not establish Docker image parity. These cases do not
certify a restored production upgrade, a deployed raster service, a full RAG journey,
source eligibility or immutable-image reopening. GeoRAG slices GEO-T03/b and SHR-05/b
remain planned until their complete acceptance criteria pass.
