# Runtime acceptance after PR #1228

This change addresses the repeatable missing `weekly_insights.py` image failure
and extends the existing live CI witnesses. It does not authorize a deployment,
rotate credentials, migrate a production database, or certify all D01–D14 gaps.

## Container acceptance

`Railway Dockerfile PR build` runs `scripts/ci/vegetation_smoke.py` after the
existing Vegetation build. A failed smoke or mutation makes that build job and
its existing final verdict fail. Repository required-check configuration remains
an independent enforcement layer; this change does not alter branch protection.

The application runs its actual Dockerfile command and non-root user, with no
checkout mounted into it. A separately reviewed JSON contract requires all
current router modules and 22 route/method pairs, including the weekly report.
A source-inventory test requires review of that contract when routes change.
The container runs with production RS256 configuration (a disposable generated
public key) and real-only Raster mode. An isolated HTTP Raster fixture proves
readiness 200 -> 503 -> 200; liveness stays 200 during the dependency outage.
This is packaging/readiness acceptance, not live imagery or tenant-data proof.

The same workflow removes only the weekly module COPY in a temporary Dockerfile,
builds it successfully, then requires liveness 200, the specific insights import
failure, readiness 503, and absence of the report route. Unrelated build/startup
failures cannot pass this mutation witness. Source Python changes select the
Vegetation build even when the new module was omitted from COPY.

Run locally with Docker after building the image:

```sh
python3 scripts/ci/vegetation_smoke.py --image IMAGE --output /tmp/vegetation-smoke
```

Receipts and logs are uploaded even on failure. `local_image_id` is the Docker
configuration ID used for these containers, **not a registry manifest digest**.
A later promotion gate still needs a registry digest, matching source/tree,
configuration revision and target-environment acceptance; this PR does not
claim to install such a gate on Railway.

## Notification interruption acceptance

The existing `Notification Queue Rollout` CI runs three additional tests against
its pinned NATS 2.15.0 server. They exercise a real broker rejection of the DLQ
payload, a deliberately lost response after actual DLQ persistence, and loss of
the worker connection after persistence but before Term. The source remains
pending, is redelivered with the same stream sequence, and terminates only after
successful persistence. Retries produce one DLQ record within the configured
JetStream deduplication window. The production 30-second NAK delay is retained.

The PubAck-loss boundary is injected after a real publish; it is not a network
packet-loss measurement. These tests do not prove deduplication beyond the
window, provider exactly-once delivery, or approved replay policy. The existing
local failure test is retained. No MAX_DELIVERIES mechanism is added to the
unlimited-delivery consumer.

## Tenant connection reuse

The existing restricted-role PG16 workflow includes six new cases, covering
both 033/034 tables after commit, rollback and cancellation of a running server
query. They use the shipped `persistence.acquire_connection` pool/release code,
limited to one connection. `pg_backend_pid()` must remain identical for tenant
A, absent context, and tenant B. Missing/cross-tenant reads and writes are denied.
The fixture role is a real LOGIN without superuser/BYPASSRLS, separate from the
migration administrator. No PgBouncer mode is assumed.

This isolates 034 policies from later correlation triggers. Existing application
and later-migration suites still run. Production role grants, deployed schema,
SECURITY DEFINER execution inventory and actual pool topology require a separate
non-secret comparison and live acceptance before D08 can be closed operationally.
