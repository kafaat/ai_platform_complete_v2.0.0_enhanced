"""
knowledge.conservative_rag
==========================
المكوّن الثالث: قاعدة المعرفة المحافِظة (Conservative RAG).

تتبع المبادئ التي اتفقنا عليها عبر النقاش:
  - الأدبيات مصدر داعم (15%)، لا بديل عن البيانات المحلية (85%).
  - مقارنة الظروف تمنع "citation washing": مصدر لا يطابق ظروف الحقل
    يُخفّض وزنه، فلا يمنح ثقة زائفة.
  - كل مصدر موثّق (مرجع كامل)، لا ادعاء بلا سند.

التصميم لا يفرض محرّك embeddings بعينه (تجنّب اعتماد GPU في سياق اليمن).
يوفّر الطبقة المنطقية؛ المتجهات (Qdrant/pgvector) تُوصَّل لاحقاً عند الحاجة.

ملاحظة صريحة: هذا هيكل قاعدة المعرفة. الفهرسة الفعلية لأبحاث موثوقة
(FAO، أبحاث المناطق الجافة) خطوة لاحقة — بدونها يعمل بالمعرفة المضمّنة فقط.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class SourceTier(StrEnum):
    LOCAL_DATA = "local_field_data"  # الجوف الفعلي — الأعلى ثقة (85%)
    ESTABLISHED = "established_eq"  # FAO-56, WOFOST — فيزياء عامة
    LITERATURE = "literature"  # أبحاث — مصدر داعم (15% سقفاً)


@dataclass
class KnowledgeSource:
    source_id: str
    tier: SourceTier
    citation: str  # مرجع كامل — لا ادعاء بلا سند
    content_ar: str
    # conditions the source was derived under (for similarity matching):
    conditions: dict = field(default_factory=dict)


@dataclass
class FieldConditions:
    """ظروف الحقل الحالي — لمقارنة ملاءمة المصدر."""

    temp_mean_c: float
    soil_texture: str
    ece_ds_m: float
    crop: str
    climate_class: str


def condition_similarity(field: FieldConditions, source_conditions: dict) -> float:
    """تشابه ظروف الحقل مع ظروف الدراسة (0-1). يمنع citation washing.

    دراسة عن القمح في الهند الرطبة ≠ الجوف الجاف → تشابه منخفض → وزن منخفض.
    """
    if not source_conditions:
        return 0.3  # unknown conditions — low default weight
    score = 0.0
    checks = 0
    if "temp_mean_c" in source_conditions:
        checks += 1
        if abs(field.temp_mean_c - source_conditions["temp_mean_c"]) < 5:
            score += 1
    if "soil_texture" in source_conditions:
        checks += 1
        if field.soil_texture == source_conditions["soil_texture"]:
            score += 1
    if "ece_ds_m" in source_conditions:
        checks += 1
        if abs(field.ece_ds_m - source_conditions["ece_ds_m"]) < 1.5:
            score += 1
    if "crop" in source_conditions:
        checks += 1
        if field.crop == source_conditions["crop"]:
            score += 1
    if "climate_class" in source_conditions:
        checks += 1
        if field.climate_class == source_conditions["climate_class"]:
            score += 1
    return score / checks if checks else 0.3


# weight ceiling — literature can never dominate local data
LITERATURE_WEIGHT_CEILING = 0.15
LOCAL_DATA_WEIGHT = 0.85


@dataclass
class RetrievedKnowledge:
    sources: list[dict]
    local_weight: float
    literature_weight: float
    disclaimer_ar: str


def retrieve(
    field: FieldConditions,
    candidate_sources: list[KnowledgeSource],
    top_k: int = 3,
) -> RetrievedKnowledge:
    """استرجاع محافظ: يرتّب بالتشابه، يحدّ وزن الأدبيات، يوثّق كل مصدر."""
    scored = []
    for s in candidate_sources:
        sim = condition_similarity(field, s.conditions)
        scored.append(
            {
                "source_id": s.source_id,
                "tier": s.tier.value,
                "citation": s.citation,
                "content_ar": s.content_ar,
                "similarity": round(sim, 2),
                # literature weight scaled by similarity AND capped
                "applied_weight": round(
                    min(sim * LITERATURE_WEIGHT_CEILING, LITERATURE_WEIGHT_CEILING), 3
                )
                if s.tier == SourceTier.LITERATURE
                else None,
            }
        )
    scored.sort(key=lambda x: -x["similarity"])
    top = scored[:top_k]

    # warn on weak matches (anti citation-washing)
    weak = [s for s in top if s["similarity"] < 0.5 and s["tier"] == "literature"]
    disclaimer = (
        "المصادر داعمة محتملة فقط. التوصية مبنية على بيانات الحقل المحلية "
        f"({int(LOCAL_DATA_WEIGHT * 100)}%) والفيزياء، لا على الأدبيات."
    )
    if weak:
        disclaimer += " ⚠️ بعض المصادر منخفضة التطابق مع ظروفك — استرشادية بحذر."

    return RetrievedKnowledge(
        sources=top,
        local_weight=LOCAL_DATA_WEIGHT,
        literature_weight=LITERATURE_WEIGHT_CEILING,
        disclaimer_ar=disclaimer,
    )
