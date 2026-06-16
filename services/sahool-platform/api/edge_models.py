"""api/edge_models.py — نماذج مزامنة الحافة (Edge Sync Models)
=====================================================================
شريحة من تفكيك ``api/main.py`` (نمط B1): استخراج نموذج «مزامنة الحافة».

يحوي ``EdgeSyncRequest`` المُستخدَم في ``api/routers/edge.py`` لاستقبال نتائج
أجهزة الحافة (edge) مع منع التكرار (dedup). النموذج مكتفٍ ذاتيّاً (pydantic فقط)
ومنقول حرفيّاً من ``api/main.py`` حفظاً للسلوك والمخطّط (OpenAPI) كما هو.
"""

from __future__ import annotations

from pydantic import BaseModel


# ─── استقبال مزامنة edge مع dedup (Hardening مراجعة 7) ───────────
class EdgeSyncRequest(BaseModel):
    type: str
    data: dict
    idempotency_key: str | None = None
    occurred_at: str | None = None  # وقت حدوث القياس على الجهاز (مرجع سببي)
    device_id: str | None = None
    field_id: str | None = None
