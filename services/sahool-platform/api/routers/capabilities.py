"""api/routers/capabilities.py — بوّابة القدرات المشروطة (Capabilities)
=====================================================================
شريحة من تفكيك ``api/main.py`` إلى وحدات ``APIRouter`` (نمط P0).

سلوك محفوظ بالكامل: مسارات/أذونات/مخرجات/مخطّط OpenAPI مطابقة تماماً لما كان
في ``main.py`` — نُقلت الدالّة حرفيّاً مع تغيير ``@app`` إلى ``@router``.

الاعتماديّات المشتركة تبقى مُعرَّفة في ``api.main`` وتُستورَد من هنا. لتفادي
الاستيراد الدائريّ: ``api.main`` يستورد هذا الموجِّه في نهايته فقط.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from api.main import UserSchema, get_current_user

router = APIRouter()


@router.get("/api/v1/capabilities")
def list_capabilities(user: UserSchema = Depends(get_current_user)):
    """بوّابة القدرات المشروطة: أيّ قدرة مؤجَّلة مُفعَّلة/خاملة وكيف تُشغَّل.
    لا يكشف أسراراً — قِيَم منطقيّة + تعليمات تفعيل فقط (شفافيّة تشغيليّة)."""
    from core.capabilities import capabilities_report

    return capabilities_report()
