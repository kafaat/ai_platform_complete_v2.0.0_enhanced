"""core/cross_domain_optimization.py — أمثَلة متعدّدة الأهداف للريّ (نقيّ، الشريحة 7).

المرحلة B. المصالحة في المرحلة A (agronomic_decision) تحلّ التعارضات **ثنائيّاً** (ريّ↔رشّ،
قيد ميزانيّة). لكن يبقى توتّر متعدّد الأهداف حقيقيّ غير محلول: «وفّر الماء» (اقتصاد) مقابل
«احمِ الغلّة» (زراعة). هذه الوحدة تحلّه صراحةً: تبحث عن **كمّيّة الريّ المثلى** التي توازن
كفاءة الماء وأمان الغلّة ضمن الميزانيّة، بأوزان شفّافة وقابلة للمراجعة.

نقيّ وحتميّ (لا I/O، لا نموذج تعلُّم): بحث شبكيّ بسيط على كمّيّات مرشّحة + دوالّ هدف
حسابيّة صريحة في [0,1] (لا تلفيق، لا صندوق أسود). الناتج يشرح المفاضلة (tradeoffs_ar)
ويُسمّي الكمّيّة المختارة وسببها — يُغذّي خطّة الريّ في القرار الموحّد بقرار قابل للتبرير.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

# الأوزان الافتراضيّة — توازن متساوٍ بين كفاءة الماء وأمان الغلّة (قابل للتجاوز/سياسة).
_DEFAULT_WEIGHTS = {"water_efficiency": 0.5, "yield_security": 0.5}
_DEFAULT_STEPS = 10  # دقّة شبكة البحث (كلّما زادت دقّت الكمّيّة المختارة)


@dataclass
class OptimizationResult:
    """نتيجة الأمثَلة: الكمّيّة المختارة + درجاتها + شرح المفاضلة (شفّاف)."""

    applied_water_mm: float
    requested_water_mm: float
    score: float  # الدرجة الموزونة [0,1] للكمّيّة المختارة
    objective_scores: dict = field(default_factory=dict)  # {water_efficiency, yield_security}
    candidates_evaluated: int = 0
    tradeoffs_ar: list[str] = field(default_factory=list)

    @property
    def water_saved_mm(self) -> float:
        return round(self.requested_water_mm - self.applied_water_mm, 2)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["water_saved_mm"] = self.water_saved_mm
        return d


def _clamp01(x: float) -> float:
    return 0.0 if x < 0 else (1.0 if x > 1 else x)


def optimize_irrigation(
    requested_mm: float,
    *,
    min_mm_for_yield: float,
    budget_mm: float | None = None,
    weights: dict | None = None,
    steps: int = _DEFAULT_STEPS,
) -> OptimizationResult:
    """يختار كمّيّة ريّ مثلى توازن كفاءة الماء وأمان الغلّة ضمن الميزانيّة (نقيّ).

    `requested_mm`: الكمّيّة التي طلبها محرّك الريّ. `min_mm_for_yield`: أدنى ماء لا تتضرّر
    الغلّة دونه (من نموذج الغلّة/الإرشاد). `budget_mm`: سقف ميزانيّة الماء (اختياريّ).

    دوالّ الهدف (صريحة، [0,1]): كفاءة الماء = نسبة الموفَّر من المطلوب (أقلّ ماء ⇒ أعلى)؛
    أمان الغلّة = نسبة تغطية الحدّ الأدنى (≥ الحدّ ⇒ 1). يُمسح شبكة كمّيّات [0..الأعلى]
    وتُختار صاحبة أعلى درجة موزونة. fail-safe: مطلوب ≤ 0 ⇒ لا ريّ (درجة محايدة).
    """
    w = {**_DEFAULT_WEIGHTS, **(weights or {})}
    req = max(0.0, float(requested_mm))
    if req == 0.0:
        return OptimizationResult(
            applied_water_mm=0.0,
            requested_water_mm=0.0,
            score=1.0,
            objective_scores={"water_efficiency": 1.0, "yield_security": 1.0},
            candidates_evaluated=0,
            tradeoffs_ar=["لا ريّ مطلوب — لا مفاضلة."],
        )

    upper = req if budget_mm is None else min(req, max(0.0, float(budget_mm)))
    min_needed = max(0.0, float(min_mm_for_yield))
    steps = max(1, int(steps))

    best_mm = 0.0
    best_score = -1.0
    best_obj: dict = {}
    for i in range(steps + 1):
        mm = upper * i / steps
        water_eff = _clamp01(1.0 - mm / req)  # أقلّ ماء ⇒ كفاءة أعلى
        yield_sec = 1.0 if min_needed == 0.0 else _clamp01(mm / min_needed)  # تغطية الحدّ
        score = w["water_efficiency"] * water_eff + w["yield_security"] * yield_sec
        if score > best_score:
            best_score = score
            best_mm = mm
            best_obj = {
                "water_efficiency": round(water_eff, 3),
                "yield_security": round(yield_sec, 3),
            }

    tradeoffs = []
    if budget_mm is not None and upper < req:
        tradeoffs.append(f"الميزانيّة تحدّ الريّ بـ{upper:.1f}مم (المطلوب {req:.1f}مم).")
    if min_needed > upper:
        tradeoffs.append(f"تعذّر تأمين حدّ الغلّة ({min_needed:.1f}مم) ضمن المتاح — خطر على الغلّة.")
    elif best_mm < req:
        tradeoffs.append(
            f"أُمثِلت الكمّيّة إلى {best_mm:.1f}مم (وُفِّر {req - best_mm:.1f}مم) مع تأمين حدّ الغلّة."
        )
    else:
        tradeoffs.append(f"الكمّيّة المطلوبة {req:.1f}مم مُثلى ضمن القيود.")

    return OptimizationResult(
        applied_water_mm=round(best_mm, 2),
        requested_water_mm=round(req, 2),
        score=round(best_score, 3),
        objective_scores=best_obj,
        candidates_evaluated=steps + 1,
        tradeoffs_ar=tradeoffs,
    )
