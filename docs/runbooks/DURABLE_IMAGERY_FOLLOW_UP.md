# Durable imagery follow-up — post-delivery v1

Gap: `VEGETATION-POST-EXECUTION-BRIDGE-CALLS-AN-UNDECLARED-RASTER-ROUTE-01`.
Source components: `shared/contracts/imagery_followup.py`,
`services/raster-service/{follow_up_store,follow_up_runtime,follow_up_worker}.py`,
`services/raster-service/routers/follow_up.py`,
`services/decision-service/observation_context.py`.

## Contract and ownership

The vegetation bridge submits an authenticated POST to
`/v1/fields/{field_id}/imagery-ingestion-requests`. A 202 is returned only after a
PostgreSQL row is persisted (or an identical prior request is found). `Location`
points to the tenant-scoped GET status resource. PostgreSQL is the timer and
handoff ledger; the existing raster backfill queue remains the pixel-processing
owner. This avoids a new broker/version dependency and a database/broker dual write.

The key is SHA256 of the canonical tuple (tenant, field, execution request,
policy version). It never includes the HTTP request time. Replays return the same
record; changed payloads return 409. Tokens are used at admission and never stored.
The shared JWT verifier checks signature/issuer/audience/expiry. An optional tenant
header must match the token. The field geometry is a visible, versioned snapshot.

**Time basis is `delivery_receipt_received_at`, not physical execution.** Decision
must expose a matching accepted request and accepted adapter receipt, including
field and season. Its persisted receipt time anchors `days_after` (1–30; default 5)
and `window_days` (1–30; default 7). The bridge cannot manufacture that timestamp.
Admission fails closed when Decision is not an authenticated, promoted SoR.
The new read endpoint does not promote it or write execution state.

## Recovery and meaning of statuses

`pending` -> `claimed` -> `dispatched`, or `waiting_for_scene` / `retry_wait`.
`failed`, `expired`, `cancelled` and `dispatched` are terminal for this scheduler.
A short transaction claims one row with `FOR UPDATE SKIP LOCKED`; the 180-second
lease token fences progress and settlement. Processing has a 120-second timeout.
Worker termination leaves a reclaimable lease. Retry exhaustion (128 attempts) and
expired observation windows become explicit terminal states.

Transient retries use bounded exponential jitter (up to one hour); no suitable
scene retries after six hours. Catalogue outages do not become successful jobs.
Scene selection requires an explicit finite known cloud percentage <=30, a
supported provider and acquisition within the window. Missing cloud is unknown.
The selected scene is persisted before the first enqueue. Each indicator's durable
reference is persisted separately, so a partial handoff resumes the same scene.
A crash between downstream enqueue and progress persistence can replay the enqueue;
the existing canonical product identity provides downstream deduplication. This is
at-least-once handoff, not a claim of exactly-once execution.

`dispatched` means durable backfill job references or an already-persisted canonical
backfill item. It does **not** mean pixel completion, physical execution, or
verified agricultural improvement. Responses always expose
`physical_execution_verified=false` and `outcome_verified=false`. Those require
separate evidence/Decision verification. GET exposes attempts, reason, timestamps
and partial job references. Unexpected exception details/tokens are not exposed.
A legacy `already_ready` asset lookup without a canonical backfill item ID is
rejected as `ready_product_identity_unproven`: the old asset preflight does not
bind provider/processing version. This can require operator investigation; it is
not silently reported as successful follow-up.
Cancellation is currently a store operation only, before a live claim; no public
cancel API or recall of downstream jobs is promised.

## Deployment and activation

1. Apply additive `migrations/v236_raster_follow_up_requests.sql` through the
   existing authorized migration process; it is ordered before the final v206
   RLS hardening pass. The application never creates schema at startup.
2. Use a restricted raster `DATABASE_URL` role with SELECT/INSERT/UPDATE on the new
   table and the existing field/history/backfill permissions. No superuser or
   BYPASSRLS. ENABLE + FORCE RLS and transaction-local `app.current_tenant` are
   mandatory. Startup rejects an elevated role or absent RLS/table.
