from __future__ import annotations

import importlib.util
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

MODULE_PATH = Path(__file__).resolve().parents[1] / "main.py"
spec = importlib.util.spec_from_file_location("indicators_service_main", MODULE_PATH)
assert spec and spec.loader
main = importlib.util.module_from_spec(spec)
spec.loader.exec_module(main)
client = TestClient(main.app)


def test_indicators_service_reports_canonical_adapter_readiness():
    response = client.get("/readyz")
    assert response.status_code == 200
    ready = response.json()
    assert ready["status"] == "ready"
    assert ready["implemented_runtime"] is True
    assert ready["runtime_role"] == "canonical-observation-adapter"
    assert ready["spectral_compute"] is False
    assert ready["observed_spectral_owner"] == "raster-service"


def test_indicator_compute_fails_closed_not_fabricated():
    response = client.post("/v1/indicators/compute")
    assert response.status_code == 409
    assert "raster-service" in response.json()["detail"]


def test_canonical_catalog_is_published():
    response = client.get("/v1/indicators/catalog")
    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "canonical-indicator-ownership-manifest"
    assert any(
        item["id"] == "ndvi" and item["owner"] == "raster-service" for item in body["indicators"]
    )


# ── OI-01: the internal hop binds the tenant to a verified identity ─────────────────────
#
# ``/observations`` used to accept a bare ``X-Tenant-Id`` and forward it to raster-service
# together with the service's own privileged ``SAHOOL_AGENT_TOKEN``: any peer on the
# internal network could read another tenant's observations without holding any secret.
# The tenant is now accepted only from a mesh caller that proves the service token, or
# from a bearer whose identity (resolved by the platform, the session owner) has that tenant.

_TENANT = "11111111-1111-4111-8111-111111111111"
_OTHER_TENANT = "22222222-2222-4222-8222-222222222222"
_SERVICE_TOKEN = "test-mesh-token"


def _observation(acquired: str):
    import observation_runtime  # main.py put the service dir on sys.path

    bundle = {
        "field_id": "fld_a",
        "observations": {
            "ndvi": {
                "real_data": True,
                "date": acquired,
                "stats": {"mean": 0.61},
                "coverage_ratio": 0.94,
                "valid_pixel_ratio": 0.91,
                "cloud_cover": 0.04,
                "indicator_product": {
                    "provenance": {
                        "scene_id": "S2A_TEST_SCENE",
                        "algorithm_version": "2.1.0",
                        "acquisition_datetime": acquired,
                    }
                },
            }
        },
    }
    return observation_runtime.canonicalize_bundle(
        bundle=bundle, tenant_id=main.UUID(_TENANT), season_id="sea_2026"
    )


class _Recorder:
    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.seen: list[httpx.Request] = []
        self.identity: dict = {
            "status": 200,
            "user": {"tenant_id": _TENANT, "permissions": ["field:view"]},
        }


@pytest.fixture
def upstream(monkeypatch):
    """Record every call that would reach raster-service with the service token."""
    rec = _Recorder()

    async def _fetch(*, field_id, tenant_id, season_id, indicators):
        rec.calls.append({"field_id": field_id, "tenant_id": str(tenant_id)})
        return _observation("2026-10-15T07:35:29Z")

    monkeypatch.setenv("SAHOOL_AGENT_TOKEN", _SERVICE_TOKEN)
    monkeypatch.setattr(main, "fetch_canonical_observations", _fetch)
    return rec


