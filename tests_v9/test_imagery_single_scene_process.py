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
