"""Immutable irrigation source binds water, equipment and the approved operating window."""

import hashlib
import json
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from persistence import _manual_irrigation_plan_violation

pytestmark = pytest.mark.unit


def canonical_digest(value):
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
            default=str,
        ).encode()
    ).hexdigest()


def fixture():
    now = datetime.now(UTC)
    source = dict(
        schema_version="manual-irrigation-source/v1",
        field_id="f",
        season_id="s",
        system_id="pivot",
        net_depth_mm=10.0,
        target_depth_mm=10.0,
        target_volume_m3=200.0,
        application_efficiency=1.0,
        irrigated_area_ha=2.0,
        water_truth_digest="a" * 64,
        specification_digest="b" * 64,
        valid_from=(now + timedelta(hours=1)).isoformat(),
        valid_until=(now + timedelta(hours=2)).isoformat(),
    )
    specification = {
        "tenant_id": "t",
        "field_id": "f",
        "season_id": "s",
        "system_id": "pivot",
        "application_efficiency": 1.0,
        "irrigated_area_ha": 2.0,
        "evidence_level": "user_declared",
        "source_reference": "operator survey",
        "observed_at": (now - timedelta(days=1)).isoformat(),
    }
    water = {
        "canonical": {
            "tenant_id": "t",
            "field_id": "f",
            "season_id": "s",
            "operational_eligible": True,
            "valid_until": (now + timedelta(hours=3)).isoformat(),
        },
        "applied_water_status": "recorded",
    }
    source.update(
        specification=specification,
        water_truth=water,
        specification_digest=canonical_digest(specification),
        water_truth_digest=canonical_digest(water),
    )
    value = {
        "season_id": "s",
        "recommendation": {"should_irrigate": True, "target_refill_mm": 10.0},
        "manual_execution_source": source,
    }
    decision = dict(
        tenant_id="t",
        decision_type="irrigation",
        approved_decision_value_digest="c" * 64,
        decision_value=value,
        field_id="f",
    )
    payload = SimpleNamespace(
        constraints=deepcopy(source),
        planned_start=datetime.fromisoformat(source["valid_from"]),
        planned_end=datetime.fromisoformat(source["valid_until"]),
    )
    return decision, payload


def test_net_ten_at_eighty_percent_requires_gross_twelve_point_five():
    decision, payload = fixture()
    for key, value in {
        "target_depth_mm": 12.5,
        "target_volume_m3": 250.0,
        "application_efficiency": 0.8,
    }.items():
        decision["decision_value"]["manual_execution_source"][key] = value
        payload.constraints[key] = value
    source = decision["decision_value"]["manual_execution_source"]
    source["specification"]["application_efficiency"] = 0.8
    source["specification_digest"] = canonical_digest(source["specification"])
    payload.constraints["specification"] = deepcopy(source["specification"])
    payload.constraints["specification_digest"] = source["specification_digest"]
    assert _manual_irrigation_plan_violation(decision, payload) is None


@pytest.mark.parametrize(
    "key,value",
    [
        ("field_id", "other"),
        ("season_id", "other"),
        ("system_id", "other"),
        ("net_depth_mm", 9),
        ("target_depth_mm", 10.5),
        ("target_volume_m3", 249),
        ("application_efficiency", 0.9),
        ("irrigated_area_ha", 3),
        ("water_truth_digest", "d" * 64),
        ("specification_digest", "d" * 64),
        ("valid_from", "2026-10-16T10:01:00+00:00"),
        ("schema_version", "manual-irrigation-source/v2"),
    ],
)
def test_changed_plan_constraint_is_rejected(key, value):
    decision, payload = fixture()
    payload.constraints[key] = value
    assert _manual_irrigation_plan_violation(decision, payload) is not None


@pytest.mark.parametrize("value", [float("nan"), float("inf"), True, 0, -1, "10"])
@pytest.mark.parametrize(
    "key",
    [
        "net_depth_mm",
        "target_depth_mm",
        "target_volume_m3",
        "application_efficiency",
        "irrigated_area_ha",
    ],
)
def test_invalid_approved_numeric_evidence_is_not_executable(key, value):
    decision, payload = fixture()
    decision["decision_value"]["manual_execution_source"][key] = value
    payload.constraints[key] = value
    assert _manual_irrigation_plan_violation(decision, payload) is not None


