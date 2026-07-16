# FII Safety Automated Stage Report — 2026-07-16

## Completed in this package

1. RLS fail-closed hardening retained for `scouting_pins` and `prescriptions`.
2. Chemical Lineage audit foundation:
   - `FII_CHEMICAL_LINEAGE_MODE=off|audit|enforce`
   - default/invalid configuration resolves to `audit`
   - additive request fields: `season_id`, `diagnosis_ref`, `evidence_ref`
   - audit violations are logged and returned in workflow context
   - enforcement path exists but was not certified or enabled automatically
3. Prescription Season Context expansion:
   - migration `v193_prescriptions_season_context_expand.sql`
   - nullable `season_id`, explicit resolution state, no guessed backfill, no `NOT NULL`
   - API supports `FII_PRESCRIPTION_SEASON_MODE=audit|enforce`
   - legacy-compatible audit is default; enforce rejects missing season
4. Score semantics correction:
   - additive `score`, `score_semantics=rule_match`, `is_calibrated=false`, `producer_type=rule_engine`
   - deprecated `confidence` retained for compatibility
   - Arabic response now says symptom-match score, not calibrated diagnostic confidence

## Validation

- Targeted suite: 38 passed, 1 skipped.
- FII RLS static gate: passed.
- Migration static validation: passed, including v192 and v193.
- Live PostgreSQL RLS test remains skipped because no live test database URL was available.

## Deliberately not completed

- Chemical Lineage was not switched to `enforce`; audit observations are required first.
- `season_id` was not made `NOT NULL`; unresolved historical data has not been certified.
- No Workspace, BFF, general FieldObservation SoR, ML, registry, event-driven FII, or learning work was added.

## Required next operational step

Run the live PostgreSQL matrix and staging probes with actual `sahool_schema_owner`, `sahool_migrator`, and `sahool_app` roles. Then collect Chemical Lineage audit metrics before any enforce decision.
