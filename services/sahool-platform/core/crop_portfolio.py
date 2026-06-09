"""
core/crop_portfolio.py — تأثير المحفظة الزراعيّة
================================================

المرجع الأساسي:
  Renard, D., & Tilman, D. (2019).
  "National food production stabilized by crop diversity."
  Nature 571, 257-260. DOI: 10.1038/s41586-019-1316-y

الفكرة المُحقَّقة من الورقة:
  • تنويع المحاصيل على المستوى الوطني/المزرعي يستقرّ الإنتاج
  • التأثير يقارب قوّة الري — مهمّ خصوصاً في المناطق الجافة
  • محسوب على ٩١ دولة × ٥٠ سنة → ثابت إحصائياً

التطبيق على سهول:
  • السياق اليمني: مياه شحيحة + تقلّب مناخي → التنويع منطقي
  • المزارع الواحد يخصّص حقولاً متعدّدة لمحاصيل مختلفة
  • النظام يحسب مؤشّر التنويع + يقترح تحسينه (لا يأمر)

المبادئ المُراعاة:
  ✓ يقترح، لا يأمر (يحترم Farmer Agency)
  ✓ شفّاف رياضياً (Shannon-Wiener + Effective Number)
  ✓ pure function (deterministic, testable)
  ✓ يحترم crop_cards الموجودة
  ✓ نواة محايدة جغرافيّاً (يأخذ list of crops، لا يفترض اليمن)

ما ليس هنا:
  ✗ market price simulation (يحتاج market data feed)
  ✗ insurance pricing model (خارج النطاق)
  ✗ "أمر" المزارع بتغيير محاصيله (يحترم الـagency)
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional


# ─── Data structures ──────────────────────────────────────────────

@dataclass(frozen=True)
class FieldAllocation:
    """تخصيص حقل لمحصول."""
    field_id: str
    crop: str
    area_ha: float


@dataclass(frozen=True)
class PortfolioMetrics:
    """مؤشّرات تحليل المحفظة."""
    # المساحة الإجماليّة
    total_area_ha: float
    # عدد المحاصيل المختلفة
    crop_count: int
    # نسب المساحة لكل محصول (٠-١)
    proportions: dict[str, float]
    # Shannon-Wiener index (٠ = monoculture، أعلى = أكثر تنوّعاً)
    shannon_index: float
    # العدد الفعّال للمحاصيل (Hill number — تفسير بديهي)
    # مثال: ٤ محاصيل متساوية → ENC = ٤
    # محصول مهيمن ٩٠٪ → ENC قريب من ١
    effective_crop_number: float
    # نسبة المحصول المُهيمن (لاكتشاف monoculture)
    dominance_pct: float
    # تصنيف
    classification: str   # 'monoculture' | 'low' | 'moderate' | 'high'


@dataclass(frozen=True)
class PortfolioSuggestion:
    """اقتراح لتحسين المحفظة (لا يُلزم المزارع)."""
    current: PortfolioMetrics
    suggestion_ar: str
    rationale_ar: str
    # ❌ ليس قراراً، فقط معلومة:
    risk_level: str       # 'low' | 'moderate' | 'high'


# ─── Core math ────────────────────────────────────────────────────

def compute_portfolio_metrics(
    allocations: list[FieldAllocation],
) -> PortfolioMetrics:
    """يحسب مؤشّرات التنويع لمحفظة الحقول.

    Args:
        allocations: قائمة حقول، كل واحد بمحصوله ومساحته

    Returns:
        PortfolioMetrics مع shannon + ENC + dominance

    Raises:
        ValueError: لو قائمة فارغة أو المساحة الإجماليّة ٠
    """
    if not allocations:
        raise ValueError("قائمة الحقول فارغة")

    total_area = sum(a.area_ha for a in allocations)
    if total_area <= 0:
        raise ValueError(f"المساحة الإجماليّة يجب > 0، وُجِد {total_area}")

    # تجميع بمحصول
    crop_areas: dict[str, float] = {}
    for a in allocations:
        crop_areas[a.crop] = crop_areas.get(a.crop, 0.0) + a.area_ha

    # نسب
    proportions = {c: a / total_area for c, a in crop_areas.items()}

    # Shannon-Wiener: H = -Σ p_i × ln(p_i)
    # القيم: 0 (monoculture) إلى ln(N) (توزيع متساوٍ)
    shannon = 0.0
    for p in proportions.values():
        if p > 0:
            shannon -= p * math.log(p)

    # Hill number (Effective Number of Crops) = exp(Shannon)
    # تفسير: "كم محصول متساوٍ يعطي نفس التنوّع؟"
    enc = math.exp(shannon)

    # المهيمنة
    dominance = max(proportions.values()) * 100

    # تصنيف بسيط (مبدئي)
    if dominance >= 95:
        classification = 'monoculture'
    elif enc < 1.5:
        classification = 'low'
    elif enc < 2.5:
        classification = 'moderate'
    else:
        classification = 'high'

    return PortfolioMetrics(
        total_area_ha=total_area,
        crop_count=len(crop_areas),
        proportions=proportions,
        shannon_index=shannon,
        effective_crop_number=enc,
        dominance_pct=dominance,
        classification=classification,
    )


# ─── Suggestions (الاقتراحات، لا الأوامر) ────────────────────────

def suggest_for_portfolio(
    metrics: PortfolioMetrics,
    context: Optional[dict] = None,
) -> PortfolioSuggestion:
    """يولّد اقتراحاً نصّياً (عربي) بناءً على المؤشّرات.

    Args:
        metrics: من compute_portfolio_metrics()
        context: اختياري — معلومات إضافيّة (مثلاً water_scarce=True)

    المرجع الفكري:
      Renard & Tilman 2019 — التنويع ≈ الري في المناطق الجافة
    """
    ctx = context or {}
    water_scarce = ctx.get('water_scarce', False)

    if metrics.classification == 'monoculture':
        # ٩٥٪+ من المساحة بمحصول واحد
        dominant = max(metrics.proportions.items(), key=lambda kv: kv[1])
        suggestion = (
            f"تركيز شبه كامل على {dominant[0]} ({metrics.dominance_pct:.0f}٪). "
            f"التنويع بمحصول واحد إضافي قد يقلّل خطر الفشل التامّ."
        )
        rationale = (
            "الأدبيات (Nature 2019): التنويع يستقرّ الإنتاج بقوّة قريبة "
            "من الري — مهمّ خصوصاً عند شحّ المياه."
        )
        risk = 'high'

    elif metrics.classification == 'low':
        suggestion = (
            f"تنويع منخفض ({metrics.effective_crop_number:.1f} محصول فعّال). "
            "إضافة محصول مقاوم للجفاف قد يفيد."
        )
        rationale = (
            "محصول مهيمن واحد يجعل المحفظة حسّاسة لأيّ مرض/آفة/جفاف "
            "يضربه تحديداً."
        )
        risk = 'moderate'

    elif metrics.classification == 'moderate':
        if water_scarce:
            suggestion = (
                f"تنويع معتدل ({metrics.effective_crop_number:.1f}). "
                "ممتاز في سياق شحّ المياه."
            )
            rationale = (
                "في المناطق الجافة، التنويع يعمل كـ'تأمين طبيعي' "
                "ضد تقلّب الأمطار."
            )
        else:
            suggestion = (
                f"تنويع معتدل ({metrics.effective_crop_number:.1f}). "
                "محفظة متوازنة."
            )
            rationale = "حافظ على التوازن الحالي."
        risk = 'low'

    else:  # 'high'
        suggestion = (
            f"تنويع عالٍ ({metrics.effective_crop_number:.1f} محصول فعّال). "
            "محفظة مستقرّة جداً."
        )
        rationale = (
            "تنويع عالٍ = مقاومة عالية للصدمات، لكنّ راقب الكفاءة "
            "الإداريّة (تعقيد العمليات)."
        )
        risk = 'low'

    return PortfolioSuggestion(
        current=metrics,
        suggestion_ar=suggestion,
        rationale_ar=rationale,
        risk_level=risk,
    )


# ─── Comparison helper ────────────────────────────────────────────

def compare_portfolios(
    current: PortfolioMetrics,
    proposed: PortfolioMetrics,
) -> dict[str, float]:
    """يقارن محفظتَين (الحالي vs مُقترَح بعد إضافة/تغيير حقل).

    مفيد قبل اتّخاذ قرار: "لو أضفت قطعة شعير، كيف يتغيّر التنويع؟"
    """
    return {
        "shannon_delta": proposed.shannon_index - current.shannon_index,
        "enc_delta": proposed.effective_crop_number - current.effective_crop_number,
        "dominance_delta_pct":
            proposed.dominance_pct - current.dominance_pct,
        "improved": (
            proposed.effective_crop_number > current.effective_crop_number
            and proposed.dominance_pct < current.dominance_pct
        ),
    }


# ─── Helpers للعرض في الواجهة ────────────────────────────────────

def format_metrics_ar(m: PortfolioMetrics) -> str:
    """نصّ عربي مفهوم للمزارع."""
    crops_str = "، ".join(
        f"{c} ({p*100:.0f}٪)"
        for c, p in sorted(m.proportions.items(),
                          key=lambda kv: kv[1], reverse=True)
    )
    label = {
        'monoculture': 'محصول واحد',
        'low': 'تنويع منخفض',
        'moderate': 'تنويع معتدل',
        'high': 'تنويع عالٍ',
    }[m.classification]
    return (
        f"المحفظة: {label}\n"
        f"  المساحة الإجماليّة: {m.total_area_ha:.1f} هكتار\n"
        f"  المحاصيل ({m.crop_count}): {crops_str}\n"
        f"  مؤشّر التنويع: {m.effective_crop_number:.2f} محصول فعّال\n"
        f"  المهيمن: {m.dominance_pct:.0f}٪"
    )
