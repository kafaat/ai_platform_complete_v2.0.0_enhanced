"""One eligibility rule for soil-moisture readings — `SOIL-MOISTURE-ELIGIBILITY-01`.

On ``8216ef41d`` the same reading was judged differently by different consumers:
``irrigation_soil_input`` used any fresh non-VWC reading with no quality check; the alerts
path passed ``value_pct`` raw (no age, no quality); ``weather_advice``/``alert_rules`` read an
undeclared ``%`` as available water; ``_latest_soil_moisture`` read superseded observations;
and the telemetry bridge sent no confidence (contract default 1.0) and a depth-less
idempotency key. These tests pin the shared rule and each consumer's use of it.
"""

from __future__ import annotations

import ast
import asyncio
import hashlib
import sys
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit]

_ROOT = Path(__file__).resolve().parents[1]
_PLATFORM = _ROOT / "services" / "sahool-platform"
if str(_PLATFORM) not in sys.path:
    sys.path.insert(0, str(_PLATFORM))

from api import soil_telemetry as st  # noqa: E402
from api import water_twin_seed as seed  # noqa: E402
from api.device_registry import get_device_type  # noqa: E402
from api.weather_advice import irrigation_advice  # noqa: E402

from shared.contracts.soil import moisture_policy as mp  # noqa: E402

_NOW = datetime(2026, 11, 8, 12, 0, tzinfo=UTC)
_FRESH = _NOW - timedelta(minutes=30)


def _elig(unit="available_pct", quality="accepted", observed=_FRESH, **kw):
    return mp.moisture_eligibility(unit, quality, observed, _NOW, **kw)


# ─── (1) the policy itself ─────────────────────────────────────────────────


def test_policy_is_versioned_and_frozen():
    assert mp.POLICY_VERSION.startswith("soil-moisture-eligibility.v")
    verdict = _elig()
    assert verdict.policy_version == mp.POLICY_VERSION
    with pytest.raises(FrozenInstanceError):
        verdict.decision_eligible = False  # type: ignore[misc]


def test_only_accepted_fresh_available_water_is_decision_eligible():
    verdict = _elig()
    assert verdict.decision_eligible and verdict.may_raise_urgency and verdict.may_seed
    assert verdict.limitations == ()
    assert not verdict.advisory and not verdict.excluded


@pytest.mark.parametrize(
    ("kwargs", "limitation"),
    [
        ({"unit": "undeclared"}, mp.LIMIT_UNIT_UNDECLARED),
        ({"unit": None}, mp.LIMIT_UNIT_UNDECLARED),
        ({"unit": "vwc_pct"}, mp.LIMIT_VWC_NOT_COMPARABLE),
        ({"quality": "uncalibrated"}, f"{mp.LIMIT_QUALITY_NOT_DECISION_ELIGIBLE}:uncalibrated"),
        ({"quality": "suspect"}, f"{mp.LIMIT_QUALITY_NOT_DECISION_ELIGIBLE}:suspect"),
        ({"quality": None}, mp.LIMIT_QUALITY_UNPROVEN),
        ({"observed": _NOW - timedelta(hours=5)}, mp.LIMIT_SENSOR_STALE),
        ({"observed": None}, mp.LIMIT_FRESHNESS_UNPROVEN),
        ({"observed": _NOW + timedelta(hours=1)}, mp.LIMIT_TIMESTAMP_IN_FUTURE),
    ],
)
def test_advisory_readings_are_shown_but_never_raise_urgency(kwargs, limitation):
    verdict = _elig(**kwargs)
    assert verdict.advisory and not verdict.excluded
    assert not verdict.decision_eligible and not verdict.may_raise_urgency
    assert limitation in verdict.limitations


def test_vwc_may_seed_the_twin_but_not_drive_threshold_decisions():
    verdict = _elig(unit="vwc_pct")
    assert verdict.may_seed and verdict.measurement_current
    assert not verdict.decision_eligible
    assert not _elig(unit="undeclared").may_seed
    assert not _elig(unit="vwc_pct", quality="uncalibrated").may_seed


