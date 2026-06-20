"""api/portfolio_allocation.py — توزيع ماء المزرعة متعدّد المصادر (#386)

يعمّق field_portfolio (الجشِع أحاديّ المورد) إلى مستوى المزرعة الحقيقيّ:
  • **آبار/مصادر متعدّدة**، لكلّ مصدر سعته، وكلّ حقل يُسحَب من مصادره المسموحة.
  • **أولويّة لكلّ حقل**: قد يكون أفضل قرار للمزرعة «إجهاد مقبول في الحقل 3 لحماية
    الحقل 1» — لا تحسين كلّ حقل منفرداً.
  • **أرضيّة دنيا** لكلّ حقل (min_water_fraction) لتجنّب فقد المحصول.

الخوارزميّة (مرحلتان، حتميّة شفّافة):
  ١) حماية: امنح كلّ حقل أرضيّته الدنيا بترتيب الأولويّة (يحمي الحرِجة أوّلاً).
  ٢) تعظيم: وزّع المتبقّي بالأولويّة ثمّ إنتاجيّة الماء (هامش/م³) حتى ملء الطلب.

ليست LP عامّة؛ التوزيع الجزئيّ خطّيّ تقريبيّ (موسوم). نقيّ حتميّ: الهوامش/الطلبات/
الأولويّات/السعات **تُمرَّر** (تُحسب من profit-aware لكلّ حقل) — لا تُلفَّق.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class WaterSource:
    """مصدر ماء (بئر/شبكة) بسعته الكلّيّة (م³)."""

    source_id: str
    capacity_m3: float


@dataclass
class PortfolioField:
    """حقل في المحفظة مع أولويّته وأرضيّته ومصادره المسموحة."""

    field_id: str
    expected_margin: float  # الهامش عند الريّ الكامل
    water_demand_m3: float  # الطلب الكلّيّ (م³)
    priority: int = 1  # أعلى = احمِ أكثر
    min_water_fraction: float = 0.0  # أرضيّة دنيا لتجنّب فقد المحصول
    source_ids: list[str] = field(default_factory=list)  # المصادر التي تخدمه (فارغ = الكلّ)


def _productivity(margin: float, demand: float) -> float:
    return margin / demand if demand > 0 else float("inf")


def allocate_portfolio(fields: list[PortfolioField], sources: list[WaterSource]) -> dict:
    """يوزّع ماء آبار متعدّدة عبر حقول ذات أولويّات لتعظيم القيمة المحميّة — نقيّ حتميّ.

    مرحلتان: حماية الأرضيّات بالأولويّة، ثمّ تعظيم بالأولويّة/الإنتاجيّة. يظهر صراحةً
    أيّ حقل أُجهِد (deficit) لحماية أعلى أولويّةً. صدق: التوزيع الجزئيّ خطّيّ تقريبيّ.
    """
    remaining: dict[str, float] = {s.source_id: max(0.0, s.capacity_m3) for s in sources}
    all_source_ids = list(remaining.keys())
    allocated: dict[str, float] = {f.field_id: 0.0 for f in fields}
    sources_used: dict[str, dict[str, float]] = {f.field_id: {} for f in fields}

    def _eligible(f: PortfolioField) -> list[str]:
        ids = f.source_ids or all_source_ids
        return [s for s in ids if s in remaining]

    def _draw(f: PortfolioField, amount: float) -> None:
        """يسحب حتى amount م³ لحقل من مصادره المؤهَّلة (بترتيبها)."""
        need = amount
        for sid in _eligible(f):
            if need <= 1e-9:
                break
            take = min(remaining[sid], need)
            if take <= 0:
                continue
            remaining[sid] -= take
            need -= take
            allocated[f.field_id] += take
            sources_used[f.field_id][sid] = sources_used[f.field_id].get(sid, 0.0) + take

    # ترتيب القرار: الأولويّة الأعلى أوّلاً، ثمّ إنتاجيّة الماء.
    order = sorted(
        fields,
        key=lambda f: (f.priority, _productivity(f.expected_margin, f.water_demand_m3), f.field_id),
        reverse=True,
    )

    # ١) حماية الأرضيّات الدنيا بالأولويّة.
    for f in order:
        floor = max(0.0, min(1.0, f.min_water_fraction)) * max(0.0, f.water_demand_m3)
        gap = floor - allocated[f.field_id]
        if gap > 0:
            _draw(f, gap)

    # ٢) تعظيم: ملء بقيّة الطلب بالأولويّة/الإنتاجيّة.
    for f in order:
        gap = max(0.0, f.water_demand_m3) - allocated[f.field_id]
        if gap > 0:
            _draw(f, gap)

    out_fields: list[dict] = []
    total_margin = 0.0
    total_alloc = 0.0
    protected, stressed, unmet = [], [], []
    for f in fields:
        demand = max(0.0, f.water_demand_m3)
        alloc = allocated[f.field_id]
        frac = alloc / demand if demand > 0 else 1.0
        captured = f.expected_margin * frac
        total_margin += captured
        total_alloc += alloc
        floor = max(0.0, min(1.0, f.min_water_fraction))
        if frac >= 0.999:
            status = "full"
        elif frac <= 0.0:
            status = "unmet"
            unmet.append(f.field_id)
        elif frac + 1e-9 >= floor and floor > 0:
            status = "protected_min" if frac < 0.999 else "full"
            protected.append(f.field_id)
            stressed.append(f.field_id)
        else:
            status = "partial"
            stressed.append(f.field_id)
        out_fields.append(
            {
                "field_id": f.field_id,
                "priority": f.priority,
                "water_demand_m3": round(demand, 2),
                "allocated_m3": round(alloc, 2),
                "fraction": round(frac, 3),
                "water_productivity": (
                    round(_productivity(f.expected_margin, demand), 4) if demand > 0 else None
                ),
                "expected_margin_captured": round(captured, 2),
                "stressed": frac < 0.999,
                "status": status,
                "sources_used": {k: round(v, 2) for k, v in sources_used[f.field_id].items()},
            }
        )

    out_sources = [
        {
            "source_id": s.source_id,
            "capacity_m3": round(s.capacity_m3, 2),
            "used_m3": round(s.capacity_m3 - remaining[s.source_id], 2),
            "remaining_m3": round(remaining[s.source_id], 2),
        }
        for s in sources
    ]

    warnings_ar = ["توزيع جشِع بالأولويّة/الإنتاجيّة؛ الجزئيّ خطّيّ تقريبيّ — غير معايَر"]
    if unmet:
        warnings_ar.append(f"حقول بلا ريّ لنقص المورد: {', '.join(unmet)}")
    if stressed:
        warnings_ar.append(f"حقول مُجهَدة لحماية الأعلى أولويّة: {', '.join(dict.fromkeys(stressed))}")

    return {
        "fields": out_fields,
        "sources": out_sources,
        "total_expected_margin": round(total_margin, 2),
        "total_allocated_m3": round(total_alloc, 2),
        "protected_fields": list(dict.fromkeys(protected)),
        "stressed_fields": list(dict.fromkeys(stressed)),
        "unmet_fields": unmet,
        "calibrated": False,
        "warnings_ar": warnings_ar,
    }
