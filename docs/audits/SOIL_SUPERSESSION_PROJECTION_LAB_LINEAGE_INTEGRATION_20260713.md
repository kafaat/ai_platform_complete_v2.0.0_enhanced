# Soil Canonical Chain Consolidation — Integration Note (2026-07-13)

Consolidates three stacked delivered bundles onto the landed shape (`ce7f8bf`) as one
certified increment: **projection + reconciliation (v157/v158)**, **supersession + explicit
current pointer (v159)**, and **lab-result publication lineage (v160)**. All three were based
on `279651d` and delivered with their PostgreSQL proofs SKIPPED (no live DB in the delivery
environment). This session executed the full runtime certification on real PostgreSQL 16 +
PostGIS and fixed the defects that only surface against a live database.

## Canonical design adopted (bundle-authoritative)

- `soil_observation_supersessions` (append-only correction relation, one replacement per
  superseded observation, FORCE RLS) and `soil_profile_current` (explicit one-row-per-field
  current-projection pointer, FORCE RLS) — replacing an inferred "latest effective_at" model.
- `SoilObservation` gains `supersedes_observation_id` + `supersession_reason`; the composer
  excludes superseded rows and adds `received_at` as the final selection tie-break, so a
  same-day lab correction deterministically wins.
- `rebuild_snapshot_locked` updates the current pointer transactionally under the per-field
  advisory lock; `get_current_snapshot` and cutover readiness read through the pointer.
- Durable projection queue (`soil_profile_projection_jobs`) + reconciliation checkpoints
  (`soil_reconciliation_checkpoints`) with an in-process worker (`SOIL_PROJECTION_WORKER_ENABLED`).
- Platform soil moisture now sourced from `soil_observations` (not `device_telemetry`).
- v160: immutable `soil_lab_results` gain `published_observation_id`/`published_at` and
  correction inputs; the platform publish bridge sends property-specific
  `supersedes_observation_ids` to soil-service, mapped into the canonical supersession chain.

## Real-PostgreSQL certification (this session)

Fresh `sahool_cert` DB, full 166-step migration manifest applied cleanly (0 errors). The
`pytest -m integration` soil certification passes: v155–v160 schema + FORCE RLS on the new
tables, NOBYPASSRLS tenant isolation, 16-way concurrent-insert idempotency, 12-way concurrent
rebuild convergence to one hash + one persisted snapshot + one current pointer, and an
end-to-end supersession correction that flips the current pointer without advancing
`effective_at`.

## Delivered defects fixed (SKIPPED-proof gaps)

1. `rebuild_snapshot_locked` / `get_current_snapshot` / `get_snapshot_history` called
   `dict(persisted)` on a JSONB value that asyncpg returns as `str` (no codec registered) —
   `ValueError: dictionary update sequence element #0 has length 1`. Normalised with
   `json.loads(...) if isinstance(..., str)`.
2. The certification fixture teardown deleted `soil_profile_snapshots` before
   `soil_profile_current` (FK violation) and ignored the new supersession/projection tables —
   fixed to an FK-safe deletion order.
3. `run_migrations.sql` was not regenerated for v157/v158/v159 (registered in `MANIFEST.txt`
   only) — the migration-runners-in-sync guard would fail. Added steps 163–166.
4. The lab-lineage guard step and v160 were added to `.github/workflows/ci.yml` with a
   dangling command under a single-line `run:` (invalid YAML) — rewritten as a proper step.

## Platform ratchets (deliberate, documented)

- `db_ownership.yml`: registered the 10 canonical soil/lab tables (soil-service owns the
  canonical evidence/projection tables; sahool-platform owns lab-intake tables).
- Module baseline: `api/lab_store.py` + `api/soil_evidence_bridge.py` tracked (611→612).
- Route budgets: `POST /api/v1/lab/samples/{sample_id}/transition` owned; baseline 595→596,
  p2_6 592→593 (durable lab chain-of-custody transition + publication).
- Structure Inspector false positive on `soil_protocol_endpoint` closed by hoisting the router's
  mid-file `# noqa: E402` imports to module top (the regex bled `tenant_connection` into the
  pure calculator's body). Behaviour-preserving.
