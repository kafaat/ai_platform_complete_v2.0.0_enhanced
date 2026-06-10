"""نماذج بيانات Pydantic v2 لخطّ أبحاث SAHOOL الزراعيّة.

SAHOOL Agronomic Research Pipeline — Pydantic v2 data models.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator


class SubQuery(BaseModel):
    """استعلام فرعي يُرسَل إلى مصدر بيانات محدَّد.

    Represents a single data-source sub-query produced by the decomposer.
    """

    type: str = Field(..., description="نوع الاستعلام، مثل ndvi_analysis أو weather_check")
    source: str = Field(
        ...,
        description="اسم المصدر: sentinel_hub / weather_api / soil_sensors / irrigation_logs / qdrant_rag",
    )
    params: dict = Field(default_factory=dict, description="معاملات الاستعلام")


class CausalLink(BaseModel):
    """علاقة سببيّة مستنتَجة بين عاملَين.

    A deterministically inferred causal relationship.
    """

    cause: str = Field(..., description="العامل المُسبِّب")
    effect: str = Field(..., description="الأثر الناتج")
    confidence: float = Field(..., ge=0.0, le=1.0, description="مستوى الثقة [0,1]")
    evidence: list[str] = Field(default_factory=list, description="مصادر الدليل")

    @field_validator("confidence", mode="before")
    @classmethod
    def clamp_confidence(cls, v: float) -> float:
        """تأطير قيمة الثقة ضمن [0, 1]."""
        return max(0.0, min(1.0, float(v)))


class Factor(BaseModel):
    """عامل زراعي مؤثِّر مستخرَج من التحليل.

    An agronomic factor extracted from data analysis.
    """

    name: str = Field(..., description="اسم العامل بالعربية")
    description: str = Field(..., description="وصف تفصيلي للعامل")
    severity: Literal["low", "medium", "high"] = Field(..., description="شدّة التأثير")
    confidence: float = Field(..., ge=0.0, le=1.0, description="مستوى الثقة [0,1]")

    @field_validator("confidence", mode="before")
    @classmethod
    def clamp_confidence(cls, v: float) -> float:
        """تأطير قيمة الثقة ضمن [0, 1]."""
        return max(0.0, min(1.0, float(v)))


class Synthesis(BaseModel):
    """نتيجة التوليف النهائيّة لخطّ الأبحاث.

    Final synthesised output of the research pipeline.
    """

    summary: str = Field(..., description="ملخّص عربي شامل للنتائج")
    factors: list[Factor] = Field(default_factory=list, description="قائمة العوامل المؤثِّرة")
    recommendations: list[str] = Field(default_factory=list, description="توصيات بالعربية")
    confidence: float = Field(..., ge=0.0, le=1.0, description="مستوى الثقة الكلّي [0,1]")

    @field_validator("confidence", mode="before")
    @classmethod
    def clamp_confidence(cls, v: float) -> float:
        """تأطير قيمة الثقة ضمن [0, 1]."""
        return max(0.0, min(1.0, float(v)))
