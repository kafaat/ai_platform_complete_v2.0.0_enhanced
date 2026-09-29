"""vegetation /v1/analyze مستهلك RIV صارم عبر Observation Bundle واحد من raster-service.

حدود الحاويات الثلاث (20260712): vegetation لا تحمل اعتمادات مزوّد ولا تجلب مباشرة،
وتستهلك **حزمة مشاهدة واحدة** tenant-scoped من raster-service (بدل 7 طلبات مفردة) عبر
`_real_observation_bundle_from_raster` (X-Agent-Token + X-Tenant-Id)، وترفض الحزم مختلطة
المشاهد وتفشل مُغلَقاً 424 عند غياب NDVI موثَّق — لا جلب مزوّد ولا تقدير تركيبيّ.

اختباران: (A) تعاقُد ساكن على المصدر (يُنفَّذ في CI بلا fastapi)، (B) سلوكيّ يثبّت
الوسم الصادق للمصادر والفشل المُغلَق (يتخطّى إن غاب fastapi في بيئة CI الخفيفة).
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import subprocess
import sys
from unittest.mock import AsyncMock

import pytest

pytestmark = pytest.mark.unit  # CI يشغّل -m unit؛ بلا الوسم لا يُنفَّذ

ROOT = os.path.join(os.path.dirname(__file__), "..")
VEG = os.path.join(ROOT, "services/vegetation-analysis-service/main.py")
# P1 decomposition: المنطق انتقل إلى vegetation_runtime.py الشقيقة — نفحص الملفّين معاً.
VEG_RT = os.path.join(ROOT, "services/vegetation-analysis-service/vegetation_runtime.py")


def _src() -> str:
    with open(VEG, encoding="utf-8") as f:
        src = f.read()
    with open(VEG_RT, encoding="utf-8") as f:
        src += "\n" + f.read()
    return src


def _func_src(name: str) -> str:
    src = _src()
    start = src.index(f"async def {name}(")
    nxt = re.search(r"\n(?:@\w|async def |def |class )", src[start + 1 :])
    end = (start + 1 + nxt.start()) if nxt else len(src)
    return src[start:end]


# ── (A) تعاقُد ساكن على المصدر — يُنفَّذ في CI دائماً (لا يستورد الوحدة) ──
def test_run_analysis_consumes_single_observation_bundle():
    body = _func_src("run_analysis")
    # حزمة واحدة بدل 7 طلبات: لا asyncio.gather على مؤشّرات مفردة.
    assert "_real_observation_bundle_from_raster" in body, "لا يستهلك حزمة المشاهدة الواحدة"
    assert "asyncio.gather" not in body, "لا يزال يجلب المؤشّرات بطلبات متوازية مفردة"
    # RS-3 cutover: المصدر يُوسَم ديناميكيّاً (canonical أو raster-service) مع ارتداد fail-closed لـ"raster-service".
    assert 'index_sources[public_name] = str(bundle.get("source") or "raster-service")' in body, (
        "لا يَسِم المصدر الحقيقيّ"
    )
    # فشل مُغلَق: حزمة غير متّسقة/غائبة ⇒ 424، وغياب NDVI ⇒ 424.
    assert "consistent validated canonical observation is required" in body
    assert "validated real NDVI is required from raster-service" in body
    # لا جلب مزوّد مباشر داخل vegetation (خرق حدود الحاويات).
    assert "fetch_from_sentinel_hub" not in body and "fetch_from_cdse" not in body
    assert '"source": index_sources.get(k' in body, "لا يَسِم مصدر كلّ مؤشّر من index_sources"


def test_raster_real_index_map_excludes_lai_cwsi():
    src = _src()
    # الأسماء الدلاليّة الحاملة محفوظة (EVI/SAVI⇐MSAVI/NDMI⇐moisture)، وlai/cwsi مستثناة.
    m = re.search(r"_RASTER_REAL_INDEX\s*=\s*\{([^}]*)\}", src)
    assert m, "خريطة _RASTER_REAL_INDEX غير موجودة"
    mapping = m.group(1)
    for real_idx in ("evi", "savi", "ndmi"):
        assert f'"{real_idx}"' in mapping, f"{real_idx} يجب أن يكون مؤشّراً حقيقيّاً"
    for est_idx in ("lai", "cwsi"):
        assert f'"{est_idx}"' not in mapping, f"{est_idx} يجب أن يبقى تفسيراً لا رصداً"


def test_bundle_consumer_is_token_scoped_and_failsafe():
    body = _func_src("_real_observation_bundle_from_raster")
    assert "RASTER_SERVICE_TOKEN" in body, "لا يشترط توكن الخدمة الداخليّ (fail-closed بدونه)"
    assert "X-Agent-Token" in body and "X-Tenant-Id" in body, "لا يمرّر هويّة/مستأجراً موثَّقاً"
    assert "indicator-observation-bundle" in body, "لا يطلب نقطة الحزمة الموحّدة"
    # ترفض الحزم مختلطة المشاهد / غير المتّسقة / غير الحقيقيّة.
    assert 'data.get("mixed_scene")' in body and 'data.get("bundle_consistency")' in body
    # fail-safe: يلتقط الاستثناء ويرتدّ None بلا رفع.
    assert "except Exception" in body
    assert body.rstrip().endswith("return None")


def test_no_provider_credentials_in_runtime():
    src = _src()
    # حدود الأسرار: لا اعتمادات Sentinel Hub/CDSE/Copernicus في runtime vegetation.
    for secret in (
        "SH_CLIENT_SECRET",
        "CDSE_CLIENT_SECRET",
        "COPERNICUS_PASSWORD",
        "_get_sh_token",
    ):
        assert secret not in src, f"سرّ/دالّة مزوّد مسرّبة في vegetation: {secret}"


# ── (B) سلوكيّ — يتخطّى إن غاب fastapi (بيئة CI الخفيفة لا تثبّته) ──
@pytest.fixture(scope="module")
def veg():
    pytest.importorskip("fastapi")
    pytest.importorskip("jwt")
    pytest.importorskip("httpx")
    pytest.importorskip("prometheus_client")
    import sys as _sys

    _svc_dir = os.path.dirname(VEG)
    if _svc_dir not in _sys.path:
        _sys.path.insert(0, _svc_dir)
    _stale = _sys.modules.get("vegetation_runtime")
    if _stale is not None and os.path.dirname(getattr(_stale, "__file__", "") or "") != _svc_dir:
        _sys.modules.pop("vegetation_runtime", None)
    spec = importlib.util.spec_from_file_location("veg_main_test", VEG)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    m = _sys.modules["vegetation_runtime"]

    async def _noop_pub(*a, **k):
        return None

    m._publish_analysis = _noop_pub
    return m


@pytest.fixture
def canonical_unavailable(veg, monkeypatch):
    """Exercise the raster fallback with a controlled unavailable canonical service."""
    adapter = AsyncMock(return_value=None)
    monkeypatch.setattr(veg, "_canonical_observation_bundle_from_indicators", adapter)
    return adapter


# runtime-truth (20260712): FIELD_REGISTRY is empty and load_field returns None unless the
# tenant-scoped platform catalog is reachable — the behavioral tests inject the field fixture
# explicitly via monkeypatch (function-scoped, so it never leaks to other test modules that
# exercise the real load_field).
async def _fixture_field(field_id, tenant_id=None):
    return {
        "name": "حقل اختبار",
        "bbox": [45.5, 15.0, 45.6, 15.1],
        "area_ha": 20.0,
        "crop": "wheat",
    }


def _bundle(mean: float = 0.77) -> dict:
    """حزمة مشاهدة متّسقة (مشهد واحد) بأسماء المؤشّرات الراستريّة."""
    obs = {}
    for raster_name in ("ndvi", "evi", "msavi", "moisture", "msi", "ndwi", "gndvi"):
        obs[raster_name] = {
            "stats": {"mean": mean},
            "indicator_product": {
                "quality_score": 0.9,
                "valid_pixel_ratio": 0.95,
                "provenance": {
                    "scene_id": "S2_ABC",
                    "acquisition_datetime": "2026-06-05T10:00:00Z",
                },
            },
        }
    return {
        "source": "raster-service",
        "real_data": True,
        "mixed_scene": False,
        "bundle_consistency": True,
        "acquisition_dates": ["2026-06-05"],
        "observations": obs,
    }


async def test_indices_labeled_raster_source_from_bundle(veg, monkeypatch, canonical_unavailable):
    monkeypatch.setattr(veg, "load_field", _fixture_field)

    async def _b(field_id, tenant_id, raster_indices):
        return _bundle(0.77)

    monkeypatch.setattr(veg, "_real_observation_bundle_from_raster", _b)
    res = await veg.run_analysis("field_01", "t1", "2026-06-01", "2026-06-10")
    canonical_unavailable.assert_awaited_once()
    for public_idx in ("ndvi", "evi", "savi", "ndmi"):
        assert res["indices"][public_idx]["value"] == 0.77
        assert res["indices"][public_idx]["source"] == "raster-service"
    assert res["indices"]["lai"]["source"] == "vegetation-model"
    assert res["indices"]["water_stress"]["source"] == "vegetation-interpretation"
    assert "cwsi" not in res["indices"]
    assert res["real_data"] is True
    assert res["data_source"] == "raster-service"


async def test_fails_closed_424_when_bundle_absent(veg, monkeypatch, canonical_unavailable):
    """غياب/عدم اتّساق الحزمة ⇒ 424 فشلاً مُغلَقاً — لا ارتداد تقديريّاً."""
    from fastapi import HTTPException

    monkeypatch.setattr(veg, "load_field", _fixture_field)

    async def _none(field_id, tenant_id, raster_indices):
        return None

    monkeypatch.setattr(veg, "_real_observation_bundle_from_raster", _none)
    with pytest.raises(HTTPException) as exc:
        await veg.run_analysis("field_01", "t1", "2026-06-01", "2026-06-10")
    assert exc.value.status_code == 424
    canonical_unavailable.assert_awaited_once()


# ── القفزة indicators-service ⇒ vegetation: عقدُ Decimal يعبر الشبكة نصّاً ──────────────
#
# **المقيس حيّاً (2026-09-29):** ``/v1/analyze`` أجاب 424 «validated real NDVI is required from
# raster-service» لكلّ حقل، ولـNDVI رصدٌ حقيقيّ (0.1243). ``CanonicalObservationV1`` يحمل
# ``summary.mean`` وحقولَ الجودة ``Decimal``، وPydantic يُسلسِلها نصّاً (``"0.1243"``)، والمُحوِّلُ
# يمرّرها كما هي، و``run_analysis`` يقبل ``int``/``float`` وحدهما ⇒ NDVI يُسقَط. الشاهدُ السابق
# (``_bundle``) مرّ لأنّه قاموسٌ منسوخ بأرقام ``float``. هنا الردُّ ناتجُ مسار indicators-service
# نفسِه: ``canonicalize_bundle`` ⇒ ``field_observations`` ⇒ ``model_dump(mode="json")``.

_INDICATORS = os.path.join(ROOT, "services", "indicators-service", "main.py")
_TENANT = "11111111-1111-4111-8111-111111111111"


async def _indicators_service_response(field_id: str, season_id: str) -> dict:
    """ما يُجيب به ``GET /v1/fields/{id}/observations`` فعلاً — بلا شبكة، بالمُنتِج الحقيقيّ."""
    spec = importlib.util.spec_from_file_location("veg_test_indicators_main", _INDICATORS)
    indicators = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(indicators)  # يُدرج دليلَه في sys.path ويستورد observation_runtime

    import observation_runtime

    # حزمةُ الراستر (مُدخَلُ المُنتِج) بشكل ``field_indicator_observation_bundle`` — رصدٌ واحد.
    raster_bundle = {
        "field_id": field_id,
        "real_data": True,
        "bundle_consistency": True,
        "mixed_scene": False,
        "observations": {
            "ndvi": {
                "real_data": True,
                "date": "2026-09-25T07:46:00Z",
                "stats": {"min": 0.1243, "max": 0.1243, "mean": 0.1243},
                "valid_pixel_ratio": 1.0,
                "coverage_ratio": 1.0,
                "confidence": 0.9,
                "indicator_product": {
                    "provenance": {
                        "scene_id": "S2B_MSIL2A_20260925T073609_N0511_R092_T38PNA",
                        "acquisition_datetime": "2026-09-25T07:46:00Z",
                        "algorithm_version": "sahool.band_math/1",
                    }
                },
            }
        },
    }

    async def _canonical(*, field_id, tenant_id, season_id, indicators):
        return observation_runtime.canonicalize_bundle(
            bundle=raster_bundle, tenant_id=tenant_id, season_id=season_id
        )

    indicators.fetch_canonical_observations = _canonical
    body = await indicators.field_observations(
        field_id, season_id=season_id, indicators="ndvi", x_tenant_id=_TENANT
    )
    assert body["observations"], "المُنتِجُ لم يُصدِر رصداً — الشاهدُ أعمى"
    return body


class _IndicatorsClient:
    """يقوم مقام ``httpx.AsyncClient`` عند حدّ الشبكة وحدَه ويُعيد ردَّ المُنتِج كما هو."""

    body: dict = {}

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get(self, url, params=None, headers=None):
        assert url.endswith("/observations"), url
        body = type(self).body

        class _Response:
            status_code = 200

            @staticmethod
            def json():
                return body

        return _Response()


async def test_canonical_decimals_reach_the_analysis_as_numbers(veg, monkeypatch):
    from fastapi import HTTPException

    season = "unscoped-2026-09-29"
    _IndicatorsClient.body = await _indicators_service_response("fld_new", season)
    wire_mean = _IndicatorsClient.body["observations"][0]["summary"]["mean"]
    assert isinstance(wire_mean, str), "العقدُ لم يعد يُسلسِل Decimal نصّاً — راجع الشاهد"
    monkeypatch.setattr(veg.httpx, "AsyncClient", _IndicatorsClient)
    monkeypatch.setattr(veg, "VEGETATION_PREFER_CANONICAL_OBSERVATIONS", True)
    monkeypatch.setattr(veg, "load_field", _fixture_field)

    bundle = await veg._canonical_observation_bundle_from_indicators(
        "fld_new", _TENANT, season, ["ndvi"]
    )
    ndvi = bundle["observations"]["ndvi"]
    assert ndvi["stats"]["mean"] == pytest.approx(0.1243)
    assert ndvi["indicator_product"]["quality_score"] == pytest.approx(0.9)
    assert ndvi["indicator_product"]["valid_pixel_ratio"] == pytest.approx(1.0)

    # التطوير: التحليلُ يعود بـNDVI الحقيقيّ بدل 424 «لا NDVI».
    monkeypatch.setattr(veg, "VEGETATION_REAL_ONLY", False)
    res = await veg.run_analysis("fld_new", _TENANT, "2026-09-01", "2026-09-29", season_id=season)
    assert res["indices"]["ndvi"]["value"] == pytest.approx(0.124)
    # الإنتاج: 424 يبقى — لكنّه حكمُ بوّابة الجودة المُعلَن لا «NDVI غائب». الرقعةُ لا تُرخي البوّابة.
    monkeypatch.setattr(veg, "VEGETATION_REAL_ONLY", True)
    with pytest.raises(HTTPException) as exc:
        await veg.run_analysis("fld_new", _TENANT, "2026-09-01", "2026-09-29", season_id=season)
    assert exc.value.status_code == 424
    assert exc.value.detail == "validated real NDVI is required in production vegetation mode"


# ── القفزة raster-service ⇒ vegetation لـ``/v1/ndvi/current`` ─────────────────────────────
#
# **المقيس حيّاً (2026-09-29):** ``/v1/ndvi/current`` أجاب 424 ``RASTER_RESPONSE_INVALID`` لكلّ
# حقلٍ له NDVI حقيقيّ. المُستهلِك يقرأ ``value``/``ndvi`` والمالكُ يُصدِر ``mean``، ويشترط
# ``scene_id`` والنقطةُ لا تحمله. ولمّا حُمِّلت النقطةُ نَسَبَها ظهر ما تحته: مسارُ CDSE كان
# يكتب ``"<scene>:<index>"`` فتصير حزمةُ المشاهدة ``mixed_scene`` لكلّ حقلٍ عولِج به.
#
# المُنتِجُ هنا **مسارُ المالك الحقيقيّ كاملاً** في عمليّةٍ مستقلّة (``routers`` و``db_persist``
# أسماءٌ تتنازعها الخدمات في جلسة pytest واحدة): ``_run_cdse_processing`` ⇒ المعالجةُ ⇒ الطبقة ⇒
# ``field_timeseries`` و``field_indicator_observation_bundle``. المستبدَلُ حدُّ الشبكة وحدَه:
# عميلُ CDSE يُعيد GeoTIFF حقيقيّاً لكلّ مؤشّر. بلا قاعدة (وضعٌ مُعلَن في ``field_owner_tenant``).

_SCENE = "S2B_MSIL2A_20260925T073609_N0511_R092_T38PNA"
_RASTER_PRODUCER = r"""
import asyncio, json, os, sys
from datetime import UTC, datetime, timedelta