@pytest.mark.parametrize(
    "key,value",
    [
        ("net_depth_mm", 9),
        ("target_depth_mm", 13),
        ("target_volume_m3", 249),
        ("application_efficiency", 1.1),
        ("water_truth_digest", "x" * 64),
        ("specification_digest", ""),
        ("season_id", "other"),
    ],
)
def test_internally_inconsistent_approved_source_is_rejected(key, value):
    decision, payload = fixture()
    decision["decision_value"]["manual_execution_source"][key] = value
    payload.constraints[key] = value
    assert _manual_irrigation_plan_violation(decision, payload) is not None


def test_outer_window_must_match_approved_window():
    decision, payload = fixture()
    payload.planned_end = datetime.fromisoformat("2026-10-16T12:00:00+00:00")
    assert _manual_irrigation_plan_violation(decision, payload) is not None


def test_unknown_constraints_cannot_add_unapproved_operating_values():
    decision, payload = fixture()
    payload.constraints["pressure_bar"] = 99
    assert _manual_irrigation_plan_violation(decision, payload) is not None


def test_missing_source_key_cannot_be_omitted_from_both_versions():
    decision, payload = fixture()
    del decision["decision_value"]["manual_execution_source"]["system_id"]
    del payload.constraints["system_id"]
    assert _manual_irrigation_plan_violation(decision, payload) is not None


def test_legacy_refill_tolerance_is_preserved():
    decision, payload = fixture()
    del decision["decision_value"]["manual_execution_source"]
    payload.constraints = {"field_id": "f", "target_depth_mm": 10.5}
    assert _manual_irrigation_plan_violation(decision, payload) is None


def test_expired_approved_source_cannot_create_a_new_plan():
    decision, payload = fixture()
    now = datetime.now(UTC)
    for key, stamp in {
        "valid_from": now - timedelta(hours=2),
        "valid_until": now - timedelta(hours=1),
    }.items():
        decision["decision_value"]["manual_execution_source"][key] = stamp.isoformat()
        payload.constraints[key] = stamp.isoformat()
    payload.planned_start = datetime.fromisoformat(payload.constraints["valid_from"])
    payload.planned_end = datetime.fromisoformat(payload.constraints["valid_until"])
    assert (
        _manual_irrigation_plan_violation(decision, payload) == "manual_irrigation_source_expired"
    )


@pytest.mark.parametrize("key", ["specification", "water_truth"])
def test_missing_full_evidence_is_rejected(key):
    decision, payload = fixture()
    del decision["decision_value"]["manual_execution_source"][key]
    del payload.constraints[key]
    assert (
        _manual_irrigation_plan_violation(decision, payload)
        == "manual_irrigation_source_evidence_missing"
    )


@pytest.mark.parametrize(
    "evidence,key,val",
    [
        ("specification", "tenant_id", "foreign"),
        ("specification", "system_id", "foreign"),
        ("specification", "application_efficiency", 0.5),
        ("specification", "evidence_level", "assumed"),
        ("water_truth", "applied_water_status", "unknown"),
        ("canonical", "tenant_id", "foreign"),
        ("canonical", "field_id", "foreign"),
        ("canonical", "season_id", "foreign"),
        ("canonical", "operational_eligible", False),
    ],
)
def test_evidence_invalid_even_when_its_digest_matches(evidence, key, val):
    decision, payload = fixture()
    source = decision["decision_value"]["manual_execution_source"]
    obj = source["water_truth"]["canonical"] if evidence == "canonical" else source[evidence]
    obj[key] = val
    for objkey, digestkey in [
        ("specification", "specification_digest"),
        ("water_truth", "water_truth_digest"),
    ]:
        source[digestkey] = canonical_digest(source[objkey])
    payload.constraints = deepcopy(source)
    assert _manual_irrigation_plan_violation(decision, payload) is not None


def test_fabricated_digest_cannot_bind_different_evidence():
    decision, payload = fixture()
    source = decision["decision_value"]["manual_execution_source"]
    source["specification"]["source_reference"] = "different survey"
    payload.constraints = deepcopy(source)
    assert (
        _manual_irrigation_plan_violation(decision, payload)
        == "manual_irrigation_source_evidence_digest_mismatch"
    )


def test_extreme_integer_is_rejected_without_conversion_exception():
    decision, payload = fixture()
    decision["decision_value"]["manual_execution_source"]["target_volume_m3"] = 10**400
    payload.constraints["target_volume_m3"] = 10**400
    assert (
        _manual_irrigation_plan_violation(decision, payload)
        == "manual_irrigation_source_amount_invalid"
    )
