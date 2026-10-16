# Decision 034 scoped operation and evidence

Gap `DECISION-033-LEGACY-POLICY-UNION-01` remains **open**. The 034 SQL repair
already exists. This change makes the remaining staging operation executable
without accidentally applying later pending migrations. It is not an application
receipt. No database, role, migration file or Railway setting was changed.

The original runner's `--check` and `--apply` behavior is unchanged. New modes:

* `--inspect-034`: server-enforced read-only transaction; returns JSON containing
  current/session role, role flags and direct memberships, journal checksums,
  table ownership/RLS flags, policy definitions, pending versions and source hash.
  It creates nothing, does not return tenant rows, and fails on permission errors.
  `ok` concerns visible source/catalog prerequisites, never runtime authorization.
* `--apply-034-only --expected-sha256 <reviewed hash>`: requires the existing
  explicit schema-change environment switch, checks the source hash **before
  connecting**, and rechecks the complete known journal under advisory lock
  `91420260709`. Missing prior versions, unknown journal versions, any checksum
  mismatch, missing tables or missing ENABLE/FORCE RLS fail closed. Only 034 SQL
  and its journal entry are committed together. Later pending migrations remain
  pending. A repeated call does not replay 034. It does not certify policy behavior.

Both modes use `pg_catalog, public, pg_temp`, 5-second lock timeout and 30-second
statement timeout inside their transaction. No service-wide environment setting
should be changed to run this one-shot operator command.

The subsequent live snapshot required a third explicit mode:
`--apply-033-034-only --expected-033-sha256 <033 hash> --expected-sha256 <034 hash>`.
It verifies both source hashes before connecting, requires all 001..032 checksums,
rejects unknown journal versions and every existing checksum mismatch, and applies
only the missing members of the exact 033+034 pair under the same advisory lock
and one transaction. If 034 fails, newly applied 033 DDL and both journal changes
roll back too. No 035/036 or arbitrary range can be supplied. The 034-only mode
still rejects a missing 033. The read-only mode separately reports
`pair_prerequisites_ok` and `pair_source_checksums`; these are source/catalog
eligibility, not owner access, recovery assurance or behavioral acceptance.

Latest pair-candidate evidence is `pair-results.json`: **30 unit tests passed**;
the 033/034 native suite has **43 collected, zero locally executed**, including
five pair cases (concurrency/repeat, 033 already applied, atomic 034 failure, and
both-table canonical/legacy/missing context behavior). The earlier measurements
below remain historical evidence for the initial 034-only candidate.

## Measured source verification

* Base: `6e8cc0f9952c037550ae1644919f88c475dd89a7`.
* New unit witness with base runner: **8 failed, 7 passed**. The failures show the
  absent scoped interface/journal validator, not a new measurement of staging RLS.
* Same witness with candidate runner: **15 passed, 0 failed, 0 skipped**.
* Dedicated native PG16 suite: **38 collected**, including **9 new cases** for
  serialization, no later migrations, invalid journal rejection, atomic rollback,
  read-only catalog inspection and FORCE RLS precondition. **Not executed locally**:
  the available PostgreSQL 16.2 binary cannot be started by the allowed ordinary
  non-root process launch in this environment. No OS safeguard was bypassed.
* Existing CI job `Decision 033 Restricted Role Proof (PG16)` already runs both
  native test files, so these added cases must pass there on the final PR head.
  The prior head's 29 passing cases are not proof of the new executor.

The two minimal-row policy tests (`test_033_isolates_reads_writes_and_rolls_back`
and `test_034_closes_legacy_policy_union`) explicitly stop at migration 034. This
preserves their direct policy-composition witness: a later correlation-parent
trigger otherwise rejects those minimal rows before RLS is evaluated. All real
application writer/replay tests still apply every discovered migration. The new
036 suite must separately prove the final parent contract and tenant boundary;
the isolated 034 cases do not substitute for that evidence.

See `results.json` and the included logs. No newly claimed closure or `verified`
transition follows from unit success or native test collection.

## Staging-only continuation

Target: project `33c50993-1110-43eb-8e92-04c15edae51e`, environment
`70cc51f8-b11f-4506-87b2-4b6615e472be`. Never substitute production.

