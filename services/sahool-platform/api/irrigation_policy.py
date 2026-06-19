"""api/irrigation_policy.py — طبقة سياسة الريّ (#375)

الطبقة الرابعة في خطّ «مركز المحاصيل»: الهدف (objective) الذي يحكم متحكّم الريّ
**قرار سياسة لا هندسة** — يختلف حسب المنطقة وندرة الماء. بدل تثبيت هدف واحد،
نُعرّفه كاستراتيجيّة قابلة للاختيار تترجم إلى مقبضَين يفهمهما المتحكّم (MPC):

  • trigger_fraction: نُطلق الريّ حين Dr ≥ trigger_fraction × RAW.
  • refill_fraction: نملأ هذه النسبة من الاستنزاف Dr (1.0 = حتى السعة الحقليّة).

السياسات:
  • WATER_SAVING (ريّ عجزيّ): ينتظر حتى RAW ثمّ يملأ جزئيّاً — يقبل إجهاداً خفيفاً
    مقابل حفظ الخزّان. الأنسب لندرة مياه اليمن (الافتراضيّ).
  • YIELD_MAX: يُطلق قبل RAW بهامش أمان ويملأ كاملاً — لا إجهاد، أعلى استهلاك.
  • PROFIT: يوازن تكلفة الماء مقابل قيمة الغلّة — **يتطلّب أسعاراً** (تُمرَّر، لا
    تُختلق)؛ عند غيابها يتراجع لـ WATER_SAVING مع تحذير صريح.

نقيّ حتميّ (لا I/O). ⚠ المقابض أوّليّة تحتاج معايرة يمنيّة. موسومة.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class IrrigationPolicy(str, Enum):
    WATER_SAVING = "water_saving"
    YIELD_MAX = "yield_max"
    PROFIT = "profit"


@dataclass
class PolicyParams:
    """مقابض المتحكّم المُشتقّة من السياسة."""

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


# مقابض كلّ سياسة — ⚠ أوّليّة، تحتاج معايرة يمنيّة (calibrated=False).
_POLICY_KNOBS: dict[IrrigationPolicy, tuple[float, float, bool]] = {
    # (trigger_fraction, refill_fraction, allow_stress)
    IrrigationPolicy.WATER_SAVING: (1.0, 0.80, True),
    IrrigationPolicy.YIELD_MAX: (0.90, 1.00, False),
    IrrigationPolicy.PROFIT: (1.0, 0.90, True),
}


def policy_params(
    policy: IrrigationPolicy | str,
    water_price_per_m3: float | None = None,
    yield_value_per_ha: float | None = None,
) -> PolicyParams:
    """يترجم السياسة إلى مقابض المتحكّم — نقيّ حتميّ.

    PROFIT يتطلّب أسعاراً؛ عند غيابها يتراجع لـ WATER_SAVING (الأحوط في ندرة الماء)
    مع تحذير — لا نختلق اقتصاداً. مع توفّر الأسعار نعدّل refill بمنطق شفّاف موسوم.
    """
    if isinstance(policy, str):
        try:
            policy = IrrigationPolicy(policy.strip().lower())
        except ValueError:
            ws = _POLICY_KNOBS[IrrigationPolicy.WATER_SAVING]
            return PolicyParams(
                IrrigationPolicy.WATER_SAVING,
                *ws,
                notes_ar=[f"سياسة غير معروفة ({policy}) — تراجع لـ water_saving (الأحوط)"],
            )

    trig, refill, allow = _POLICY_KNOBS[policy]
    notes: list[str] = []

    if policy is IrrigationPolicy.PROFIT:
        if water_price_per_m3 is None or yield_value_per_ha is None:
            ws = _POLICY_KNOBS[IrrigationPolicy.WATER_SAVING]
            return PolicyParams(
                IrrigationPolicy.WATER_SAVING,
                *ws,
                notes_ar=[
                    "PROFIT يتطلّب water_price_per_m3 وyield_value_per_ha — "
                    "غائبة ⇒ تراجع لـ water_saving (لا اختلاق اقتصاد)"
                ],
            )
        # منطق شفّاف موسوم: ماء أغلى نسبةً للغلّة ⇒ ملء أقلّ (عجز أعمق)، والعكس.
        # النسبة price/value مقيّسة إلى نطاق refill [0.7, 1.0]. ⚠ heuristic غير معايَر.
        ratio = water_price_per_m3 / max(yield_value_per_ha, 1e-9)
        refill = max(0.7, min(1.0, 1.0 - 5000.0 * ratio))
        notes.append("refill من منطق اقتصاديّ heuristic (price/value) غير معايَر يمنيّاً — راجِع")

    return PolicyParams(
        policy=policy,
        trigger_fraction=trig,
        refill_fraction=refill,
        allow_stress=allow,
        notes_ar=notes,
    )
