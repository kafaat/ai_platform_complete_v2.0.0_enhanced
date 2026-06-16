"""api/routers/yield_interval.py — نطاق الإنتاج النزيه لكلّ حقل (Honest Yield Interval).

يكشف نطاق إنتاج conformal بدل تقدير نقطيّ وهميّ: ``[low, high] t/ha`` بتغطية
محدّدة، أو «قيد المعايرة» حين لا تتوفّر بقايا معايرة كافية. الإحصاء مُفوَّض لِ
``core.yield_interval_service.field_yield_interval`` (الذي يُفوّض بدوره لِمحرّك
``conformal_interval``). لا قراءة قاعدة بيانات — البقايا/التقدير يُوفّرها العميل
من سِجِلّ معايرته المحجوب؛ ``field_id`` سياق مسار فقط. مُقيَّد بالدور (FIELD_VIEW)
اتّساقاً مع لوحات الحقل.

ملاحظة: هذا الراوتر غير مُسجَّل في ``main.py`` — القائد يُسجّله.
"""

from __future__ import annotations

from core.yield_interval_service import field_yield_interval
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, field_validator

from api.main import Permission, UserSchema, require_permission

router = APIRouter()


class YieldIntervalRequest(BaseModel):
    """جسم الطلب: تقدير نقطيّ اختياريّ + بقايا المعايرة المحجوبة + التغطية."""

    point_estimate: float | None = Field(
        default=None,
        description="التقدير النقطيّ المرجعيّ (t/ha) لِبناء النطاق حوله؛ None ⇒ قيد المعايرة",
    )
    residuals: list[float] = Field(
        default_factory=list,
        description="بقايا المعايرة المحجوبة من سِجِلّ العميل (تُحتاج ≥10 لِنطاق موثوق)",
    )
    coverage: float = Field(
        default=0.90,
        description="مستوى التغطية المطلوب، ضمن (0, 1)",
    )

    @field_validator("coverage")
    @classmethod
    def _coverage_in_open_unit(cls, v: float) -> float:
        if not (0.0 < v < 1.0):
            raise ValueError("coverage يجب أن يكون ضمن المجال المفتوح (0, 1)")
        return v


@router.post("/api/v1/fields/{field_id}/yield-interval")
async def field_yield_interval_endpoint(
    field_id: str,
    body: YieldIntervalRequest,
    user: UserSchema = Depends(require_permission(Permission.FIELD_VIEW)),
):
    """نطاق إنتاج conformal نزيه لحقل، أو «قيد المعايرة» عند نقص البيانات.

    لا قراءة قاعدة — المُدخلات يُوفّرها العميل؛ ``field_id`` سياق فقط.
    422 على تغطية غير صالحة (خارج (0, 1)) عبر التحقّق من Pydantic.
    """
    return field_yield_interval(
        point_estimate=body.point_estimate,
        residuals=body.residuals,
        coverage=body.coverage,
    )
