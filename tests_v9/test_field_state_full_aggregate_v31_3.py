"""Guard: unified field-state aggregate endpoint composes REAL readers, honest absences.

`GET /api/v1/fields/{id}/state/full` is the single-source-of-truth read that screens
depend on instead of fanning out to many endpoints. Contract:
- tenant-scoped (FIELD_VIEW) with a hard 404 gate (_assert_field_in_tenant) and 503 on
  total DB failure;
- composes existing real readers (field/geometry, active season, canonical field_state,
  soil_lab_tests, water_ledger/irrigation_runs) — never fabricates;
- sources with no real per-field store (water lab samples, per-field economics) and the
  heavy live recommendations are declared available=false with a reason/endpoint pointer,
  not faked.
- must NOT be a duplicate of the existing /state route (distinct path).
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_FIELDS = (
    Path(__file__).resolve().parents[1]
    / "services"
    / "sahool-platform"
    / "api"
    / "routers"
    / "fields.py"
)


def _src() -> str:
    return _FIELDS.read_text(encoding="utf-8")


def test_aggregate_route_exists_and_is_distinct():
    src = _src()
    assert '@router.get("/api/v1/fields/{field_id}/state/full")' in src
    # the pre-existing canonical route stays single (no duplicate registration).
    assert src.count('@router.get("/api/v1/fields/{field_id}/state")') == 1


def test_aggregate_composes_real_readers_tenant_scoped():
    src = _src()
    block = src[src.index("/state/full") :]
    assert "await _assert_field_in_tenant(conn, field_id)" in block
    assert "recompute_field_state" in block
    assert "_field_season_context" in block
    assert "soil_lab_tests" in block
    assert "water_ledger" in block
    assert "irrigation_runs" in block
    assert "_row_to_field_detail" in block


def test_aggregate_declares_absent_sources_honestly():
    src = _src()
    block = src[src.index("/state/full") :]
    # no fabricated economics / water-lab-samples; declared available:false with pointer.
    assert '"water_samples"' in block
    assert '"economics"' in block
    assert '"recommendations"' in block
    assert '"available": False' in block
    assert "/api/v1/fields/{field_id}/recommendations" in block
