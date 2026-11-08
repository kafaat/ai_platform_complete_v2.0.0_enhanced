from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest
from profile_composer import compose_snapshot

from shared.contracts.soil import SoilObservation

TENANT = "11111111-1111-1111-1111-111111111111"
NOW = datetime.now(UTC)


def row(*, obs_id, prop, value, source, confidence=0.8, quality="accepted", observed_at=NOW):
    return {
        "observation_id": obs_id,
        "property": prop,
        "value_json": value,
        "unit": None,
        "depth_from_cm": 0,
        "depth_to_cm": 30,
        "observed_at": observed_at,
        "source_type": source,
        "source_id": source + "-1",
        "quality_status": quality,
        "confidence": confidence,
    }


def test_observation_requires_depth_order_and_idempotency():
    payload = {
        "tenant_id": TENANT,
        "field_id": "f1",
        "property": "ph",
        "value": 7.4,
        "unit": "pH",
        "depth_from_cm": 0,
        "depth_to_cm": 30,
        "observed_at": NOW,
        "source_type": "laboratory",
        "idempotency_key": "lab:1:ph",
    }
    obs = SoilObservation.model_validate(payload)
    assert obs.contract_version == "soil-observation.v1"
    with pytest.raises(Exception):  # noqa: B017
        SoilObservation.model_validate({**payload, "depth_from_cm": 30, "depth_to_cm": 10})


def test_laboratory_beats_newer_sensor_for_static_property():
    snapshot = compose_snapshot(
        tenant_id=TENANT,
        field_id="f1",
        observations=[
            row(obs_id="sensor", prop="ph", value=8.1, source="sensor", observed_at=NOW),
            row(
                obs_id="lab",
                prop="ph",
                value=7.3,
                source="laboratory",
                observed_at=NOW - timedelta(days=3),
            ),
        ],
    )
    ph = snapshot.layers[0].properties["ph"]
    assert ph.value == 7.3
    assert ph.selected_source == "laboratory"
    assert snapshot.status.value == "verified"
    assert snapshot.conflicts


def test_sensor_beats_lab_for_dynamic_soil_moisture():
    snapshot = compose_snapshot(
        tenant_id=TENANT,
        field_id="f1",
        observations=[
            row(
                obs_id="lab-m",
                prop="soil_moisture",
                value=18,
                source="laboratory",
                observed_at=NOW - timedelta(days=5),
            ),
            row(
                obs_id="sensor-m", prop="soil_moisture", value=27, source="sensor", observed_at=NOW
            ),
        ],
    )
    moisture = snapshot.layers[0].properties["soil_moisture"]
    assert moisture.value == 27
    assert moisture.selected_source == "sensor"


def test_rejected_observation_never_selected():
    snapshot = compose_snapshot(
        tenant_id=TENANT,
        field_id="f1",
        observations=[
            row(obs_id="bad", prop="ec", value=20, source="laboratory", quality="rejected"),
            row(obs_id="good", prop="ec", value=2.2, source="field", confidence=0.7),
        ],
    )
    assert snapshot.layers[0].properties["ec"].value == 2.2


def test_hydraulic_inputs_gate_execution():
    incomplete = compose_snapshot(
        tenant_id=TENANT,
        field_id="f1",
        observations=[row(obs_id="m", prop="soil_moisture", value=26, source="sensor")],
    )
    assert incomplete.quality_gate.passed is True
    assert incomplete.quality_gate.executable is False
    assert "automatic_irrigation_execution" in incomplete.blocked_use

    complete = compose_snapshot(
        tenant_id=TENANT,
        field_id="f1",
        observations=[
            row(obs_id="fc", prop="field_capacity", value=0.31, source="laboratory"),
            row(obs_id="wp", prop="wilting_point", value=0.14, source="laboratory"),
            row(obs_id="rd", prop="rootable_depth", value=80, source="field"),
        ],
    )
    assert complete.quality_gate.executable is True
    assert complete.model_inputs.field_capacity == 0.31


def test_snapshot_hash_is_deterministic_for_payload_content(monkeypatch):
    # Profile ids are intentionally unique; integrity is established by a valid canonical hash.
    snapshot = compose_snapshot(
        tenant_id=TENANT,
        field_id="f1",
        observations=[row(obs_id="o1", prop="texture", value="sandy_loam", source="soilgrids")],
    )
    assert len(snapshot.profile_hash) == 64
    assert snapshot.evidence_level.value == "modelled"


# ─── SOIL-MOISTURE-ELIGIBILITY-01: dynamic selection, quality tier, derived gate ───


