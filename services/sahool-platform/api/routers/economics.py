"""api/routers/economics.py — اقتصاديّات المزرعة (Farm Economics)
==============================================================
شريحة من تفكيك ``api/main.py`` إلى وحدات ``APIRouter`` (نمط P0).

سلوك محفوظ بالكامل: مسارات/أذونات/مخرجات/مخطّط OpenAPI مطابقة تماماً لما كان
في ``main.py`` — نُقلت الدوالّ حرفيّاً مع تغيير ``@app`` إلى ``@router``.

الاعتماديّات المشتركة (التبعيات/النماذج/المساعِدات) تبقى مُعرَّفة في ``api.main``
وتُستورَد من هنا تفادياً لكسر ``_rebuild_pydantic_models`` واستيرادات الاختبارات.
لتفادي الاستيراد الدائريّ: ``api.main`` يستورد هذا الموجِّه في نهايته فقط (بعد
تعريف كلّ التبعيات/النماذج)، فيُحلّ الاستيراد.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from api.farm_economics import break_even_price, cost_categories, feasibility
from api.feasibility_models import FeasibilityRequest
from api.main import UserSchema, get_current_user

router = APIRouter()


@router.get("/api/v1/economics/cost-categories")
def economics_categories_endpoint():
    """بنود التكلفة القياسيّة لبناء تقدير الجدوى."""
    return cost_categories()


@router.post("/api/v1/economics/feasibility")
def economics_feasibility_endpoint(
    req: FeasibilityRequest, user: UserSchema = Depends(get_current_user)
):
    """جدوى المحصول: الإيراد المتوقّع + صافي الربح + الهامل + فحص السوق."""
    return feasibility(
        req.area_ha,
        req.yield_t_per_ha,
        req.price_per_t,
        req.costs,
        req.total_cost,
    )


@router.get("/api/v1/economics/break-even")
def economics_break_even_endpoint(area_ha: float, yield_t_per_ha: float, total_cost: float):
    """سعر التعادل: أدنى سعر/طن يغطّي التكاليف."""
    return break_even_price(area_ha, yield_t_per_ha, total_cost)
