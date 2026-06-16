"""api/equipment_models.py — نماذج المعدّات والصيانة (Equipment & Maintenance)
=============================================================================
كتلة مكتفية ذاتيّاً مُستخرَجة من ``api/main.py`` (تفكيك B1، نمط P0).

تحتوي على نموذجَي طلب المعدّات والصيانة. مكتفية ذاتيّاً: تعتمد فقط على
``pydantic`` + stdlib، بلا أيّ رمز آخر من ``api.main``. مستهلِكها الوحيد
``api/routers/equipment.py``. النماذج منسوخة حرفيّاً للحفاظ على السلوك/مخطّط
OpenAPI دون تغيير.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


# ─── المعدّات (Equipment) — الطبقة ١١ (v23) ──────────────────────
class EquipmentRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    type: str = Field(pattern="^(tractor|pump|harvester|sprayer|other)$")
    operating_hours: float = Field(default=0, ge=0)
    purchase_date: str | None = None
    notes: str | None = None


class MaintenanceRequest(BaseModel):
    kind: str = Field(pattern="^(scheduled|repair|breakdown|inspection)$")
    status: str = Field(default="planned", pattern="^(planned|done|cancelled)$")
    scheduled_date: str | None = None
    performed_date: str | None = None
    cost_usd: float | None = None
    notes: str | None = None