@pytest.fixture
def platform_identity(monkeypatch, upstream):
    """Stand in for the platform's ``/api/v1/auth/me`` at the HTTP transport boundary."""

    def _handler(request: httpx.Request) -> httpx.Response:
        upstream.seen.append(request)
        assert request.url.path == "/api/v1/auth/me"
        if upstream.identity["status"] != 200:
            return httpx.Response(upstream.identity["status"], json={"detail": "denied"})
        return httpx.Response(200, json={"user": upstream.identity["user"]})

    real_client = httpx.AsyncClient

    def _client(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(_handler)
        return real_client(*args, **kwargs)

    monkeypatch.setattr(main.httpx, "AsyncClient", _client)
    return upstream


def _get(path: str = "/v1/fields/fld_a/observations", params=None, **headers):
    return client.get(path, params=params or {"season_id": "sea_2026"}, headers=headers)


def test_observations_reject_bare_tenant_header(upstream):
    response = _get(**{"X-Tenant-Id": _TENANT})
    assert response.status_code == 401
    assert upstream.calls == []


def test_observations_reject_wrong_service_token(upstream):
    response = _get(**{"X-Tenant-Id": _TENANT, "X-Agent-Token": "guessed"})
    assert response.status_code == 401
    assert upstream.calls == []


def test_observations_fail_closed_when_service_token_unset(upstream, monkeypatch):
    monkeypatch.setenv("SAHOOL_AGENT_TOKEN", "")
    response = _get(**{"X-Tenant-Id": _TENANT, "X-Agent-Token": ""})
    assert response.status_code == 503
    assert upstream.calls == []


def test_observations_accept_mesh_service_token(upstream):
    response = _get(**{"X-Tenant-Id": _TENANT, "X-Agent-Token": _SERVICE_TOKEN})
    assert response.status_code == 200
    assert upstream.calls == [{"field_id": "fld_a", "tenant_id": _TENANT}]


def test_observations_bearer_cannot_spoof_another_tenant(platform_identity):
    response = _get(**{"X-Tenant-Id": _OTHER_TENANT, "Authorization": "Bearer user-a"})
    assert response.status_code == 403
    assert platform_identity.calls == []
    assert platform_identity.seen[0].headers["authorization"] == "Bearer user-a"


def test_observations_bearer_bound_to_verified_tenant(platform_identity):
    response = _get(**{"X-Tenant-Id": _TENANT, "Authorization": "Bearer user-a"})
    assert response.status_code == 200
    assert platform_identity.calls == [{"field_id": "fld_a", "tenant_id": _TENANT}]


def test_observations_bearer_requires_field_view(platform_identity):
    platform_identity.identity["user"] = {"tenant_id": _TENANT, "permissions": ["chat:use"]}
    response = _get(**{"X-Tenant-Id": _TENANT, "Authorization": "Bearer user-a"})
    assert response.status_code == 403
    assert platform_identity.calls == []


def test_observations_bearer_rejected_by_platform(platform_identity):
    platform_identity.identity["status"] = 401
    response = _get(**{"X-Tenant-Id": _TENANT, "Authorization": "Bearer expired"})
    assert response.status_code == 401
    assert platform_identity.calls == []


# ── EXTRA-7: a requested temporal extent is enforced, never relabelled as latest ─────────
#
# Raster-service serves the latest bundle only. A January request used to receive an
# October observation with no trace of the mismatch; the window is now checked against
# the actual acquisition and both extents are returned.

_MESH = {"X-Tenant-Id": _TENANT, "X-Agent-Token": _SERVICE_TOKEN}


def test_observations_reject_latest_outside_requested_window(upstream):
    response = _get(
        params={"season_id": "sea_2026", "date_from": "2026-01-01", "date_to": "2026-01-31"},
        **_MESH,
    )
    assert response.status_code == 424
    detail = response.json()["detail"]
    assert detail["code"] == "observation_outside_requested_window"
    assert detail["requested_temporal_extent"] == {
        "date_from": "2026-01-01",
        "date_to": "2026-01-31",
    }
    assert detail["actual_temporal_extent"]["start"].startswith("2026-10-15")


def test_observations_report_requested_and_actual_extent(upstream):
    response = _get(
        params={"season_id": "sea_2026", "date_from": "2026-10-01", "date_to": "2026-10-15"},
        **_MESH,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["temporal_selection"] == "latest"
    assert body["requested_temporal_extent"] == {
        "date_from": "2026-10-01",
        "date_to": "2026-10-15",
    }
    assert body["actual_temporal_extent"]["start"].startswith("2026-10-15")
    assert body["actual_temporal_extent"]["end"].startswith("2026-10-15")


def test_observations_without_window_declare_latest(upstream):
    response = _get(**_MESH)
    assert response.status_code == 200
    body = response.json()
    assert body["temporal_selection"] == "latest"
    assert body["requested_temporal_extent"] is None
    assert body["actual_temporal_extent"]["start"].startswith("2026-10-15")


@pytest.mark.parametrize(
    "window",
    [
        {"date_from": "2026-02-01", "date_to": "2026-01-01"},
        {"date_from": "not-a-date"},
    ],
)
def test_observations_reject_invalid_window(upstream, window):
    response = _get(params={"season_id": "sea_2026", **window}, **_MESH)
    assert response.status_code == 422
    assert upstream.calls == []