def test_todays_reading_beats_a_30_day_old_high_confidence_one():
    snapshot = compose_snapshot(
        tenant_id=TENANT,
        field_id="f1",
        now=NOW,
        observations=[
            row(
                obs_id="old",
                prop="soil_moisture",
                value=40,
                source="sensor",
                confidence=0.99,
                observed_at=NOW - timedelta(days=30),
            ),
            row(
                obs_id="today",
                prop="soil_moisture",
                value=22,
                source="sensor",
                confidence=0.6,
                observed_at=NOW - timedelta(minutes=10),
            ),
        ],
    )
    assert snapshot.layers[0].properties["soil_moisture"].value == 22
    assert snapshot.selection_policy_version == "soil-profile-selection.v2"


def test_accepted_field_reading_beats_uncalibrated_sensor():
    snapshot = compose_snapshot(
        tenant_id=TENANT,
        field_id="f1",
        now=NOW,
        observations=[
            row(
                obs_id="sensor",
                prop="soil_moisture",
                value=12,
                source="sensor",
                quality="uncalibrated",
                confidence=0.9,
            ),
            row(
                obs_id="field",
                prop="soil_moisture",
                value=31,
                source="field",
                observed_at=NOW - timedelta(hours=1),
            ),
        ],
    )
    moisture = snapshot.layers[0].properties["soil_moisture"]
    assert (moisture.value, moisture.selected_source) == (31, "field")
    assert "irrigation_schedule" in snapshot.allowed_use


def test_recency_wins_within_the_window_at_equal_quality():
    snapshot = compose_snapshot(
        tenant_id=TENANT,
        field_id="f1",
        now=NOW,
        observations=[
            row(
                obs_id="sensor-3h",
                prop="soil_moisture",
                value=35,
                source="sensor",
                confidence=0.95,
                observed_at=NOW - timedelta(hours=3),
            ),
            row(
                obs_id="field-5m",
                prop="soil_moisture",
                value=28,
                source="field",
                confidence=0.7,
                observed_at=NOW - timedelta(minutes=5),
            ),
        ],
    )
    assert snapshot.layers[0].properties["soil_moisture"].value == 28


def test_stale_moisture_is_shown_but_removes_irrigation_schedule():
    from shared.contracts.soil import validate_soil_use

    snapshot = compose_snapshot(
        tenant_id=TENANT,
        field_id="f1",
        now=NOW,
        observations=[
            row(
                obs_id="m",
                prop="soil_moisture",
                value=20,
                source="sensor",
                observed_at=NOW - timedelta(hours=5),
            ),
            row(
                obs_id="ph",
                prop="ph",
                value=7.6,
                source="laboratory",
                observed_at=NOW - timedelta(days=60),
            ),
        ],
    )
    assert snapshot.layers[0].properties["soil_moisture"].value == 20
    assert snapshot.quality_gate.passed is True  # accepted lab pH is decision-eligible
    assert "soil_moisture_not_fresh" in snapshot.quality_gate.reasons
    assert "irrigation_schedule" not in snapshot.allowed_use
    assert "irrigation_schedule" in snapshot.blocked_use
    assert not validate_soil_use(snapshot, "irrigation_schedule").allowed


def test_quality_gate_fails_when_no_selected_value_is_decision_eligible():
    snapshot = compose_snapshot(
        tenant_id=TENANT,
        field_id="f1",
        now=NOW,
        observations=[
            row(
                obs_id="m", prop="soil_moisture", value=20, source="sensor", quality="uncalibrated"
            ),
            row(
                obs_id="fc",
                prop="field_capacity",
                value=0.31,
                source="laboratory",
                quality="uncalibrated",
            ),
            row(
                obs_id="wp",
                prop="wilting_point",
                value=0.14,
                source="laboratory",
                quality="uncalibrated",
            ),
            row(obs_id="rd", prop="rootable_depth", value=80, source="field", quality="suspect"),
        ],
    )
    gate = snapshot.quality_gate
    assert gate.passed is False and gate.executable is False
    assert "soil_profile_no_decision_eligible_evidence" in gate.reasons
    assert "soil_moisture_quality_not_accepted" in gate.reasons
    assert "irrigation_schedule" not in snapshot.allowed_use


def test_a_row_without_depth_is_not_bucketed_into_0_30():
    undeclared = row(obs_id="nodepth", prop="ph", value=9.9, source="laboratory")
    undeclared["depth_from_cm"] = None
    undeclared["depth_to_cm"] = None
    snapshot = compose_snapshot(
        tenant_id=TENANT,
        field_id="f1",
        now=NOW,
        observations=[undeclared, row(obs_id="ph", prop="ph", value=7.2, source="field")],
    )
    assert snapshot.layers[0].properties["ph"].value == 7.2
    assert "nodepth" not in snapshot.evidence_ids
