"""api/field_portfolio.py — تحسين محفظة الحقول (Field Portfolio Optimization)

#381 (قمّة «نظام تشغيل المحصول»): حين تكون المياه/الميزانيّة محدودة على مستوى
**المزرعة كاملةً**، أين نوجّهها؟ توزّع الموردَ الشحيح عبر حقول متعدّدة لتعظيم العائد
الكلّيّ — «أعطِ الماء حيث يُنتج أكثر قيمة».

طبقة **نقيّة حتميّة** (لا I/O، لا واجهة): تتلقّى لكلّ حقل هامشه المتوقّع واحتياجه
المائيّ (يُحسبان من economic_state + خطّة الريّ خارجها) — **لا تُلفَّق** أرقام.

الخوارزميّة: جشِعة شفّافة بإنتاجيّة الماء (هامش/م³) — ترتّب الحقول تنازليّاً وتملأ
الأعلى إنتاجيّةً حتى نفاد المورد. ليست LP عامّة؛ والتوزيع الجزئيّ خطّيّ تقريبيّ
(العجز يخفض الهامش تناسبيّاً — تبسيط، الاستجابة الحقيقيّة مقعّرة). موسوم calibrated=False.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class FieldInput:
    """حقل في المحفظة: هامشه واحتياجه المائيّ عند الريّ الكامل (مُمرَّران، لا مُلفَّقان)."""

    field_id: str
    expected_margin: float  # الهامش المتوقّع للحقل عند الريّ الكامل
    water_demand_m3: float  # احتياج الحقل المائيّ الكلّيّ (م³)
    area_ha: float = 1.0


def _productivity(margin: float, demand: float) -> float:
    """إنتاجيّة الماء = هامش/م³؛ احتياج صفر ⇒ ∞ (قيمة بلا كلفة مائيّة)."""
    return margin / demand if demand > 0 else float("inf")


def optimize_field_portfolio(fields: list[FieldInput], total_water_m3: float) -> dict:
    """يوزّع ماءً محدوداً عبر الحقول لتعظيم العائد الكلّيّ — نقيّ حتميّ (جشِع بالإنتاجيّة).

    يرتّب الحقول تنازليّاً بإنتاجيّة الماء (هامش/م³)، ويملأ الأعلى حتى نفاد المورد؛ آخر
    حقل قد يأخذ ريّاً جزئيّاً (هامش متناسب خطّيّاً — تبسيط). صدق: لا اختلاق هوامش.
    """
    warnings_ar: list[str] = [
        "توزيع جشِع بإنتاجيّة الماء (هامش/م³)؛ التوزيع الجزئيّ خطّيّ تقريبيّ — غير معايَر",
    ]
    remaining = max(0.0, float(total_water_m3))
    # ترتيب تنازليّ بالإنتاجيّة (مع تثبيت الترتيب بـfield_id عند التساوي).
    order = sorted(
        fields,
        key=lambda f: (_productivity(f.expected_margin, f.water_demand_m3), f.field_id),
        reverse=True,
    )

    out: list[dict] = []
    total_margin = 0.0
    total_alloc = 0.0
    for f in order:
        demand = max(0.0, f.water_demand_m3)
        if demand <= 0.0:
            # لا كلفة مائيّة ⇒ الهامش كامل بلا تخصيص ماء.
            alloc, frac = 0.0, 1.0
        else:
            alloc = min(remaining, demand)
            frac = alloc / demand if demand > 0 else 0.0
            remaining -= alloc
        captured = f.expected_margin * frac
        total_margin += captured
        total_alloc += alloc
        status = "full" if frac >= 0.999 else "partial" if frac > 0.0 else "unmet"
        out.append(
            {
                "field_id": f.field_id,
                "area_ha": round(f.area_ha, 3),
                "water_demand_m3": round(demand, 2),
                "allocated_m3": round(alloc, 2),
                "fraction": round(frac, 3),
                "water_productivity": (
                    round(_productivity(f.expected_margin, demand), 4) if demand > 0 else None
                ),
                "expected_margin_captured": round(captured, 2),
                "status": status,
            }
        )

    # إعادة الترتيب إلى ترتيب المدخلات (أوضح للمستدعي).
    by_id = {d["field_id"]: d for d in out}
    ordered_out = [by_id[f.field_id] for f in fields]

    unmet = [d["field_id"] for d in ordered_out if d["status"] == "unmet"]
    if unmet:
        warnings_ar.append(f"حقول بلا ريّ لنقص المورد: {', '.join(unmet)}")

    return {
        "total_water_m3": round(float(total_water_m3), 2),
        "allocated_m3": round(total_alloc, 2),
        "unallocated_m3": round(max(0.0, remaining), 2),
        "total_expected_margin": round(total_margin, 2),
        "fields": ordered_out,
        "calibrated": False,
        "warnings_ar": warnings_ar,
    }
