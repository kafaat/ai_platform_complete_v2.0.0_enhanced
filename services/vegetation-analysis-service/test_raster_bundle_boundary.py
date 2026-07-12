from __future__ import annotations

import sys
from pathlib import Path

import pytest

SERVICE_DIR = Path(__file__).resolve().parent
if str(SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(SERVICE_DIR))

import vegetation_runtime as vr  # noqa: E402


class _Response:
    status_code = 200

    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


@pytest.mark.asyncio
async def test_bundle_client_propagates_tenant_and_service_token(monkeypatch):
    seen = {}

    class Client:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def get(self, url, *, params, headers):
            seen.update(url=url, params=params, headers=headers)
            return _Response(
                {
                    "real_data": True,
                    "bundle_consistency": True,
                    "mixed_scene": False,
                    "observations": {"ndvi": {}},
                }
            )

    monkeypatch.setattr(vr.httpx, "AsyncClient", Client)
    monkeypatch.setattr(vr, "RASTER_SERVICE_TOKEN", "service-token")
    result = await vr._real_observation_bundle_from_raster("field-1", "tenant-1", ["ndvi", "ndmi"])

    assert result is not None
    assert seen["headers"] == {
        "X-Tenant-Id": "tenant-1",
        "X-Agent-Token": "service-token",
    }
    assert seen["params"]["indices"] == "ndvi,ndmi"


@pytest.mark.asyncio
async def test_bundle_client_rejects_mixed_scene(monkeypatch):
    class Client:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def get(self, *args, **kwargs):
            return _Response({"real_data": True, "bundle_consistency": False, "mixed_scene": True})

    monkeypatch.setattr(vr.httpx, "AsyncClient", Client)
    monkeypatch.setattr(vr, "RASTER_SERVICE_TOKEN", "service-token")
    assert await vr._real_observation_bundle_from_raster("field-1", "tenant-1", ["ndvi"]) is None


def test_vegetation_runtime_has_no_provider_credentials():
    source = Path(vr.__file__).read_text(encoding="utf-8")
    for forbidden in (
        "SH_CLIENT_ID",
        "SH_CLIENT_SECRET",
        "COPERNICUS_USER",
        "COPERNICUS_PASSWORD",
        "_get_sh_token",
        "fetch_from_cdse",
    ):
        assert forbidden not in source
