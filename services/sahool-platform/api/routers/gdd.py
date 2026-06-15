"""api/routers/gdd.py — تتبّع GDD (Growing Degree Days Tracking)
==================================================================
شريحة من تفكيك ``api/main.py`` إلى وحدات ``APIRouter`` (نمط P0).

سلوك محفوظ بالكامل: مسارات/أذونات/مخرجات/مخطّط OpenAPI مطابقة تماماً لما كان
في ``main.py`` — نُقلت الدالّة حرفيّاً مع تغيير ``@app`` إلى ``@router``.

الدوالّ النقيّة (``api.gdd_tracker``) تُستورَد مباشرةً من وحدتها — هنا نستورد
``DailyTemp``/``track_gdd``؛ بقيت في ``main`` نسخة مُعنونة (``_DTemp``) تستعملها نقاط
السيناريوهات فلا يتيتّم استيراد ``main``. أمّا التبعيات/النماذج المُعرَّفة في ``main``
فتبقى هناك وتُستورَد من ``api.main``. لتفادي الاستيراد الدائريّ: ``api.main`` يستورد
هذا الموجِّه في نهايته فقط، فيُحلّ الاستيراد.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from api.gdd_tracker import DailyTemp, track_gdd
from api.main import (
    GDDRequest,
    UserSchema,
    get_current_user,
)

router = APIRouter()


@router.post("/api/v1/gdd/track")
def gdd_track(
    req: GDDRequest,
    user: UserSchema = Depends(get_current_user),
):
    """يتراكم GDD ويحدّد مرحلة المحصول الحاليّة + المتبقّي للتالية."""
    temps = [DailyTemp(t.t_min_c, t.t_max_c) for t in req.temps]
    try:
        return track_gdd(req.crop, temps).to_dict()
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