root, tenant, field, scene = sys.argv[1:5]
sys.path.insert(0, os.path.join(root, "services", "raster-service"))
sys.path.insert(0, root)
import numpy as np
import rasterio
from rasterio.transform import from_bounds

W, S, E, N = 44.20, 15.30, 44.21, 15.31
GEOM = {"type": "Polygon", "coordinates": [[[W, S], [E, S], [E, N], [W, N], [W, S]]]}
VALUES = {"ndvi": 0.1243, "ndmi": 0.05, "msi": 1.4}
ACQUIRED = (datetime.now(UTC) - timedelta(days=3)).strftime("%Y-%m-%dT07:46:00Z")


def geotiff(value):
    with rasterio.MemoryFile() as mem:
        with mem.open(driver="GTiff", height=32, width=32, count=1, dtype="float32",
                      crs="EPSG:4326", transform=from_bounds(W, S, E, N, 32, 32),
                      nodata=float("nan")) as dst:
            dst.write(np.full((32, 32), value, dtype="float32"), 1)
        return mem.read()


class CdseNetworkBoundary:
    def search_scenes(self, **_kw):
        return [{"id": scene, "datetime": ACQUIRED, "cloud_cover_pct": 3.0}]

    def process_index(self, *, index, **_kw):
        return geotiff(VALUES[index])


