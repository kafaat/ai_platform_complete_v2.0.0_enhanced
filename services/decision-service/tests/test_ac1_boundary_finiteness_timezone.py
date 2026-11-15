"""AC-1 boundary: finite numbers and timezone-aware instants on the point-in-time authority.

* ``FeatureEntryIn.value: Any`` accepted NaN/Infinity. ``model_dump(mode="json")`` rewrote them to
  ``null``, so the feature-manifest hash covered a value nobody supplied. They are now a typed
  ``non_finite_number`` violation of ``validate_composition`` (also nested, and in
  ``context``/``history``), which the route returns as its 422 violation envelope. A feature that
  declares a unit must carry a real number: ``True`` is not ``1 mm``.
* A naive ``observed_at``/``available_at``/``as_of_time``/``decision_cutoff_time``/
  ``history_from``/``history_to`` made ``validate_composition`` raise ``TypeError`` against an
  aware one (HTTP 500), the class of DECISION-PLAN-MIXED-TIMEZONE-500-01. It is now a pydantic 422,
  and ``validate_composition`` refuses an unvalidated naive payload with typed reasons.

Pure: the contracts and the policy are called directly. The HTTP boundary runs through
``TestClient`` with ``compose_agronomic_context`` replaced by its own first step, the real
``validate_composition`` (a separate test pins that persistence runs it before connecting), so no
connection or stand-in is involved; an admitted composition raises a sentinel instead of writing.
"""

from __future__ import annotations

import inspect
import json
import sys
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

SERVICE_DIR = Path(__file__).resolve().parents[1]
if str(SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(SERVICE_DIR))

from agronomic_context.contracts import (  # noqa: E402
    CONTEXT_GROUPS,
    ContextComposeIn,
    FeatureEntryIn,
)
from agronomic_context.point_in_time import validate_composition  # noqa: E402

pytestmark = pytest.mark.unit

TENANT = "00000000-0000-0000-0000-000000001426"
TOKEN = "isolated-test-token"
NOW = datetime(2026, 7, 9, 6, 0, tzinfo=UTC)
NON_FINITE = [float("nan"), float("inf"), float("-inf")]
DATETIME_FIELDS = [
    ("as_of_time", None),
    ("decision_cutoff_time", None),
    ("history_from", "historical"),
    ("history_to", "historical"),
    ("observed_at", "feature"),
    ("available_at", "feature"),
]


def _feature(**overrides) -> dict:
    feature = {
        "name": "ndvi_mean",
        "value": 0.61,
        "unit": "index",
        "source_service": "raster-service",
        "source_snapshot_id": "scene-1",
        "observed_at": NOW - timedelta(days=2),
        "available_at": NOW - timedelta(days=2),
        "quality_status": "verified",
        "formula_version": "ndvi-v2",
    }
    feature.update(overrides)
    return feature


def _body(**overrides) -> dict:
    body = {
        "field_id": "field-1426",
        "season_id": "s2026",
        "as_of_time": NOW,
        "decision_cutoff_time": NOW,
        "context": {group: {"note": group} for group in CONTEXT_GROUPS},
        "historical": {
            "history_from": NOW - timedelta(days=30),
            "history_to": NOW - timedelta(hours=1),
            "history": {"ndvi_trend_14d": -0.03},
        },
        "features": [
            _feature(),
            _feature(name="crop_id", value="wheat", unit=None),
            _feature(name="rainfed", value=True, unit=None),
            _feature(name="days_since_sowing", value=41, unit="d"),
        ],
        "idempotency_key": "ac1-boundary-1",
    }
    body.update(overrides)
    return body


def _naive(field: str, where: str | None) -> dict:
    """The happy body with exactly one instant stripped of its timezone (the rest stay aware)."""
    body = _body()
    if where is None:
        body[field] = body[field].replace(tzinfo=None)
    elif where == "historical":
        body["historical"][field] = body["historical"][field].replace(tzinfo=None)
    else:
        body["features"][0][field] = body["features"][0][field].replace(tzinfo=None)
    return body


def _codes(payload: ContextComposeIn) -> list[str]:
    return [v["code"] for v in validate_composition(payload)]


# ── happy path stays admissible ───────────────────────────────────────────────────────────────


def test_the_happy_path_is_admissible_with_numeric_string_and_flag_values():
    payload = ContextComposeIn(**_body())
    assert validate_composition(payload) == []
    dumped = [f.model_dump(mode="json")["value"] for f in payload.features]
    assert dumped == [0.61, "wheat", True, 41]


def test_a_non_utc_offset_is_still_an_aware_instant():
    plus3 = NOW.astimezone(timezone(timedelta(hours=3)))
    assert validate_composition(ContextComposeIn(**_body(as_of_time=plus3))) == []


# ── non-finite numbers ────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("bad", NON_FINITE, ids=["nan", "inf", "-inf"])
def test_a_non_finite_feature_value_is_a_typed_violation(bad):
    payload = ContextComposeIn(**_body(features=[_feature(value=bad)]))
    assert validate_composition(payload) == [
        {"code": "non_finite_number", "feature": "ndvi_mean", "path": "value"}
    ]


@pytest.mark.parametrize(
    ("value", "path"),
    [
        ({"mean": 0.5, "band": {"p90": float("nan")}}, "value.band.p90"),
        ([0.1, 0.2, float("inf")], "value[2]"),
        ({"series": [{"v": 1.0}, {"v": float("-inf")}]}, "value.series[1].v"),
    ],
    ids=["dict", "list", "list-in-dict"],
)
def test_a_nested_non_finite_value_is_found_and_located(value, path):
    payload = ContextComposeIn(**_body(features=[_feature(value=value, unit=None)]))
    assert validate_composition(payload) == [
        {"code": "non_finite_number", "feature": "ndvi_mean", "path": path}
    ]


