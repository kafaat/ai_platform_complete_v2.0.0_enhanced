"""api/routers/indices.py — تغطية المؤشّرات الطيفيّة (Spectral Indices)
=====================================================================
شريحة من تفكيك ``api/main.py`` إلى وحدات ``APIRouter`` (نمط P0).

سلوك محفوظ بالكامل: مسارات/أذونات/مخرجات/مخطّط OpenAPI مطابقة تماماً لما كان
في ``main.py`` — نُقلت الدالّة حرفيّاً مع تغيير ``@app`` إلى ``@router``.

الاعتماديّات المشتركة تبقى مُعرَّفة في ``api.main`` وتُستورَد من هنا. لتفادي
الاستيراد الدائريّ: ``api.main`` يستورد هذا الموجِّه في نهايته فقط.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from api.main import Permission, UserSchema, require_permission

router = APIRouter()


@router.get("/api/v1/indices/coverage-report")
def indices_coverage_report(
    user: UserSchema = Depends(require_permission(Permission.FIELD_VIEW)),
):
    """تقرير شفّاف: أيّ مؤشّرات طيفيّة مربوطة بالقرار وأيّها عرض/سياق (حوكمة)."""
    from core.engines.spectral_stress_bridge import index_coverage_report

    return index_coverage_report()