import cdse_client
cdse_client.get_client = lambda: CdseNetworkBoundary()
cdse_client.supported_indices = lambda: set(VALUES)
import raster_api_models
import raster_field_runtime
from raster_security_context import REQ_TENANT
from routers import fields

raster_field_runtime._run_cdse_processing("job-producer", field, raster_api_models.ProcessCdseRequest(
    tenant_id=tenant, indicators=list(VALUES), bbox=[W, S, E, N], geometry=GEOM))


async def produce():
    REQ_TENANT.set(tenant)
    timeseries = await fields.field_timeseries(field, index="ndvi", dates="", grid=16)
    bundle = await fields.field_indicator_observation_bundle(
        field, indices="ndvi,moisture,msi", date="latest", grid=16,
        x_agent_token=os.environ["SAHOOL_AGENT_TOKEN"])
    return {"timeseries": timeseries, "bundle": bundle}


print("PRODUCED " + json.dumps(asyncio.run(produce()), default=str))
"""


def _raster_owner_output(tmp_path, *, tenant: str, field: str) -> dict:
    script = tmp_path / "raster_producer.py"
    script.write_text(_RASTER_PRODUCER, encoding="utf-8")
    uploads = tmp_path / "rasters"
    uploads.mkdir()
    env = {k: v for k, v in os.environ.items() if k not in ("DATABASE_URL", "JOBS_DATABASE_URL")}
    env.update(RASTER_UPLOAD_DIR=str(uploads), SAHOOL_AGENT_TOKEN="producer-token")
    run = subprocess.run(
        [sys.executable, str(script), os.path.abspath(ROOT), tenant, field, _SCENE],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        timeout=180,
        check=False,
    )
    produced = [ln for ln in run.stdout.splitlines() if ln.startswith("PRODUCED ")]
    assert produced, f"مُنتِجُ الراستر لم يُنتِج (rc={run.returncode}):\n{run.stderr[-3000:]}"
    output = json.loads(produced[-1][len("PRODUCED ") :])
    assert output["timeseries"].get("points"), (
        "المالكُ لم يُنتِج رصداً — الشاهدُ لا يقيس شيئاً:\n"
        f"{json.dumps(output['timeseries'], ensure_ascii=False)[:800]}\n{run.stdout[-3000:]}"
    )
    return output


class _RasterClient:
    """يقوم مقام ``httpx.AsyncClient`` عند حدّ الشبكة وحدَه — يُعيد ردَّ المالك كما أنتجه."""

    timeseries: dict = {}

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get(self, url, params=None, headers=None):
        assert url.endswith("/timeseries") and (params or {}).get("index") == "ndvi", url
        body = type(self).timeseries

        class _Response:
            status_code = 200

            @staticmethod
            def json():
                return body

        return _Response()


async def test_current_ndvi_reads_the_point_the_raster_owner_produces(veg, monkeypatch, tmp_path):
    pytest.importorskip("rasterio")
    field = "fld_ndvi_current"
    owner = _raster_owner_output(tmp_path, tenant=_TENANT, field=field)

    # المالك: مشهدٌ واحد لكلّ المؤشّرات، ونَسَبُه على النقطة وفي الحزمة.
    point = owner["timeseries"]["points"][-1]
    assert point["mean"] == pytest.approx(0.1243)
    assert point["scene_id"] == _SCENE, "النقطةُ لا تحمل نَسَبَ مشهدِها (أو تحمله بلاحقة المؤشّر)"
    bundle = owner["bundle"]
    assert bundle["scene_ids"] == [_SCENE] and bundle["mixed_scene"] is False, bundle["scene_ids"]

    # المُستهلِك: ما أنتجه المالكُ نفسُه يصير NDVI الحاليّ — لا 424.
    _RasterClient.timeseries = owner["timeseries"]
    monkeypatch.setattr(veg.httpx, "AsyncClient", _RasterClient)
    observed, code = await veg._current_ndvi_from_raster(field, tenant_id=_TENANT)
    assert code == "OK", code
    assert observed["value"] == pytest.approx(0.1243)
    assert observed["scene_id"] == _SCENE
    assert observed["observed_at"] == point["datetime"]
    assert observed["valid_pixel_pct"] == pytest.approx(100.0)
