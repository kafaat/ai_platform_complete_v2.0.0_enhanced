"""core/agronomic_decision.py — محرّك القرار الزراعيّ الموحّد (نقيّ، الأولويّة 1).

الفجوة التي أكّدها القياس (Unified Decision Engine): المحركات (طقس/تربة/ريّ/آفات/
اقتصاد/غلّة) تُنتج توصيات **متوازية ومنفصلة**؛ القرار النهائيّ موزَّع بينها. هذا المحرّك
يجمعها في **قرار واحد مُصالَح**:

    إشارات المجالات ──▶ بوّابة الحواجز ──▶ مصالحة التعارضات ──▶ خطّة عمل موحّدة

مثال: «الطقس: قلّل الريّ» + «الآفات: رشّ خلال ٣ أيّام (يحتاج جفافاً)» + «الاقتصاد:
خفّض الماء ١٢٪» ⇒ قرار موحّد: «أجّل الريّ ٤٨س (ليجفّ قبل الرشّ)، قدّم الرشّ، اخفض
الماء وفق الميزانيّة» — بمصالحة صريحة شفّافة لا تلفيق.

**نقيّ وحتميّ (لا I/O):** يأخذ لقطة حالة + إشارات، يُرجِع `UnifiedDecision`. لا يُنفّذ
شيئاً — يُنتج خطّة تُغذّي الموزِّع المحروس (`core.decision_dispatch`) ثمّ التنفيذ.

**مصالحة مبدئيّة صريحة (لا صندوق أسود):**
  1. بوّابة صلبة: أيّ إشارة `halt` (خطّ أحمر: PHI/ملوحة/حوكمة) ⇒ القرار BLOCKED، لا خطّة.
  2. تعارض الريّ↔الرشّ: رشّ يحتاج جفافاً + ريّ ⇒ يُؤجَّل الريّ بنافذة الرشّ (مصالحة توقيت).
  3. قيد الماء (اقتصاد): ميزانيّة ماء <100٪ ⇒ تُقلَّص كمّيّة الريّ نسبيّاً (مصالحة مورد).
  4. الترتيب بالإلحاح (CRITICAL أوّلاً)؛ الثقة = أدنى ثقات الإشارات (تحفّظ).
الأمثَلة متعدّدة الأهداف الكاملة (مفاضلة ماء/غلّة/تكلفة) طبقة لاحقة (الأولويّة 8).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class Urgency(str, Enum):
    """إلحاح موحّد عبر المجالات (يُطبّع المفردات المتفرّقة none/low/moderate/high)."""

    NONE = "none"
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    CRITICAL = "critical"

    @property
    def rank(self) -> int:
        return {"none": 0, "low": 1, "moderate": 2, "high": 3, "critical": 4}[self.value]


def to_urgency(v: Any) -> Urgency:
    """يُطبّع قيمة إلحاح (نصّ/Urgency) إلى Urgency — مجهول ⇒ MODERATE (تحفّظ معتدل)."""
    if isinstance(v, Urgency):
        return v
    s = (str(v) if v is not None else "").strip().lower()
    _alias = {"medium": "moderate", "urgent": "high", "": "none"}
    s = _alias.get(s, s)
    try:
        return Urgency(s)
    except ValueError:
        return Urgency.MODERATE


@dataclass
class DomainSignal:
    """إشارة مجال واحد: ماذا يقترح، بأيّ إلحاح، بأيّ معاملات/قيود."""

    domain: str  # weather | soil | irrigation | pest | economics | yield
    action: str  # irrigate | spray | reduce_water | defer | none | …
    urgency: Urgency = Urgency.NONE
    params: dict = field(default_factory=dict)
    halt: bool = False  # خطّ أحمر من هذا المجال (يحجب القرار كلّه)
    reason_ar: str = ""
    confidence: float = 1.0  # [0,1]


@dataclass
class PlannedAction:
    """إجراء واحد في الخطّة الموحّدة — مع أصله وسبب إدراجه."""

    action: str
    domains: list[str]
    urgency: Urgency
    params: dict = field(default_factory=dict)
    rationale_ar: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        d["urgency"] = self.urgency.value
        return d


@dataclass
class UnifiedDecision:
    """القرار الزراعيّ الموحّد: خطّة عمل مُصالَحة + أثر شفّاف لما حُجِب/صُولِح."""

    field_id: str
    state: str  # ready | blocked
    action_plan: list[PlannedAction] = field(default_factory=list)
    halt_reasons: list[str] = field(default_factory=list)
    reconciliations_ar: list[str] = field(default_factory=list)
    confidence: float = 1.0
    rationale_ar: str = ""

    @property
    def is_ready(self) -> bool:
        return self.state == "ready"

    def to_dict(self) -> dict:
        return {
            "field_id": self.field_id,
            "state": self.state,
            "action_plan": [a.to_dict() for a in self.action_plan],
            "halt_reasons": self.halt_reasons,
            "reconciliations_ar": self.reconciliations_ar,
            "confidence": round(self.confidence, 3),
            "rationale_ar": self.rationale_ar,
        }


_DEFER_HOURS_DEFAULT = 48  # تأجيل الريّ الافتراضيّ ليجفّ الغطاء قبل الرشّ


def reconcile_decision(field_id: str, signals: list[DomainSignal]) -> UnifiedDecision:
    """يجمع إشارات المجالات في قرار موحّد مُصالَح (نقيّ) — انظر docstring الوحدة.

    صدق: لا تلفيق — كلّ مصالحة مُعلَنة في reconciliations_ar، وأيّ halt يحجب بشفافيّة.
    """
    halts = [s for s in signals if s.halt]
    if halts:
        return UnifiedDecision(
            field_id=field_id,
            state="blocked",
            halt_reasons=[s.reason_ar or f"{s.domain}:halt" for s in halts],
            confidence=1.0,
            rationale_ar="قرار محجوب — خطّ أحمر من: " + "، ".join(s.domain for s in halts),
        )

    actionable = [s for s in signals if (s.action or "none") != "none"]
    reconciliations: list[str] = []

    # تجميع الإجراءات حسب نوعها (دمج إشارات المجالات على نفس الإجراء).
    by_action: dict[str, list[DomainSignal]] = {}
    for s in actionable:
        by_action.setdefault(s.action, []).append(s)

    # ── مصالحة ١: تعارض الريّ ↔ الرشّ (الرشّ يحتاج جفافاً) ──
    spray = [s for s in actionable if s.action == "spray"]
    irrigate = [s for s in actionable if s.action == "irrigate"]
    spray_needs_dry = any(
        s.params.get("needs_dry", True) for s in spray
    )  # الرشّ افتراضاً يحتاج جفافاً
    defer_hours = 0
    if spray and irrigate and spray_needs_dry:
        window_days = max((int(s.params.get("window_days", 3)) for s in spray), default=3)
        defer_hours = min(_DEFER_HOURS_DEFAULT, max(24, window_days * 8))
        reconciliations.append(
            f"تعارض الريّ↔الرشّ: الرشّ يحتاج غطاءً جافّاً ⇒ أُجّل الريّ {defer_hours} ساعة قبله."
        )

    # ── مصالحة ٢: قيد ميزانيّة الماء (اقتصاد) ──
    water_budget = None
    for s in actionable:
        if s.domain == "economics" and "water_budget_pct" in s.params:
            water_budget = float(s.params["water_budget_pct"])
    water_scale = None
    if water_budget is not None and 0 <= water_budget < 100 and irrigate:
        water_scale = water_budget / 100.0
        reconciliations.append(
            f"قيد اقتصاديّ: ميزانيّة الماء {water_budget:.0f}٪ ⇒ خُفِّضت كمّيّة الريّ بهذه النسبة."
        )

    # ── بناء الخطّة المُصالَحة ──
    plan: list[PlannedAction] = []
    for action, sigs in by_action.items():
        urg = max((s.urgency for s in sigs), key=lambda u: u.rank)
        params: dict = {}
        for s in sigs:
            params.update(s.params)
        rationale = "؛ ".join(s.reason_ar for s in sigs if s.reason_ar) or action
        if action == "irrigate":
            if defer_hours:
                params["defer_hours"] = defer_hours
                action_name = "defer_irrigation"
            else:
                action_name = "irrigate"
            if water_scale is not None and "water_mm" in params:
                params["water_mm"] = round(float(params["water_mm"]) * water_scale, 1)
        else:
            action_name = action
        plan.append(
            PlannedAction(
                action=action_name,
                domains=sorted({s.domain for s in sigs}),
                urgency=urg,
                params=params,
                rationale_ar=rationale,
            )
        )

    plan.sort(key=lambda a: a.urgency.rank, reverse=True)
    confidence = min((s.confidence for s in actionable), default=1.0)
    rationale = (
        "لا إجراء مطلوب — كلّ المجالات هادئة." if not plan else "قرار موحّد مُصالَح: "
    ) + "، ".join(a.action for a in plan)
    return UnifiedDecision(
        field_id=field_id,
        state="ready",
        action_plan=plan,
        reconciliations_ar=reconciliations,
        confidence=confidence,
        rationale_ar=rationale,
    )
