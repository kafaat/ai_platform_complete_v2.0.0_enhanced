"""api/routers/registry.py — سجلّات الاستبطان (Introspection Registries)
========================================================================
شريحة من تفكيك ``api/main.py`` إلى وحدات ``APIRouter`` (نمط P0).

سلوك محفوظ بالكامل: مسارات/أذونات/مخرجات/مخطّط OpenAPI مطابقة تماماً لما كان
في ``main.py`` — نُقلت الدوالّ السبع حرفيّاً مع تغيير ``@app`` إلى ``@router``.

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


# ─── سجلّات الاستبطان: حقول التقرير + تعريفات سير العمل (قراءة فقط) ──────
# تكشف الكتالوجات المُعلَنة كبيانات (report_builder/workflow_definitions) لطبقة
# الواجهة دون قاعدة — دوالّ نقيّة. الصلاحيّة FIELD_VIEW (قراءة) مطابقةً لـendpoints
# التقارير القائمة.
@router.get("/api/v1/registry/report-fields")
def list_registry_report_fields(
    user: UserSchema = Depends(require_permission(Permission.FIELD_VIEW)),
):
    """حقول التقرير المتاحة (Report Builder) — كتالوج البيانات الوصفيّة لا بيانات مُجمَّعة.

    مصدر واحد لما يمكن إدراجه في تقرير (المعرّف/الاسم/الكيان/النوع/الوحدة). نقيّ — لا
    قاعدة. تجميع البيانات الفعليّ متابعة لاحقة (انظر api/report_builder)."""
    from api.report_builder import list_report_fields

    return {"report_fields": list_report_fields()}


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


@router.get("/api/v1/registry/device-types")
async def registry_device_types(
    user: UserSchema = Depends(require_permission(Permission.FIELD_VIEW)),
):
    """سجلّ أنواع الأجهزة (device types) المدعومة — بيانات وصفيّة."""
    from api.device_registry import list_device_types

    return {"device_types": list_device_types()}


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


@router.get("/api/v1/registry/data-quality-rules")
async def registry_data_quality_rules(
    user: UserSchema = Depends(require_permission(Permission.FIELD_VIEW)),
):
    """قواعد جودة البيانات (data-quality rules) — بيانات وصفيّة."""
    from core.data_quality import list_rules

    return {"data_quality_rules": list_rules()}