def test_non_finite_numbers_in_context_and_history_are_refused_too():
    body = _body()
    body["context"]["weather"] = {"et0_mm": float("nan")}
    body["historical"]["history"] = {"trend": [float("inf")]}
    violations = validate_composition(ContextComposeIn(**body))
    assert {"code": "non_finite_number", "path": "context.weather.et0_mm"} in violations
    assert {"code": "non_finite_number", "path": "history.trend[0]"} in violations


def test_the_manifest_hash_input_never_carries_a_null_the_caller_did_not_send():
    """The original defect: NaN dumped as ``null`` was hashed as if it had been supplied."""
    payload = ContextComposeIn(**_body(features=[_feature(value=float("nan"))]))
    assert payload.features[0].model_dump(mode="json")["value"] is None
    assert "non_finite_number" in _codes(payload)


# ── bool where a number is meant ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize("flag", [True, False])
def test_a_bool_is_not_a_number_for_a_feature_with_a_unit(flag):
    with pytest.raises(ValidationError, match="must carry a number"):
        FeatureEntryIn(**_feature(value=flag, unit="mm"))


def test_a_string_is_not_a_number_for_a_feature_with_a_unit():
    with pytest.raises(ValidationError, match="must carry a number"):
        FeatureEntryIn(**_feature(value="5.2", unit="mm"))


# ── naive instants ────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(("field", "where"), DATETIME_FIELDS, ids=[f for f, _ in DATETIME_FIELDS])
def test_a_naive_instant_is_a_validation_error(field, where):
    with pytest.raises(ValidationError) as caught:
        ContextComposeIn(**_naive(field, where))
    assert [e["type"] for e in caught.value.errors()] == ["timezone_aware"]
    assert caught.value.errors()[0]["loc"][-1] == field


@pytest.mark.parametrize(("field", "where"), DATETIME_FIELDS, ids=[f for f, _ in DATETIME_FIELDS])
def test_an_unvalidated_naive_instant_is_a_typed_violation_not_a_type_error(field, where):
    """Second line: a payload built without validation must not reach an ordering comparison."""
    payload = ContextComposeIn(**_body())
    stamp_owner = (
        payload
        if where is None
        else payload.historical
        if where == "historical"
        else payload.features[0]
    )
    object.__setattr__(stamp_owner, field, getattr(stamp_owner, field).replace(tzinfo=None))
    violations = validate_composition(payload)
    assert [v["code"] for v in violations] == ["naive_timestamp"]
    assert violations[0]["field"] == field


# ── HTTP: 422, never 500, and never a connection ──────────────────────────────────────────────


class _Reached(Exception):
    """Raised when the policy admits a composition: the write would happen next."""


def test_persistence_runs_the_policy_before_it_connects():
    import persistence

    source = inspect.getsource(persistence.compose_agronomic_context)
    policy = source.index("violations = validate_composition(payload)")
    rejected = source.index('return {"status": "rejected", "reason": "point_in_time_policy"')
    assert policy < rejected < source.index("await _connect()")


@pytest.fixture
def client(monkeypatch):
    import main
    from fastapi.testclient import TestClient

    async def policy_then_stop(*, tenant_id, created_by, payload):
        # The first step of persistence.compose_agronomic_context, verbatim in effect.
        violations = validate_composition(payload)
        if violations:
            return {
                "status": "rejected",
                "reason": "point_in_time_policy",
                "violations": violations,
            }
        raise _Reached("the policy admitted the composition")

    monkeypatch.setenv("DECISION_SERVICE_AUTH_TOKEN", TOKEN)
    monkeypatch.setattr(main, "sor_enabled", lambda: True)
    monkeypatch.setattr(main, "compose_agronomic_context", policy_then_stop)
    return TestClient(main.app, raise_server_exceptions=True)


def _post(test_client, body: dict):
    return test_client.post(
        "/v1/context-snapshots",
        content=json.dumps(body, default=lambda d: d.isoformat()),
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "X-Tenant-Id": TENANT,
            "X-Requested-By": "composer",
            "Content-Type": "application/json",
        },
    )


def test_http_happy_path_is_admitted_by_the_policy(client):
    with pytest.raises(_Reached):
        _post(client, _body())


@pytest.mark.parametrize("bad", NON_FINITE, ids=["nan", "inf", "-inf"])
def test_http_non_finite_value_is_a_422_violation(client, bad):
    response = _post(client, _body(features=[_feature(value={"x": [bad]}, unit=None)]))
    assert response.status_code == 422, response.text
    assert response.json()["detail"]["violations"] == [
        {"code": "non_finite_number", "feature": "ndvi_mean", "path": "value.x[0]"}
    ]


def test_http_bool_with_a_unit_is_a_422(client):
    response = _post(client, _body(features=[_feature(value=True, unit="mm")]))
    assert response.status_code == 422, response.text


@pytest.mark.parametrize(("field", "where"), DATETIME_FIELDS, ids=[f for f, _ in DATETIME_FIELDS])
def test_http_naive_instant_is_a_422_not_a_500(client, field, where):
    response = _post(client, _naive(field, where))
    assert response.status_code == 422, response.text
    assert response.json()["detail"][0]["type"] == "timezone_aware"
