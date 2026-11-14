"""api/routers/analytics.py — تحليلات التكلفة (Cost Analytics)
===========================================================
شريحة من تفكيك ``api/main.py`` إلى وحدات ``APIRouter`` (نمط P0).

سلوك محفوظ بالكامل: مسارات/أذونات/مخرجات/مخطّط OpenAPI مطابقة تماماً لما كان
في ``main.py`` — نُقلت الدوالّ حرفيّاً مع تغيير ``@app`` إلى ``@router``.

الاعتماديّات المشتركة (التبعيات/النماذج/المساعِدات) تبقى مُعرَّفة في ``api.main``
وتُستورَد من هنا تفادياً لكسر ``_rebuild_pydantic_models`` واستيرادات الاختبارات.
لتفادي الاستيراد الدائريّ: ``api.main`` يستورد هذا الموجِّه في نهايته فقط (بعد
تعريف كلّ التبعيات/النماذج)، فيُحلّ الاستيراد.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends

from api.main import (
    Permission,
    UserSchema,
    require_permission,
    tenant_connection,
)

router = APIRouter()
TaskCostScope = Literal["completed", "recorded"]
_TASK_COST_FILTER = {
    "completed": "actual_cost_usd IS NOT NULL AND status = 'completed'",
    "recorded": "actual_cost_usd IS NOT NULL",
}


@router.get("/api/v1/analytics/costs")
async def analytics_costs(
    user: UserSchema = Depends(require_permission(Permission.ANALYTICS_VIEW)),
    task_scope: TaskCostScope = "completed",
):
    """تكاليف فعليّة مُجمَّعة من الجداول القائمة (لا أرقام ثابتة).

    completed يحصر التقرير في المهام المنجزة. recorded يشمل المبلغ المحفوظ
    لكل مهمة حتى بعد إعادة فتحها. تكاليف الصيانة مستقلة عن نطاق المهام.
    """
    async with tenant_connection(user) as conn:
        tasks = await conn.fetchrow(
            "SELECT COALESCE(SUM(actual_cost_usd), 0) AS total, COUNT(*) AS count "
            f"FROM field_tasks WHERE {_TASK_COST_FILTER[task_scope]}"
        )
        maint_total = await conn.fetchval(
            "SELECT COALESCE(SUM(cost_usd), 0) FROM equipment_maintenance WHERE cost_usd IS NOT NULL"
        )
    tasks_total_f = float(tasks["total"])
    maint_total_f = float(maint_total or 0)
    return {
        "by_source": [
            {"source": "field_tasks", "total_usd": tasks_total_f},
            {"source": "maintenance", "total_usd": maint_total_f},
        ],
        "total_usd": tasks_total_f + maint_total_f,
        "task_count": int(tasks["count"]),
        "task_scope": task_scope,
    }


@router.get("/api/v1/analytics/costs/by-field")
async def analytics_costs_by_field(
    user: UserSchema = Depends(require_permission(Permission.ANALYTICS_VIEW)),
    task_scope: TaskCostScope = "completed",
):
    """إجماليّات تكلفة المهامّ لكلّ حقل."""
    async with tenant_connection(user) as conn:
        rows = await conn.fetch(
            "SELECT field_id, COALESCE(SUM(actual_cost_usd), 0) AS total_usd "
            f"FROM field_tasks WHERE {_TASK_COST_FILTER[task_scope]} "
            "GROUP BY field_id ORDER BY total_usd DESC"
        )
    return [{"field_id": r["field_id"], "total_usd": float(r["total_usd"] or 0)} for r in rows]
