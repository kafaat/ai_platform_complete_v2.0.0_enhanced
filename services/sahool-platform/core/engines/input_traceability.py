"""core/engines/input_traceability.py — تتبّع مدخلات الإنتاج من البذرة للحصاد.

السؤال (المستخدم): هل نستفيد من مشروع warehouse لتتبّع مدخلات الإنتاج (بذور/
أسمدة/مبيدات…) انتهاءً بالحصاد؟

الجواب الصادق (لا نقل WareMap):
  • WareMap نظام Java/MySQL عامّ للمستودعات — تعارض مكدّس + ERPNext (نظامنا
    الأساسي) فيه Stock/Batch/Supplier/PO أنضج، وموصول عبر odoo-bridge.
  • الحاجة الزراعيّة الحقيقيّة ليست «مخزون عامّ» بل **نَسَب per حقل+موسم**: أيّ
    مدخل طُبّق على أيّ حقل/موسم → كلفته → ناتج الحصاد. هذا **يركّب القائم**:
      - `activities` (v35): يسجّل بذر/تسميد/رشّ/حصاد بتفاصيل JSONB ✓
      - `recommendation_outcomes` (v49): ناتج الحصاد الفعلي (t/ha) ✓
      - أحداث FERTILIZER_APPLIED/PESTICIDE_APPLIED/HARVEST ✓
  • المخزون نفسه (كمّيّات/موردون/شراء) يبقى في **ERPNext** — هذا يجمع النَسَب
    والاقتصاد per حقل، لا يستبدل الـERP.

ما يضيفه (الفجوة المسدودة): دفتر مدخلات يربط تطبيقات المدخل بالحقل+الموسم+الحصاد،
ويحسب كلفة/هكتار وكلفة/طنّ — النسخة الزراعيّة الصادقة من «warehouse».

⚠ المبدأ:
  • صدق: كلفة غائبة ⇒ تُستثنى من الإجمالي + يُعلَن نقص التغطية (لا تأليف رقم).
  • لا حصاد بعد ⇒ كلفة/طنّ غير متاحة (لا اختراع إنتاجيّة).
  • مساحة مجهولة ⇒ كلفة/هكتار غير متاحة.
  • حتميّ شفّاف: يُظهر النَسَب المرتّب (بذرة→مدخلات→حصاد) ومدى اكتمال التتبّع.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

# تصنيف نوع المدخل من نوع العمليّة (activities.activity_type).
ACTIVITY_TO_INPUT = {
    "planting": "seed",  # بذور/شتلات
    "fertilization": "fertilizer",  # أسمدة
    "spraying": "pesticide",  # مبيدات
    "irrigation": "water",  # ريّ (مدخل اقتصادي)
}
# ترتيب النَسَب من البذرة للحصاد (للعرض الزمنيّ المنطقيّ).
_INPUT_ORDER = {"seed": 0, "fertilizer": 1, "pesticide": 2, "water": 3, "other": 4}


class TraceabilityState(str, Enum):
    NO_INPUTS = "no_inputs"  # لا مدخلات مسجّلة بعد
    PARTIAL = "partial"  # مدخلات بلا حصاد/كلفة كاملة
    COMPLETE = "complete"  # بذرة→مدخلات→حصاد، كلفة مغطّاة


@dataclass
class InputApplication:
    """تطبيق مدخل إنتاج على حقل (مشتقّ من activities + تفاصيلها، أو من ERPNext)."""

    activity_type: str  # planting/fertilization/spraying/irrigation
    product_name: str | None = None  # اسم المنتج (سماد NPK، مبيد…)
    quantity: float | None = None
    unit: str | None = None  # kg/L/...
    cost: float | None = None  # كلفة المدخل (عملة موحّدة للمستأجِر)
    applied_on: str | None = None  # ISO date
    source: str = "sahool"  # sahool (activities) أو erpnext (procurement)

    @property
    def input_type(self) -> str:
        return ACTIVITY_TO_INPUT.get(self.activity_type, "other")


def build_input_ledger(
    applications: list[InputApplication],
    *,
    field_id: str,
    season_id: str | None = None,
    area_ha: float | None = None,
    harvest_yield_t_ha: float | None = None,
    currency: str = "YER",
) -> dict:
    """يبني دفتر المدخلات (بذرة→حصاد) + الاقتصاد per حقل/موسم — حتميّ صادق.

    كلفة غائبة تُستثنى من الإجمالي (تُعدّ في نقص التغطية، لا تُؤلَّف). كلفة/هكتار
    تتطلّب area_ha؛ كلفة/طنّ تتطلّب area_ha + إنتاجيّة الحصاد.
    """
    if not applications:
        return {
            "field_id": field_id,
            "season_id": season_id,
            "state": TraceabilityState.NO_INPUTS.value,
            "by_input_type": {},
            "total_cost": 0.0,
            "cost_coverage": 0.0,
            "currency": currency,
            "reason_ar": "لا مدخلات مسجّلة لهذا الحقل/الموسم بعد.",
        }

    # تجميع حسب نوع المدخل + جمع الكلفة المعروفة فقط.
    by_type: dict[str, dict] = {}
    n_with_cost = 0
    total_cost = 0.0
    for app in applications:
        t = app.input_type
        grp = by_type.setdefault(
            t, {"count": 0, "cost": 0.0, "n_with_cost": 0, "products": []}
        )
        grp["count"] += 1
        if app.product_name and app.product_name not in grp["products"]:
            grp["products"].append(app.product_name)
        if app.cost is not None:  # كلفة معروفة فقط — لا تأليف للغائب.
            grp["cost"] = round(grp["cost"] + app.cost, 2)
            grp["n_with_cost"] += 1
            n_with_cost += 1
            total_cost = round(total_cost + app.cost, 2)
    # ترتيب النَسَب من البذرة للحصاد.
    ordered = dict(sorted(by_type.items(), key=lambda kv: _INPUT_ORDER.get(kv[0], 9)))

    n_total = len(applications)
    cost_coverage = round(n_with_cost / n_total, 3) if n_total else 0.0

    # الاقتصاد — متاح فقط بشروطه الصادقة.
    cost_per_ha = round(total_cost / area_ha, 2) if area_ha and area_ha > 0 else None
    cost_per_ton = None
    if cost_per_ha is not None and harvest_yield_t_ha and harvest_yield_t_ha > 0:
        # كلفة/طنّ = (كلفة/هكتار) ÷ (طنّ/هكتار).
        cost_per_ton = round(cost_per_ha / harvest_yield_t_ha, 2)

    has_seed = "seed" in by_type
    has_harvest = harvest_yield_t_ha is not None and harvest_yield_t_ha > 0
    if has_seed and has_harvest and cost_coverage >= 1.0:
        state = TraceabilityState.COMPLETE
    else:
        state = TraceabilityState.PARTIAL

    gaps: list[str] = []
    if not has_seed:
        gaps.append("لا عمليّة بذر مسجّلة — النَسَب يبدأ ناقصاً")
    if not has_harvest:
        gaps.append("لا حصاد بعد — كلفة/طنّ غير متاحة")
    if area_ha is None or area_ha <= 0:
        gaps.append("مساحة الحقل مجهولة — كلفة/هكتار غير متاحة")
    if cost_coverage < 1.0:
        gaps.append(
            f"كلفة {n_with_cost}/{n_total} مدخل فقط معروفة "
            f"(تغطية {cost_coverage:.0%}) — الإجمالي جزئيّ"
        )

    return {
        "field_id": field_id,
        "season_id": season_id,
        "state": state.value,
        "by_input_type": ordered,
        "total_cost": total_cost,
        "cost_coverage": cost_coverage,
        "cost_per_ha": cost_per_ha,
        "cost_per_ton": cost_per_ton,
        "harvest_yield_t_ha": harvest_yield_t_ha,
        "area_ha": area_ha,
        "currency": currency,
        "gaps_ar": gaps,
        "honesty_note_ar": (
            "نَسَب المدخلات من البذرة للحصاد per حقل/موسم. الكلفة الغائبة تُستثنى "
            "من الإجمالي (تُعلَن لا تُؤلَّف). كلفة/طنّ تتطلّب حصاداً فعليّاً ومساحة. "
            "المخزون والشراء يبقيان في ERPNext — هذا يجمع النَسَب الزراعي، لا يستبدله."
        ),
    }
