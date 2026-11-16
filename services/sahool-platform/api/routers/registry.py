"""api/routers/registry.py — سجلّات الاستبطان (Introspection Registries)
========================================================================
شريحة من تفكيك ``api/main.py`` إلى وحدات ``APIRouter`` (نمط P0).

سلوك محفوظ بالكامل: مسارات/أذونات/مخرجات/مخطّط OpenAPI مطابقة تماماً لما كان
في ``main.py`` — نُقلت الدوالّ السبع حرفيّاً مع تغيير ``@app`` إلى ``@router``
(ثمّ أقعد W4-09 ثلاثاً منها؛ انظر التعليق فوق المسارات).

الاعتماديّات المشتركة (التبعيات/الأذونات) تبقى مُعرَّفة في ``api.main`` وتُستورَد
من هنا تفادياً لكسر ``_rebuild_pydantic_models`` واستيرادات الاختبارات. لتفادي
الاستيراد الدائريّ: ``api.main`` يستورد هذا الموجِّه في نهايته فقط (بعد تعريف كلّ
التبعيات/النماذج)، فيُحلّ الاستيراد.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from api.main import (
    Permission,
    UserSchema,
    require_permission,
)

router = APIRouter()


# ─── سجلّات الاستبطان (قراءة فقط، FIELD_VIEW) ─────────────────────────────
# W4-09 (routes-10) أقعد ثلاثةً من سبعة: report-fields · device-types ·
# data-quality-rules — بلا أيّ مستدعٍ (لا frontend ولا mobile ولا خدمة ولا SDK ولا
# nginx) ولا اختبار ولا سجلّ قدرات. وحداتها (report_builder · device_registry ·
# core/data_quality) باقية لمستهلكيها الحيّين داخل العمليّة. أمّا workflows · indices ·
# events فباقية: هي الجذر الوحيد القابل للتنفيذ لوحداتها في
# platform_module_reachability_guard، وحذفها يترك تلك الوحدات طرفيّةً في الأساس.
# إعادة أيّ مسار مُقعَد تمرّ بقرار ميزانية؛ يحرسها tests/test_w4_09_retired_dead_routes.py.
@router.get("/api/v1/registry/workflows")
def list_registry_workflows(
    user: UserSchema = Depends(require_permission(Permission.FIELD_VIEW)),
):
    """تعريفات سير العمل المتاحة (مراحل + انتقالات) — كتالوج لا محرّك تنفيذ.

    التنفيذ يبقى في core/workflow_engine ومحرّكات النطاق؛ هنا الوصف فقط (انظر
    api/workflow_definitions)."""
    from api.workflow_definitions import list_workflows

    return {"workflows": list_workflows()}


@router.get("/api/v1/registry/indices")
async def registry_indices(
    user: UserSchema = Depends(require_permission(Permission.FIELD_VIEW)),
):
    """سجلّ مؤشّرات الاستشعار عن بُعد (vegetation/water indices) — بيانات وصفيّة."""
    from api.index_registry import list_indices

    return {"indices": list_indices()}


@router.get("/api/v1/registry/events")
async def registry_events(
    user: UserSchema = Depends(require_permission(Permission.FIELD_VIEW)),
):
    """كتالوج أحداث المجال (domain events) — بيانات وصفيّة."""
    from api.event_catalog import list_events

    return {"events": list_events()}


@router.get("/api/v1/registry/cost-profiles")
async def registry_cost_profiles(
    user: UserSchema = Depends(require_permission(Permission.FIELD_VIEW)),
):
    """ملفّات حوكمة الكلفة (cost profiles) — بيانات وصفيّة."""
    from api.cost_governance import list_profiles

    return {"cost_profiles": list_profiles()}
