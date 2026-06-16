"""api/setting_models.py — نماذج الإعدادات (Settings).
====================================================================
شريحة من تفكيك ``api/main.py`` (نمط B1): استخراج كتلة نموذج «الإعدادات».

نطاقات الإعدادات: منصّة/مزرعة/ريّ/إشعارات (platform/farm/irrigation/notification)
بمفتاح+قيمة (JSON) لكلّ مستأجِر.

self-contained: pydantic + stdlib فقط. single-consumer: api/routers/settings.py.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


# ─── الإعدادات (Settings) — منصّة/مزرعة/ريّ/إشعارات — (v28) ───────
class SettingRequest(BaseModel):
    scope: str = Field(pattern="^(platform|farm|irrigation|notification)$")
    key: str = Field(min_length=1, max_length=80)
    value: dict | None = None
