"""vegetation /v1/analyze يفضّل المؤشّرات الحقيقيّة من raster-service (مع ارتداد آمن).

سدّ فجوة Raster→indices من التدقيق المعماريّ: المؤشّرات كانت تقديريّة تركيبيّة؛ الآن
تُفضَّل القيم الحقيقيّة البكسليّة من raster band_math عند توفّرها — لـNDVI + EVI +
SAVI(MSAVI2) + NDMI(moisture) — وتُوسَم المصادر بصدق. fail-safe مطلق per-index: أيّ
تعذّر ⇒ ارتداد للتقدير المُعلَّم (السلوك لا يسوء). lai/cwsi تبقيان تقديراً (نموذج/LST).

اختباران: (A) تعاقُد على المصدر (يُنفَّذ في CI بلا fastapi)، (B) سلوكيّ يثبّت الاستبدال
والوسم والارتداد (يتخطّى إن غاب fastapi في بيئة CI الخفيفة).
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


# ── (A) تعاقُد على المصدر — يُنفَّذ في CI دائماً (لا يستورد الوحدة) ──
def test_run_analysis_prefers_real_indices():
    body = _func_src("run_analysis")
    assert "_real_index_mean_from_raster" in body, "لا يستدعي مصدر المؤشّر الحقيقيّ من raster"
    assert "_RASTER_REAL_INDEX" in body, "لا يستعمل خريطة المؤشّرات الحقيقيّة"
    assert "asyncio.gather" in body, "لا يجلب القيم الحقيقيّة بالتوازي"
    assert "ndvi_is_real" in body
    assert "indices[_vk] = round(_rv" in body, "لا يستبدل قيمة المؤشّر بالحقيقيّة"
    assert 'index_sources[_vk] = "raster-service"' in body, "لا يَسِم المصدر الحقيقيّ"
    assert '"real_data": ndvi_is_real' in body, "real_data لا يعكس مصدر NDVI"
    assert '"source": index_sources.get(k' in body, "لا يَسِم مصدر كلّ مؤشّر من index_sources"


def test_raster_real_index_map_excludes_lai_cwsi():
    src = _src()
    # الخريطة تشمل EVI/SAVI/NDMI الحقيقيّة، وتستثني lai/cwsi (تبقيان تقديراً بصدق).
    m = re.search(r"_RASTER_REAL_INDEX\s*=\s*\{([^}]*)\}", src)
    assert m, "خريطة _RASTER_REAL_INDEX غير موجودة"
    mapping = m.group(1)
    for real_idx in ("evi", "savi", "ndmi"):
        assert f'"{real_idx}"' in mapping, f"{real_idx} يجب أن يكون مؤشّراً حقيقيّاً"
    for est_idx in ("lai", "cwsi"):
        assert f'"{est_idx}"' not in mapping, f"{est_idx} يجب أن يبقى تقديراً (نموذج/LST)"


def test_helper_is_failsafe():
    body = _func_src("_real_index_mean_from_raster")
    assert "VEGETATION_PREFER_RASTER" in body, "لا يحترم مفتاح التفعيل/الإيقاف"
    assert 'data.get("real_data")' in body, "لا يتحقّق من real_data من raster"
    # الارتداد الآمن: يلتقط Exception ويُنهي بـreturn None (لا يصعد فيكسر التحليل)
    assert "except Exception" in body, "لا يلتقط الاستثناء (ليس fail-safe)"
    assert body.rstrip().endswith("return None"), "لا يرتدّ None عند التعذّر"


# ── (B) سلوكيّ — يتخطّى إن غاب fastapi (بيئة CI الخفيفة لا تثبّته) ──
@pytest.fixture(scope="module")
def veg():
    pytest.importorskip("fastapi")
    pytest.importorskip("jwt")
    pytest.importorskip("httpx")
    pytest.importorskip("prometheus_client")
    # P1 decomposition: main.py يستورد وحدة شقيقة (*_runtime) — يجب أن يكون
    # مجلّد الخدمة على sys.path قبل exec_module.
    import sys as _sys

    _svc_dir = os.path.dirname(VEG)
    if _svc_dir not in _sys.path:
        _sys.path.insert(0, _svc_dir)
    # عزل: نسخة شقيقة قديمة (خدمة أخرى/بيئة سابقة) في sys.modules تُفسد الاستيراد.
    _stale = _sys.modules.get("vegetation_runtime")
    if _stale is not None and os.path.dirname(getattr(_stale, "__file__", "") or "") != _svc_dir:
        _sys.modules.pop("vegetation_runtime", None)
    spec = importlib.util.spec_from_file_location("veg_main_test", VEG)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    # P1 decomposition: run_analysis وخطافات الجلب تعيش في vegetation_runtime — الحقن
    # على وحدة الواجهة لا يصل globals المنطق؛ نحقن ونُرجِع وحدة الـruntime نفسها.
    m = _sys.modules["vegetation_runtime"]

    async def _noop_meta(*a, **k):
        return {}

    async def _noop_pub(*a, **k):
        return None

    m.fetch_from_sentinel_hub = _noop_meta
    m.fetch_from_cdse = _noop_meta
    m._publish_analysis = _noop_pub
    return m


async def test_real_indices_used_and_labeled(veg):
    # المنفذ الحقيقيّ يُرجِع الآن غلافاً (dict) فيه المتوسّط + النوعيّة/المصدر
    # (ValidatedIndicatorProduct) بدل float مجرّد — WS-A. القيمة تبقى تحت "mean".
    async def _r(field_id, raster_index="ndvi"):
        return {
            "mean": 0.77,
            "quality_score": 0.9,
            "valid_pixel_ratio": 0.95,
            "provenance": None,
            "estimated": False,
        }

    veg._real_index_mean_from_raster = _r
    res = await veg.run_analysis("field_01", "t1", "2026-06-01", "2026-06-10")
    # المؤشّرات الأربعة صارت حقيقيّة (raster-service)
    for real_idx in ("ndvi", "evi", "savi", "ndmi"):
        assert res["indices"][real_idx]["value"] == 0.77
        assert res["indices"][real_idx]["source"] == "raster-service"
    # الزيادة المُسلَّمة (VEG-AGRIAI): عند توفّر NDVI حقيقيّ يُشتقّ LAI منه بنموذج موثَّق
    # (خوارزميّة + uncertainty) فيُوسم "vegetation-model" — أصدق من "estimate"؛ CWSI يبقى تقديراً.
    assert res["indices"]["lai"]["source"] == "vegetation-model"
    assert res["indices"]["cwsi"]["source"] == "estimate"
    assert res["real_data"] is True
    assert res["data_source"] == "raster-service"


async def test_fallback_to_estimate_when_raster_absent(veg):
    async def _none(field_id, raster_index="ndvi"):
        return None

    veg._real_index_mean_from_raster = _none
    res = await veg.run_analysis("field_01", "t1", "2026-06-01", "2026-06-10")
    # السلوك الحاليّ محفوظ تماماً: تقدير مُعلَّم، لا حقيقيّ
    assert res["real_data"] is False
    assert res["indices"]["ndvi"]["source"] == "estimate"
    assert res["indices"]["evi"]["source"] == "estimate"
