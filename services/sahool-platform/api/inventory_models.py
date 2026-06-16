"""api/inventory_models.py — نماذج طلبات المخزون (Inventory request models).

مُستخرَجة حرفيّاً من ``api/main.py`` ضمن تفكيك الراوترات (B1).
self-contained: تعتمد على pydantic + stdlib فقط.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


# ─── المخزون (Inventory) — الطبقة ١٠ (v22) ───────────────────────
class InventoryItemRequest(BaseModel):
    category: str = Field(pattern="^(fertilizer|pesticide|seed|spare_part|other)$")
    name: str = Field(min_length=1, max_length=120)
    unit: str = "unit"
    reorder_level: float | None = Field(default=None, ge=0)
    notes: str | None = None


class InventoryBatchRequest(BaseModel):
    quantity: float = Field(ge=0)
    unit: str | None = None
    batch_code: str | None = None
    expiry_date: str | None = None  # ISO date
    received_at: str | None = None
    supplier: str | None = None
    notes: str | None = None
