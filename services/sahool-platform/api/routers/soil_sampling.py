"""api/routers/soil_sampling.py — بروتوكول أخذ عيّنة التربة (Soil Sampling)
=========================================================================
شريحة من تفكيك ``api/main.py`` إلى وحدات ``APIRouter`` (نمط P0).

سلوك محفوظ بالكامل: مسارات/مخرجات/مخطّط OpenAPI مطابقة تماماً لما كان في
``main.py`` — نُقلت الدوالّ الثلاث حرفيّاً مع تغيير ``@app`` إلى ``@router``.

دوالّ النطاق (``soil_sampling_protocol``) كانت مُستورَدة على مستوى وحدة ``main``
وتُستخدَم حصريّاً من هذه الـendpoints؛ نُقل استيرادها هنا (من المصدر مباشرةً)
لتفادي استيراد يتيم في ``main`` بعد النقل — لا تغيير سلوكيّ.
"""

from __future__ import annotations

from fastapi import APIRouter

from api.soil_sampling_protocol import (
    sampling_depth,
    sampling_protocol,
    subsamples_for_area,
)

router = APIRouter()


@router.get("/api/v1/soil-sampling/subsamples")
def soil_subsamples_endpoint(area_ha: float):
    """عدد العيّنات الفرعيّة الموصى بها حسب مساحة الحقل."""
    return subsamples_for_area(area_ha)


@router.get("/api/v1/soil-sampling/depth")
def soil_depth_endpoint(purpose: str = "general"):
    """العمق المناسب لأخذ العيّنة حسب الغرض (general/nitrate/no_till/orchard)."""
    return sampling_depth(purpose)


@router.get("/api/v1/soil-sampling/protocol")
def soil_protocol_endpoint(area_ha: float | None = None, purpose: str = "general"):
    """البروتوكول الكامل لأخذ عيّنة تربة صحيحة (خطوات + تحذيرات + توقيت)."""
    return sampling_protocol(area_ha, purpose)
