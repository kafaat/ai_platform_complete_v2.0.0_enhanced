# Remaining runtime acceptance after PR #1199

This is a reviewable operation plan, not an application receipt or permission to
operate Railway. Source anchor: `main@9f0bcece487a8e9e2fc1ea590af5f2af5ab17504`.
The three operations below have separate scopes and stop conditions. No global
migration flag, deployment branch, permission to share speech, or gap status is
changed by this document.

## Observed baseline and evidence boundary

The 2026-10-16 11:58 UTC read-only Railway observation found 24 successful new
builds across staging and production. Both migrator logs explicitly reported
`MIGRATIONS_NOT_APPLIED reason=apply_not_permitted`, `apply=false`, and three
missing U07 columns. Deployment success is not schema acceptance. Platform
remained pinned to `deploy/sahool-platform-db-ready-eb6da9df` in staging and
`deploy/sahool-staging-fa92a1f7` in production; staging TTS remained pinned to
`claude/project-exploration-dtjw3p`.

Project: `33c50993-1110-43eb-8e92-04c15edae51e`.
Staging: `70cc51f8-b11f-4506-87b2-4b6615e472be`.
Production: `79de27a7-dae8-4cae-b37e-e9f7fae66c1d`.
Migrator deployments: staging `d03ce9ac-eec9-42f5-9596-ae25586c9225`,
production `a0a75d14-1ccd-4bbc-8e72-3620e358353a`.

The reusable workspace receipts are `evidence/railway-postmerge-1199/final-status.json`
and the two `migrator-<deployment-id>.json` files. These are dated observations;
refresh them before any operation. Missing schema coverage under an insufficiently
privileged identity means unknown, not absent. No live database was queried while
preparing this plan.

## Pre-operation observation

Use a separately authorized read-only identity and the
[bounded catalog snapshot](runtime_acceptance_20261016/catalog_snapshot.sql).
It inspects only metadata, uses `BEGIN READ ONLY`, bounded timeouts, and ends in
`ROLLBACK`. It must not be treated as an application-role isolation test. Capture
its exit code, server version, environment and source SHA. Stop on permission
errors; do not widen the role automatically or infer missing objects from them.

Use `services/decision-service/migration_runner.py --check` with an approved
read-only connection to inspect the Decision migration journal; the check path
does not create it. Record pending versions and checksum mismatches. No credentials
or user records belong in receipts. Observe service identities and active image
SHAs separately from the database receipt.

## Operation A: Decision 034, staging only

Gap: `DECISION-033-LEGACY-POLICY-UNION-01`. Source repair already exists. Its
remaining closure condition is committed staging application plus restricted-role
behavior, not another textual edit to SQL.

Candidate source bytes to verify, SHA-256 (not runtime authorization):

- `services/decision-service/migrations/034_tenant_boundary_policy_composition.sql`:
  `36e9740e83b8f56373ac16a1b2422c6adc646d875fd77d405fcffbc81cb70d69`.

Before authorizing application, obtain the live migration journal, existing policy
and RLS definitions for `decision_outbox_events` and `decision_reviews`, a verified
restore point, and a restricted application identity with neither superuser nor
BYPASSRLS. Check membership and table ownership as well as role flags; an owner
requires FORCE RLS. Existing 033 and earlier checksums must match.

The current runner applies **every pending file** in one transaction. Its `--apply`
option is admissible for this operation only if the fresh pending set is exactly
`[034_tenant_boundary_policy_composition.sql]` and checksum mismatches are empty.
If any other migration is pending, stop and prepare a separately reviewed
single-version executor preserving the runner's advisory lock, exact checksum and
journal transaction. Do not temporarily edit the migrations directory or journal,
and do not set a service-wide schema-change flag to work around this restriction.
If 034 is already recorded, verify bytes and actual policy definitions; do not
reapply merely because the gap is open.

Run native isolated PostgreSQL 16 proof first, using the existing dedicated
loopback harness and CI job `Decision 033 Restricted Role Proof (PG16)`
(`.github/workflows/ci.yml`). The harness creates and drops isolated databases;
it deliberately rejects Railway URLs and is **not** a staging probe.

After the committed staging application, use separately approved synthetic tenants
and rollback-only application transactions, with publishers and SoR activation
remaining off. On both tables record the following matrix under an authenticated
restricted role:

| Context | Required result |
| --- | --- |
| Canonical A, legacy unset | Own A insert/read permitted; B read hidden and write rejected |
| Canonical unset, legacy A | No rows visible; insert rejected with RLS error |
| Canonical A, legacy B | Canonical A controls access; B write rejected |
| Both missing | No rows visible; insert rejected with RLS error |

Use savepoints for expected rejected writes; verify fixtures are absent after the
outer rollback. Include the actual application write/read path, not just a
superuser query. Capture role identity, policy definitions, journal checksum,
SQLSTATEs and redacted counts. This is the acceptance evidence for `fixed`; it
neither enables SoR/NATS nor promotes other Decision gaps to `verified`.

Failure before transaction commit rolls back policy and journal changes together.
After commit, deleting the restrictive policies reopens the original isolation
hole and is not a safe automatic rollback. Stop traffic through the affected path,
retain the guards, and use a reviewed forward correction; a database restore is a
separate owner operation with its data-loss window declared.

## Operation B: U07 v234, staging first

Gap: `REPORT3-U07-REVIEW-DECISION-NOT-PERSISTED-01` is fixed in source. Runtime
acceptance remains outstanding; persistence is not reviewer authentication and
Decision-service mirroring is outside this repair.

Candidate source bytes to verify, SHA-256 (not runtime authorization):

- `migrations/v234_learning_agronomic_review.sql`:
  `acd0935af8bc8593ee99fa222b363e3b765d5036f2cc3797df83ad3ef3eb89f5`.
