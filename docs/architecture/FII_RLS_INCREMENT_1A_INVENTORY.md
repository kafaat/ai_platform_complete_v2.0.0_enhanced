# FII Safety Increment 1A — RLS Write Inventory

Reference tree: `0da934a` pre-gate archive.

## First remediation batch

| Table | Source migration | FORCE RLS | Read policy | Write policy before v192 | Owner |
|---|---|---:|---|---|---|
| `scouting_pins` | `v94_scouting_pins.sql` | Yes | fail-closed | **unsafe:** missing tenant context allowed | `sahool-platform` |
| `prescriptions` | `v95_prescriptions.sql` | Yes | fail-closed | **unsafe:** missing tenant context allowed | `sahool-platform` |

`v192_fii_rls_write_fail_closed.sql` replaces both policies with identical fail-closed
`USING` and `WITH CHECK` expressions based on `NULLIF(current_setting(...), '')`.

## Wider inventory findings (not modified in this increment)

The repository contains additional historical policies that explicitly allow missing tenant
context, including migrations for enterprise GIS, precision agriculture, crop-stress memory,
backfill runs, MFA audit/recovery, farm ledgers, outbox delivery attempts, and other domains.
They require owner-by-owner remediation batches because some currently document privileged
job semantics. They are **not** silently changed by this FII increment.

The static ratchet baselines historical migrations through v191 and enforces the corrected FII
files plus every future numbered migration. A subsequent safety backlog must burn down the
historical inventory without widening this commit.

## Live proof

`tests_v9/test_fii_rls_write_fail_closed_postgres.py` proves on real PostgreSQL:

- absent/empty/malformed/wrong tenant context cannot insert;
- correct tenant context can insert only matching rows;
- reset and connection reuse do not leak tenant A into tenant B.

The test skips explicitly when `TEST_DATABASE_URL` is unavailable.
