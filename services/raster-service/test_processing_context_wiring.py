"""حارس تشغيليّ: سياق المعالجة يحمل كلّ السجلّات التي يقيّدها الأنبوب.

الجذر (بلاغ حيّ 2026-07-07، سجلّ عامل backfill): ``make_processing_context`` أسند
``ctx._layers`` لكن نسي ``ctx._field_layers``، فرمى ``raster_job_orchestration.run_processing``
(السطر: ``ctx._field_layers.setdefault(field_id, []).append(layer_id)``)
``AttributeError: 'types.SimpleNamespace' object has no attribute '_field_layers'`` على
**كلّ** تشغيلة معالجة/backfill لحقل ⇒ تبقى التشغيلات عالقة و«الشهر الحاليّ فقط» في الخطّ الزمنيّ.

هذا الحارس يُنشئ السياق فعليّاً ويؤكّد أنّ ``_field_layers`` موجود وهو نفس السجلّ المشترَك
الذي يقرأه القرّاء (لا نسخة منفصلة)، فأيّ انحدار مماثل يُكشَف بلا رفع خدمات.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit

raster_processing_runtime = pytest.importorskip("raster_processing_runtime")
import raster_runtime_state  # noqa: E402


def test_processing_context_exposes_field_layers_shared_registry():
    ctx = raster_processing_runtime.make_processing_context(upload_dir="/tmp/raster_ctx_test")
    # الحقلان اللذان يقيّدهما run_processing على كلّ معالجة لحقل.
    assert hasattr(ctx, "_layers"), "ctx._layers مفقود"
    assert hasattr(ctx, "_field_layers"), (
        "ctx._field_layers مفقود — run_processing يرمي AttributeError على كلّ معالجة لحقل"
    )
    # نفس singleton المشترَك (القرّاء يعتمدون رؤية ما يكتبه العامل).
    assert ctx._layers is raster_runtime_state.LAYERS
    assert ctx._field_layers is raster_runtime_state.FIELD_LAYERS


def test_processing_context_field_layers_is_writable_like_pipeline():
    """يُحاكي السطر المُعطِل: setdefault ثمّ append لا يرمي."""
    ctx = raster_processing_runtime.make_processing_context(upload_dir="/tmp/raster_ctx_test")
    fid = "fld_ctx_wiring_guard"
    try:
        ctx._field_layers.setdefault(fid, []).append("lyr_test")
        assert "lyr_test" in ctx._field_layers[fid]
    finally:
        ctx._field_layers.pop(fid, None)
