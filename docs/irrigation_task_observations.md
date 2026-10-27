# Task irrigation observations

Candidate based on `main@5c7e1cb83d236dcf21f6d352faae2dc5d3fc1471`, verified against
the GitHub main branch on 2026-10-27. No deployment or live migration was performed.

## User flow

From a field task in the web Tasks page or mobile task details, open irrigation
observations, select an existing manual irrigation execution for the same field,
and record either a farmer report or a field inspection. These are self-reported
sources, not independent-verifier credentials. Record the actual observation
time, outcome, optional actual irrigated area and notes.

| Scenario | Recorded evidence | Water calculation |
|---|---|---|
| Meter available | Start/end readings in m³ | End minus start; regression rejected |
| No meter, estimated flow known | m³/hour, elapsed minutes, interruption minutes | Flow × net pumping hours; explicitly estimated |
| Farmer knows volume | Declared m³ | Retained as declared, not metered |
| Irrigation occurred, volume unknown | Outcome and optional area | Volume and depth remain null |
| No irrigation / outcome unknown | Outcome and notes | No quantity evidence accepted; null volume |
| Part of the field irrigated | Actual irrigated hectares | Depth = volume / hectares / 10 |
| Late entry | Original observation time | Separate server received_at; no historical ledger rewrite |
| Inspection of farmer's operation | Same execution, separate observation | No sum or second water entry |
| Lost response / offline replay | Original observation UUID and body | Same event returned; changed content rejected |

Saving an observation does **not** complete the task, start/stop a valve, change
the execution state, independently verify it, or update water accounting.
The existing manual-execution confirmation, independent verification and
reconciliation workflow remains the only path to that water ledger.

## API and persistence

- `POST /api/v1/observations` with `{task_id, irrigation_observation}`: permission
  `OBSERVATION_RECORD`, including workers; authenticated actor and tenant are
  authoritative. `observation_id` in the body is the durable retry identity.
- `GET /api/v1/tasks?irrigation_task_id=...`: `FIELD_VIEW`; returns the most recent
  200 observations in `irrigation_observations`, with an empty `tasks` list.
  Ordinary task listing and legacy observation requests retain their existing behavior.
- Existing routes are extended; the platform domain route budget remains 629/629.
  Invalid irrigation envelopes cannot fall back to the legacy observation contract.
- Existing append-only `irrigation_manual_execution_events` stores the record.
  `event_type=task.irrigation_observation.v1`; `from_state=to_state` preserves the
  lifecycle and does not impersonate a confirmation event.
- Explicit tenant predicates plus task/execution field matching precede insert.
  Existing composite tenant/execution FK and RLS remain in force.
- Duplicate IDs compare the original request digest, task, tenant and actor;
  lifecycle advancement does not invalidate a legitimate retry. The conflict
  read assumes READ COMMITTED, as the platform's default transactions do.
- No schema migration or database role changes are introduced.

Web retains an unresolved submitted payload in account-scoped browser session
storage and retries that original payload. Mobile persists to the existing
account-scoped encrypted outbox before sending. Local queuing is displayed as
pending, never as server confirmation. Browser session storage is not a backup
and does not provide mobile-style durable background synchronization.

## Deliberate limits and deployment checks

An existing governed manual execution is required. Unplanned standalone irrigation
without such an execution, creating farmer tasks, linking a separate scout form
submission, photographs, meter rollover/replacement reconciliation and automatic
promotion of observations into verified as-applied evidence are not introduced.
Do not invent a recommendation or bypass the approved-plan gate to create an
execution. Existing live schema/role availability must be checked before rollout.

Unit and HTTP tests exercise validation, explicit ownership checks, replay,
permissions and absence of ledger/task mutations. Their database connection is a
test double: they do not prove live PostgreSQL locking, RLS or crash recovery.
Live staging acceptance must cover concurrent same-ID commit/rollback, different
tenants/actors, late reports and an execution advancing between retries. Flutter
tests and analysis must run in the Flutter CI environment before release.

Merging this candidate changes platform and frontend source and may trigger their
deployment according to repository workflows. It is not a documentation-only PR.

## Local verification

- 97 Python tests passed: observation validation and HTTP boundaries, existing
  task endpoints, existing task-update idempotency, observation validation and
  offline-first regression tests. The HTTP smoke includes
  the real application's route registration with a substituted DB connection.
- 17 new frontend tests passed; TypeScript, scoped ESLint and production build
  passed. Build warnings in existing map code are not a browser acceptance test.
- Ruff and whitespace checks passed for the changed Python/source files.
- Seven mobile tests were added; Flutter execution and analysis are NOT_RUN.
- Real PostgreSQL, live services, device commands, browser E2E and full repository
  preflight are NOT_RUN. Generated-artifact sweep is tracked separately from tests.
