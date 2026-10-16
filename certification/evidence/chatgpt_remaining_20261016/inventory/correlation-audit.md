# Correlation chain audit — 2026-10-16

Base: `9f0bcece487a8e9e2fc1ea590af5f2af5ab17504`. Source audit, no live database query and no migration/write performed. Gap remains **open**.

## What the code actually joins

| Surface | Actual identity / connection | Authority and source |
|---|---|---|
| Agronomic decision | `decision_record.decision_id`; candidate lineage and immutable content digest | Current platform interim bridge; decision-service mirror. `docs/architecture/db_ownership.yml:197–215`; service writer `services/decision-service/persistence.py:168`; platform writers `api/routers/decision_record.py:200,374` and `api/routers/weather.py:1447`. |
| Review | `decision_reviews.(tenant_id, decision_id)` links to decision; append-only review; nullable `request_id` exists but current INSERT does not populate it | Sole owner decision-service, not platform. `services/decision-service/migrations/002_decision_review.sql:47–90`; `services/decision-service/persistence.py:715–733`. Interim bridge review endpoint is fail-closed per ownership declaration. |
| Legacy dispatch/outcome | `execution_ledger.decision_id` points to a **dispatch_decisions** `disp_…` identifier, not a demonstrated foreign key to `decision_record` | Platform owner. `migrations/v68_execution_ledger.sql:7–33`; `services/sahool-platform/api/routers/decision_dispatch.py:312–349,603–646`. A lookup by `decision_record.decision_id` alone must not be declared a full chain. |
| Physical irrigation run | `as_applied_irrigation_runs`: decision_id, authorization_id, execution_plan_id, digests | Platform owner, `migrations/v178_canonical_as_applied_irrigation_truth.sql:2–22`; ownership at `docs/architecture/db_ownership.yml:1378–1396`. |
| Physical receipt | `(tenant_id, run_id)` FK points to run, not directly to decision_record | `migrations/v178_canonical_as_applied_irrigation_truth.sql:24–41`; read path `services/sahool-platform/api/irrigation_closed_loop_runtime.py:29,65`. No literal INSERT into these two tables was found in Python source by this audit; that search is not proof no generic/other producer exists. |
| Approval workflow | `approval_workflows.approvals` is a JSONB column, **not an approvals table** | `migrations/v9_new_tables.sql:47–66`. The original three-table gap wording was inaccurate. |
| Event transport | Some durable execution event/outbox paths already accept correlation/causation IDs | `services/decision-service/persistence.py:1648–1660`; relay `services/sahool-platform/api/irrigation_dispatch_relay_worker.py:96`. Existing transport IDs do not prove propagation through the foregoing record writers. |

## Bounded implementation proposal, pending contract/owner selection

1. Scope the first contract to agronomic decision → append-only review → execution authorization/plan/request. Explicitly decide whether legacy `dispatch_decisions` outcomes are part of this same chain or a separate trace joined by a documented parent reference. Never join unlike IDs solely because both columns are named `decision_id`.
2. Choose a server-owned opaque `correlation_id`, minted once at trusted ingress and retained on idempotent replay. Treat inbound HTTP correlation headers as untrusted hints unless a bounded validation/ownership rule is approved. Every lookup and unique key includes tenant. Do not derive trace identity from secrets, PII, raw request bodies, or changing request IDs.
3. Add nullable indexed correlation columns in the owning migration streams: platform for current interim-bridge decision/dispatch/outcome/run/receipt records, decision-service for the review/SoR stream. Do not invent historical IDs or overwrite existing append-only receipts/content hashes. Historical rows remain explicitly unknown. Establish compatibility and content-digest coverage before changing any signed record.
4. Thread the trusted identity through **all actual writers** and event envelopes, not only schemas. Replays retain the first stored ID; conflicting supplied IDs fail. Cross-tenant reads fail closed; preexisting rows remain readable with an explicit missing-trace state.
5. Add real PostgreSQL restricted-role tests for each owner, including same-tenant success, cross-tenant denial, missing context, duplicate replay, conflicting correlation, rollback, legacy NULL rows, and immutable audit-digest behavior. A read-only trace reconstruction test must follow actual foreign-key/reference edges, including run-to-receipt joins. No actuator dispatch or physical operation is part of the tests.
6. Apply only to isolated staging after owner review of migration order, declared ownership and bridge/SoR state. Record schema receipts and an authenticated negative/positive read-only trace test. Production application is a separately approved operation.

## Frozen/coordination boundaries

`docs/architecture/gate01_policy.json` remains globally CLOSED. A migration manifest change touches `migrations/MANIFEST.txt`; ownership edits touch `docs/architecture/db_ownership.yml`. Event/store/worker/actuator propagation may touch `api/event_bus.py`, `api/phase_runtime_store.py`, `api/phase_runtime_workers.py`, `services/actuator-service/actuator_runtime.py` or `routers/commands.py`: all require a **fresh byte-scoped ISSUED grant** if included. Do not reuse U07's consumed v234 grant. `scripts_v9/run_migrations.sql` is the documented real runner alias; absence from an old frozen list is not authorization.

No implementation change to these boundaries is proposed as an incidental inventory fix. This audit resolves the mistaken table assumption and narrows the decision required; it is not closure evidence.