The owner has requested completion of the remaining gaps. Before the scoped
operation can proceed, the concrete target still needs an accessible authorized
connection, a fresh metadata receipt, a verified recovery point, and the approved
restricted application identity/synthetic tenants for behavioral acceptance.
The initial connector inspection exposed no direct SQL/shell operation. The
coordinator subsequently obtained a real read-only snapshot through a scoped
temporary Railway function at **2026-10-16T16:18:17.254Z**. Its assessment is saved
in `staging-before-assessment.json`: PostgreSQL 15.8, `sahool_app` without superuser
or BYPASSRLS, both target tables owned by `sahool_user` with ENABLE/FORCE RLS, and
exactly 001..032 journaled. All 32 checksums match the source; none are unknown.

**Consequently the current staging state is not eligible for `--apply-034-only`.**
033 is genuinely pending as well as 034 and 035 (and any later new migration).
Do not weaken the prerequisite check or use broad `--apply`. A separately
source-pinned 033+034 transaction is required to advance this observed state while
leaving 035+ untouched. Its 033 hash is
`bdbc863a02e40505b68d2e7ae020aa31b0551b87f01847e6d8da772b7afecf04`.
DDL-owner access, a verified restore point, final native proof and the behavioral
acceptance remain unmeasured. No staging application follows from the snapshot.

After those prerequisites, the explicit command matching this observed 032
baseline is:

```bash
DECISION_SERVICE_ALLOW_SCHEMA_CHANGE=true \
python services/decision-service/migration_runner.py \
  --apply-033-034-only \
  --expected-033-sha256 bdbc863a02e40505b68d2e7ae020aa31b0551b87f01847e6d8da772b7afecf04 \
  --expected-sha256 36e9740e83b8f56373ac16a1b2422c6adc646d875fd77d405fcffbc81cb70d69 \
  > decision033034-application.json
```

This command has been prepared, not run against staging. Use the same fresh target
inspection and post-application restricted-role acceptance as the 034-only path.

First run the read-only mode with the approved connection supplied securely via
the session environment; never paste credentials into command history or evidence:

```bash
python services/decision-service/migration_runner.py --inspect-034 > decision034-before.json
```

Review `journal_error`, `pending`, all 001..033 checksums, both ENABLE/FORCE RLS
flags, existing policies and target identity. A missing journal requires a separate
historical reconciliation; do not bootstrap it or mark unobserved versions applied.
Review role memberships transitively before accepting an application identity;
the inspector exposes direct memberships and does not certify inherited privileges.

Only if a fresh journal already records 033 correctly, after native CI succeeds
and target/recovery prerequisites are measured, the 034-only command is:

```bash
DECISION_SERVICE_ALLOW_SCHEMA_CHANGE=true \
python services/decision-service/migration_runner.py \
  --apply-034-only \
  --expected-sha256 36e9740e83b8f56373ac16a1b2422c6adc646d875fd77d405fcffbc81cb70d69 \
  > decision034-application.json
python services/decision-service/migration_runner.py --inspect-034 > decision034-after.json
```

Keep later migrations pending. Do not activate SoR, publishers or platform migration
flags. If 034 was already journaled, inspect actual restrictive policies and run
acceptance instead of reapplying. An error or timeout is failure, not permission
to bypass a check. Before commit, DDL and journal roll back together. After commit,
do not delete the restrictive policies: use a reviewed forward correction.

The remaining closure condition is unchanged: authenticated non-superuser,
non-BYPASSRLS application-role behavior on **both** tables for canonical-only,
legacy-only, conflicting and absent tenant contexts, including hidden cross-tenant
reads, rejected writes (SQLSTATE 42501), positive own-tenant control, real application
write/read path and synthetic fixture rollback. Capture the actual role, policy and
journal receipt, then prove fixtures absent after rollback. Use the detailed matrix
in `docs/runbooks/REMAINING_RUNTIME_ACCEPTANCE_20261016.md`, Operation A.

U07 v234 and production application are separate scopes. This change touches no
frozen path and creates or reuses no GATE-01 adjudication.
