import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

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


_GEOMETRY = {
    "type": "Polygon",
    "coordinates": [[[44, 15], [44.01, 15], [44.01, 15.01], [44, 15.01], [44, 15]]],
}


async def _trigger(monkeypatch, client_cls):
    import httpx

    client_cls.calls = []
    monkeypatch.setattr(httpx, "AsyncClient", client_cls)
    auto = ImageryAutomation()
    return await auto.trigger_field_imagery_processing(
        field_id="fld_real",
        tenant_id="00000000-0000-0000-0000-000000000001",
        bbox=[44.0, 15.0, 44.01, 15.01],
        geometry=_GEOMETRY,
        reason="field.created",
        indicators=["ndvi", "ndre"],
    )


def _element84_calls(calls):
    """أيّ طلبٍ إلى مسار Element84 (بحث المشهد الأفضل أو المعالجة من STAC)."""
    return [
        c for c in calls if c[1].endswith("/process-from-stac") or c[1].endswith("/imagery/best")
    ]


@pytest.mark.asyncio
async def test_a_cdse_failure_is_a_provider_failure_not_an_element84_fallback(monkeypatch):
    """كان تعذّر CDSE يسقط **صامتاً** إلى Element84 (imagery/best + process-from-stac).

    المسار محجوب الآن (``radiometry_containment``)، وتعذّر المزوّد يُبلَّغ كما هو: لا «لا
    مشهد»، ولا ارتداد إلى المسار المحجوب. ``_FakeClient.post`` يرمي على حمولة process-cdse
    (لا ``indicator`` مفرد فيها) فيُمثّل تعذّر CDSE.
    """
    result = await _trigger(monkeypatch, _FakeClient)

    assert result["status"] == "provider_failed"
    assert result["provider"] == "cdse"
    assert result["queued"] is False and result["real_data"] is False
    assert _element84_calls(_FakeClient.calls) == [], "ارتدادٌ إلى مسار Element84 المحجوب"


class _CdseUnavailableClient(_FakeClient):
    async def post(self, url, **kwargs):
        self.calls.append(("POST", url, kwargs))
        if url.endswith("/process-cdse"):
            return _Resp({"provider": "cdse", "available": False, "queued": False})
        return _Resp({"job_id": "job_should_not_exist", "status": "pending"})


@pytest.mark.asyncio
async def test_cdse_unavailable_reports_radiometry_unresolved_without_calling_element84(
    monkeypatch,
):
    """بلا CDSE مُهيّأ لا مسار صالح: النتيجة ``radiometry_unresolved`` ولا طلب raster لـElement84."""
    result = await _trigger(monkeypatch, _CdseUnavailableClient)

    assert result["status"] == "radiometry_unresolved"
    assert result["provider"] == "element84"
    assert result["queued"] is False and result["real_data"] is False
    assert _element84_calls(_CdseUnavailableClient.calls) == []


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
