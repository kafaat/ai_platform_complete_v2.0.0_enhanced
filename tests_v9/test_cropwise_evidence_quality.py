"""Behavioral regressions from the source/research comparison; no live services."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from uuid import UUID

import pytest

pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


B = load("cropwise_baseline", "services/vegetation-analysis-service/baseline_engine.py")
A = load("cropwise_anomaly", "services/vegetation-analysis-service/anomaly_engine.py")
T = load("cropwise_timeline", "services/indicators-service/observation_timeline.py")


def entries(values):
    return [
        {
            "observation_ref": f"obs{i}",
            "acquired_at": f"2026-07-{i:02}T00:00:00Z",
            "indicator": {"code": "ndvi"},
            "summary": {"mean": v},
            "observation_quality": {
                "gate_status": "passed",
                "valid_pixel_ratio": "0.9",
                "field_coverage_ratio": "0.9",
                "field_cloud_ratio": "0.1",
                "policy": {"use_case": "anomaly_detection"},
                "score": "0.9",
            },
        }
        for i, v in enumerate(values, 1)
    ]


def test_missing_quality_never_qualifies_for_detection():
    rows = T.canonicalize_timeseries(
        field_id="fld_probe",
        tenant_id=UUID(int=1),
        season_id="sea_probe",
        indicator_code="ndvi",
        points=[{"datetime": "2026-07-01", "mean": 0.6}, {"datetime": "2026-07-02", "mean": 0.3}],
    )
    assert rows[0].observation_quality.valid_pixel_ratio is None
    assert rows[0].observation_quality.gate_status != "passed"
    assert (
        B.build_baselines(
            field_id="fld_probe",
            indicator="ndvi",
            entries=[x.model_dump(mode="json") for x in rows],
        )
        == []
    )


def test_stage_reference_precedes_larger_unmatched_deviation():
    comparisons = B.build_baselines(
        field_id="fld_probe",
        indicator="ndvi",
        entries=entries([0.2, 0.3, 0.8, 0.7]),
        current_stage="flowering",
        stage_by_observation={"obs3": "flowering"},
    )
    result = A.detect_signals(
        field_id="fld_probe", indicator="ndvi", comparisons=[x.to_dict() for x in comparisons]
    )
    assert result[0].signal_type == "ndvi_decline"
    assert float(result[0].deviation_percent) == -12.5


def test_baseline_identity_binds_members_and_policy():
    kwargs = dict(field_id="fld_probe", indicator="ndvi", entries=entries([0.2, 0.3, 0.8, 0.7]))
    full = B.build_baselines(**kwargs, max_history=3)[1]
    short = B.build_baselines(**kwargs, max_history=1)[1]
    assert full.baseline_run_ref != short.baseline_run_ref


def test_geometry_alone_cannot_claim_productivity():
    from services.ai_agronomist.productivity_zones import propose_productivity_zones

    result = propose_productivity_zones({"bbox": [44, 16, 44.4, 16.4]})
    assert result["productivity_zones"] == []
    assert result["status"] == "insufficient_data"


def test_confidence_does_not_increase_with_severity():
    from decimal import Decimal

    assert A._confidence(Decimal(".7"), "critical", 4) == A._confidence(Decimal(".7"), "low", 4)


def test_display_policy_cannot_enter_detection():
    rows = entries([0.6, 0.4])
    for row in rows:
        row["observation_quality"]["policy"]["use_case"] = "timeline_display"
    assert B.build_baselines(field_id="fld_probe", indicator="ndvi", entries=rows) == []


def test_quiet_matched_stage_does_not_fall_back_to_seasonal_growth():
    comparisons = B.build_baselines(
        field_id="fld_probe",
        indicator="ndvi",
        entries=entries([0.2, 0.3, 0.7, 0.71]),
        current_stage="flowering",
        stage_by_observation={"obs3": "flowering"},
    )
    assert (
        A.detect_signals(
            field_id="fld_probe", indicator="ndvi", comparisons=[x.to_dict() for x in comparisons]
        )
        == []
    )


@pytest.mark.parametrize("mean", ["NaN", "Infinity", None])
def test_invalid_latest_value_cannot_reuse_an_older_alert(mean):
    assert (
        B.build_baselines(field_id="fld_probe", indicator="ndvi", entries=entries([0.6, 0.3, mean]))
        == []
    )


def test_missing_latest_quality_cannot_reuse_an_older_alert():
    rows = entries([0.6, 0.3, 0.4])
    rows[-1]["observation_quality"]["field_cloud_ratio"] = None
    assert B.build_baselines(field_id="fld_probe", indicator="ndvi", entries=rows) == []


def test_future_stale_and_gapped_history_are_not_assessed():
    from datetime import UTC, datetime

    for as_of in [datetime(2026, 6, 1, tzinfo=UTC), datetime(2026, 9, 1, tzinfo=UTC)]:
        assert (
            B.build_baselines(
                field_id="fld_probe", indicator="ndvi", entries=entries([0.6, 0.3]), as_of=as_of
            )
            == []
        )
    rows = entries([0.6, 0.3])
    rows[-1]["acquired_at"] = "2026-10-01T00:00:00Z"
    assert B.build_baselines(field_id="fld_probe", indicator="ndvi", entries=rows) == []


def test_zero_baseline_is_not_an_infinite_percentage_alert():
    comparisons = B.build_baselines(
        field_id="fld_probe", indicator="ndvi", entries=entries([0, 0.4])
    )
    assert (
        A.detect_signals(
            field_id="fld_probe", indicator="ndvi", comparisons=[x.to_dict() for x in comparisons]
        )
        == []
    )


def test_reprocessed_point_and_policy_change_identity():
    kwargs = dict(
        field_id="fld_probe", tenant_id=UUID(int=1), season_id="sea_probe", indicator_code="ndvi"
    )
    point = {
        "datetime": "2026-07-01",
        "mean": 0.6,
        "valid_pixel_ratio": 0.9,
        "coverage_ratio": 0.95,
        "cloud_pct": 2,
    }
    original = T.canonicalize_timeseries(**kwargs, points=[point])[0]
    changed = T.canonicalize_timeseries(**kwargs, points=[{**point, "mean": 0.61}])[0]
    assert original.observation_ref != changed.observation_ref
    assert original.lineage.input_hash != changed.lineage.input_hash


@pytest.mark.asyncio
async def test_timeline_uses_authorized_season_window(monkeypatch):
    import httpx

    calls = []

    async def handler(request):
        calls.append(request)
        if request.url.path.endswith("/seasons"):
            assert request.headers["Authorization"] == "Bearer owner"
            return httpx.Response(
                200,
                json=[
                    {
                        "field_id": "fld_probe",
                        "season_id": "sea_probe",
                        "sowing_date": "2026-07-01",
                        "season_end": "2026-07-10",
                    }
                ],
            )
        assert request.headers["X-Tenant-Id"] == str(UUID(int=1))
        return httpx.Response(
            200,
            json={
                "available": True,
                "real_data": True,
                "points": [
                    {"datetime": "2026-06-30", "mean": 0.9},
                    {"datetime": "2026-07-03", "mean": 0.5},
                    {"datetime": "2026-07-11", "mean": 0.2},
                ],
            },
        )

    original = httpx.AsyncClient
    monkeypatch.setattr(T, "RASTER_SERVICE_TOKEN", "test-token")
    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kw: original(transport=httpx.MockTransport(handler), **kw)
    )
    rows = await T.fetch_canonical_timeline(
        field_id="fld_probe",
        tenant_id=UUID(int=1),
        season_id="sea_probe",
        indicators=["ndvi"],
        authorization="Bearer owner",
    )
    assert [x.acquired_at.day for x in rows] == [3]
    assert len(calls) == 2
    with pytest.raises(RuntimeError, match="season_window_unavailable"):
        await T.fetch_canonical_timeline(
            field_id="fld_probe",
            tenant_id=UUID(int=1),
            season_id="invented",
            indicators=["ndvi"],
            authorization="Bearer owner",
        )
    assert len(calls) == 3  # Reject before any raster read.


def test_weekly_report_is_replayable_and_marks_unknown(monkeypatch):
    from datetime import UTC, datetime

    monkeypatch.setitem(sys.modules, "baseline_engine", B)
    monkeypatch.setitem(sys.modules, "anomaly_engine", A)
    weekly = load("cropwise_weekly", "services/vegetation-analysis-service/weekly_insights.py")
    rows = entries([0.6, 0.3])
    fields = [
        {"field_id": "fld_probe", "season_id": "sea_probe", "entries": rows},
        {"field_id": "fld_unknown", "season_id": "sea_probe", "entries": []},
    ]
    kwargs = dict(
        tenant_id=str(UUID(int=1)), week_end=datetime(2026, 7, 3, tzinfo=UTC), fields=fields
    )
    result = weekly.build_weekly_insights(**kwargs)
    assert [x["status"] for x in result["fields"]] == ["review_requested", "not_assessable"]
    assert result["fields"][0]["summary"]["ar"] and result["fields"][0]["summary"]["en"]
    rows[0]["observed_at"] = "2026-07-03T01:00:00Z"
    assert result["snapshot_sha256"] == weekly.build_weekly_insights(**kwargs)["snapshot_sha256"]
    assert result["delivery_status"] == "not_requested"
    assert result["persistence"] == "response_snapshot_only"


def test_change_grid_requires_spatial_identity_not_only_shape():
    from pydantic import ValidationError

    model = load("cropwise_raster_models", "services/raster-service/raster_api_models.py")
    identity = {
        "crs": "EPSG:32638",
        "transform": [10, 0, 400000, 0, -10, 1600000],
        "geometry_revision": 1,
        "rows": 2,
        "cols": 2,
    }
    data = dict(
        field_id="fld_probe",
        date_before="2026-07-01",
        date_after="2026-07-03",
        grid_before=[[0.5, 0.5], [0.5, None]],
        grid_after=[[0.3, 0.3], [0.3, None]],
        grid_before_identity=identity,
        grid_after_identity=identity,
    )
    model.ChangeDetectRequest(**data)
    for changes in [
        {"crs": "EPSG:4326"},
        {"geometry_revision": 2},
        {"transform": [10, 0, 400010, 0, -10, 1600000]},
    ]:
        with pytest.raises(ValidationError, match="spatial_identity_mismatch"):
            model.ChangeDetectRequest(**{**data, "grid_after_identity": {**identity, **changes}})
    with pytest.raises(ValidationError):
        model.ChangeDetectRequest(**{k: v for k, v in data.items() if not k.endswith("_identity")})


def test_change_percent_denominator_is_common_valid_pixels():
    change = load("cropwise_change", "services/raster-service/change_detection.py")
    result = change.detect_change([[0.8, None], [None, None]], [[0.2, 0.2], [0.2, 0.2]])
    assert result["percentage_denominator"] == "common_valid_pixels"
    assert result["degraded_grid_pct"] == 25.0


@pytest.mark.asyncio
async def test_task_acknowledgement_requires_persistence_evidence(monkeypatch):
    import httpx

    bridge = load(
        "cropwise_task_bridge", "services/vegetation-analysis-service/ground_verification_bridge.py"
    )
    original = httpx.AsyncClient

    async def handler(request):
        return httpx.Response(202, json={"task_id": "tsk_queued"})

    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kw: original(transport=httpx.MockTransport(handler), **kw)
    )
    with pytest.raises(RuntimeError, match="persistence_unconfirmed"):
        await bridge.GroundVerificationBridge("http://task-service").create_scouting_task(
            anomaly={"anomaly_ref": "anm_probe", "field_id": "fld_probe", "season_id": "sea_probe"},
            authorization="Bearer owner",
            idempotency_key="key",
        )


def test_weekly_report_http_authorization_and_wire_contract(tmp_path):
    """Boot the actual ASGI app in isolation; only external HTTP is replaced."""
    import os
    import subprocess

    script = r"""
