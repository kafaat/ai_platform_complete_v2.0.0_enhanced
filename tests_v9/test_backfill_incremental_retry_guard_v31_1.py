"""Guard: incremental backfill retries previously-failed items, not silently drops them.

The async scan worker inserts ``backfill_run_items`` with
``ON CONFLICT (tenant_id, idempotency_key) DO NOTHING``. A conflict means the
idempotency key already exists — which happens when a prior run enqueued the
same (field, scene, index) but it FAILED (429 / transient CDSE error). The old
code ``continue``d on the conflict, so a failed item could never be retried: it
just vanished and the run reported success dishonestly.

The fix: on conflict, decide honestly —
  * a ready ``raster_asset`` exists  → skip (already done),
  * no ready asset                   → re-attach the existing run_item to this
    run and reset it to ``queued`` (job_id/error/processed_at cleared) so it is
    re-pulled instead of disappearing.

CI unit (``testpaths = tests_v9``) does not collect the co-located behavioural
guard in ``services/raster-service/`` — this static guard keeps the contract.

Evidence: services/raster-service/backfill_scan_worker.py :: run_item enqueue loop
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_WORKER = (
    Path(__file__).resolve().parents[1] / "services" / "raster-service" / "backfill_scan_worker.py"
)


def _source() -> str:
    return _WORKER.read_text(encoding="utf-8")


def test_worker_exists():
    assert _WORKER.is_file(), f"missing {_WORKER}"


def test_conflict_reattaches_and_requeues_unready_items():
    src = _source()
    # The DO NOTHING insert stays (global dedup) ...
    assert "ON CONFLICT (tenant_id, idempotency_key) DO NOTHING" in src
    # ... but a conflict must recover the row and reset it to queued rather than
    # continue past it silently.
    assert "UPDATE backfill_run_items" in src
    assert "status='queued'" in src
    assert "job_id=NULL" in src
    assert "error=NULL" in src
    assert "processed_at=NULL" in src


def test_ready_asset_still_short_circuits_to_skip():
    src = _source()
    # Preflight readiness gate must remain strict so already-ready assets are not
    # reprocessed on retry.
    assert "asset_status = 'ready'" in src
    assert "items_skipped += 1" in src


def test_unrecoverable_conflict_counts_as_failed_not_success():
    src = _source()
    # A rare race where the row can neither be inserted nor recovered must not be
    # reported as a silent success.
    assert "items_failed += 1" in src
