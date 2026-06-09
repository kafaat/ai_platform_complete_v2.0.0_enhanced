"""
sahool_core.index_scheduler
============================
نظام "المؤشّر عند الطلب" — يصنّف المؤشّرات حسب طبيعتها لتقنين التكلفة.

الفكرة (المستخدم): بعض المؤشّرات تُؤخذ لغرض محدّد مرّة (مثل نوع التربة)
ثم تُوقَف، وتُفعَّل عند الحاجة. أخرى تُراقَب دورياً (مثل NDVI المتغيّر).

المبرّر التقني:
  • كل طلب صورة/معالجة = تكلفة (credits + حوسبة)
  • BSI/نوع التربة ثابت جيولوجياً → حسابه دورياً هدر
  • NDVI/الرطوبة متغيّران موسمياً → يحتاجان مراقبة دورية

التصنيف:
  CONTINUOUS  → يُراقَب بإيقاع دوري (NDVI, NDMI, CWSI)
  ON_DEMAND   → يُفعَّل لغرض ثم يُوقَف (BSI/نوع التربة, مؤشّرات التربة)
  EVENT       → يُفعَّل عند حدث (SI ملوحة عند شكّ، عند الجفاف)
"""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum


class IndexCadence(str, Enum):
    CONTINUOUS = "continuous"   # مراقبة دورية
    ON_DEMAND = "on_demand"     # لغرض محدّد ثم يُوقَف
    EVENT = "event"             # عند حدث/شكّ


@dataclass
class IndexPolicy:
    """سياسة تفعيل مؤشّر — متى يُحسب ولماذا."""
    index_id: str
    cadence: IndexCadence
    purpose_ar: str
    refresh_days: int | None    # كل كم يوم (للدوري)؛ None لغير الدوري
    rationale_ar: str


# سياسات المؤشّرات (مبنية على طبيعة كل مؤشّر)
_INDEX_POLICIES = {
    # دائمة — متغيّرة موسمياً، تستحقّ المراقبة الدورية
    "NDVI": IndexPolicy("NDVI", IndexCadence.CONTINUOUS,
        "مراقبة صحة الغطاء", 7,
        "يتغيّر أسبوعياً مع نمو المحصول — مراقبة دورية ضرورية"),
    "NDMI": IndexPolicy("NDMI", IndexCadence.CONTINUOUS,
        "مراقبة رطوبة المحتوى", 10,
        "يتغيّر مع الري والإجهاد — مراقبة دورية"),
    "CWSI": IndexPolicy("CWSI", IndexCadence.CONTINUOUS,
        "مراقبة الإجهاد المائي", 7,
        "حسّاس للإجهاد الآني — مراقبة متكرّرة في موسم الجفاف"),

    # عند الطلب — ثابتة نسبياً، تُحسب لغرض ثم تُوقَف
    "BSI": IndexPolicy("BSI", IndexCadence.ON_DEMAND,
        "تقدير نوع التربة (مرّة عند الإنشاء أو التربة العارية)", None,
        "نوع التربة ثابت جيولوجياً — يُحسب مرّة عند الإنشاء أو بعد الحصاد "
        "(تربة عارية)، ثم يُوقَف. حسابه دورياً هدر للتكلفة"),
    "clay_iron": IndexPolicy("clay_iron", IndexCadence.ON_DEMAND,
        "تمييز نسيج التربة (الطين/الحديد)", None,
        "خصائص تربة ثابتة — تُحسب لغرض التصنيف مرّة، ثم تُوقَف"),

    # عند الحدث — تُفعَّل عند شكّ أو ظرف
    "SI": IndexPolicy("SI", IndexCadence.EVENT,
        "كشف الملوحة السطحية", None,
        "يُفعَّل عند الشكّ بملوحة (أعراض، سياق المديرية) — لا دورياً"),
}


def get_index_policy(index_id: str) -> IndexPolicy | None:
    """يُرجع سياسة تفعيل مؤشّر."""
    return _INDEX_POLICIES.get(index_id)


def should_compute_now(index_id: str, days_since_last: int | None,
                       purpose_active: bool = False) -> dict:
    """يقرّر هل يُحسب المؤشّر الآن — يوفّر التكلفة بتجنّب الحساب غير الضروري.

    days_since_last: أيام منذ آخر حساب (None = لم يُحسب قطّ)
    purpose_active: هل الغرض مُفعَّل (للمؤشّرات عند الطلب/الحدث)"""
    policy = get_index_policy(index_id)
    if policy is None:
        return {"compute": True, "reason_ar": "مؤشّر غير مُصنَّف — يُحسب افتراضياً"}

    if policy.cadence == IndexCadence.CONTINUOUS:
        if days_since_last is None:
            return {"compute": True, "reason_ar": f"{index_id}: أوّل حساب"}
        due = days_since_last >= (policy.refresh_days or 7)
        return {"compute": due,
                "reason_ar": (f"{index_id}: {'حان وقت التحديث' if due else 'حديث، لا داعي'} "
                              f"(كل {policy.refresh_days} يوم)")}

    if policy.cadence == IndexCadence.ON_DEMAND:
        # يُحسب مرّة إن لم يُحسب، أو عند تفعيل الغرض صراحةً
        if days_since_last is None:
            return {"compute": True, "reason_ar": f"{index_id}: حساب أوّلي للغرض"}
        if purpose_active:
            return {"compute": True, "reason_ar": f"{index_id}: الغرض مُفعَّل مجدّداً"}
        return {"compute": False,
                "reason_ar": f"{index_id}: مُحسَب سابقاً وثابت — موقوف لتوفير التكلفة"}

    # EVENT
    return {"compute": purpose_active,
            "reason_ar": (f"{index_id}: {'الحدث مُفعَّل' if purpose_active else 'لا حدث — موقوف'}")}


def cost_summary(active_indices: "list[str]") -> dict:
    """يلخّص أي المؤشّرات دائمة (تكلفة متكرّرة) وأيها عند الطلب (تكلفة مرّة)."""
    continuous, on_demand, event = [], [], []
    for idx in active_indices:
        p = get_index_policy(idx)
        if p is None:
            continue
        {IndexCadence.CONTINUOUS: continuous,
         IndexCadence.ON_DEMAND: on_demand,
         IndexCadence.EVENT: event}[p.cadence].append(idx)
    return {
        "continuous": continuous,
        "on_demand": on_demand,
        "event": event,
        "note_ar": (f"دائمة (تكلفة متكرّرة): {len(continuous)} · "
                    f"عند الطلب (مرّة): {len(on_demand)} · "
                    f"عند الحدث: {len(event)}. "
                    f"تقنين التكلفة: حساب الدائمة فقط دورياً، والباقي عند الحاجة."),
    }