@pytest.mark.parametrize(
    ("kwargs", "limitation"),
    [
        ({"quality": "rejected"}, mp.LIMIT_QUALITY_REJECTED),
        ({"superseded": True}, mp.LIMIT_SUPERSEDED),
    ],
)
def test_rejected_and_superseded_are_excluded(kwargs, limitation):
    verdict = _elig(**kwargs)
    assert verdict.excluded and not verdict.advisory
    assert not (verdict.decision_eligible or verdict.may_seed or verdict.measurement_current)
    assert limitation in verdict.limitations


def test_ttl_boundary_and_naive_timestamps():
    assert _elig(observed=_NOW - timedelta(seconds=mp.SOIL_MOISTURE_SENSOR_TTL_S)).decision_eligible
    assert not _elig(
        observed=_NOW - timedelta(seconds=mp.SOIL_MOISTURE_SENSOR_TTL_S + 1)
    ).decision_eligible
    assert _elig(observed=_FRESH.replace(tzinfo=None)).decision_eligible  # naive ⇒ UTC
    assert _elig(quality=" Accepted ").decision_eligible


def test_the_ttl_has_one_source():
    device = get_device_type("soil_moisture_sensor")
    assert device["max_reading_age_s"] == mp.SOIL_MOISTURE_SENSOR_TTL_S == 4 * 3600
    assert seed.SEED_ELIGIBLE_QUALITY_STATUSES is mp.DECISION_ELIGIBLE_QUALITY_STATUSES
    for age in (None, -400.0, 0.0, 3600.0, 4 * 3600 + 1.0, float("nan")):
        assert seed.sensor_freshness(age, 4 * 3600) == mp.classify_freshness(age, 4 * 3600)


# ─── (2) irrigation_soil_input / decision_soil_moisture ─────────────────────


def _reading(unit_kind="available_pct", quality="accepted", age=timedelta(minutes=30), pct=20.0):
    return st.SoilMoistureReading(
        value_pct=pct,
        recorded_at=_NOW - age,
        unit=unit_kind,
        unit_kind=unit_kind,
        quality_status=quality,
    )


@pytest.mark.parametrize(
    ("kwargs", "used"),
    [
        ({}, True),
        ({"unit_kind": "undeclared"}, False),
        ({"quality": "uncalibrated"}, False),
        ({"quality": "suspect"}, False),
        ({"quality": None}, False),
        ({"age": timedelta(hours=5)}, False),
        ({"unit_kind": "vwc_pct"}, False),
    ],
)
def test_irrigation_soil_input_routes_through_the_policy(kwargs, used):
    out = st.irrigation_soil_input(_reading(**kwargs), now=_NOW)
    assert out["soil_moisture_used"] is used
    assert out["usable_pct"] == (20.0 if used else None)
    assert out["soil_moisture_pct"] == 20.0  # the raw value is still shown
    assert out["soil_moisture_policy_version"] == mp.POLICY_VERSION
    assert out["soil_moisture_quality_status"] == kwargs.get("quality", "accepted")


def test_decision_soil_moisture_gives_the_alert_path_the_usable_value_only():
    assert st.decision_soil_moisture(_reading(), now=_NOW) == (20.0, "available_pct")
    stale = st.decision_soil_moisture(_reading(age=timedelta(days=7)), now=_NOW)
    assert stale[0] is None
    assert st.decision_soil_moisture(_reading(quality="uncalibrated"), now=_NOW)[0] is None
    assert st.decision_soil_moisture(None, now=_NOW) == (None, "available_pct")


@pytest.mark.parametrize("pct", [5.0, 20.0, 29.0, 70.0])
@pytest.mark.parametrize("unit_kind", ["undeclared", "vwc_pct", "banana"])
def test_a_non_available_unit_never_changes_urgency(pct, unit_kind):
    common = dict(et0_mm=6.0, crop="wheat", stage="mid", rain_recent_mm=0.0, forecast_rain_mm=0.0)
    baseline = irrigation_advice(**common, soil_moisture_pct=None)
    out = irrigation_advice(**common, soil_moisture_pct=pct, soil_moisture_unit_kind=unit_kind)
    assert out["urgency"] == baseline["urgency"]