3. Confirm Decision SoR certification and existing 019 lineage migration, service
   bearer configuration (`DECISION_SERVICE_AUTH_TOKEN` on both services), and
   `DECISION_SERVICE_URL`. Service bearer grants read access to receipt context;
   treat it as a secret. Receipt reads are tenant-qualified across all joins.
4. Confirm the existing STAC provider, pixel worker and versioned field geometry.
   Configure `RASTER_FOLLOWUP_TENANTS` as an explicit comma-separated UUID allowlist
   on each intended raster worker instance. Empty/unset leaves submission disabled
   (503), preventing an unserviced 202. Multiple instances may claim safely.
5. Measure with an isolated staging tenant: accepted receipt -> POST202 -> replay
   same ID -> due claim -> pinned scene -> downstream references -> status GET.
   Check cross-tenant denial, provider failure, expiry and worker termination.
   Separately measure pixel completion and any outcome verification.
6. Roll back activation by clearing the tenant allowlist and restarting raster.
   Retain durable rows/schema for investigation/recovery; never drop queued work.
   In-flight downstream jobs are not recalled by disabling the scheduler.

Deployment requires coordinated raster + vegetation + Decision consumers.
Merging migration changes may trigger the existing migrator; a green PR does not
certify production migration state or authorize claiming production acceptance.
The scoped GATE-01 record binds only the required registration/ownership bytes;
it does not globally unfreeze other paths or constitute independent attestation.

## Acceptance levels and reproducibility

Local behavioral tests and raw output:
`certification/evidence/imagery_follow_up_20261018/`.
Real PostgreSQL tests: `tests_v9/test_imagery_follow_up_pg16.py`, run by
`.github/workflows/imagery-follow-up-pg16.yml` against an exact disposable loopback
PG16 target. They test concurrent insert/claim, restricted-role and owner FORCE
RLS, transaction-local context reset, stale lease rejection, expiry, partial
progress persistence, and the actual Decision receipt query. The Decision fixture
uses existing 001/005/006 DDL plus the exact season column from 019; it is not full
Decision migration/cutover certification. Recreating a client/worker is not a
PostgreSQL server crash/restart test.

```bash
PYTHONPATH=/tmp/sahool-slice-python python -m pytest tests_v9/test_imagery_follow_up.py services/vegetation-analysis-service/test_post_execution_bridge.py -q --no-cov
FOLLOWUP_REQUIRE_PG16=1 FOLLOWUP_TEST_DATABASE_URL=postgresql://followup_admin:disposable_test_only@127.0.0.1:5437/followup_test python -m pytest tests_v9/test_imagery_follow_up_pg16.py -v
```

CI uses a digest-pinned PG16 image through the existing verified mirror helper.
Local PG execution is blocked by this workspace's inability to start PostgreSQL
under a non-root OS user (`runuser: cannot set groups: Operation not permitted`).
Collection alone is not execution. Staging and production acceptance have not
been measured by this change; no `verified` promotion is justified.

## Design references (primary sources)

- PostgreSQL 16 SELECT / SKIP LOCKED (queue-like consumers; not general consistency):
  https://www.postgresql.org/docs/16/sql-select.html
- PostgreSQL 16 row security (owners, FORCE RLS and bypass roles):
  https://www.postgresql.org/docs/16/ddl-rowsecurity.html
- Azure asynchronous request-reply (202 + Location and status polling):
  https://learn.microsoft.com/en-us/azure/architecture/patterns/asynchronous-request-reply
- AWS transactional outbox (dual-write failure and idempotent consumers):
  https://docs.aws.amazon.com/prescriptive-guidance/latest/cloud-design-patterns/transactional-outbox.html
- NATS scheduled messages ADR (alternative requires deployed scheduling support):
  https://github.com/nats-io/nats-architecture-and-design/blob/main/adr/ADR-51.md
- Procrastinate stalled jobs (leases/recovery are explicit responsibilities):
  https://procrastinate.readthedocs.io/en/stable/howto/production/retry_stalled_jobs.html

These references inform the design; tests of this repository establish its actual
behavior. No external library is claimed to certify the implementation.