import asyncio, json, time
import httpx, jwt
from fastapi.testclient import TestClient
import main
from routers import insights
secret = 's' * 64
token = jwt.encode({'sub': 'usr_test', 'tenant_id': '00000000-0000-0000-0000-000000000001',
    'iss': 'sahool-auth', 'aud': 'sahool', 'exp': int(time.time()) + 300,
    'iat': int(time.time()), 'token_type': 'access'}, secret, algorithm='HS256')
original = httpx.AsyncClient
seen = []
async def upstream(request):
    seen.append(request)
    assert request.headers['Authorization'] == 'Bearer ' + token
    assert request.headers['X-Tenant-Id'] == '00000000-0000-0000-0000-000000000001'
    if 'fld_foreign' in request.url.path:
        return httpx.Response(403)
    if 'fld_unavailable' in request.url.path:
        return httpx.Response(503)
    return httpx.Response(200, json={'entries': []})
httpx.AsyncClient = lambda **kw: original(transport=httpx.MockTransport(upstream), **kw)
client = TestClient(main.app)
url = '/v1/reports/weekly-field-insights'
body = {'fields': [{'field_id': 'fld_probe', 'season_id': 'sea_probe'}],
        'week_end': '2026-07-03T00:00:00Z'}
assert client.post(url, json=body).status_code == 401
assert not seen
headers = {'Authorization': 'Bearer ' + token}
response = client.post(url, json=body, headers=headers)
assert response.status_code == 200, response.text
assert response.json()['fields'][0]['status'] == 'not_assessable'
body['fields'][0]['field_id'] = 'fld_foreign'
assert client.post(url, json=body, headers=headers).status_code == 403
body['fields'][0]['field_id'] = 'fld_unavailable'
response = client.post(url, json=body, headers=headers)
assert response.json()['fields'][0]['reason_codes'] == ['canonical_source_unavailable']
body['fields'] *= 2
assert client.post(url, json=body, headers=headers).status_code == 422
"""
    env = {
        **os.environ,
        "JWT_SECRET": "s" * 64,
        "JWT_PUBLIC_KEY": "",
        "SAHOOL_ENV": "test",
        "VEGETATION_ANOMALY_STORE": "sqlite",
        "VEGETATION_ANOMALY_DB_PATH": str(tmp_path / "anomalies.db"),
        "PYTHONPATH": str(ROOT / "services/vegetation-analysis-service") + os.pathsep + str(ROOT),
    }
    result = subprocess.run(
        [sys.executable, "-c", script],
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_scouting_evaluation_counts_abstentions_and_rejects_field_leakage():
    module = load(
        "cropwise_evaluation", "services/vegetation-analysis-service/scouting_evaluation.py"
    )
    rows = [
        {"field_id": "a", "week": "2026-W28", "eligible": True, "score": 9, "needs_scouting": True},
        {
            "field_id": "b",
            "week": "2026-W28",
            "eligible": True,
            "score": 8,
            "needs_scouting": False,
        },
        {"field_id": "c", "week": "2026-W28", "eligible": False, "needs_scouting": True},
        {
            "field_id": "d",
            "week": "2026-W28",
            "eligible": True,
            "score": 10,
            "needs_scouting": None,
        },
    ]
    result = module.evaluate_scouting(field_weeks=rows, training_fields={"train"}, k=2)
    assert result["selected"] == 2 and result["selected_labeled"] == 1
    assert result["recall_at_k_labeled"] == 0.5
    assert result["eligible_coverage"] == 0.75
    assert result["selected_label_coverage"] == 0.5
    assert result["calibration_measured"] is False
    with pytest.raises(ValueError, match="training_field"):
        module.evaluate_scouting(field_weeks=rows, training_fields={"a"}, k=2)


def test_tiler_wrapper_has_local_and_object_storage_access_without_removing_legacy():
    import yaml

    services = yaml.safe_load((ROOT / "docker-compose.v9.yml").read_text(encoding="utf-8"))[
        "services"
    ]
    wrapper = services["raster-tiler-service"]
    assert "raster-data:/data/rasters:ro" in wrapper["volumes"]
    env = dict(item.split("=", 1) for item in wrapper["environment"])
    assert env["AWS_S3_ENDPOINT"] == services["sahool-titiler"]["environment"]["AWS_S3_ENDPOINT"]
    assert "RASTER_S3_ACCESS_KEY:?" in env["AWS_ACCESS_KEY_ID"]
    assert "RASTER_S3_SECRET_KEY:?" in env["AWS_SECRET_ACCESS_KEY"]
    assert services["sahool-titiler"]["profiles"] == ["legacy-tiler"]


def test_invalid_latest_raster_point_cannot_expose_an_older_alert():
    rows = T.canonicalize_timeseries(
        field_id="fld_probe",
        tenant_id=UUID(int=1),
        season_id="sea_probe",
        indicator_code="ndvi",
        points=[
            {"datetime": "2026-07-01", "mean": 0.6},
            {"datetime": "2026-07-02", "mean": 0.3},
            {"datetime": "2026-07-03", "mean": float("nan")},
        ],
    )
    assert rows == []