def test_the_alert_path_does_not_pass_raw_value_pct():
    """`_evaluate_field_alerts_persist` used `soil_reading.value_pct` with no age/quality check."""
    tree = ast.parse((_PLATFORM / "api" / "main.py").read_text(encoding="utf-8"))
    fn = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "_evaluate_field_alerts_persist"
    )
    attrs = {n.attr for n in ast.walk(fn) if isinstance(n, ast.Attribute)}
    calls = {
        n.func.id for n in ast.walk(fn) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
    }
    assert "value_pct" not in attrs
    assert "decision_soil_moisture" in calls


def test_low_moisture_alert_ignores_an_undeclared_reading():
    from api.alert_rules import FieldAlertContext, evaluate_field_alerts

    ctx = FieldAlertContext(
        field_id="f", soil_moisture_pct=10.0, soil_moisture_unit_kind="undeclared"
    )
    assert not [a for a in evaluate_field_alerts(ctx) if a.alert_type == "low_moisture"]


# ─── (3) device telemetry bridge ───────────────────────────────────────────


def _legacy_key(device_id, prop, observed_at):
    raw = f"{device_id}|{prop}|{observed_at.astimezone(UTC).isoformat()}"
    return f"dev_{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:48]}"


def test_idempotency_key_is_backward_compatible_and_depth_aware():
    from api.soil_evidence_bridge import idempotency_key

    common = dict(device_id="d1", property_name="soil_moisture", observed_at=_NOW)
    assert idempotency_key(**common) == _legacy_key("d1", "soil_moisture", _NOW)
    shallow = idempotency_key(**common, depth_from_cm=0, depth_to_cm=15)
    deep = idempotency_key(**common, depth_from_cm=15, depth_to_cm=30)
    assert len({idempotency_key(**common), shallow, deep}) == 3
    assert shallow == idempotency_key(**common, depth_from_cm=0.0, depth_to_cm=15.0)


def test_bridge_sends_uncalibrated_confidence_and_declared_depth_only():
    from api.soil_evidence_bridge import build_observation

    from shared.contracts.soil import SoilObservation

    common = dict(
        tenant_id="t",
        field_id="f",
        device_id="d",
        property_name="soil_moisture",
        value=21.5,
        unit="%",
        observed_at=_NOW,
    )
    bare = build_observation(**common)
    assert bare["confidence"] <= 0.65
    assert "quality_status" not in bare
    assert not {"depth_from_cm", "depth_to_cm", "calibration_id"} & set(bare)
    obs = SoilObservation.model_validate({**bare, "received_at": _NOW})
    assert obs.quality_status.value == "uncalibrated" and obs.confidence <= 0.65

    full = build_observation(**common, depth_from_cm=15, depth_to_cm=30, calibration_id="cal-7")
    assert (full["depth_from_cm"], full["depth_to_cm"], full["calibration_id"]) == (
        15.0,
        30.0,
        "cal-7",
    )
    assert full["idempotency_key"] != bare["idempotency_key"]
    obs = SoilObservation.model_validate({**full, "received_at": _NOW})
    assert obs.quality_status.value == "uncalibrated"  # a claimed calibration is not acceptance


@pytest.mark.parametrize("bad", [True, False, float("nan"), float("inf"), "-inf"])
def test_telemetry_value_rejects_non_measurements(bad):
    from api.device_models import TelemetryRequest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        TelemetryRequest(sensor_type="soil_moisture", value=bad)


def test_telemetry_accepts_ints_and_a_complete_depth_pair():
    from api.device_models import TelemetryRequest
    from pydantic import ValidationError

    assert TelemetryRequest(sensor_type="soil_moisture", value=21).value == 21.0
    req = TelemetryRequest(
        sensor_type="soil_moisture", value=21, depth_from_cm=0, depth_to_cm=15, calibration_id="c"
    )
    assert (req.depth_from_cm, req.depth_to_cm, req.calibration_id) == (0.0, 15.0, "c")
    for bad in ({"depth_from_cm": 10}, {"depth_from_cm": 30, "depth_to_cm": 15}):
        with pytest.raises(ValidationError):
            TelemetryRequest(sensor_type="soil_moisture", value=21, **bad)
