"""field_request_models.py — نماذج طلبات راوتر الحقول (Pydantic).

مُستخرَجة حرفيّاً من ``routers/fields.py`` (تفكيك): تجميع عقود الطلب في وحدة واحدة
وتقليل ضخامة الراوتر. نقيّة بلا I/O ولا حالة — pydantic فقط. ``fields.py`` يستوردها.
السلوك محفوظ: الحقول/الافتراضات/المحقّقات منسوخة كما هي.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class FieldImageryRefreshRequest(BaseModel):
    date: str | None = None


class FieldImageryBackfillRequest(BaseModel):
    """حمولة سحب الصور التاريخيّة (preset/مخصّص). الهندسة تُحقن من جانب الخادم."""

    preset: str | None = None
    from_date: str | None = None
    to_date: str | None = None
    months: int | None = None
    indices: list[str] | None = None
    max_cloud_pct: float | None = None
    limit_per_month: int | None = None
    apply_cloud_mask: bool | None = None
    dry_run: bool | None = None


class FieldMergeRequest(BaseModel):
    """طلب دمج عدّة حقول مصدر في حقل واحد (الهندسة المدموجة محسوبة @turf في الواجهة)."""

    source_field_ids: list[str] = Field(min_length=2, max_length=50)
    name: str = Field(min_length=1, max_length=100)
    geometry: dict  # GeoJSON Polygon المدموج (اتّحاد @turf) — يتحقّق منه الخادم
    crop: str | None = None
    soil_type: str | None = None
    manager: str | None = Field(default=None, max_length=100)
    farm_id: str | None = None
    field_code: str | None = Field(default=None, max_length=50)
    description: str | None = None
    water_source: str | None = Field(default=None, max_length=20)
    irrigation_type: str | None = Field(default=None, max_length=20)
    ownership_type: str | None = Field(default=None, max_length=20)
    gov: str | None = None
    country: str | None = Field(default=None, max_length=60)
    region: str | None = Field(default=None, max_length=80)

    @field_validator("source_field_ids")
    @classmethod
    def _dedupe_sources(cls, v: list[str]) -> list[str]:
        if len(set(v)) != len(v):
            raise ValueError("معرّفات الحقول المصدر مكرّرة")
        return v


class ChildField(BaseModel):
    """حقل وليد ناتج عن انقسام (اسم + هندسة @turf؛ المحصول اختياريّ يُورَّث/يُحدَّد)."""

    name: str = Field(min_length=1, max_length=100)
    geometry: dict  # GeoJSON Polygon للجزء (محسوب @turf) — يتحقّق منه الخادم
    crop: str | None = None
    soil_type: str | None = None
    manager: str | None = Field(default=None, max_length=100)
    field_code: str | None = Field(default=None, max_length=50)
    description: str | None = None
    water_source: str | None = Field(default=None, max_length=20)
    irrigation_type: str | None = Field(default=None, max_length=20)
    ownership_type: str | None = Field(default=None, max_length=20)


class FieldSplitRequest(BaseModel):
    """طلب انقسام حقل واحد إلى عدّة حقول وليدة (٢..١٠؛ كلّ وليد بهندسته @turf)."""

    source_field_id: str
    children: list[ChildField] = Field(min_length=2, max_length=10)
