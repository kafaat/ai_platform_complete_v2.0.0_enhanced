"""api/water_efficiency.py — كفاءة استخدام المياه (Outcome KPI، تجميع من دفتر المياه).

الغرض:
   مؤشّر **نتيجة** لكلّ حقل على فترة: كم من الماء المُورَّد (ريّ + مطر فعّال) ذهب فعلاً
   لتلبية الطلب المائيّ للمحصول (ETc)؟ يخدم هدف «خفض المياه» مباشرةً — كفاءة منخفضة =
   إفراط ريّ (هدر) قابل للخفض. يُجمَّع من حقول `water_ledger` اليوميّة الموجودة (etc/مطر/ريّ).

صدق صريح — ما هذا وما ليس هو:
   - **توازن مائيّ لا غلّة:** يقيس الكفاءة من ETc مقابل الماء المُورَّد. الـWUE القائم على
     **الغلّة** (kg/m³) **خارج النطاق** — لا حلقة غلّة-أرضيّة بمقياس، فلا يُقاس بصدق.
   - **بوّابات needs_data:** لا أيّام بطلب (ETc) ⇒ `needs_data`؛ لا ريّ فعليّ مُسجَّل ⇒
     `needs_irrigation_data` (المطر وحده لا يقيس الكفاءة) — لا رقم مُضلِّل، لا اختلاق.
   - **تبسيط مُعلَن:** المطر الفعّال = `min(rain, etc)` يوميّاً (الفائض يُفقَد جرياً/صرفاً) —
     تبسيط FAO-56 نمطيّ، موسوم `calibrated=False`.
   - دالّة **نقيّة** (لا I/O)، fail-safe: مدخل غير صالح ⇒ كتلة `needs_data` (لا رمي).
"""

from __future__ import annotations

_BASE_NOTE = (
    "الكفاءة من التوازن المائيّ (ETc مقابل المُورَّد)؛ WUE القائم على الغلّة خارج النطاق (لا حلقة غلّة)."
)


def _num(v) -> float | None:
    if v is None or isinstance(v, bool):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def compute_water_efficiency(entries) -> dict:
    """يجمّع كفاءة استخدام المياه من قيود دفتر المياه (entries: قائمة dict لكلّ يوم).

    يقرأ من كلّ قيد: ``etc_mm`` (الطلب) · ``rain_mm`` · ``irrigation_mm``. يُرجِع كتلة:
    ``status`` (ok|needs_data|needs_irrigation_data) · مجاميع · ``water_use_efficiency``
    (نسبة الماء المُورَّد المُستغَلّ، ≤1؛ أدنى = هدر) · ``demand_met_pct`` (تغطية الطلب) ·
    ``over_application_mm`` (الماء الزائد — ذراع الخفض) · ``calibrated=False`` · ``source``.
    """
    if not isinstance(entries, list):
        entries = []

    etc_total = irr_total = eff_rain_total = 0.0
    days_with_etc = days_with_irrigation = 0
    for e in entries:
        if not isinstance(e, dict):
            continue
        etc = _num(e.get("etc_mm"))
        if etc is None or etc <= 0:
            continue  # يوم بلا طلب مائيّ معروف لا يدخل الحساب (لا تلفيق)
        days_with_etc += 1
        etc_total += etc
        irr = _num(e.get("irrigation_mm"))
        if irr is not None and irr > 0:
            days_with_irrigation += 1
            irr_total += irr
        rain = _num(e.get("rain_mm"))
        # المطر الفعّال: ما يُغطّي الطلب فقط (الفائض يُفقَد) — تبسيط مُعلَن.
        eff_rain_total += min(rain, etc) if rain is not None and rain > 0 else 0.0

    supplied_total = irr_total + eff_rain_total
    base = {
        "days_counted": days_with_etc,
        "etc_mm_total": round(etc_total, 1),
        "irrigation_mm_total": round(irr_total, 1),
        "effective_rain_mm_total": round(eff_rain_total, 1),
        "supplied_mm_total": round(supplied_total, 1),
        "water_use_efficiency": None,
        "demand_met_pct": None,
        "over_application_mm": None,
        "calibrated": False,  # تبسيط FAO-56، غير معايَر ميدانيّاً
        "source": "water_ledger",
    }

    if days_with_etc == 0:
        return {
            **base,
            "status": "needs_data",
            "note_ar": "لا أيّام بطلب مائيّ (ETc) مُسجَّل — لا كفاءة محسوبة (صدق).",
        }
    if days_with_irrigation == 0:
        return {
            **base,
            "status": "needs_irrigation_data",
            "note_ar": "لا ريّ فعليّ مُسجَّل — سجّل الريّ لقياس الكفاءة (المطر وحده لا يكفي).",
        }

    # WUE = نسبة الماء المُورَّد المُستغَلّ (مقصوصة ≤1: الفائض هدر، النقص لا يرفعها فوق 1).
    wue = round(min(1.0, etc_total / supplied_total), 3) if supplied_total > 0 else None
    return {
        **base,
        "status": "ok",
        "water_use_efficiency": wue,
        "demand_met_pct": round(min(1.0, supplied_total / etc_total) * 100.0, 1),
        "over_application_mm": round(max(0.0, supplied_total - etc_total), 1),
        "note_ar": _BASE_NOTE,
    }
