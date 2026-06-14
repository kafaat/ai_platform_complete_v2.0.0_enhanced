"""vegetation /v1/analyze يفضّل NDVI الحقيقيّ من raster-service (مع ارتداد آمن).

سدّ فجوة Raster→NDVI من التدقيق المعماريّ (بإذن صريح): بطاقة الصحّة كانت تعرض
NDVI تقديريّاً تركيبيّاً؛ الآن تُفضّل NDVI الحقيقيّ البكسليّ من raster عند توفّره،
وتُوسَم المصادر بصدق. fail-safe مطلق: أيّ تعذّر ⇒ ارتداد للتقدير (السلوك لا يسوء).

اختباران: (A) تعاقُد على المصدر (يُنفَّذ في CI بلا fastapi)، (B) سلوكيّ يثبّت
الاستبدال والوسم والارتداد (يتخطّى إن غاب fastapi في بيئة CI الخفيفة).
"""

from __future__ import annotations

import importlib.util
import os
import re

import pytest

pytestmark = pytest.mark.unit  # CI يشغّل -m unit؛ بلا الوسم لا يُنفَّذ

ROOT = os.path.join(os.path.dirname(__file__), "..")
VEG = os.path.join(ROOT, "services/vegetation-analysis-service/main.py")


def _src() -> str:
    with open(VEG, encoding="utf-8") as f:
        return f.read()


def _func_src(name: str) -> str:
    src = _src()
    start = src.index(f"async def {name}(")
    nxt = re.search(r"\n(?:@\w|async def |def |class )", src[start + 1 :])
    end = (start + 1 + nxt.start()) if nxt else len(src)
    return src[start:end]


# ── (A) تعاقُد على المصدر — يُنفَّذ في CI دائماً (لا يستورد الوحدة) ──
def test_run_analysis_prefers_real_ndvi():
    body = _func_src("run_analysis")
    assert "_real_ndvi_mean_from_raster" in body, "لا يستدعي مصدر NDVI الحقيقيّ من raster"
    assert "ndvi_is_real" in body
    assert 'indices["ndvi"] = round(real_ndvi' in body, "لا يستبدل قيمة NDVI بالحقيقيّة"
    assert '"real_data": ndvi_is_real' in body, "real_data لا يعكس مصدر NDVI"
    # وسم المصدر لكلّ مؤشّر (NDVI حقيقيّ، الباقي تقدير)
    assert '"source"' in body and "raster-service" in body


def test_helper_is_failsafe():
    body = _func_src("_real_ndvi_mean_from_raster")
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
    spec = importlib.util.spec_from_file_location("veg_main_test", VEG)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)

    async def _noop_meta(*a, **k):
        return {}

    async def _noop_pub(*a, **k):
        return None

    m.fetch_from_sentinel_hub = _noop_meta
    m.fetch_from_cdse = _noop_meta
    m._publish_analysis = _noop_pub
    return m


async def test_real_ndvi_used_and_labeled(veg):
    async def _r(field_id):
        return 0.77

    veg._real_ndvi_mean_from_raster = _r
    res = await veg.run_analysis("field_01", "t1", "2026-06-01", "2026-06-10")
    assert res["indices"]["ndvi"]["value"] == 0.77
    assert res["indices"]["ndvi"]["source"] == "raster-service"
    assert res["indices"]["evi"]["source"] == "estimate"  # الباقي تقدير
    assert res["real_data"] is True
    assert res["data_source"] == "raster-service"


async def test_fallback_to_estimate_when_raster_absent(veg):
    async def _none(field_id):
        return None

    veg._real_ndvi_mean_from_raster = _none
    res = await veg.run_analysis("field_01", "t1", "2026-06-01", "2026-06-10")
    # السلوك الحاليّ محفوظ تماماً: تقدير مُعلَّم، لا حقيقيّ
    assert res["real_data"] is False
    assert res["indices"]["ndvi"]["source"] == "estimate"
