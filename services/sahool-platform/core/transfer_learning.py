"""
sahool_core.transfer_learning
==============================
نقل التعلّم بين المديريات — يبني فوق multi_season + cross_reference.

الفجوة المسدودة: عند التوسّع لمديرية جديدة، نبدأ من الصفر. لا
calibrations، لا outcomes، لا سياق تاريخي. هذا يخلق "cold start
problem" زراعي.

الحلّ: نقل تعلّم محدود من مديرية غنيّة بالبيانات إلى أخرى، بشروط:
  • مناخياً متشابهتان (نفس governorate أو ظروف مماثلة)
  • نفس المحصول
  • نفس صنف التربة (إن وُجد)
  • وزن مخفّض (لا نُعامل المنقول مثل المعاير محلياً)

المبدأ الحاكم: "Suggestion not Substitution"
  المُنقول يُقدَّم كـ"baseline أوّلي مقترح"، لا كحقيقة.
  المعايرة المحلّية تستبدله فور توفّرها (2+ موسم).

التمييز عن transfer learning في ML:
  • هنا: نقل zone_factor + crop suitability + management practices
  • لا "fine-tuning" — قواعد زراعية لا أوزان شبكة عصبية
  • شفّاف كلياً (المهندس يرى المصدر + درجة الثقة)

المبادئ المحفوظة:
  • صفر اختراع: لا مديرية مصدر متطابقة → "لا نقل ممكن" صراحة
  • Tenant isolation: النقل يحدث بين مديريات tenant واحد فقط
  • Decay confidence: ثقة النقل تنخفض كلّما زاد الاختلاف
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class TransferConfidence(str, Enum):
    NONE = "none"  # لا نقل ممكن
    LOW = "low"  # baseline مقترح فقط
    MEDIUM = "medium"  # متشابهتان جدّاً
    HIGH = "high"  # متشابهتان + outcomes متطابقة


@dataclass
class DistrictProfile:
    """ملخّص مديرية للمقارنة."""

    district_id: str
    tenant_id: str
    governorate_id: str | None = None
    crop_seasons_count: int = 0  # بيانات كم موسم
    avg_yield_t_ha: float | None = None
    typical_salinity_ds_m: float | None = None
    dominant_soil_type: str | None = None
    common_crops: list[str] = field(default_factory=list)
    avg_zone_factor: float | None = None


@dataclass
class TransferSuggestion:
    """اقتراح نقل من مديرية لأخرى."""

    target_district: str
    source_district: str
    crop: str
    suggested_zone_factor: float | None
    suggested_practices: list[str] = field(default_factory=list)
    confidence: TransferConfidence = TransferConfidence.NONE
    similarity_score: float = 0.0
    reasons_ar: list[str] = field(default_factory=list)
    decay_factors_ar: list[str] = field(default_factory=list)
    notes_ar: str = ""


def _compute_district_similarity(
    source: DistrictProfile,
    target: DistrictProfile,
) -> tuple[float, list[str], list[str]]:
    """يحسب درجة تشابه بين مديريتين. شفّاف، أوزان صريحة.

    يُرجع (score 0-1، أسباب التشابه، عوامل decay)."""
    score = 0.0
    reasons: list[str] = []
    decays: list[str] = []

    # 1. نفس المحافظة (مناخياً متقاربتان)
    if (
        source.governorate_id
        and target.governorate_id
        and source.governorate_id == target.governorate_id
    ):
        score += 0.40
        reasons.append(f"نفس المحافظة ({source.governorate_id})")
    else:
        decays.append("محافظات مختلفة (تباين مناخي محتمل)")

    # 2. نفس صنف التربة (المعايرة الزراعية)
    if (
        source.dominant_soil_type
        and target.dominant_soil_type
        and source.dominant_soil_type == target.dominant_soil_type
    ):
        score += 0.30
        reasons.append(f"تربة متشابهة ({source.dominant_soil_type})")
    elif source.dominant_soil_type and target.dominant_soil_type:
        decays.append(
            f"تربة مختلفة (مصدر: {source.dominant_soil_type}، هدف: {target.dominant_soil_type})"
        )

    # 3. ملوحة متقاربة (تأثير مباشر على zone_factor)
    if source.typical_salinity_ds_m and target.typical_salinity_ds_m:
        diff = abs(source.typical_salinity_ds_m - target.typical_salinity_ds_m)
        denom = max(source.typical_salinity_ds_m, target.typical_salinity_ds_m, 1e-6)
        salinity_pct_diff = diff / denom * 100
        if salinity_pct_diff < 20:
            score += 0.20
            reasons.append(f"ملوحة متقاربة (فرق {salinity_pct_diff:.0f}%)")
        else:
            decays.append(f"ملوحة مختلفة (فرق {salinity_pct_diff:.0f}%)")

    # 4. كفاية بيانات المصدر
    if source.crop_seasons_count >= 4:
        score += 0.10
        reasons.append(f"بيانات وفيرة في المصدر ({source.crop_seasons_count} موسم)")
    elif source.crop_seasons_count >= 2:
        score += 0.05
        decays.append(f"بيانات محدودة ({source.crop_seasons_count} موسم فقط)")
    else:
        decays.append(f"بيانات قليلة جدّاً ({source.crop_seasons_count})")

    return round(min(score, 1.0), 2), reasons, decays


def suggest_transfer(
    target_district: DistrictProfile,
    source_candidates: list[DistrictProfile],
    crop: str,
    *,
    min_similarity: float = 0.4,
) -> TransferSuggestion:
    """يقترح نقل تعلّم من أفضل مديرية مصدر متاحة.

    Tenant isolation حرج: لا ينقل بين tenants أبداً.
    إن لم تتوفّر مديرية مناسبة → confidence=NONE صراحة، لا اختراع."""
    # حرس tenant
    same_tenant_sources = [
        s
        for s in source_candidates
        if s.tenant_id == target_district.tenant_id and s.district_id != target_district.district_id
    ]

    if not same_tenant_sources:
        return TransferSuggestion(
            target_district=target_district.district_id,
            source_district="",
            crop=crop,
            suggested_zone_factor=None,
            confidence=TransferConfidence.NONE,
            notes_ar=(
                "لا مديريات مصدر متاحة في نفس tenant — "
                "لا نقل ممكن. ابدأ بمعايرة محلّية من الموسم الأوّل."
            ),
        )

    # يجب أن يحوي المحصول
    relevant_sources = [s for s in same_tenant_sources if crop in s.common_crops]
    if not relevant_sources:
        return TransferSuggestion(
            target_district=target_district.district_id,
            source_district="",
            crop=crop,
            suggested_zone_factor=None,
            confidence=TransferConfidence.NONE,
            notes_ar=(f"لا مديرية مصدر زرعت '{crop}' من قبل — لا نقل ممكن لهذا المحصول."),
        )

    # احسب التشابه لكل مرشّح، اختر الأفضل
    scored = []
    for src in relevant_sources:
        score, reasons, decays = _compute_district_similarity(src, target_district)
        scored.append((score, src, reasons, decays))

    scored.sort(key=lambda x: x[0], reverse=True)
    best_score, best_source, best_reasons, best_decays = scored[0]

    if best_score < min_similarity:
        return TransferSuggestion(
            target_district=target_district.district_id,
            source_district=best_source.district_id,
            crop=crop,
            suggested_zone_factor=None,
            confidence=TransferConfidence.NONE,
            similarity_score=best_score,
            reasons_ar=best_reasons,
            decay_factors_ar=best_decays,
            notes_ar=(
                f"أفضل مرشّح ({best_source.district_id}) أقلّ من العتبة "
                f"({best_score:.2f} < {min_similarity}). "
                "ابدأ بمعايرة محلّية."
            ),
        )

    # حدّد مستوى الثقة
    if best_score >= 0.85 and best_source.crop_seasons_count >= 4:
        confidence = TransferConfidence.HIGH
    elif best_score >= 0.65:
        confidence = TransferConfidence.MEDIUM
    else:
        confidence = TransferConfidence.LOW

    # احسب zone_factor المقترح مع تخفيض حسب الثقة
    suggested_zf = None
    if best_source.avg_zone_factor is not None:
        # نضرب بـreduction factor: HIGH=1.0، MEDIUM=0.95، LOW=0.85
        reduction = {
            TransferConfidence.HIGH: 1.0,
            TransferConfidence.MEDIUM: 0.95,
            TransferConfidence.LOW: 0.85,
        }[confidence]
        # نُحوّل نحو 1.0 (محايد) بنسبة 1-reduction
        # zone_factor=0.85 منقول بثقة LOW → 0.85*0.85 + 1.0*0.15 = 0.7225+0.15 = 0.8725
        # هذا تخفيف "نحو المحايد" — لا نُعامل المنقول كمعاير محلياً
        suggested_zf = round(best_source.avg_zone_factor * reduction + 1.0 * (1 - reduction), 3)

    return TransferSuggestion(
        target_district=target_district.district_id,
        source_district=best_source.district_id,
        crop=crop,
        suggested_zone_factor=suggested_zf,
        confidence=confidence,
        similarity_score=best_score,
        reasons_ar=best_reasons,
        decay_factors_ar=best_decays,
        notes_ar=(
            f"اقتراح أوّلي من '{best_source.district_id}' بثقة "
            f"{confidence.value}. يُستبدَل فور توفّر معايرة "
            "محلّية (2+ موسم)."
        ),
    )


def transfer_summary(suggestion: TransferSuggestion) -> str:
    """ملخّص قابل للقراءة للواجهة."""
    if suggestion.confidence == TransferConfidence.NONE:
        return f"⚠️ {suggestion.notes_ar}"

    parts = [
        f"💡 نقل من {suggestion.source_district} → {suggestion.target_district}",
        f"ثقة: {suggestion.confidence.value} (score={suggestion.similarity_score})",
    ]
    if suggestion.suggested_zone_factor is not None:
        parts.append(f"zone_factor مقترح: {suggestion.suggested_zone_factor}")
    if suggestion.reasons_ar:
        parts.append("أسباب: " + "، ".join(suggestion.reasons_ar[:2]))
    if suggestion.decay_factors_ar:
        parts.append("تحفّظات: " + "، ".join(suggestion.decay_factors_ar[:2]))
    return "\n  ".join(parts)
