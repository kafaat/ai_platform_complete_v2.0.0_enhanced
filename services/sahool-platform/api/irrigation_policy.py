"""api/irrigation_policy.py — طبقة سياسة الريّ + مُحلِّل السياق (#375)

أهمّ طبقة قرار: كلّ ما قبلها يعرف **ماذا يحتاج المحصول**؛ هذه تقرّر **كيف نتصرّف**
تجاه الاحتياج. الهدف قرار سياسة لا هندسة — يختلف بالمنطقة وندرة الماء وتكلفته.

نُعرّف الهدف كاستراتيجيّة قابلة للاختيار تترجم لمقبضَين يفهمهما المُخطِّط:
  • trigger_fraction: نُطلق الريّ حين Dr ≥ trigger_fraction × RAW.
  • refill_fraction: نملأ هذه النسبة من الاستنزاف Dr (1.0 = حتى السعة الحقليّة).

السياسات الخمس:
  • WATER_SAVING — ريّ عجزيّ: ينتظر RAW ويملأ جزئيّاً (يقبل إجهاداً خفيفاً، يحفظ الخزّان).
  • YIELD_MAX — يُطلق قبل RAW ويملأ كاملاً (لا إجهاد، أعلى استهلاك).
  • PROFIT_MAX — يوازن تكلفة الماء/الطاقة مقابل قيمة الغلّة (يتطلّب أسعاراً، لا تُختلق).
  • SUSTAINABILITY — يترك سعة تخزين للمطر (refill أقلّ) فيقلّل التسرّب العميق/التملّح.
  • RISK_AVERSE — يُطلق مبكّراً بهامش أمان ويملأ كاملاً (يحمي من خطأ التنبّؤ/الإجهاد).

و**Policy Resolver**: لا سياسة افتراضيّة عالميّة ثابتة — يقرأ السياق (المنطقة/المحصول/
مصدر الماء/تكلفة الماء/الطاقة) ويختار الافتراضيّ المناسب (قابل للتجاوز يدويّاً).

نقيّ حتميّ (لا I/O). ⚠ المقابض وقواعد المُحلِّل أوّليّة تحتاج معايرة يمنيّة. موسومة.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class IrrigationPolicy(str, Enum):
    WATER_SAVING = "water_saving"
    YIELD_MAX = "yield_max"
    PROFIT_MAX = "profit_max"
    SUSTAINABILITY = "sustainability"
    RISK_AVERSE = "risk_averse"


# مرادفات/توافق خلفيّ (مثلاً "profit" ⇒ profit_max).
_POLICY_ALIASES: dict[str, IrrigationPolicy] = {
    "profit": IrrigationPolicy.PROFIT_MAX,
}


@dataclass
class PolicyParams:
    """مقابض المُخطِّط المُشتقّة من السياسة."""

    policy: IrrigationPolicy
    trigger_fraction: float  # × RAW ⇒ عتبة الإطلاق
    refill_fraction: float  # نسبة Dr المُعوَّضة
    allow_stress: bool  # هل تسمح السياسة بإجهاد خفيف (Dr يتجاوز RAW)
    calibrated: bool = False
    notes_ar: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "policy": self.policy.value,
            "trigger_fraction": round(self.trigger_fraction, 3),
            "refill_fraction": round(self.refill_fraction, 3),
            "allow_stress": self.allow_stress,
            "calibrated": self.calibrated,
            "notes_ar": self.notes_ar,
        }


# مقابض كلّ سياسة (trigger_fraction, refill_fraction, allow_stress).
# ⚠ أوّليّة، تحتاج معايرة يمنيّة (calibrated=False).
_POLICY_KNOBS: dict[IrrigationPolicy, tuple[float, float, bool]] = {
    IrrigationPolicy.WATER_SAVING: (1.0, 0.80, True),
    IrrigationPolicy.YIELD_MAX: (0.90, 1.00, False),
    IrrigationPolicy.PROFIT_MAX: (1.0, 0.90, True),
    IrrigationPolicy.SUSTAINABILITY: (1.0, 0.75, True),
    IrrigationPolicy.RISK_AVERSE: (0.80, 1.00, False),
}


def _coerce_policy(policy: IrrigationPolicy | str) -> IrrigationPolicy | None:
    """يطبّع سياسة (enum/نصّ/مرادف) ⇒ IrrigationPolicy أو None إن مجهولة."""
    if isinstance(policy, IrrigationPolicy):
        return policy
    key = str(policy).strip().lower()
    if key in _POLICY_ALIASES:
        return _POLICY_ALIASES[key]
    try:
        return IrrigationPolicy(key)
    except ValueError:
        return None


def policy_params(
    policy: IrrigationPolicy | str,
    water_price_per_m3: float | None = None,
    yield_value_per_ha: float | None = None,
) -> PolicyParams:
    """يترجم السياسة إلى مقابض المُخطِّط — نقيّ حتميّ.

    PROFIT_MAX يتطلّب أسعاراً؛ عند غيابها يتراجع لـ WATER_SAVING (الأحوط) مع تحذير —
    لا نختلق اقتصاداً. مع توفّرها نعدّل refill بمنطق شفّاف موسوم. سياسة مجهولة ⇒ تراجع.
    """
    resolved = _coerce_policy(policy)
    if resolved is None:
        ws = _POLICY_KNOBS[IrrigationPolicy.WATER_SAVING]
        return PolicyParams(
            IrrigationPolicy.WATER_SAVING,
            *ws,
            notes_ar=[f"سياسة غير معروفة ({policy}) — تراجع لـ water_saving (الأحوط)"],
        )

    trig, refill, allow = _POLICY_KNOBS[resolved]
    notes: list[str] = []

    if resolved is IrrigationPolicy.PROFIT_MAX:
        if water_price_per_m3 is None or yield_value_per_ha is None:
            ws = _POLICY_KNOBS[IrrigationPolicy.WATER_SAVING]
            return PolicyParams(
                IrrigationPolicy.WATER_SAVING,
                *ws,
                notes_ar=[
                    "PROFIT_MAX يتطلّب water_price_per_m3 وyield_value_per_ha — "
                    "غائبة ⇒ تراجع لـ water_saving (لا اختلاق اقتصاد)"
                ],
            )
        # منطق شفّاف موسوم: ماء أغلى نسبةً للغلّة ⇒ ملء أقلّ (عجز أعمق)، والعكس.
        # النسبة price/value مقيّسة إلى نطاق refill [0.7, 1.0]. ⚠ heuristic غير معايَر.
        ratio = water_price_per_m3 / max(yield_value_per_ha, 1e-9)
        refill = max(0.7, min(1.0, 1.0 - 5000.0 * ratio))
        notes.append("refill من منطق اقتصاديّ heuristic (price/value) غير معايَر يمنيّاً — راجِع")

    return PolicyParams(
        policy=resolved,
        trigger_fraction=trig,
        refill_fraction=refill,
        allow_stress=allow,
        notes_ar=notes,
    )


# ── مُحلِّل السياسة من السياق (Policy Resolver) ─────────────────────────────────


@dataclass
class PolicyContext:
    """سياق زراعيّ يقود اختيار السياسة الافتراضيّة (كلّه اختياريّ)."""

    region: str | None = None
    crop: str | None = None
    water_source: str | None = None  # surface | shallow_well | deep_well | rain
    water_cost: str | None = None  # cheap | moderate | expensive
    energy_cost: str | None = None  # cheap | moderate | expensive


# مصادر ماء مكلفة الضخّ (طاقة عالية) ⇒ تميل لـ PROFIT_MAX.
_EXPENSIVE_SOURCES = {"deep_well", "deep well", "بئر عميق"}
_CHEAP_SOURCES = {"surface", "rain", "سطحي", "مطر"}
_EXPENSIVE = {"expensive", "high", "مرتفع", "غالٍ", "غالي"}
_CHEAP = {"cheap", "low", "منخفض", "رخيص"}
# محاصيل دائمة عالية القيمة ⇒ حسّاسة لتكلفة الضخّ (تميل PROFIT_MAX عند الماء الغالي).
_PERENNIAL_HIGH_VALUE = {"citrus", "حمضيات", "موالح", "coffee", "بنّ", "بن", "mango", "مانجو"}


def _is(val: str | None, options: set[str]) -> bool:
    return bool(val) and val.strip().lower() in options


def resolve_policy(ctx: PolicyContext) -> tuple[IrrigationPolicy, list[str]]:
    """يختار السياسة الافتراضيّة المناسبة من السياق ⇒ (السياسة، أسباب) — قابلة للتجاوز.

    ⚠ قواعد heuristic أوّليّة (لا معايرة يمنيّة بعد). الافتراضيّ الأحوط WATER_SAVING.
    أمثلة: ماء غالٍ/بئر عميق ⇒ PROFIT_MAX؛ ماء رخيص+سطحيّ ⇒ YIELD_MAX.
    """
    reasons: list[str] = []
    expensive_water = _is(ctx.water_cost, _EXPENSIVE) or _is(ctx.energy_cost, _EXPENSIVE)
    deep_source = _is(ctx.water_source, _EXPENSIVE_SOURCES)
    cheap_water = _is(ctx.water_cost, _CHEAP)
    cheap_source = _is(ctx.water_source, _CHEAP_SOURCES)
    high_value = _is(ctx.crop, _PERENNIAL_HIGH_VALUE)

    # ١) ماء/طاقة غالية أو بئر عميق ⇒ الربحيّة تحكم (كلّ مكعّب مكلف).
    if expensive_water or deep_source:
        reasons.append("ماء/طاقة مرتفعة التكلفة (أو بئر عميق) ⇒ PROFIT_MAX")
        if high_value:
            reasons.append(f"محصول دائم عالي القيمة ({ctx.crop}) يعزّز اعتبار الربحيّة")
        return IrrigationPolicy.PROFIT_MAX, reasons

    # ٢) ماء رخيص ومصدر وفير ⇒ تعظيم الغلّة (لا قيد ماء فعليّ).
    if cheap_water and (cheap_source or ctx.water_source is None):
        reasons.append("ماء رخيص + مصدر سطحيّ/وفير ⇒ YIELD_MAX")
        return IrrigationPolicy.YIELD_MAX, reasons

    # ٣) إشارة استدامة صريحة (منطقة مجهدة المياه الجوفيّة).
    if _is(ctx.region, {"aquifer_stressed", "groundwater_stressed", "مجهدة"}):
        reasons.append("منطقة مجهدة المياه الجوفيّة ⇒ SUSTAINABILITY")
        return IrrigationPolicy.SUSTAINABILITY, reasons

    # ٤) الافتراضيّ الأحوط لندرة مياه اليمن.
    reasons.append("لا إشارة حاسمة ⇒ الافتراضيّ الأحوط WATER_SAVING")
    return IrrigationPolicy.WATER_SAVING, reasons
