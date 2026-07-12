# SAHOOL Agronomic Lineage Integrity — Continuation

Date: 2026-07-12
Base: `sahool_de0c61d_agronomic_lineage_closed.zip`

## Closed in this increment

- Added migration `020_agronomic_lineage_integrity.sql`.
- Replaced snapshot foreign keys with tenant-scoped composite foreign keys.
- Added semantic field/season validation for agronomic, vegetation, and field-history snapshots.
- Enabled tenant RLS on `decision_record` and bound `app.current_tenant` before authoritative writes.
- Made evidence snapshot creation truly idempotent by returning the canonical existing snapshot ID on hash replay.
- Added feature-manifest hash validation.
- Added a real PostgreSQL certification test covering migration presence, snapshot-to-decision writes, semantic mismatch rejection, and tenant isolation.
- Added a fail-closed certification runner: `scripts/certification/certify_agronomic_lineage.py`.
- Added `agronomic_lineage_integrity_gate.py` and wired it into CI.
- Fixed the AgriAI test import path so the complete focused suite can run from repository root.
- Repaired and validated the Vegetation/AgriAI GitHub Actions workflow YAML.

## Validation performed

- Python compileall: PASS
- Vegetation/AgriAI production gate: PASS
- Vegetation/AgriAI full closure gate: PASS
- Agronomic decision lineage gate: PASS
- Agronomic lineage integrity gate: PASS
- Workflow YAML parse: PASS
- Focused complete suite: 53 passed, 1 skipped

The skipped test is the real PostgreSQL proof because this environment has no `DATABASE_URL`, PostgreSQL client, or Docker runtime. The repository now contains the exact fail-closed command to execute that proof in staging:

```bash
DATABASE_URL=postgresql://... python scripts/certification/certify_agronomic_lineage.py
```

## Honest remaining external evidence

- Apply migrations 018–020 on a real PostgreSQL staging instance.
- Execute the certification runner and retain its output as release evidence.
- Validate existing historical rows before validating the `NOT VALID` foreign keys.
- Run real Sentinel COG, soil, irrigation, weather, crop-card, and measured-outcome scenarios for scientific certification.

---

## Integration note (landed shape) — appended by the integrating session

The delivered 019+020 migrations referenced the bundle's never-landed 018 tables
(`decision_agronomic_context_snapshots` in the bundle's weaker shape,
`decision_field_history_snapshots`). Both were reconciled into ONE landed migration,
`services/decision-service/migrations/019_agronomic_lineage_integrity.sql`, targeting the
landed AC-1 contracts instead:

1. `decision_vegetation_snapshots` + its writer `POST /v1/evidence/vegetation-snapshots`
   land as delivered (this CLOSES the previously-open gap VEG-EVIDENCE-STORE — the store
   now arrives together with its writer, typed validation and append-only enforcement).
2. The bundle's push-writers for context (`/v1/evidence/agronomic-context-snapshots`) and
   field history (`/v1/evidence/field-history-snapshots`) were NOT landed: the landed AC-1
   composer (`POST /v1/context-snapshots`) already owns those two contracts with strictly
   stronger semantics (point-in-time validation before any write, feature manifests,
   idempotency + replay). Landing a second, weaker write path for the same evidence would
   split the source of truth.
3. `field_history_snapshot_id` maps to the landed `field_historical_context_snapshot_id`
   column; the tenant-composite FK references
   `decision_field_historical_context_snapshots (tenant_id, historical_snapshot_id)`.
4. The semantic trigger keeps the delivered mismatch messages, with one calibrated policy:
   a season mismatch requires BOTH sides to declare a season (legacy decisions without
   season_id keep recording; a declared season must match the bound evidence), and it
   additionally verifies the claimed `feature_manifest_hash` against the stored manifest
   content hash ("feature manifest hash mismatch").
5. Persistence maps DB-trigger/constraint violations to a typed fail-closed rejection
   (`lineage_integrity_violation:...`) instead of surfacing a 500; typed pre-validation
   covers the same conditions first (`context_season_mismatch`,
   `unknown_vegetation_snapshot`, `feature_manifest_hash_mismatch`, ...).
6. RLS honesty: the service currently connects as the table owner and owners bypass
   non-FORCE RLS — the policies become enforcing once a dedicated non-owner runtime role
   is provisioned (recorded within the operator SoR-cutover work). Persistence already
   binds `app.current_tenant` on every authoritative write.
7. Strict mode (`DECISION_REQUIRE_AGRONOMIC_CONTEXT`) now demands the full lineage
   (identity + context triple + vegetation evidence + manifest hash) and is checked
   before the SoR branch, in the delivered `agronomic_context_required` detail contract.
