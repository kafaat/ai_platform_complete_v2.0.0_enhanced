from datetime import UTC, datetime, timezone

from evidence_adapters import observations_from_properties
from profile_composer import compose_snapshot

from shared.contracts.soil import SoilObservationSource, validate_soil_use

NOW = datetime.now(UTC)
TENANT = "11111111-1111-4111-8111-111111111111"


def _rows(observations):
    return [
        {
            "observation_id": o.observation_id,
            "property": o.property,
            "value_json": o.value,
            "unit": o.unit,
            "depth_from_cm": o.depth_from_cm,
            "depth_to_cm": o.depth_to_cm,
            "observed_at": o.observed_at,
            "source_type": o.source_type.value,
            "source_id": o.source_id,
            "quality_status": o.quality_status.value,
            "confidence": o.confidence,
        }
        for o in observations
    ]


def test_soilgrids_stays_modelled_and_high_risk_blocked():
    obs = observations_from_properties(
        tenant_id=TENANT,
        field_id="f1",
        source_type=SoilObservationSource.SOILGRIDS,
        source_id="sg:v2",
        properties={"texture": "sandy_loam", "ph": 7.7},
        observed_at=NOW,
    )
    snap = compose_snapshot(tenant_id=TENANT, field_id="f1", observations=_rows(obs))
    assert snap.evidence_level.value == "modelled"
    assert validate_soil_use(snap, "sampling_plan").allowed
    assert not validate_soil_use(snap, "gypsum_rate").allowed


def test_approved_lab_with_hydraulics_can_authorize_high_risk_use():
    obs = observations_from_properties(
        tenant_id=TENANT,
        field_id="f1",
        source_type=SoilObservationSource.LABORATORY,
        source_id="lab-1",
        approved=True,
        observed_at=NOW,
        properties={
            "ph": 7.4,
            "ec": 1.2,
            "field_capacity": 0.30,
            "wilting_point": 0.14,
            "rootable_depth": 90,
            "bulk_density": 1.35,
        },
    )
    snap = compose_snapshot(tenant_id=TENANT, field_id="f1", observations=_rows(obs))
    assert snap.evidence_level.value == "lab_verified"
    assert snap.quality_gate.executable
    assert validate_soil_use(snap, "gypsum_rate").allowed


def test_unapproved_lab_is_uncalibrated_and_cannot_unlock_high_risk():
    obs = observations_from_properties(
        tenant_id=TENANT,
        field_id="f1",
        source_type=SoilObservationSource.LABORATORY,
        source_id="lab-2",
        approved=False,
        observed_at=NOW,
        properties={"ph": 7.4, "field_capacity": 0.30, "wilting_point": 0.14, "rootable_depth": 90},
    )
    assert all(o.quality_status.value == "uncalibrated" for o in obs)
