"""W1-04 unit layer: a snapshot rebuild hands its hydraulic profile to the store.

Stubbed at the store-function level (``p1_store.project_hydraulic_in_transaction``); the SQL is
measured on live PostgreSQL in ``tests_v9/test_soil_hydraulic_projection_live_pg.py``.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import p1_store
import pytest
import soil_store
from profile_composer import compose_snapshot

pytestmark = pytest.mark.unit

_TENANT = "11111111-1111-1111-1111-111111111111"


def _row(prop: str, value: float):
    t = datetime(2026, 7, 1, tzinfo=UTC)
    return {
        "observation_id": f"obs-{prop}",
        "tenant_id": _TENANT,
        "field_id": "fld-1",
        "property": prop,
        "value_json": value,
        "unit": "m3/m3",
        "depth_from_cm": 0,
        "depth_to_cm": 30,
        "observed_at": t,
        "received_at": t,
        "source_type": "laboratory",
        "source_id": "lab-1",
        "quality_status": "accepted",
        "confidence": 1.0,
        "is_superseded": False,
    }


def _capture(monkeypatch):
    seen = []

    async def _project(conn, profile):
        seen.append((conn, profile))
        return True

    monkeypatch.setattr(p1_store, "project_hydraulic_in_transaction", _project)
    return seen


def test_snapshot_with_layers_projects_a_profile_keyed_by_its_hash(monkeypatch):
    seen = _capture(monkeypatch)
    snapshot = compose_snapshot(
        tenant_id=_TENANT,
        field_id="fld-1",
        observations=[_row("field_capacity", 0.31), _row("wilting_point", 0.12)],
    )
    assert snapshot.layers, "fixture must compose at least one layer"
    conn = object()
    asyncio.run(soil_store._project_hydraulic_profile(conn, snapshot))
    assert len(seen) == 1, f"expected one projection, got {len(seen)}"
    got_conn, profile = seen[0]
    assert got_conn is conn, "projection must use the snapshot's own transaction connection"
    assert profile.source_soil_profile_hash == snapshot.profile_hash, (
        "hydraulic profile must be keyed by the snapshot's profile_hash"
    )
    assert profile.tenant_id == _TENANT and profile.field_id == "fld-1", (
        f"profile identity: {profile.tenant_id}/{profile.field_id}"
    )
    assert profile.executable, f"measured FC and WP must execute: {profile.reasons}"


def test_snapshot_without_layers_projects_nothing(monkeypatch):
    """The contract requires a layer: no profile, rather than a crash that would also block the
    snapshot rebuild (the builder raises on an empty layer list)."""
    seen = _capture(monkeypatch)
    composed = compose_snapshot(
        tenant_id=_TENANT, field_id="fld-1", observations=[_row("field_capacity", 0.31)]
    )
    snapshot = composed.model_copy(update={"layers": []})
    assert not snapshot.layers, "fixture must compose an empty snapshot"
    asyncio.run(soil_store._project_hydraulic_profile(object(), snapshot))
    assert seen == [], f"an empty snapshot projected a profile: {seen}"


def test_failed_quality_gate_projects_a_non_executable_profile_with_its_reasons(monkeypatch):
    """Negative control: uncalibrated FC/WP readings exist as values but fail the snapshot's
    canonical quality gate. The projection must not expose them as executable hydraulics."""
    seen = _capture(monkeypatch)
    rows = [
        dict(_row(prop, value), source_type="sensor", quality_status="uncalibrated")
        for prop, value in (("field_capacity", 0.31), ("wilting_point", 0.12))
    ]
    snapshot = compose_snapshot(tenant_id=_TENANT, field_id="fld-1", observations=rows)
    assert snapshot.layers, "fixture must compose at least one layer"
    assert not snapshot.quality_gate.passed, f"fixture gate must fail: {snapshot.quality_gate}"
    asyncio.run(soil_store._project_hydraulic_profile(object(), snapshot))
    assert len(seen) == 1, f"expected one projection, got {len(seen)}"
    profile = seen[0][1]
    assert profile.layers[0].field_capacity is not None, "fixture must carry FC values"
    assert not profile.executable, f"failed gate projected as executable: {profile.reasons}"
    assert "soil_profile_quality_gate_failed" in profile.reasons, profile.reasons
    for reason in snapshot.quality_gate.reasons:
        assert reason in profile.reasons, f"gate reason {reason!r} lost: {profile.reasons}"
