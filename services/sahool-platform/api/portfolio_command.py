"""api/portfolio_command.py — مركز قيادة المحفظة: ربح × مخاطر لكلّ سياسة (#8)

يعمّق ``portfolio_allocation`` (توزيع ماء متعدّد المصادر) إلى **مستوى مزرعة/شركة**
يقارن **عدّة سياسات ريّ** على نفس الحقول/المصادر، فيُبرز لكلّ سياسة **الربح والمخاطر
معاً** (لا الربح وحده)، تحت **قيود الإنتاجيّة الواقعيّة**:

  • **بئر** (well): سعة كلّيّة (م³) خلال نافذة التخطيط.
  • **مضخّة** (pump): حدّ تدفّق يوميّ (م³/يوم) — السعة الفعّالة = min(السعة، التدفّق×الأيّام).
  • **محور** (pivot): تغطية فيزيائيّة — يخدم حقولاً بعينها فقط (عبر ``source_ids`` للحقل).

**توصية فقط، لا تنفيذ**: يُرشّح السياسة الأفضل بهدف شفّاف (ربح معدَّل بالنُّفور من
المخاطرة) ويعلنها ``recommended`` صراحةً — لا إجراء، لا حجز ماء، لا كتابة قاعدة.

**الصدق**: هوامش/طلبات كلّ حقل تحت كلّ سياسة **تُمرَّر** (تُحسب من profit-aware لكلّ
سياسة، كنمط ScenarioCompare) — لا تُلفَّق. درجة المخاطرة معادلة شفّافة مُوثَّقة، لا
نموذج معايَر. ``calibrated=False`` دائماً.

نقيّ حتميّ (لا قاعدة، لا I/O) — قابل للاختبار offline؛ يستهلكه ``routers/portfolio_command``.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from api.portfolio_allocation import PortfolioField, WaterSource, allocate_portfolio

_KINDS = ("well", "pump", "pivot", "network")


@dataclass
class ConstraintSource:
    """مصدر ماء بقيد إنتاجيّته: بئر/شبكة (سعة)، مضخّة (تدفّق يوميّ)، محور (تغطية)."""

    source_id: str
    capacity_m3: float
    kind: str = "well"  # well | pump | pivot | network
    max_rate_m3_per_day: float | None = None  # حدّ تدفّق المضخّة (م³/يوم)
    window_days: float | None = None  # نافذة التخطيط لتحويل التدفّق إلى سعة فعّالة


def _effective_capacity(s: ConstraintSource) -> tuple[float, bool]:
    """السعة الفعّالة (م³) لمصدر تحت قيده + هل القيد مُلزِم (throughput-bound)؟

    مضخّة بحدّ تدفّق يوميّ ونافذة ⇒ السعة الفعّالة = min(السعة، التدفّق×الأيّام). إن
    قيَّد التدفّقُ السعةَ، يُعلَن ``bound=True`` (صدق: القيد ظاهر لا مخفيّ). غير ذلك
    السعة الكلّيّة كما هي.
    """
    cap = max(0.0, s.capacity_m3)
    if s.max_rate_m3_per_day is not None and s.window_days is not None:
        throughput = max(0.0, s.max_rate_m3_per_day) * max(0.0, s.window_days)
        if throughput < cap:
            return throughput, True
    return cap, False


def _risk_score(n_fields: int, unmet: int, stressed: int, unmet_water_frac: float) -> float:
    """درجة مخاطرة شفّافة في [0,1] — أعلى = أخطر (فقد محصول/إجهاد أوسع).

    تركيبة موزونة مُوثَّقة (ليست نموذجاً معايَراً): 0.5 لنسبة الحقول بلا ريّ (الأخطر:
    فقد محصول)، 0.3 لنسبة الحقول المُجهَدة، 0.2 لنسبة الماء غير المموَّل من الطلب.
    """
    if n_fields <= 0:
        return 0.0
    score = (
        0.5 * (unmet / n_fields)
        + 0.3 * (stressed / n_fields)
        + 0.2 * max(0.0, min(1.0, unmet_water_frac))
    )
    return round(max(0.0, min(1.0, score)), 3)


def evaluate_policy_scenario(
    fields: list[PortfolioField],
    sources: list[ConstraintSource],
    *,
    policy_label: str,
) -> dict:
    """يقيّم سياسة واحدة: يوزّع الماء تحت القيود ثمّ يركّب الربح والمخاطر — نقيّ حتميّ.

    يحوّل القيود إلى سعات فعّالة (المضخّة محدودة بتدفّقها)، يستدعي ``allocate_portfolio``
    (إعادة استخدام بلا تكرار)، ثمّ يلخّص الربح المحقَّق ومقاييس المخاطرة ودرجتها.
    """
    eff_sources: list[WaterSource] = []
    constraints: list[dict] = []
    for s in sources:
        cap, bound = _effective_capacity(s)
        eff_sources.append(WaterSource(source_id=s.source_id, capacity_m3=cap))
        constraints.append(
            {
                "source_id": s.source_id,
                "kind": s.kind if s.kind in _KINDS else "well",
                "capacity_m3": round(max(0.0, s.capacity_m3), 2),
                "effective_capacity_m3": round(cap, 2),
                "throughput_bound": bound,
            }
        )

    alloc = allocate_portfolio(fields, eff_sources)

    n = len(fields)
    demand_total = sum(max(0.0, f.water_demand_m3) for f in fields)
    served = alloc["total_allocated_m3"]
    unmet_water_frac = (1.0 - served / demand_total) if demand_total > 0 else 0.0
    unmet_n = len(alloc["unmet_fields"])
    stressed_n = len(alloc["stressed_fields"])
    risk = _risk_score(n, unmet_n, stressed_n, unmet_water_frac)

    return {
        "policy": policy_label,
        "total_expected_margin": alloc["total_expected_margin"],
        "total_allocated_m3": alloc["total_allocated_m3"],
        "total_demand_m3": round(demand_total, 2),
        "served_fraction": round(served / demand_total, 3) if demand_total > 0 else 1.0,
        "risk_score": risk,
        "fields_count": n,
        "protected_count": len(alloc["protected_fields"]),
        "stressed_count": stressed_n,
        "unmet_count": unmet_n,
        "constraints": constraints,
        "constraints_bound": [c["source_id"] for c in constraints if c["throughput_bound"]],
        "allocation": alloc,  # التفصيل الكامل لكلّ حقل/مصدر (إعادة استخدام)
    }


@dataclass
class PolicyScenario:
    """سيناريو سياسة: تسمية + حقولها (بهوامش/طلبات تلك السياسة) + مصادرها المقيَّدة."""

    policy_label: str
    fields: list[PortfolioField] = field(default_factory=list)
    sources: list[ConstraintSource] = field(default_factory=list)


def compare_portfolio_policies(
    scenarios: list[PolicyScenario], *, risk_aversion: float = 1.0
) -> dict:
    """يقارن سياسات المحفظة على الربح×المخاطر ويُرشّح الأفضل — **توصية فقط لا تنفيذ**.

    لكلّ سياسة: يقيّمها (توزيع تحت القيود + ربح + مخاطر). الهدف الشفّاف للترشيح:
    ``score = total_margin × (1 − risk_aversion × risk_score)`` — يعاقب السياسات
    الخطرة بحسب ``risk_aversion`` (0 = ربح صرف؛ أعلى = أكثر نُفوراً). يُعلَن
    ``recommended_policy`` كاقتراح فقط؛ لا حجز ماء ولا كتابة. صدق: المدخلات مُمرَّرة،
    ``calibrated=False``، تحذيرات صريحة.
    """
    ra = max(0.0, risk_aversion)
    evaluated: list[dict] = []
    for sc in scenarios:
        ev = evaluate_policy_scenario(sc.fields, sc.sources, policy_label=sc.policy_label)
        ev["objective_score"] = round(
            ev["total_expected_margin"] * max(0.0, 1.0 - ra * ev["risk_score"]), 2
        )
        evaluated.append(ev)

    recommended_policy = None
    if evaluated:
        best = max(
            evaluated,
            key=lambda e: (e["objective_score"], -e["risk_score"], e["total_expected_margin"]),
        )
        recommended_policy = best["policy"]

    warnings_ar = [
        "مقارنة سياسات على مستوى المحفظة — **توصية فقط، لا تنفيذ ولا حجز ماء**.",
        "درجة المخاطرة معادلة موزونة شفّافة لا نموذج معايَر — calibrated=False.",
    ]
    bound = sorted({sid for e in evaluated for sid in e["constraints_bound"]})
    if bound:
        warnings_ar.append("مصادر قيَّدها تدفّق المضخّة دون السعة الكلّيّة: " + "، ".join(bound))

    return {
        "policies": evaluated,
        "recommended_policy": recommended_policy,
        "risk_aversion": round(ra, 3),
        "calibrated": False,
        "warnings_ar": warnings_ar,
    }
