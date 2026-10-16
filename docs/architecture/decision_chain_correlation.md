# Durable correlation for the actual decision chains

This contract addresses `CORRELATION-ID-ABSENT-FROM-THE-THREE-TABLES-THAT-CARRY-THE-DECISION-CHAIN-01`.
The historical name incorrectly assumed an `approvals` table. No such table is introduced.

| Chain | Actual parent references | Migration owner |
|---|---|---|
| Agronomic decision → review → plan → authorization → request | `decision_record.decision_id`; then `decision_reviews.review_id`, `decision_execution_plans.execution_plan_id`, `decision_dispatch_authorizations.dispatch_authorization_id`. Every hop also verifies matching tenant and decision/plan/review references. | Decision-service 036; decision root is also extended by platform v235 while the interim bridge owns it. |
| Legacy dispatch → execution ledger | `execution_ledger.decision_id` references `dispatch_decisions.decision_id`. A `disp_` identity is not presumed to be an agronomic decision ID. | Platform v235 |
| Agronomic decision → physical run → receipt | Run's `(tenant_id, decision_id)` locates the agronomic decision; receipt's `(tenant_id, run_id)` locates the run. This is trace metadata only, not authorization validation. | Platform v235 |

`correlation_id` is a server-generated random UUID on a new root. Application request
headers, content digests and user-provided IDs never determine it. Existing SQL writers
omit the new field, and a BEFORE INSERT trigger allocates it. A caller trying to supply
its own root correlation is rejected. Child BEFORE INSERT triggers copy the stored
parent value; they never mint a replacement. A supplied conflicting child value fails.
The triggers are SECURITY INVOKER with a fixed search path, and explicit tenant predicates
retain caller RLS. Decision-service child rows require a visible parent. Platform v68/v178
previously allowed decision-parent orphans: these retain NULL when no correlation was
supplied, preserving the old write contract without inventing ancestry. A caller-supplied
non-NULL correlation with a missing/invisible platform parent is rejected. The existing
receipt-to-run foreign key remains authoritative; tracing does not relax it.

The immutable metadata triggers reject a changed correlation, tenant, row identity or
parent reference. An existing row with NULL remains NULL, including newly added children
of a genuinely legacy NULL root. There is no history rewrite or fabricated backfill.
Existing content/evidence/receipt digests are unchanged. Idempotent inserts retain the
winning stored root; state updates that do not change identity remain possible.

Trace queries use `(tenant_id, correlation_id)` indexes. Correlation is not an authorization
credential and is not globally unique across unrelated roots by an asserted database
constraint. Read-only consumers must still supply the authenticated tenant scope.

## Authority and rollout limits

The UUID is scoped to the authoritative owning database. While an interim bridge mirrors
rows into a **different** database, independent roots may carry different UUIDs. The mirror
is not a second authoritative trace. A later ownership cutover must copy and validate the
existing authoritative correlation column with its records; it must not re-insert roots
through allocation triggers and claim identity continuity. Ownership remains unchanged.

Migration v235 is registered before final RLS hardening. Service migration 036 belongs to
its existing owner runner; it is not injected into the platform manifest. Apply the owning
schema before accepting the new trace contract. No migration is applied at startup, no
physical-effect gate is opened and no command/actuator behavior is enabled by this change.

The native PG16 witness uses the complete service migration runner and actual persistence
functions under a separate nonprivileged LOGIN role. A second PostgreSQL-WASM witness
exercises both streams on a minimal relational projection, explicitly not the complete
platform/PostGIS schema or a native/live acceptance claim. Operational application and
an authenticated trace read in each target deployment remain separate acceptance steps.
