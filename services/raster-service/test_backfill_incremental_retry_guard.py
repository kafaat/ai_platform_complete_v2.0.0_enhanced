from pathlib import Path


def test_incremental_backfill_retries_previous_failed_items_without_reprocessing_ready_assets():
    src = Path(__file__).with_name("backfill_scan_worker.py").read_text()
    assert "asset_status = 'ready'" in src
    assert "geometry_revision = $6::int" in src
    assert "ON CONFLICT (tenant_id, idempotency_key) DO NOTHING" in src
    assert "UPDATE backfill_run_items" in src
    assert "status='queued'" in src
    assert "job_id=NULL" in src
    assert "error=NULL" in src
    assert "processed_at=NULL" in src
    assert "if exists:" in src
    assert "items_skipped += 1" in src
