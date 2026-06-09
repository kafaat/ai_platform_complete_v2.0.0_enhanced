"""
sahool_core.practice_promotion
==============================
سلّم ترقية الممارسة الجماعية — تحويل الخبرة المحلية من سقف ثابت
إلى مسار مكتسب مشروط.

المبدأ: الممارسة المجتمعية تبدأ تخميناً (FSI≈0.10)، وتُرقّى بالتراكم
(عدد + زمن + اتساق مكاني/زمني + توافق فيزيائي + قابلية قياس + تبنٍّ).

الخط الأحمر (لا يُكسَر):
  • السقف المطلق FSI=0.65 — الممارسة المجتمعية لا تبلغ الفيزياء (0.95)
    ولا المختبر (0.90) مهما تراكمت. أقصاها "نمط إقليمي مُعاير".
  • التعارض مع PHI أو FAO-56 → رفض نهائي (لا ترقية مهما كان العدد).
  • التباين العالي (std > mean) → تجميد (لا نمط).
  • الترقية تتطلّب تراكماً لا صعوداً فردياً (كل مستوى يحتاج ما قبله).

يكمّل: knowledge_levels (يعطي المجتمعي سقفاً)، farmer_agency (يسجّل القبول/الرفض).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

FSI_CEILING_COMMUNITY = 0.65  # السقف المطلق — لا تتجاوزه الممارسة المجتمعية أبداً
FSI_FLOOR = 0.10  # أرضية التخمين


class PhysicalCompat:
    COMPATIBLE = "compatible"  # +0.10
    PARTIAL = "partial"  # +0.05
    CONFLICTING = "conflicting"  # -0.30
    VIOLATES_SAFETY = "violates"  # رفض نهائي (PHI/FAO صارخ)


@dataclass
class PracticeEvidence:
    """شواهد ممارسة جماعية — كلها قابلة للتحقّق."""

    n_farmers: int = 0
    n_seasons: int = 0
    spatial_fields: int = 0  # حقول متجاورة بنفس التربة/المناخ
    temporal_success_seasons: int = 0
    physical_compat: str = PhysicalCompat.PARTIAL
    has_yield_data: bool = False
    has_full_dataset: bool = False  # غلة+طقس+تربة
    adoption_rate: float = 0.0  # 0..1
    yield_std: float | None = None  # للكشف عن التباين العالي
    yield_mean: float | None = None


@dataclass
class PromotionResult:
    fsi: float
    weight: float
    ceiling: str  # سقف الثقة (none/low/medium)
    status_ar: str
    show_in_farmer_view: bool
    breakdown: dict = field(default_factory=dict)
    reason_ar: str = ""


def _adoption_bonus(rate: float) -> float:
    if rate >= 0.70:
        return 0.20
    if rate >= 0.50:
        return 0.15
    if rate >= 0.30:
        return 0.10
    if rate >= 0.10:
        return 0.05
    return 0.0


def _spatial_bonus(fields: int) -> float:
    if fields >= 20:
        return 0.15
    if fields >= 5:
        return 0.10
    if fields >= 3:
        return 0.05
    return 0.0


def _temporal_bonus(seasons: int) -> float:
    if seasons >= 10:
        return 0.15
    if seasons >= 3:
        return 0.10
    if seasons >= 2:
        return 0.05
    return 0.0


def _measurability_bonus(ev: PracticeEvidence) -> float:
    if ev.has_full_dataset:
        return 0.20
    if ev.has_yield_data:
        return 0.10
    return 0.0


def _count_bonus(n_farmers: int) -> float:
    if n_farmers >= 200:
        return 0.20
    if n_farmers >= 50:
        return 0.15
    if n_farmers >= 30:
        return 0.10
    if n_farmers >= 10:
        return 0.05
    return 0.0


def _physical_delta(compat: str) -> float:
    return {
        PhysicalCompat.COMPATIBLE: 0.10,
        PhysicalCompat.PARTIAL: 0.05,
        PhysicalCompat.CONFLICTING: -0.30,
    }.get(compat, 0.0)


def evaluate_practice(ev: PracticeEvidence) -> PromotionResult:
    """يحسب FSI الممارسة من شواهدها التراكمية، مع الخطوط الحمراء.

    الترتيب: الرفض النهائي أولاً (سلامة/تباين)، ثم التراكم، ثم السقف الصارم."""
    # ١. رفض نهائي: تعارض السلامة (PHI/FAO صارخ)
    if ev.physical_compat == PhysicalCompat.VIOLATES_SAFETY:
        return PromotionResult(
            fsi=0.0,
            weight=0.0,
            ceiling="none",
            status_ar="مرفوضة",
            show_in_farmer_view=False,
            reason_ar="تتعارض مع السلامة (PHI/FAO) — رفض نهائي لا يُرقّى",
        )

    # ٢. تجميد: تباين عالٍ (std > mean = لا نمط)
    if (
        ev.yield_std is not None
        and ev.yield_mean is not None
        and ev.yield_mean > 0
        and ev.yield_std > ev.yield_mean
    ):
        return PromotionResult(
            fsi=FSI_FLOOR,
            weight=0.0,
            ceiling="none",
            status_ar="مجمّدة",
            show_in_farmer_view=False,
            reason_ar="نتائج متباينة (الانحراف > المتوسط) — لا نمط موثوق",
        )

    # ٣. التراكم
    bd = {
        "count": _count_bonus(ev.n_farmers),
        "spatial": _spatial_bonus(ev.spatial_fields),
        "temporal": _temporal_bonus(ev.temporal_success_seasons),
        "physical": _physical_delta(ev.physical_compat),
        "measurability": _measurability_bonus(ev),
        "adoption": _adoption_bonus(ev.adoption_rate),
    }
    raw = sum(bd.values())

    # التعارض الفيزيائي يخفض مباشرةً (لا تخميد للسالب)
    if bd["physical"] < 0:
        fsi = max(FSI_FLOOR, FSI_FLOOR + raw)
    else:
        # تخميد لوغاريتمي (diminishing returns): يحافظ على التمييز ويقترب
        # من السقف دون بلوغه خطّياً. يحلّ تناقض الوثيقة (جمع 0.90 → ~0.55-0.62).
        # المدى الفعّال [FLOOR, CEILING] عبر: floor + (ceiling-floor)·(1-e^(-k·raw))
        span = FSI_CEILING_COMMUNITY - FSI_FLOOR
        fsi = FSI_FLOOR + span * (1.0 - math.exp(-2.4 * raw))

    # ٤. السقف الصارم: لا تبلغ الممارسة المجتمعية الفيزياء/المختبر
    capped = min(fsi, FSI_CEILING_COMMUNITY)
    was_capped = fsi > FSI_CEILING_COMMUNITY
    fsi = round(capped, 2)

    # تحويل FSI لسقف ثقة وحالة
    if fsi < 0.30:
        ceiling, status, show = "none", "تخمين", False
    elif fsi < 0.35:
        ceiling, status, show = "low", "مجتمعية", True
    elif fsi < 0.50:
        ceiling, status, show = "low", "موثّقة", True
    elif fsi < 0.60:
        ceiling, status, show = "medium", "استقرائية", True
    else:
        ceiling, status, show = "medium", "مُعايرة/إقليمية", True

    weight = round(fsi * 0.9, 2)  # الوزن أقلّ قليلاً من FSI (تحفّظ)
    reason = f"FSI={fsi} ({status})"
    if was_capped:
        reason += f" — حُدّ بالسقف المجتمعي {FSI_CEILING_COMMUNITY} (لا يبلغ الفيزياء)"
    return PromotionResult(
        fsi=fsi,
        weight=weight,
        ceiling=ceiling,
        status_ar=status,
        show_in_farmer_view=show,
        breakdown={k: round(v, 2) for k, v in bd.items()},
        reason_ar=reason,
    )
