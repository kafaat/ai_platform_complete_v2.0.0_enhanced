"""api/feasibility_models.py — نماذج الجدوى الاقتصاديّة (Feasibility)
==================================================================
شريحة من تفكيك ``api/main.py`` (نمط B1): نموذج طلب الجدوى الاقتصاديّة
مُستخرَج حرفيّاً ليُستورَد من ``api/routers/economics.py``.

النموذج مكتفٍ ذاتيّاً (pydantic فقط) — لا يعتمد على رموز ``api.main`` الخاصّة.
"""

from __future__ import annotations

from pydantic import BaseModel

# ─── ٤١. دراسة الجدوى الاقتصاديّة (هل سأربح؟) ─────────────────────


class FeasibilityRequest(BaseModel):
    area_ha: float
    yield_t_per_ha: float
    price_per_t: float
    costs: dict[str, float] | None = None
    total_cost: float | None = None
