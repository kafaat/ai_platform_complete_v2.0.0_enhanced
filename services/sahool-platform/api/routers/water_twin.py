"""api/routers/water_twin.py — توأم المياه مُغذّى بدفتر المياه (المرحلة الثانية)

يُكمِّل نقطة ``/api/v1/scenario/water-twin`` النقيّة (المرحلة الأولى) بنقطة **field-scoped**
تستثمر **دفتر المياه اليوميّ v98**: تقرأ أحدث صفوف الدفتر للحقل (RLS) فتشتقّ منها الحالة
الابتدائيّة (النضوب) وتقدير ETc اليوميّ، ثمّ تحاكي «ماذا لو أخّرت/خفّضت الريّ؟» للأفق الأماميّ.

صدق منهجيّ صارم:
  - الاشتقاق من الدفتر فقط (``api/water_twin_seed.py`` النقيّ) — **لا اختراع أرقام**؛ غياب
    مصدر الاشتقاق ⇒ **422 صادق** يطلب مدخلاً صريحاً (لا حالة مُلفّقة).
  - **TAW/RAW يُمرَّران صراحةً** (إقرار زراعيّ: قوام تربة + عمق جذور) — لا يُخمَّنان.
  - **مصدر كلّ قيمة مُعلَن** في الردّ (``seed.*_source``) للتدقيق.
  - الفيزياء كلّها في المحرّك النقيّ ``api/water_twin.py`` (FAO-56) — هذا الموجِّه تنسيق فقط.
  - معزول بالمستأجِر (RLS، FIELD_VIEW)؛ حقل خارج المستأجِر ⇒ 404.

نمط الاستيراد من ``api.main`` يطابق ``routers/water_ledger.py``: التبعيّات تبقى في ``main``
ويستوردها هذا الموجِّه، و``api.main`` يستورده في نهايته فقط (يُحلّ الاستيراد الدائريّ).
"""

from __future__ import annotations

import logging
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Path
from pydantic import BaseModel, Field

from api.main import (
    _DB_POOL,
    Permission,
    UserSchema,
    _assert_field_in_tenant,
    _db_unavailable,
    require_permission,
    tenant_connection,
)
from api.water_ledger_compute import LEDGER_SELECT_COLS, row_to_ledger_entry
from api.water_twin import DayPlan, compare_scenarios, delay_irrigation, scale_irrigation
from api.water_twin_seed import seed_daily_etc, seed_initial_depletion

logger = logging.getLogger(__name__)

router = APIRouter()


class FieldWaterTwinRequest(BaseModel):
    """طلب محاكاة توأم المياه لحقل، مُغذّى بالدفتر.

    ``taw_mm``/``raw_mm`` إلزاميّان (إقرار زراعيّ — لا يُشتقّان). ``initial_depletion_mm``
    و``daily_etc_mm`` اختياريّان: إن غابا يُشتقّان من الدفتر؛ وإن تعذّر ⇒ 422 صادق.
    """

    taw_mm: float = Field(..., gt=0, description="إجماليّ الماء المتاح في منطقة الجذور")
    raw_mm: float = Field(..., gt=0, description="الماء المتاح بسهولة (= p·TAW)")
    horizon_days: int = Field(default=7, ge=1, le=60, description="أفق المحاكاة الأماميّ")
    baseline_irrigation_mm: float = Field(
        default=0.0, ge=0, description="الريّ اليوميّ المخطّط (سيناريو الأساس)"
    )
    daily_rain_mm: float = Field(default=0.0, ge=0, description="مطر فعّال يوميّ متوقَّع")
    daily_etc_mm: float | None = Field(
        default=None, ge=0, description="ETc يوميّ صريح (وإلّا متوسّط الدفتر الأخير)"
    )
    initial_depletion_mm: float | None = Field(
        default=None, ge=0, description="نضوب ابتدائيّ صريح (وإلّا من أحدث صفّ دفتر)"
    )
    recent_days_window: int = Field(
        default=7, ge=1, le=60, description="عدد صفوف الدفتر الأخيرة لتقدير ETc"
    )
    scenario_kind: Literal["delay", "scale"] = "scale"
    delay_days: int = Field(default=0, ge=0)
    scale_factor: float = Field(default=0.8, ge=0)


