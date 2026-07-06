"""حارس: تفكيك raster main.py (phase2–5) موصولٌ بالكامل — لا رمز مُستخرَج معلَّق.

الجذر (رُصِد أثناء دمج phase5): التفكيك نقل مُعالِجات إلى وحدات شقيقة لكن نسي وصلها
بـmain: (١) ``raster_asset_persistence`` لم يُستورَد فاختفى ``main._persist_raster_asset``/
``_is_valid_field_id_text`` بينما ``raster_job_orchestration`` يستدعي
``ctx._persist_raster_asset`` ⇒ AttributeError على كلّ حفظ؛ (٢) سطر كتب
``_fieldctx._layers`` (اسم غير مُعرَّف + مخزن خاطئ) بدل ``ctx._field_layers``.

هذا الحارس يستورد ``main`` فعليّاً ويؤكّد أنّ كلّ رمز يشير إليه العامل/الراوترات عبر
``main.*``، وكلّ ``ctx.<attr>`` تستعمله وحدات التفكيك، موجودٌ فعلاً على main — فيسقط CI
إن تُرِك أيّ استخراج لاحق بلا وصل. نقيّ (استيراد فقط، بلا شبكة/قاعدة).
"""

from __future__ import annotations

import importlib
import re
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

RASTER = Path(__file__).resolve().parents[1] / "services" / "raster-service"
_DECOMP_MODULES = (
    "raster_job_orchestration",
    "scene_policy",
    "stac_search",
    "raster_asset_persistence",
    "raster_date_geo",
    "cdse_singleflight",
    "layer_lookup",
    "tile_cache_io",
)
# رموز يعتمدها عامل الـbackfill/الراوترات عبر main.* (اختفاؤها = كسر صامت وقت التشغيل).
_WORKER_CONTRACT = (
    "_persist_raster_asset",
    "_is_valid_field_id_text",
    "_select_backfill_scenes_by_policy",
    "_stac_search",
    "_run_processing",
    "_field_layers",
    "_layers",
)


@pytest.fixture(scope="module")
def _main():
    # عزل: خدمات أخرى (sam2/modbus) تستورد main.py خاصّتها فتشغل sys.modules['main']
    # قبل هذا الاختبار في الجناح الكامل. نُزيح الوحدة الأجنبيّة، نستورد main راستر
    # طازجاً (RASTER أوّل المسار لاستيراد الوحدات الشقيقة)، ثمّ نُعيد الأجنبيّة كما كانت.
    saved = sys.modules.pop("main", None)
    sys.path.insert(0, str(RASTER))
    try:
        yield importlib.import_module("main")
    finally:
        if str(RASTER) in sys.path:
            sys.path.remove(str(RASTER))
        sys.modules.pop("main", None)
        if saved is not None:
            sys.modules["main"] = saved


def test_main_exposes_worker_and_test_contract(_main):
    missing = [s for s in _WORKER_CONTRACT if not hasattr(_main, s)]
    assert not missing, f"main فقد رموزاً يعتمدها العامل/الاختبارات بعد التفكيك: {missing}"


def test_every_ctx_attr_used_by_decomposition_resolves_on_main(_main):
    missing: dict[str, list[str]] = {}
    for mod in _DECOMP_MODULES:
        src = (RASTER / f"{mod}.py").read_text(encoding="utf-8")
        attrs = set(re.findall(r"\bctx\.([A-Za-z_][A-Za-z0-9_]*)", src))
        bad = sorted(a for a in attrs if not hasattr(_main, a))
        if bad:
            missing[mod] = bad
    assert not missing, f"وحدات التفكيك تشير إلى رموز غير موجودة على main (ctx.*): {missing}"


def test_no_undefined_fieldctx_alias(_main):
    # الاسم الخاطئ _fieldctx يجب ألّا يعود (استُبدِل بـctx._field_layers).
    for mod in _DECOMP_MODULES:
        src = (RASTER / f"{mod}.py").read_text(encoding="utf-8")
        assert "_fieldctx" not in src, f"{mod}: اسم غير مُعرَّف _fieldctx عاد للظهور"
