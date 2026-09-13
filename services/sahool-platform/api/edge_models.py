"""api/edge_models.py — نماذج مزامنة الحافة (Edge Sync Models)
=====================================================================
شريحة من تفكيك ``api/main.py`` (نمط B1): استخراج نموذج «مزامنة الحافة».

يحوي ``EdgeSyncRequest`` المُستخدَم في ``api/routers/edge.py`` لاستقبال نتائج
أجهزة الحافة (edge) مع منع التكرار (dedup). النموذج مكتفٍ ذاتيّاً (pydantic فقط)
ومنقول حرفيّاً من ``api/main.py`` حفظاً للسلوك والمخطّط (OpenAPI) كما هو.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator


# ─── استقبال مزامنة edge مع dedup (Hardening مراجعة 7) ───────────
class EdgeSyncRequest(BaseModel):
    type: str
    data: dict
    idempotency_key: str = Field(min_length=16, max_length=128)
    occurred_at: datetime
    device_id: str = Field(min_length=1, max_length=50)
    field_id: str = Field(min_length=1, max_length=50)

    @field_validator("occurred_at")
    @classmethod
    def timestamp_has_timezone(cls, value: datetime) -> datetime:
        if value.utcoffset() is None:
            raise ValueError("occurred_at must include a timezone")
        return value
