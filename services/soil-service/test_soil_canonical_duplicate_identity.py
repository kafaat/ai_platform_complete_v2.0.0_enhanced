"""Canonical duplicate identity — review R01 F3.

**Fault:** ``POST /v1/soil/observations`` with an idempotency key that already exists
answered ``status: duplicate`` with the freshly generated ``observation_id`` of a row that
was never written, and a *different* reading under the same key was dropped silently
(``ON CONFLICT DO NOTHING``). Now the stored row is selected by tenant + key: the same
reading answers with the stored id; a different one is a 409.

The comparison is a pure helper (``soil_store.stored_observation_matches``) shared with the
wide-ingest retry path; route tests replace store functions, not connections.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
for path in (HERE, ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

pytestmark = pytest.mark.unit

_TENANT = "11111111-1111-1111-1111-111111111111"
_HEADERS = {"X-Tenant-Id": _TENANT, "X-Agent-Token": "review-agent-token"}
_OBSERVED = datetime(2026, 11, 8, 8, tzinfo=UTC)


def _body(**over):
    body = {
        "tenant_id": _TENANT,
        "field_id": "review-field",
        "property": "soil_moisture",
        "value": 23.5,
        "unit": "vwc_pct",
        "depth_from_cm": 0,
        "depth_to_cm": 15,
        "observed_at": _OBSERVED.isoformat(),
        "source_type": "sensor",
        "source_id": "dev_1",
        "idempotency_key": "dev_key_1",
    }
    body.update(over)
    return body


def _stored_row(**over):
    """A row as asyncpg returns it: JSON text value, NUMERIC depths, aware timestamp."""
    row = {
        "observation_id": "sob_stored",
        "idempotency_key": "dev_key_1",
        "field_id": "review-field",
        "property": "soil_moisture",
        "value_json": "23.5",
        "unit": "vwc_pct",
        "depth_from_cm": Decimal("0.00"),
        "depth_to_cm": Decimal("15.00"),
        "observed_at": _OBSERVED,
        "source_type": "sensor",
        "source_id": "dev_1",
    }
    row.update(over)
    return row


# ─── the pure comparison ──────────────────────────────────────────────────


def _observation(**over):
    from shared.contracts.soil import SoilObservation

    return SoilObservation.model_validate({**_body(**over), "received_at": _OBSERVED})


def test_the_same_reading_matches_its_stored_row():
    import soil_store

    assert soil_store.stored_observation_matches(_stored_row(), _observation())
    # Same instant in another offset is the same reading.
    other_offset = _OBSERVED.astimezone(timezone(timedelta(hours=3)))
    assert soil_store.stored_observation_matches(
        _stored_row(observed_at=other_offset), _observation()
    )


@pytest.mark.parametrize(
    "row_change",
    [
        {"value_json": "31.0"},
        {"unit": "%"},
        {"depth_from_cm": Decimal("15.00"), "depth_to_cm": Decimal("30.00")},
        {"observed_at": _OBSERVED + timedelta(seconds=1)},
        {"field_id": "another-field"},
        {"source_id": "dev_2"},
    ],
)
def test_a_different_reading_under_the_same_key_does_not_match(row_change):
    import soil_store

    assert not soil_store.stored_observation_matches(_stored_row(**row_change), _observation())


def test_observed_at_can_be_excluded_for_the_wide_ingest_retry_path():
    import soil_store

    row = _stored_row(observed_at=_OBSERVED + timedelta(hours=1))
    assert soil_store.stored_observation_matches(row, _observation(), check_observed_at=False)


# ─── the route ────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def loaded_main():
    os.environ["SAHOOL_AGENT_TOKEN"] = "review-agent-token"
    for name in [m for m in sys.modules if m == "routers" or m.startswith("routers.")]:
        del sys.modules[name]
    spec = importlib.util.spec_from_file_location("main", HERE / "main.py")
    main = importlib.util.module_from_spec(spec)
    sys.modules["main"] = main
    assert spec.loader is not None
    spec.loader.exec_module(main)
    return main


@pytest.fixture
def service(monkeypatch, loaded_main):
    import soil_store

    main = loaded_main
    state: dict = {"inserted": False, "stored": _stored_row(), "lookups": []}

    async def _persist(pool, observation):
        return state["inserted"]

    async def _load(pool, tenant_id, key):
        state["lookups"].append((tenant_id, key))
        return state["stored"]

    class _Snapshot:
        profile_id = "prof_stub"
        profile_hash = "hash_stub"

    async def _rebuild(pool, *, tenant_id, field_id):
        return _Snapshot()

    async def _field_ok(field_id):
        return None

    monkeypatch.setattr(main, "_require_field_tenant", _field_ok)
    monkeypatch.setattr(main, "_pool", object())
    monkeypatch.setattr(soil_store, "persist_observation", _persist)
    monkeypatch.setattr(soil_store, "load_observation_by_key", _load)
    monkeypatch.setattr(soil_store, "rebuild_snapshot_locked", _rebuild)
    return TestClient(main.app, headers=_HEADERS), state


def test_a_new_observation_returns_its_own_id_without_a_lookup(service):
    client, state = service
    state["inserted"] = True
    response = client.post("/v1/soil/observations", json=_body(observation_id="sob_new"))
    assert response.status_code == 201, response.text
    assert response.json()["status"] == "created"
    assert response.json()["observation_id"] == "sob_new"
    assert state["lookups"] == []


def test_a_duplicate_returns_the_stored_id_not_a_fresh_one(service):
    client, state = service
    response = client.post("/v1/soil/observations", json=_body(observation_id="sob_never_written"))
    assert response.status_code == 201, response.text
    assert response.json()["status"] == "duplicate"
    assert response.json()["observation_id"] == "sob_stored"
    assert state["lookups"] == [(_TENANT, "dev_key_1")]


def test_a_conflicting_value_under_the_same_key_is_409_not_a_silent_drop(service):
    client, _state = service
    response = client.post("/v1/soil/observations", json=_body(value=31.0))
    assert response.status_code == 409, response.text


def test_a_conflict_whose_stored_row_is_not_visible_fails_closed(service):
    client, state = service
    state["stored"] = None
    response = client.post("/v1/soil/observations", json=_body())
    assert response.status_code == 409, response.text


def test_a_keyed_retry_of_a_server_timed_reading_is_a_duplicate_not_a_conflict(service):
    """The platform marks a server-assigned instant; a retry carries a later arrival time."""
    client, _state = service
    later = (_OBSERVED + timedelta(seconds=9)).isoformat()
    marked = _body(observed_at=later, provenance={"observed_at_source": "server_receipt"})
    response = client.post("/v1/soil/observations", json=marked)
    assert response.status_code == 201, response.text
    assert response.json()["observation_id"] == "sob_stored"
    # Control: the same time difference on a device-declared instant is a conflict.
    assert client.post("/v1/soil/observations", json=_body(observed_at=later)).status_code == 409


# ─── the evidence batch (platform lab publication) ────────────────────────


def _lab_row(**over):
    row = {
        "observation_id": "sob_lab_ph",
        "idempotency_key": "laboratory:sample-a:ph:0.0:30.0",
        "property": "ph",
        "value_json": "7.1",
        "unit": "pH",
        "depth_to_cm": Decimal("30.00"),
        "source_type": "laboratory",
        "source_id": "sample-a",
    }
    return _stored_row(**{**row, **over})


def _lab_batch(**over):
    batch = {
        "source_type": "laboratory",
        "source_id": "sample-a",
        "properties": {"ph": 7.1},
        "observed_at_by_property": {"ph": _OBSERVED.isoformat()},
        "depth_from_cm": 0,
        "depth_to_cm": 30,
        "approved": True,
    }
    batch.update(over)
    return batch


def test_a_retried_lab_batch_returns_the_stored_observation_ids(service):
    # A publish retry (e.g. after the platform transaction rolled back) must hand back the
    # id the soil owner already stored, so published_observation_id names a real row.
    client, state = service
    state["stored"] = _lab_row()
    response = client.post("/v1/fields/review-field/soil/evidence", json=_lab_batch())
    assert response.status_code == 201, response.text
    assert response.json()["observation_ids"] == ["sob_lab_ph"]
    assert response.json()["duplicates"] == 1
    assert state["lookups"] == [(_TENANT, "laboratory:sample-a:ph:0.0:30.0")]


def test_a_different_lab_value_under_the_same_batch_key_is_409(service):
    client, state = service
    state["stored"] = _lab_row(value_json="6.0")
    response = client.post("/v1/fields/review-field/soil/evidence", json=_lab_batch())
    assert response.status_code == 409, response.text


def test_a_lab_correction_gets_its_own_key_and_a_stable_retry_identity():
    import evidence_adapters

    from shared.contracts.soil import SoilObservationSource

    def build(prior=None):
        return evidence_adapters.observations_from_properties(
            tenant_id=_TENANT,
            field_id="review-field",
            source_type=SoilObservationSource.LABORATORY,
            source_id="sample-a",
            properties={"ec_dsm": 1.7},
            approved=True,
            supersedes_observation_ids={"ec": prior} if prior else None,
        )[0].idempotency_key

    original = build()
    correction = build("sob_old")
    assert correction != original
    assert build("sob_old") == correction
    assert build("sob_other") != correction


def test_a_legacy_lab_row_replays_although_its_observed_at_was_the_publish_instant(service):
    # Before the platform sent the lab's own measurement time it published observed_at=now()
    # and no observed_at_source. Republishing the same value under the same key is a replay.
    client, state = service
    state["stored"] = _lab_row(
        observed_at=_OBSERVED + timedelta(days=3),
        provenance={"sample_id": "sample-a", "units": {"ph": "1"}, "workflow_status": "published"},
    )
    response = client.post("/v1/fields/review-field/soil/evidence", json=_lab_batch())
    assert response.status_code == 201, response.text
    assert response.json()["observation_ids"] == ["sob_lab_ph"]


@pytest.mark.parametrize(
    "provenance",
    [
        {"sample_id": "sample-a", "workflow_status": "published", "observed_at_source": "x"},
        {"sample_id": "sample-a"},
        None,
    ],
)
def test_a_lab_row_with_its_measured_time_still_conflicts_on_another_time(service, provenance):
    client, state = service
    state["stored"] = _lab_row(observed_at=_OBSERVED + timedelta(days=3), provenance=provenance)
    response = client.post("/v1/fields/review-field/soil/evidence", json=_lab_batch())
    assert response.status_code == 409, response.text


def test_a_legacy_row_with_a_different_value_is_still_a_conflict(service):
    client, state = service
    state["stored"] = _lab_row(
        value_json="6.0",
        observed_at=_OBSERVED + timedelta(days=3),
        provenance={"sample_id": "sample-a", "workflow_status": "published"},
    )
    response = client.post("/v1/fields/review-field/soil/evidence", json=_lab_batch())
    assert response.status_code == 409, response.text


def test_an_invalid_supersession_target_is_409_not_500(service, monkeypatch):
    import soil_store

    client, _state = service

    async def _refuse(pool, observation):
        raise ValueError("soil_observation_supersession_target_invalid_or_already_replaced")

    monkeypatch.setattr(soil_store, "persist_observation", _refuse)
    body = _lab_batch(supersedes_observation_ids={"ph": "sob_gone"}, supersession_reason="fix")
    response = client.post("/v1/fields/review-field/soil/evidence", json=body)
    assert response.status_code == 409, response.text