- `services/sahool-platform/api/phase_runtime_store.py`:
  `9e62d10c7fd4df1e81b0cd88927551f551b0b9acebfd3e5a445e1aac286b7534`.

The consumed `GATE01-ADJ-2026-10-16-001` authorizes its recorded source bytes; it
is not reusable permission for production schema changes or further frozen-path
edits. No new gate opening is needed to inspect the existing source.

Before any staging application, confirm table ownership/schema, all three existing
column definitions if present, both constraint definitions/validation flags, row
volume and lock budget, current platform writer SHA, and an independently verified
restore point. `IF NOT EXISTS` does not prove an existing column or constraint is
correct. Native PostgreSQL acceptance must cover both the currently observed
server major (the saved migrator receipt reports 15.8) and the intended deployment
major; the existing PostgreSQL 18.6 WASM receipt is not that evidence.

Apply only these exact v234 bytes in an approved one-shot session with
`ON_ERROR_STOP`, explicit lock/statement timeouts and verified `search_path` to
`public`. The file owns its `BEGIN`/`COMMIT`; do not wrap it in a supposed
rollback-only dry run whose outer transaction it can commit. Do not invoke the
MANIFEST runner, set `SAHOOL_MIGRATE_APPLY=1`, or rerun role bootstrap. Timeout or
DDL error is failure: disconnect/rollback the failed transaction and inspect the
catalog again before retry. Record old/new schema snapshots and the applied hash.

Acceptance uses an isolated clone first: apply actual prerequisite schemas and
v234 twice, prove historical defaults `unreviewed/false/NULL`, then exercise the
real platform writer with a restricted tenant identity. Cases: approved, rejected,
unreviewed, approved-to-unreviewed downgrade, same update ID across two tenants,
wrong-tenant write, failed insert rollback, and malformed review rejection
(including SQL NULL and empty evidence). The writer must set tenant context and
persist in one real transaction; read back after commit with a new connection.
External mirroring stays disabled or captured locally during the isolated test.

For staging, approve a named synthetic tenant and cleanup/retention policy, deploy
a compatible platform writer only after schema acceptance, then collect the same
bounded write/read evidence. A successful schema-only migrator does not deploy
that writer because the platform is branch-pinned. Production is a separate
promotion after staging evidence review, not part of staging authorization.

After commit, preserve the additive columns and review values if the application
is rolled back. Dropping columns would discard reviews and is not an automatic
rollback. Verify the old writer accepts the additive schema; because it does not
persist reviews, pause affected learning writes rather than silently losing new
review decisions. No blanket approval backfill is permitted.

## Operation C: TTS/platform contract deployment

Gap: `TTS-PLATFORM-POLICY-CONTRACT-SKEW-IN-PRODUCTION-01`. Contract v2 is already
merged. Missing `PLATFORM_API_URL` deliberately yields local-only behavior. A
health endpoint returning 200 does not establish speech availability.

Prepare a staging-only change record naming exact platform and TTS image SHAs,
previous deployment IDs, a trusted platform origin, authentication path, and
configuration-name diff with secret values omitted. Obtain the owner's choice of
a usable local provider or explicitly declared local unavailability. Keep all
external speech grants absent in the initial validation; enabling external speech
or changing tenant data-sharing policy is a distinct data approval, even if an
LLM grant already exists.

Pre-deploy checks: platform `/api/v1/me` emits
`contract=sahool.ai_policy_envelope`, `contract_version=2`, matching tenant, explicit
`external_tts_allowed` and named `external_tts_providers`; TTS consumes this version.
Confirm the trusted origin route and token validation without recording tokens.
Changing platform branches can include unrelated changes: review the exact diff
from the deployed image before selecting the release, rather than switching to a
moving `main` reference.

Staging acceptance must test synthesis and streaming with an instrumented egress
boundary, not just mocked method calls:

| Input/policy | Required result |
| --- | --- |
| No envelope, malformed/old version, platform unavailable, tenant mismatch | Local-only; zero external requests |
| LLM permission only; explicit speech denial; no named provider | Zero external requests |
| Local-only with installed local provider | Usable local audio or stream; zero external requests |
| Local-only without local provider | Declared `503 local_provider_unavailable_for_policy`; zero external requests |

A separately authorized external-provider test may use a synthetic non-sensitive
phrase and one named provider; it must never fall back to other external providers.
Do not infer zero egress from HTTP response code alone. Record source/image SHA,
request case, policy version, error/audio outcome and aggregate egress observation;
no user audio, bearer tokens or tenant content in the public evidence.

Only after staging acceptance should a second production change record be
approved. Rollback pins the previous compatible application images and restores
the previous trusted-origin configuration snapshot. Preserve local-only denial
throughout; never restore the retired LLM-to-TTS permission fallback. A newly
unavailable local provider is an availability regression to declare, not permission
to transmit text externally.

## What is complete and what needs a decision

On the pinned source the existing U07 writer and TTS envelope/router suites were
rerun: **120 passed, 0 skipped**, using Python 3.12.14. These are local source tests,
not live database or Railway acceptance. No native PostgreSQL server, client or
Docker executable was available during preparation, so native proof was not run
or counted as skipped success. No new fixed/verified status follows from this plan.

Required bounded approvals are independent: (A) committed staging 034 only plus
synthetic restricted-role probes; (B) exact v234 staging application and compatible
writer deployment after native proof, followed by separate production promotion;
(C) a reviewed compatible staging platform/TTS release and trusted origin, plus
local-provider/declared-unavailability choice. Each request must include refreshed
before-state evidence and a verified recovery point. Broader migration, production
deployment, external speech permission and SoR/NATS activation remain separate.
