"""api/irrigation_models.py — نماذج/مساعِدات الريّ التشغيليّ (صمامات + جداول).

شريحة من تفكيك ``api/main.py`` (نمط B1): النماذج (``ValveRequest`` /
``ValveStateRequest`` / ``ScheduleRequest``) والمساعِد ``_parse_time`` نُقِلت
حرفيّاً إلى هنا. self-contained: pydantic فقط للنماذج، و``datetime`` +
``fastapi.HTTPException`` لـ``_parse_time``. يستوردها ``api.routers.irrigation``.
"""

from __future__ import annotations

from fastapi import HTTPException
from pydantic import BaseModel, Field


class ValveRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    field_id: str | None = None
    device_id: str | None = None
    valve_type: str = Field(default="solenoid", pattern="^(solenoid|manual|drip_header|gate)$")
    flow_rate_lpm: float | None = Field(default=None, ge=0)


class ValveStateRequest(BaseModel):
    status: str = Field(pattern="^(open|closed)$")


class ScheduleRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    field_id: str | None = None
    valve_id: str | None = None
    start_time: str  # HH:MM أو HH:MM:SS
    duration_min: int = Field(ge=1, le=1440)
    days_of_week: list[int] | None = None
    water_target_mm: float | None = Field(default=None, ge=0)
    enabled: bool = True


def _parse_time(value: str):
    """يحوّل HH:MM[:SS] إلى time؛ 400 على قيمة غير صالحة (لا 500)."""
    from datetime import time as _time

    try:
        return _time.fromisoformat(value.strip())
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(
            status_code=400, detail="start_time غير صالح — استخدم HH:MM أو HH:MM:SS"
        ) from None
