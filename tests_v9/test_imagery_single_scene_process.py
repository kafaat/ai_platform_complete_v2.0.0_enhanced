"""Guard: single-scene «process this date» reuses the backfill model — no second state machine.

Owner decision (V8-05 PR1-a): selecting/browsing a date must NOT create any processing;
an explicit "process this date" action schedules ONE single_scene run (run_kind='single_scene')
with ONE pre-created run_item, reusing backfill_runs/backfill_run_items. No new processing_jobs
table, no parallel state machine. Idempotent: a ready asset ⇒ reused_existing_job with no run.

Static guard (no live DB): asserts the migration, the db_persist orchestrator, the worker
branch, the endpoint, and the request model are all present and wired. Prevents a regression
that forks a separate single-scene pipeline or drops the run_kind branch.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "migrations" / "v213_backfill_runs_single_scene.sql"
MANIFEST = ROOT / "migrations" / "MANIFEST.txt"
RUNNER = ROOT / "scripts_v9" / "run_migrations.sql"
DB_PERSIST = ROOT / "services" / "raster-service" / "db_persist.py"
WORKER = ROOT / "services" / "raster-service" / "backfill_scan_worker.py"
ROUTE = ROOT / "services" / "raster-service" / "routers" / "fields.py"
MODELS = ROOT / "services" / "raster-service" / "raster_api_models.py"


def test_migration_adds_run_kind_and_is_registered() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")
    assert "ADD COLUMN IF NOT EXISTS run_kind" in sql, "v213 must add run_kind column"
    assert "run_kind IN ('backfill', 'single_scene')" in sql, "run_kind CHECK must constrain values"
    # Idempotent (compose runner re-applies every migration under ON_ERROR_STOP).
    assert "DROP CONSTRAINT IF EXISTS chk_backfill_runs_run_kind" in sql, "CHECK must be idempotent"
    # Registered in BOTH runners.
    assert "v213_backfill_runs_single_scene.sql" in MANIFEST.read_text(encoding="utf-8")
    assert "v213_backfill_runs_single_scene.sql" in RUNNER.read_text(encoding="utf-8")


def test_db_persist_has_single_scene_orchestrator() -> None:
    src = DB_PERSIST.read_text(encoding="utf-8")
    assert "async def enqueue_single_scene_process(" in src, "orchestrator function must exist"
    # insert_backfill_run threads run_kind (so backfill path and single_scene share one writer).
    assert 'run_kind: str = "backfill"' in src, "insert_backfill_run must accept run_kind"
    # Honest reuse contract keys.
    for token in ('"already_ready"', '"reused_existing_job"', "run_kind, status"):
        assert token in src, f"orchestrator must express {token}"
    # Idempotency preflight against a ready asset (no duplicate processing).
    assert "asset_status='ready'" in src, "orchestrator must preflight ready assets"


def test_worker_branches_on_run_kind() -> None:
    src = WORKER.read_text(encoding="utf-8")
    # The claim query must surface run_kind so the branch can fire.
    assert "COALESCE(run_kind, 'backfill') AS run_kind" in src, "worker must select run_kind"
    assert 'run.get("run_kind") or "backfill") == "single_scene"' in src, "worker must branch"
    assert "async def _process_single_scene_run(" in src, "single-scene worker path must exist"
    # Single-scene resolves a KNOWN scene for one day — not a monthly discovery scan.
    assert "queued فقط" in src or "status='queued'" in src, (
        "single-scene processes pre-created items"
    )


def test_route_and_model_present() -> None:
    src = ROUTE.read_text(encoding="utf-8")
    assert '"/v1/fields/{field_id}/imagery/process-date"' in src, "process-date endpoint must exist"
    assert "enqueue_single_scene_process(" in src, "endpoint must call the orchestrator"
    for key in ('"run_id"', '"item_id"', '"reused_existing_job"'):
        assert key in src, f"process-date response must carry {key}"
    models = MODELS.read_text(encoding="utf-8")
    assert "class ProcessDateRequest(" in models, "ProcessDateRequest model must exist"


# ─────────────── review hardening (P0-1 / P1-1 / P1-2 / P2-1) ───────────────


def test_p0_tenant_is_authenticated_context_not_body() -> None:
    """P0-1: the body's tenant_id must NEVER override the authenticated context tenant.

    Field ownership is checked against the request-context tenant; the enqueue must use the
    SAME tenant. A body tenant_id that differs fails closed (403), never creates a run/item
    under a different tenant. Guards against the `req.tenant_id or _REQ_TENANT.get()` footgun.
    """
    src = ROUTE.read_text(encoding="utf-8")
    # The dangerous "body-or-context" override must be gone from EVERY raster field route
    # (process-date, historical-backfill async+sync fallback, geoparquet export) — not just
    # process-date. A body tenant_id must never override the authenticated context tenant.
    assert "req.tenant_id or _REQ_TENANT.get()" not in src, (
        "no raster field route may let the body tenant_id override the authenticated context"
    )
    # A single fail-closed helper derives the tenant from context and rejects a mismatched body.
    assert "def _authenticated_tenant(" in src, "the authenticated-tenant helper must exist"
    assert "context_tenant = _REQ_TENANT.get()" in src, "helper derives tenant from request context"
    assert "str(body_tenant) != str(context_tenant)" in src, "helper rejects body/context mismatch"
    assert "403" in src, "a mismatched body tenant must be rejected with 403"
    # The process-date handler routes its tenant through the helper.
    assert "tenant = _authenticated_tenant(req.tenant_id)" in src


def test_p1_ready_asset_preflight_matches_scene_id() -> None:
    """P1-1: the enqueue ready-asset preflight must match scene_id (canonical-identity field).

    Otherwise a ready asset for a DIFFERENT scene on the same day returns already_ready for the
    scene the user actually picked. The worker's own preflight already matches scene_id — the
    enqueue must be consistent.
    """
    src = DB_PERSIST.read_text(encoding="utf-8")
    # Locate the enqueue preflight query and assert scene_id is part of the ready-asset match.
    idx = src.index("async def enqueue_single_scene_process(")
    body = src[idx : idx + 4000]
    assert "asset_status='ready'" in body
    assert "AND scene_id=$5" in body, "ready-asset preflight must match scene_id"


def test_p1_race_deletes_orphan_single_scene_run() -> None:
    """P1-2: on a concurrent ON CONFLICT loss, the just-created single_scene run must be deleted.

    Without this, the losing request commits a `planned` run with zero items (orphan) — misleading
    counters and a run the worker could claim with nothing to do.
    """
    src = DB_PERSIST.read_text(encoding="utf-8")
    assert "DELETE FROM backfill_runs WHERE id=$1 AND run_kind='single_scene'" in src, (
        "the race branch must delete the orphaned run before returning the winner's item"
    )
    assert "NOT EXISTS (SELECT 1 FROM backfill_run_items WHERE run_id=$1)" in src


def test_p2_jobs_scheduled_counts_ran_jobs() -> None:
    """P2-1: jobs_scheduled must count jobs that actually ran (persisted + failed), not only
    persisted — otherwise a job that ran and failed reports jobs_scheduled=0."""
    src = WORKER.read_text(encoding="utf-8")
    assert "jobs_scheduled = items_persisted + items_failed" in src, (
        "single-scene jobs_scheduled must include failed jobs that were actually scheduled"
    )
