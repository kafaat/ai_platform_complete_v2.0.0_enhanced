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
import os
import re

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


async def test_indices_labeled_raster_source_from_bundle(veg, monkeypatch):
    monkeypatch.setattr(veg, "load_field", _fixture_field)

    async def _b(field_id, tenant_id, raster_indices):
        return _bundle(0.77)

    monkeypatch.setattr(veg, "_real_observation_bundle_from_raster", _b)
    res = await veg.run_analysis("field_01", "t1", "2026-06-01", "2026-06-10")
    for public_idx in ("ndvi", "evi", "savi", "ndmi"):
        assert res["indices"][public_idx]["value"] == 0.77
        assert res["indices"][public_idx]["source"] == "raster-service"
    assert res["indices"]["lai"]["source"] == "vegetation-model"
    assert res["indices"]["water_stress"]["source"] == "vegetation-interpretation"
    assert "cwsi" not in res["indices"]
    assert res["real_data"] is True
    assert res["data_source"] == "raster-service"


async def test_fails_closed_424_when_bundle_absent(veg, monkeypatch):
    """غياب/عدم اتّساق الحزمة ⇒ 424 فشلاً مُغلَقاً — لا ارتداد تقديريّاً."""
    from fastapi import HTTPException

    monkeypatch.setattr(veg, "load_field", _fixture_field)

    async def _none(field_id, tenant_id, raster_indices):
        return None

    monkeypatch.setattr(veg, "_real_observation_bundle_from_raster", _none)
    with pytest.raises(HTTPException) as exc:
        await veg.run_analysis("field_01", "t1", "2026-06-01", "2026-06-10")
    assert exc.value.status_code == 424
