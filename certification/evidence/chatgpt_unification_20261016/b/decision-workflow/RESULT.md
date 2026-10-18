# Decision-service irrigation completion

Isolated worktree: `/workspace/scratch/881ca3efb91d/irrigation-completion` (base HEAD `ee9ea1b9dcfa8045d11eccdb948e466cffa997da`). No stage or commit.

Files changed:
- services/decision-service/main.py
- services/decision-service/persistence.py
- services/decision-service/tests/test_wx10_8_review_queue.py
- services/decision-service/tests/test_manual_irrigation_source_binding.py (new)

Review queue default stays pending-only. Supplying both field_id and season_id opts into tenant/field/season-scoped irrigation pending+approved rows. Results include review and execution_plan only from persisted matching tenant, decision, lineage and approved digest. Review object contains standard authoritative-review fields plus new_state and approved_decision_value_digest aliases. Execution plan uses existing plan_state, plan_digest and decision_value_digest fields. Approved rows with stale/absent approval remain visible but have no usable review/plan.

New immutable manual-irrigation-source/v1 binds every submitted constraint to approved source and requires explicit net/gross/efficiency/area/volume relationships; net 10 mm at Ea .8 correctly permits gross 12.5 mm. The full required source keys must be copied to constraints including window strings. The plan constraints may omit full specification/water snapshot objects, but the approved decision source must contain both complete objects and valid recomputed hashes. Outer planned_start/end must match the approved window, and new plans after its expiry are rejected (the existing exact-idempotency replay path remains unchanged). Invalid numbers, booleans, unknown source versions, incomplete sources, digest syntax and scope mismatches fail closed. Old decisions without any manual_execution_source retain original ±10% net-depth legacy contract; an invalid present source cannot fall back. No migrations or dispatch changed.

Evidence:
- decision-binding-main-red.log: actual pinned main@239c01a47442df13d9cbb492017afae103b98dc8 persistence module: 60 FAILED / 8 PASSED, pytest exit 1.
- decision-binding-green.log: new source tests + queue tests: 75 PASSED; 19 existing native PostgreSQL tests SKIPPED because DATABASE_URL absent.
- Ruff format/check and git diff --check pass for all four files.
- result.json: 19 checks passed against PGlite PostgreSQL 18.6 with unmodified migrations 001/002/003/026/035 and pgcrypto. Exact actual function query captured in captured-queries.json. Includes tenant/field/season/type/stage filtering; foreign tenant/lineage and stale approval/plan exclusion; authoritative reload and default pending-only contract.
- This is embedded WASM PostgreSQL evidence, not native PostgreSQL, network, production, or physical execution acceptance.

## Reviewer follow-up
Scoped workflow only now wraps the SELECT in a real transaction and binds app.current_tenant transaction-locally before reading; original unscoped branch unchanged. Two transaction lifecycle tests cover success and rollback. JSONB decision_value strings are normalized to objects; malformed/non-object candidates are omitted failclosed. Source evidence now requires full specification and canonical-water objects, trusted tenant/field/season, user_declared equipment source identity/area/Ea, recorded applied water and operational eligibility, recomputed SHA256 evidence digests, observation timestamp and water validity cap.

PGlite evidence now also applies unchanged v194 and decision-service 033/034 RLS migrations; unrelated v194-required tables are minimal tenant_id fixtures. The exact recorded BEGIN/set_config/SELECT/COMMIT sequence succeeds under NOSUPERUSER NOBYPASSRLS role with FORCE RLS; absence/wrong tenant yields no rows and transaction-local identity is cleared at commit. Capturing tool: capture.py. Native PostgreSQL remains untested.
