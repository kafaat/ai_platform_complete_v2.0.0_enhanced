import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services" / "sahool-platform"))

from api.imagery_automation import ImageryAutomation  # noqa: E402


class _Resp:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


class _FakeClient:
    calls = []

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, url, **kwargs):
        self.calls.append(("GET", url, kwargs))
        return _Resp(
            {
                "best": {
                    "item_id": "S2_SCENE_REAL",
                    "datetime": "2026-06-20T08:00:00Z",
                    "bands_urls": {
                        "red": "https://example.invalid/red.tif",
                        "nir": "https://example.invalid/nir.tif",
                        "green": "https://example.invalid/green.tif",
                        "blue": "https://example.invalid/blue.tif",
                        "rededge1": "https://example.invalid/rededge.tif",
                        "swir16": "https://example.invalid/swir1.tif",
                        "swir22": "https://example.invalid/swir2.tif",
                        "scl": "https://example.invalid/scl.tif",
                    },
                },
                "candidates": 1,
            }
        )

    async def post(self, url, **kwargs):
        self.calls.append(("POST", url, kwargs))
        return _Resp({"job_id": f"job_{kwargs['json']['indicator']}", "status": "pending"})


@pytest.mark.asyncio
async def test_trigger_field_imagery_processing_queues_process_from_stac(monkeypatch):
    import httpx

    _FakeClient.calls = []
    monkeypatch.setattr(httpx, "AsyncClient", _FakeClient)

    auto = ImageryAutomation()
    result = await auto.trigger_field_imagery_processing(
        field_id="fld_real",
        tenant_id="00000000-0000-0000-0000-000000000001",
        bbox=[44.0, 15.0, 44.01, 15.01],
        geometry={
            "type": "Polygon",
            "coordinates": [[[44, 15], [44.01, 15], [44.01, 15.01], [44, 15.01], [44, 15]]],
        },
        reason="field.created",
        indicators=["ndvi", "ndre"],
    )

    assert result["queued"] is True
    assert result["real_data"] is False  # becomes true only when raster-service reads generated COG
    post_calls = [c for c in _FakeClient.calls if c[0] == "POST"]
    assert len(post_calls) == 2
    for _, url, kwargs in post_calls:
        assert url.endswith("/v1/fields/fld_real/process-from-stac")
        body = kwargs["json"]
        assert body["tenant_id"] == "00000000-0000-0000-0000-000000000001"
        assert body["scene_id"] == "S2_SCENE_REAL"
        assert body["band_hrefs"]["red"].endswith("red.tif")
        assert body["band_hrefs"]["nir"].endswith("nir.tif")
        assert body["clip_polygon_geojson"]["type"] == "Polygon"


def test_band_hrefs_normalize_stac_asset_names():
    scene = {
        "bands_urls": {
            "rededge1": "re.tif",
            "swir16": "s1.tif",
            "swir22": "s2.tif",
            "red": "r.tif",
            "nir08": "n.tif",
        }
    }
    out = ImageryAutomation._band_hrefs_from_scene(scene)
    assert out["rededge"] == "re.tif"
    assert out["swir1"] == "s1.tif"
    assert out["swir2"] == "s2.tif"
    assert out["nir"] == "n.tif"
