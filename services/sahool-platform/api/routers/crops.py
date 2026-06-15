"""api/routers/crops.py — صفات المحاصيل (Crops: Drought Resilience)
====================================================================
شريحة من تفكيك ``api/main.py`` إلى وحدات ``APIRouter`` (نمط P0).

سلوك محفوظ بالكامل: مسارات/أذونات/مخرجات/مخطّط OpenAPI مطابقة تماماً لما كان
في ``main.py`` — نُقلت الدالّتان حرفيّاً مع تغيير ``@app`` إلى ``@router``.
الاستيرادات الكسولة داخل الدوالّ تبقى كما هي. التبعيات/الأذونات تبقى مُعرَّفةً في
``api.main`` وتُستورَد من هنا. لتفادي الاستيراد الدائريّ: ``api.main`` يستورد هذا
الموجِّه في نهايته فقط، فيُحلّ الاستيراد.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from api.main import (
    Permission,
    UserSchema,
    require_permission,
)

router = APIRouter()


@router.get("/api/v1/crops/drought-resilience")
def crop_drought_resilience(
    crop_id: str,
    forecast_max_temp_c: float | None = None,
    is_irrigated: bool | None = None,
    user: UserSchema = Depends(require_permission(Permission.RECOMMENDATION_VIEW)),
):
    """درجة تحمّل الجفاف/الحرارة لمحصول من صفات موثّقة (مبدأ TRY، لا أرقام مخترعة).

    يجمع صفات سهول (عمق الجذور، حدّ حرارة الإزهار، عتبة الملوحة) في درجة مركّبة.
    يحذّر إن تجاوزت حرارة الهواء المتوقّعة حدّ الإزهار (قد تكون أخطر). على الحقل
    المرويّ يُضاف تنويه أنّ الريّ يبرّد الغطاء فالهواء يبالغ (Zhu et al. 2022).
    صدق: بلا صفات → لا درجة.
    """
    from core.engines.drought_resilience import compute_drought_resilience

    return compute_drought_resilience(
        crop_id, forecast_max_temp_c=forecast_max_temp_c, is_irrigated=is_irrigated
    )


@router.get("/api/v1/crops/compare-drought-resilience")
def compare_drought_resilience(
    crop_ids: str,
    forecast_max_temp_c: float | None = None,
    is_irrigated: bool | None = None,
    user: UserSchema = Depends(require_permission(Permission.RECOMMENDATION_VIEW)),
):
    """يقارن تحمّل محاصيل للجفاف (قائمة مفصولة بفواصل) — لاختيار الأصمد."""
    from core.engines.drought_resilience import compare_crops_resilience

    crops = [c.strip() for c in crop_ids.split(",") if c.strip()]
    return compare_crops_resilience(
        crops, forecast_max_temp_c=forecast_max_temp_c, is_irrigated=is_irrigated
    )
