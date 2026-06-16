"""api/master_data_models.py — نموذج «البيانات المرجعيّة» (Master Data).
=====================================================================
شريحة من تفكيك ``api/main.py`` (نمط B1): استخراج كتلة نموذج «البيانات المرجعيّة».

self-contained: pydantic + stdlib فقط. single-consumer: api/routers/master_data.py.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class MasterDataRequest(BaseModel):
    category: str = Field(
        pattern="^(crop|soil_type|fertilizer|pesticide|seed_variety|equipment_type|other)$"
    )
    code: str = Field(min_length=1, max_length=60)
    name_ar: str = Field(min_length=1, max_length=160)
    name_en: str | None = None
    metadata: dict | None = None
