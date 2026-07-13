from datetime import UTC, datetime, timedelta

from profile_composer import compose_snapshot

from shared.contracts.soil import SoilObservation


def _row(
    observation_id: str,
    value: float,
    *,
    observed_at: datetime,
    received_at: datetime,
    is_superseded: bool = False,
):
    return {
        "observation_id": observation_id,
        "tenant_id": "11111111-1111-1111-1111-111111111111",
        "field_id": "fld-1",
        "property": "ph",
        "value_json": value,
        "unit": "pH",
        "depth_from_cm": 0,
        "depth_to_cm": 30,
        "observed_at": observed_at,
        "received_at": received_at,
        "source_type": "laboratory",
        "source_id": "lab-1",
        "quality_status": "accepted",
        "confidence": 1.0,
        "is_superseded": is_superseded,
    }


def test_superseded_observation_is_never_projected():
    t = datetime(2026, 7, 1, tzinfo=UTC)
    snapshot = compose_snapshot(
        tenant_id="11111111-1111-1111-1111-111111111111",
        field_id="fld-1",
        observations=[
            _row("old", 7.8, observed_at=t, received_at=t + timedelta(days=1), is_superseded=True),
            _row("new", 6.9, observed_at=t, received_at=t + timedelta(days=2)),
        ],
    )
    assert snapshot.layers[0].properties["ph"].value == 6.9
    assert snapshot.evidence_ids == ["new"]


def test_equal_observation_time_prefers_latest_received_correction():
    t = datetime(2026, 7, 1, tzinfo=UTC)
    snapshot = compose_snapshot(
        tenant_id="11111111-1111-1111-1111-111111111111",
        field_id="fld-1",
        observations=[
            _row("early", 7.3, observed_at=t, received_at=t + timedelta(hours=1)),
            _row("late", 7.0, observed_at=t, received_at=t + timedelta(hours=2)),
        ],
    )
    assert snapshot.layers[0].properties["ph"].value == 7.0
    assert snapshot.evidence_ids == ["late"]


def test_observation_contract_rejects_self_supersession():
    t = datetime(2026, 7, 1, tzinfo=UTC)
    try:
        SoilObservation(
            observation_id="sob-1",
            tenant_id="11111111-1111-1111-1111-111111111111",
            field_id="fld-1",
            property="ph",
            value=7.0,
            observed_at=t,
            received_at=t,
            source_type="laboratory",
            idempotency_key="k1",
            supersedes_observation_id="sob-1",
        )
    except ValueError as exc:
        assert "cannot_supersede_itself" in str(exc)
    else:
        raise AssertionError("self supersession must be rejected")


def test_store_uses_explicit_current_pointer_and_filters_superseded_sensor_rows():
    from pathlib import Path

    text = Path(__file__).with_name("soil_store.py").read_text()
    assert "FROM soil_profile_current c" in text
    assert 'or row.get("is_superseded")' in text
