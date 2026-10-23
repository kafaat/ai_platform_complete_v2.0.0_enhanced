"""Production platform client -> real weather HTTP route, without formula mocks.

The only replacement is the network transport: HTTPX serializes the production
request and the actual weather FastAPI app validates and computes its response.
This witnesses the boundary that isolated client mocks and direct-kernel tests
cannot. BFF cases mount the real water-balance router with authentication
overridden; neither database nor full application lifespan nor live networking
is exercised.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import httpx
import pytest
from api import weather_service_client as client
from fastapi import FastAPI

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parents[1]
_SERVICE = _ROOT / "services" / "weather-service"
_HTTPX_CLIENT = httpx.AsyncClient
_BASE = {
    "t_max_c": 30.0,
    "t_min_c": 18.0,
    "solar_rad_mj_m2": 22.0,
    "rh_mean_pct": 55.0,
    "wind_2m_ms": 2.0,
    "t_mean_c": 24.0,
    "lat_deg": 15.5,
    "elevation_m": 2000.0,
    "day_of_year": 100,
    "valid_time": "2026-04-10T00:00:00Z",
    "weather_snapshot_id": "hop/station-7/day-100",
}


@pytest.fixture(scope="module")
def weather_app():
    """Load the production entrypoint without claiming the generic `main` name."""
    module_name = "_et0_http_hop_weather_entrypoint"
    with pytest.MonkeyPatch.context() as patch:
        patch.syspath_prepend(str(_SERVICE))
        # Do not let unrelated modules with a common service filename become
        # silent substitutes when this file runs alongside other test suites.
        for name in ("weather_runtime", "et0", "canonical_weather_state"):
            existing = sys.modules.get(name)
            if existing is not None:
                assert Path(existing.__file__).resolve().parent == _SERVICE
        spec = importlib.util.spec_from_file_location(module_name, _SERVICE / "main.py")
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        patch.setitem(sys.modules, module_name, module)
        spec.loader.exec_module(module)
        assert "/v1/weather/agro/et0" in module.app.openapi()["paths"]
        yield module.app


@pytest.fixture
def hop(monkeypatch, weather_app):
    events = []
    original_client = httpx.AsyncClient

    class RecordingTransport(httpx.ASGITransport):
        async def handle_async_request(self, request):
            event = {
                "method": request.method,
                "path": request.url.path,
                "body": json.loads(await request.aread()),
                "headers": dict(request.headers),
            }
            response = await super().handle_async_request(request)
            await response.aread()
            event.update(status=response.status_code, response=response.json())
            events.append(event)
            return response

    def asgi_client(*args, **kwargs):
        assert "transport" not in kwargs
        return original_client(*args, transport=RecordingTransport(app=weather_app), **kwargs)

    monkeypatch.setenv("WEATHER_SERVICE_URL", "http://weather-owner.test")
    monkeypatch.setenv("SAHOOL_AGENT_TOKEN", "et0-hop-service-token")
    monkeypatch.setattr(httpx, "AsyncClient", asgi_client)
    return events


async def _request(events, overrides=None, *, tenant_id="tenant-et0-hop"):
    vector = {**_BASE, **(overrides or {})}
    product = await client.get_et0_product(**vector, tenant_id=tenant_id)
    assert len(events) == 1, "The real owner route must answer exactly one request"
    event = events[0]
    assert event["method"] == "POST"
    assert event["path"] == "/v1/weather/agro/et0"
    assert event["body"] == vector, "A request field was renamed, defaulted or lost in transit"
    assert event["status"] == 200
    assert product == event["response"], "The platform client changed the owner's product"
    assert product["derived_from"] == "canonical_weather_state"
    assert product["source_snapshot_id"] == product["weather_snapshot_id"]
    assert product["canonical_state_id"]
    return product


async def test_complete_pm_vector_survives_http_with_owner_provenance(hop):
    product = await _request(hop)
    assert product["method"] == "fao56_penman_monteith"
    assert product["quality_status"] == "validated"
    assert product["et0_mm"] == pytest.approx(5.270, abs=0.001)
    assert product["valid_time"] == _BASE["valid_time"]
    assert product["weather_snapshot_id"] == _BASE["weather_snapshot_id"]
    assert product["formula_version"]


@pytest.mark.parametrize("field", ["solar_rad_mj_m2", "rh_mean_pct", "wind_2m_ms"])
async def test_each_missing_pm_variable_remains_null_and_names_fallback(hop, field):
    product = await _request(hop, {field: None})
    assert product["method"] == "hargreaves_fallback"
    assert product["quality_status"] == "degraded"
    assert field in product["missing_inputs"]
    assert product["et0_mm"] is not None


async def test_multiple_missing_pm_inputs_are_individually_preserved(hop):
    absent = {field: None for field in ("solar_rad_mj_m2", "rh_mean_pct", "wind_2m_ms")}
    product = await _request(hop, absent)
    assert product["method"] == "hargreaves_fallback"
    assert product["quality_status"] == "degraded"
    assert set(absent) <= set(product["missing_inputs"])


@pytest.mark.parametrize("field", ["elevation_m", "t_mean_c"])
async def test_optional_pm_metadata_is_not_fabricated_by_the_client(hop, field):
    # The owner's current PM model supports these omissions. The seam test
    # witnesses that HTTP sends null and preserves the owner's answer; it does
    # not assert a new completeness policy or pretend these fields are required.
    product = await _request(hop, {field: None})
    assert product["method"] == "fao56_penman_monteith"
    assert product["et0_mm"] is not None
    if field == "elevation_m":
        assert product["quality_status"] == "degraded"
        assert "elevation_m" in product["missing_inputs"]


async def test_true_sea_level_is_not_treated_as_unknown_elevation(hop):
    product = await _request(hop, {"elevation_m": 0.0})
    assert product["method"] == "fao56_penman_monteith"
    assert product["quality_status"] == "validated"
    assert "elevation_m" not in product["missing_inputs"]


@pytest.mark.parametrize("field", ["t_max_c", "t_min_c", "lat_deg", "day_of_year"])
async def test_missing_core_reaches_owner_as_null_and_remains_insufficient(hop, field):
    product = await _request(hop, {field: None})
    assert product["method"] == "insufficient"
    assert product["quality_status"] == "insufficient"
    assert product["et0_mm"] is None
    assert field in product["missing_inputs"]


@pytest.mark.parametrize(
    "overrides, rejected",
    [
        ({"t_max_c": 10.0, "t_min_c": 20.0}, {"t_max_c", "t_min_c"}),
        ({"lat_deg": 95.0}, {"lat_deg"}),
        ({"day_of_year": 400}, {"day_of_year"}),
    ],
)
async def test_invalid_core_is_not_a_validated_number_after_http(hop, overrides, rejected):
    product = await _request(hop, overrides)
    assert product["et0_mm"] is None
    assert product["quality_status"] == "invalid"
    assert rejected <= set(product["invalid_inputs"])


async def test_true_zero_is_a_number_and_not_a_missing_temperature(hop):
    product = await _request(
        hop, {"t_min_c": 0.0, "t_max_c": 0.0, "t_mean_c": 0.0, "solar_rad_mj_m2": None}
    )
    assert product["et0_mm"] == 0.0
    assert product["et0_mm"] is not None
    assert product["method"] == "hargreaves_fallback"
    assert "t_min_c" not in product["missing_inputs"]
    assert "t_max_c" not in product["missing_inputs"]


async def test_service_identity_and_tenant_are_forwarded_by_production_client(hop):
    await _request(hop, tenant_id="tenant-b")
    assert hop[0]["headers"]["x-tenant-id"] == "tenant-b"
    assert hop[0]["headers"]["x-agent-token"] == "et0-hop-service-token"


async def test_no_tenant_does_not_create_an_implicit_tenant(hop):
    await _request(hop, tenant_id=None)
    assert "x-tenant-id" not in hop[0]["headers"]


async def test_missing_valid_time_and_snapshot_are_not_invented_by_client(hop):
    product = await _request(hop, {"valid_time": None, "weather_snapshot_id": None})
    assert product["valid_time"] is None
    assert product["weather_snapshot_id"].startswith("wsnap/")
    assert any("valid_time not supplied" in item for item in product["limitations"])


@pytest.fixture(scope="module")
def bff_app():
    # Import the real registered handlers and request models; no AST extraction,
    # copied endpoint or replacement api.main module. The fresh app only avoids
    # unrelated middleware/lifespan/database work outside this boundary test.
    from api.routers import irrigation_recommendation
    from api.routers import water_balance as route
    from core.canonical_schemas import UserRole, UserSchema

    app = FastAPI()
    app.include_router(route.router)
    app.include_router(irrigation_recommendation.router)
    user = UserSchema(
        user_id="et0-hop-user", tenant_id="et0-hop-tenant", role=UserRole.OWNER, name_ar="اختبار"
    )
    app.dependency_overrides[route.get_current_user] = lambda: user
    return app


def _bff_body():
    body = {
        key: value
        for key, value in _BASE.items()
        if key not in {"lat_deg", "t_mean_c", "valid_time", "weather_snapshot_id"}
    }
    return {**body, "crop": "wheat", "rain_mm": 0.0, "latitude_deg": _BASE["lat_deg"]}


async def _bff_post(app, body, path="/api/v1/water-balance"):
    async with _HTTPX_CLIENT(
        transport=httpx.ASGITransport(app=app), base_url="http://platform-bff.test"
    ) as session:
        return await session.post(path, json=body)


@pytest.mark.parametrize(
    "missing",
    [
        (),
        ("solar_rad_mj_m2",),
        ("rh_mean_pct",),
        ("wind_2m_ms",),
        ("solar_rad_mj_m2", "rh_mean_pct", "wind_2m_ms"),
    ],
)
async def test_real_bff_route_consumes_real_weather_http_result(bff_app, hop, missing):
    body = _bff_body()
    for field in missing:
        body[field] = None
    response = await _bff_post(bff_app, body)
    assert response.status_code == 200
    assert len(hop) == 1
    event = hop[0]
    assert event["path"] == "/v1/weather/agro/et0" and event["status"] == 200
    assert event["headers"]["x-tenant-id"] == "et0-hop-tenant"
    assert event["body"]["lat_deg"] == body["latitude_deg"]
    assert "latitude_deg" not in event["body"]
    for key in ("t_min_c", "t_max_c", "solar_rad_mj_m2", "rh_mean_pct", "wind_2m_ms"):
        assert event["body"][key] == body[key]
    owner = event["response"]
    assert owner["derived_from"] == "canonical_weather_state"
    assert owner["method"] == ("hargreaves_fallback" if missing else "fao56_penman_monteith")
    assert response.json()["et0_mm"] == round(owner["et0_mm"], 2)
    assert response.json()["method"] == owner["method"]


async def test_real_bff_translates_actual_owner_invalid_core_to_named_422(bff_app, hop):
    response = await _bff_post(bff_app, {**_bff_body(), "t_max_c": 10.0, "t_min_c": 20.0})
    assert len(hop) == 1
    assert hop[0]["status"] == 200
    owner = hop[0]["response"]
    assert owner["et0_mm"] is None and owner["quality_status"] == "invalid"
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["reason_code"] == "invalid_weather_inputs"
    assert detail["invalid_inputs"] == owner["invalid_inputs"]
    assert detail["limitations"] == owner["limitations"]


async def test_real_bff_keeps_actual_thermal_zero_as_zero(bff_app, hop):
    response = await _bff_post(
        bff_app, {**_bff_body(), "t_min_c": 0.0, "t_max_c": 0.0, "solar_rad_mj_m2": None}
    )
    assert response.status_code == 200 and len(hop) == 1
    assert hop[0]["response"]["et0_mm"] == 0.0
    assert response.json()["et0_mm"] == 0.0
    assert response.json()["method"] == "hargreaves_fallback"


async def test_real_bff_missing_required_temperature_is_422_before_weather_call(bff_app, hop):
    body = _bff_body()
    del body["t_min_c"]
    response = await _bff_post(bff_app, body)
    assert response.status_code == 422
    assert hop == []
    assert any(item["loc"] == ["body", "t_min_c"] for item in response.json()["detail"])


async def test_real_bff_uses_authenticated_tenant_not_an_extra_body_claim(bff_app, hop):
    response = await _bff_post(bff_app, {**_bff_body(), "tenant_id": "forged-tenant"})
    assert response.status_code == 200 and len(hop) == 1
    assert hop[0]["headers"]["x-tenant-id"] == "et0-hop-tenant"
    assert "tenant_id" not in hop[0]["body"]


_WEATHER_FIELDS = (
    "t_min_c",
    "t_max_c",
    "solar_rad_mj_m2",
    "rh_mean_pct",
    "wind_2m_ms",
    "latitude_deg",
    "elevation_m",
    "day_of_year",
)
_MODEL_FIELDS = [
    (name, field)
    for name in ("WaterBalanceRequest", "IrrigationRecommendationRequest", "FieldIrrigationRequest")
    for field in _WEATHER_FIELDS
    if name != "FieldIrrigationRequest" or field not in ("latitude_deg", "elevation_m")
]


def _weather_request_model(name):
    from api import irrigation_models, water_balance_models

    return getattr(
        water_balance_models if name == "WaterBalanceRequest" else irrigation_models, name
    )


@pytest.mark.parametrize("model_name,field", _MODEL_FIELDS)
@pytest.mark.parametrize("value", [False, True, "1"])
def test_bff_weather_models_refuse_bool_and_numeric_strings(model_name, field, value):
    from pydantic import ValidationError

    model = _weather_request_model(model_name)
    with pytest.raises(ValidationError) as error:
        model(**{"crop": "wheat", "t_min_c": 0, "t_max_c": 0, field: value})
    assert any(item["loc"] == (field,) for item in error.value.errors())


@pytest.mark.parametrize("model_name,field", _MODEL_FIELDS)
def test_bff_weather_models_keep_real_numeric_zero(model_name, field):
    model = _weather_request_model(model_name)
    value = 1 if field == "day_of_year" else 0
    result = model(**{"crop": "wheat", "t_min_c": 0, "t_max_c": 0, field: value})
    assert getattr(result, field) == value
    assert not isinstance(getattr(result, field), bool)


@pytest.mark.parametrize("field", _WEATHER_FIELDS)
@pytest.mark.parametrize("value", [False, True, "1"])
@pytest.mark.parametrize("path", ["/api/v1/water-balance", "/api/v1/irrigation-recommendation"])
async def test_real_bff_weather_coercion_is_rejected_before_weather_call(
    bff_app, hop, field, value, path
):
    response = await _bff_post(bff_app, {**_bff_body(), field: value}, path)
    assert response.status_code == 422
    assert hop == []
    assert any(item["loc"] == ["body", field] for item in response.json()["detail"])


@pytest.mark.parametrize(
    "model_name",
    ["WaterBalanceRequest", "IrrigationRecommendationRequest", "FieldIrrigationRequest"],
)
def test_bff_day_of_year_requires_integer_type(model_name):
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        _weather_request_model(model_name)(crop="wheat", t_min_c=0, t_max_c=0, day_of_year=1.0)


@pytest.mark.parametrize(
    "model_name",
    ["WaterBalanceRequest", "IrrigationRecommendationRequest", "FieldIrrigationRequest"],
)
def test_bff_weather_optional_unknowns_and_existing_defaults_are_preserved(model_name):
    result = _weather_request_model(model_name)(crop="wheat", t_min_c=0, t_max_c=0)
    for field in ("solar_rad_mj_m2", "rh_mean_pct", "wind_2m_ms"):
        assert getattr(result, field) is None
    if model_name == "FieldIrrigationRequest":
        assert result.day_of_year is None
    else:
        # Legacy site/altitude/day defaults are unchanged by this type-only fix.
        # This test does not claim those defaults are observations or calibrated.
        assert (result.latitude_deg, result.elevation_m, result.day_of_year) == (15.5, 2000.0, 100)


@pytest.mark.parametrize("model_name,field", _MODEL_FIELDS)
@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_bff_weather_models_reject_nonfinite_with_json_safe_input(model_name, field, value):
    from pydantic import ValidationError

    with pytest.raises(ValidationError) as error:
        _weather_request_model(model_name)(
            **{"crop": "wheat", "t_min_c": 0, "t_max_c": 0, field: value}
        )
    details = error.value.errors()
    assert any(item["loc"] == (field,) and item["type"] == "finite_number" for item in details)
    assert all(isinstance(item["input"], str) for item in details)
    json.dumps(details, allow_nan=False)


@pytest.mark.parametrize("field", _WEATHER_FIELDS)
@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
@pytest.mark.parametrize("path", ["/api/v1/water-balance", "/api/v1/irrigation-recommendation"])
async def test_raw_nonfinite_json_is_bff_422_before_weather_call(bff_app, hop, field, value, path):
    # HTTPX's json= rejects these values itself. Raw bytes exercise the actual
    # permissive JSON decoder -> request-model validation -> error serialization.
    raw = json.dumps({**_bff_body(), field: value})
    async with _HTTPX_CLIENT(
        transport=httpx.ASGITransport(app=bff_app), base_url="http://platform-bff.test"
    ) as session:
        response = await session.post(
            path, content=raw, headers={"Content-Type": "application/json"}
        )
    assert response.status_code == 422
    assert hop == []
    errors = response.json()["detail"]
    assert any(
        item["loc"] == ["body", field] and item["type"] == "finite_number" for item in errors
    )
    assert all(isinstance(item["input"], str) for item in errors)
    json.dumps(response.json(), allow_nan=False)


@pytest.mark.parametrize(
    "model_name",
    ["WaterBalanceRequest", "IrrigationRecommendationRequest", "FieldIrrigationRequest"],
)
def test_multiple_nonfinite_weather_fields_keep_individual_safe_locations(model_name):
    from pydantic import ValidationError

    model = _weather_request_model(model_name)
    fields = [field for name, field in _MODEL_FIELDS if name == model_name]
    with pytest.raises(ValidationError) as error:
        model(**{"crop": "wheat", **{field: float("nan") for field in fields}})
    details = error.value.errors()
    assert {item["loc"] for item in details} == {(field,) for field in fields}
    assert all(item["type"] == "finite_number" and item["input"] == "nan" for item in details)
    json.dumps(details, allow_nan=False)


def test_owner_and_bff_models_share_the_same_numeric_contract(weather_app):
    import weather_runtime

    from shared.weather_input_contract import Et0Number, Et0WeatherInput

    assert weather_runtime.Et0Number is Et0Number
    models = [
        weather_runtime.Et0ProductRequest,
        weather_runtime.Et0SeriesRequest,
        *[
            _weather_request_model(name)
            for name in (
                "WaterBalanceRequest",
                "IrrigationRecommendationRequest",
                "FieldIrrigationRequest",
            )
        ],
    ]
    for model in models:
        assert Et0WeatherInput in model.__bases__
        assert (
            model.reject_nonfinite_weather_values.__func__
            is Et0WeatherInput.reject_nonfinite_weather_values.__func__
        )


@pytest.mark.parametrize(
    "field",
    [
        "daily_t_min",
        "daily_t_max",
        "daily_solar_rad_mj_m2",
        "daily_rh_mean_pct",
        "daily_wind_2m_ms",
        "lat_deg",
        "elevation_m",
        "day_of_year_start",
    ],
)
@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
async def test_weather_series_nonfinite_http_is_json_safe_with_sample_location(
    weather_app, field, value
):
    daily = field.startswith("daily_")
    payload = {field: [0, value] if daily else value}
    raw = json.dumps(payload)
    async with _HTTPX_CLIENT(
        transport=httpx.ASGITransport(app=weather_app), base_url="http://weather-owner.test"
    ) as session:
        response = await session.post(
            "/v1/weather/agro/et0/series", content=raw, headers={"Content-Type": "application/json"}
        )
    assert response.status_code == 422
    expected = ["body", field, 1] if daily else ["body", field]
    errors = response.json()["detail"]
    assert any(item["loc"] == expected and item["type"] == "finite_number" for item in errors)
    assert all(isinstance(item["input"], str) for item in errors)
    json.dumps(response.json(), allow_nan=False)