@router.post("/api/v1/fields/{field_id}/water-twin")
async def field_water_twin(
    req: FieldWaterTwinRequest,
    field_id: str = Path(..., description="معرّف الحقل لمحاكاة توأم مياهه"),
    user: UserSchema = Depends(require_permission(Permission.FIELD_VIEW)),
):
    """يحاكي توأم مياه الحقل مُغذّى بأحدث صفوف دفتره (RLS) — «ماذا لو أخّرت/خفّضت الريّ؟».

    يشتقّ النضوب الابتدائيّ + ETc من الدفتر (أو من تجاوزات الطلب الصريحة)، يبني جدول الأساس
    للأفق، يطبّق البديل (تأجيل/تحجيم)، ويقارن (أيّام إجهاد/استهلاك ماء). صدق: تعذّر الاشتقاق
    (لا دفتر ولا تجاوز) ⇒ 422 يطلب مدخلاً صريحاً؛ حقل خارج المستأجِر ⇒ 404؛ تعذّر القاعدة ⇒ 503.
    """
    if req.raw_mm > req.taw_mm:
        raise HTTPException(status_code=422, detail="RAW يجب أن يكون ≤ TAW.")

    # اقرأ أحدث صفوف الدفتر (DESC) لاشتقاق الحالة الابتدائيّة + متوسّط ETc.
    recent: list[dict] = []
    if _DB_POOL is not None:
        try:
            async with tenant_connection(user) as conn:
                await _assert_field_in_tenant(conn, field_id)
                rows = await conn.fetch(
                    f"SELECT {LEDGER_SELECT_COLS} FROM water_ledger "
                    "WHERE field_id = $1 ORDER BY ledger_date DESC LIMIT $2",
                    field_id,
                    req.recent_days_window,
                )
            recent = [row_to_ledger_entry(r) for r in rows]
        except HTTPException:
            raise  # 404 (حقل خارج المستأجِر) يصعد كما هو
        except Exception as e:  # noqa: BLE001 — خطأ DB ⇒ 503 موثَّق
            raise _db_unavailable("قراءة دفتر المياه لتوأم المياه", e) from e

    latest_row = recent[0] if recent else None
    init_dr, dr_source = seed_initial_depletion(latest_row, req.taw_mm, req.initial_depletion_mm)
    try:
        daily_etc, etc_source = seed_daily_etc(recent, req.daily_etc_mm)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e

    if init_dr is None:
        raise HTTPException(
            status_code=422,
            detail=(
                "تعذّر اشتقاق النضوب الابتدائيّ: لا صفّ دفتر يحمل depletion_mm/soil_moisture_pct "
                "ولا initial_depletion_mm في الطلب. سجّل قيد دفتر أوّلاً أو مرّر القيمة صراحةً."
            ),
        )
    if daily_etc is None:
        raise HTTPException(
            status_code=422,
            detail=(
                "تعذّر اشتقاق ETc: لا صفّ دفتر يحمل etc_mm ولا daily_etc_mm في الطلب. "
                "سجّل قيود دفتر أوّلاً أو مرّر القيمة صراحةً."
            ),
        )

    baseline = [
        DayPlan(daily_etc, req.daily_rain_mm, req.baseline_irrigation_mm)
        for _ in range(req.horizon_days)
    ]
    if req.scenario_kind == "delay":
        scenario = delay_irrigation(baseline, req.delay_days)
    else:  # scale
        scenario = scale_irrigation(baseline, req.scale_factor)

    try:
        result = compare_scenarios(req.taw_mm, req.raw_mm, init_dr, baseline, scenario)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e

    result["field_id"] = field_id
    result["seed"] = {
        "initial_depletion_mm": round(init_dr, 2),
        "initial_depletion_source": dr_source,
        "daily_etc_mm": round(daily_etc, 2),
        "daily_etc_source": etc_source,
        "ledger_rows_used": len(recent),
        "horizon_days": req.horizon_days,
    }
    return result
