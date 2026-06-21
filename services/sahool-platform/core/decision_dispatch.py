"""core/decision_dispatch.py — موزِّع القرار المحروس (دماغ الحلقة المغلقة، نقيّ).

الفجوة المعماريّة الوحيدة غير المقصودة (تدقيق docs/ARCHITECTURE_DEPENDENCY_AND_GAPS_2026-06):
محركات القرار (core/engines/*, recommendation_engine) والمُشغِّل (actuator-service)
**منفصلان** — المُشغِّل يُطلق أوامر MQTT من عتبات مستشعر بدائيّة لا يكتبها أيّ محرّك،
ويتجاوز الحواجز (guardrails) كليّاً. هذه الوحدة هي **القرار الموحّد** الذي يربطهما:

    توصية محرّك ──▶ فحص الحواجز ──▶ بوّابة الموافقة ──▶ قرار توزيع (state)

نقيّة وحتميّة (لا I/O): تأخذ توصيةً + نتيجة حواجز (`core.guardrails.GuardrailResult`)
+ عدد الموافقات المُجمَّعة، وتُرجِع `DispatchDecision` بحالة واحدة من ثلاث:
  • BLOCKED — خرق HALT (خط أحمر، PHI/ملوحة/حوكمة): **لا تنفيذ أبداً**.
  • PENDING_APPROVAL — مخلَّص من الحواجز لكن يحتاج موافقات بشريّة (طبقات المخاطر).
  • READY — محروس + موافَق (أو منخفض المخاطر): مُخلَّص للتنفيذ.

تُعيد كذلك **أثر تدقيق موحّداً** يربط recommendation_id ← خروق الحواجز ← حالة
الموافقة ← القرار (الأثر الذي رصد التدقيق غيابه؛ يربط لاحقاً بالأمر والنتيجة المُقاسة).

**أمان بالتصميم (fail-closed):**
  • أيّ HALT ⇒ BLOCKED، أيّاً كانت الموافقات (الخط الأحمر لا يُتجاوَز ببشر).
  • مستوى مخاطر مجهول ⇒ يُعامَل كأعلى تحفّظ (يتطلّب موافقة) لا كمنخفض.
  • هذه الوحدة **لا تُنفّذ شيئاً** — تقرّر فقط. التنفيذ الفعليّ (إنشاء أمر المُشغِّل/
    صفّ automation_rules) شريحة لاحقة خلف علم، تستهلك `state == READY` فقط.

طبقات الموافقة مطابِقة لـguardrails-engine/human_in_loop (`required_count`):
MEDIUM=1, HIGH=2, CRITICAL=3 — ومضافٌ LOW=0 (منخفض المخاطر يُخلَّص بلا بشر).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class DispatchState(str, Enum):
    """حالة قرار التوزيع — مخرَج وحيد للموزِّع المحروس."""

    BLOCKED = "blocked"  # خرق HALT — لا تنفيذ أبداً
    PENDING_APPROVAL = "pending_approval"  # محروس لكن يحتاج موافقة بشريّة
    READY = "ready"  # محروس + موافَق (أو منخفض المخاطر) — مُخلَّص للتنفيذ


# طبقات الموافقة المطلوبة لكلّ مستوى مخاطر — مطابِقة لـhuman_in_loop.required_count.
# مستوى مجهول يُعامَل تحفّظاً كـCRITICAL (fail-closed: لا نُخلّص ما لا نعرف خطره).
_REQUIRED_APPROVALS = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}
_CONSERVATIVE_REQUIRED = 3  # للمستوى المجهول


def required_approvals_for(risk_level: str) -> int:
    """عدد الموافقات البشريّة المطلوبة لمستوى مخاطر — مجهول ⇒ أعلى تحفّظ."""
    return _REQUIRED_APPROVALS.get((risk_level or "").strip().upper(), _CONSERVATIVE_REQUIRED)


@dataclass
class DispatchDecision:
    """قرار التوزيع + أثر التدقيق الموحّد (توصية←حواجز←موافقة←قرار)."""

    state: DispatchState
    recommendation_id: str
    action_type: str
    field_id: str | None
    risk_level: str
    required_approvals: int
    approvals_collected: int
    halt_breaches: list[str] = field(default_factory=list)  # rule_ids من الحواجز
    warn_breaches: list[str] = field(default_factory=list)
    reason_ar: str = ""

    @property
    def executable(self) -> bool:
        """هل القرار مُخلَّص للتنفيذ فعلاً؟ (الشريحة اللاحقة تستهلك هذا فقط)."""
        return self.state == DispatchState.READY

    def to_audit(self) -> dict:
        """أثر تدقيق قابل للتسلسل — يربط القرار بمصدره (للسجلّ/التتبّع)."""
        d = asdict(self)
        d["state"] = self.state.value
        d["executable"] = self.executable
        return d


# حالات الحَوكمة التي تَسمح بالتوزيع (مطابِقة لـcoordinator). أيّ حالة أخرى
# (not_evaluated/error/مجهول) ⇒ القرار لم تُقَرّ حوكمته ⇒ لا يُوزَّع (fail-closed).
_GOVERNANCE_APPROVED_STATES = frozenset({"approved", "passed", "cleared", "ok"})


class GovernanceNotEvaluatedError(RuntimeError):
    """يُرفع عند محاولة توزيع قرار لم تُقَرّ حوكمته (governance.status != approved).

    الخطّ الأحمر للحوكمة: قرار من field_intelligence_coordinator بحالة
    not_evaluated **لا يصل** إلى evaluate_dispatch — لا تُختلق موافقة، لا تنفيذ.
    """


def assert_governance_evaluated(governance: dict | None) -> None:
    """حارس بوّابة التوزيع: يرفض القرار إن لم تُقَرّ حوكمته (fail-closed، نقيّ).

    يُستدعى قبل توزيع أيّ قرار من المسار القانونيّ (field_intelligence). إن كانت
    `governance.status` not_evaluated/error/مجهولة ⇒ يرفع GovernanceNotEvaluatedError
    بسبب صريح (governance_not_evaluated). صدق: لا نُعامل المجهول كموافقة.
    """
    status = str((governance or {}).get("status", "")).strip().lower()
    if status not in _GOVERNANCE_APPROVED_STATES:
        raise GovernanceNotEvaluatedError(
            f"governance_not_evaluated: حالة الحَوكمة {status or 'مجهولة'!r} "
            "لا تسمح بالتوزيع — القرار استشاريّ فقط حتى تمرّ القواعد الحاكمة."
        )


def evaluate_dispatch(
    *,
    recommendation_id: str,
    action_type: str,
    risk_level: str,
    guardrail: Any,
    field_id: str | None = None,
    approvals_collected: int = 0,
) -> DispatchDecision:
    """يقرّر توزيع توصية إلى تنفيذ — محروسٌ ومحكومٌ بالموافقة (نقيّ، لا I/O).

    `guardrail`: كائن بعقد `core.guardrails.GuardrailResult` (له `breaches`
    وخاصّيّة `halted`). أيّ HALT ⇒ BLOCKED قطعاً. وإلّا تُحسب الموافقات المطلوبة
    من مستوى المخاطر؛ READY إن تجمّعت، وإلّا PENDING_APPROVAL.
    """
    from core.guardrails import GuardrailSeverity

    breaches = list(getattr(guardrail, "breaches", []) or [])
    halt = [b for b in breaches if getattr(b, "severity", None) == GuardrailSeverity.HALT]
    warn = [b for b in breaches if getattr(b, "severity", None) == GuardrailSeverity.WARN]
    halt_ids = [getattr(b, "name", None) or getattr(b, "rule_id", str(b)) for b in halt]
    warn_ids = [getattr(b, "name", None) or getattr(b, "rule_id", str(b)) for b in warn]

    required = required_approvals_for(risk_level)
    approvals = max(0, int(approvals_collected))

    if halt:
        state = DispatchState.BLOCKED
        reason = "خرق خطّ أحمر (HALT) — لا تنفيذ: " + "، ".join(halt_ids)
    elif approvals >= required:
        state = DispatchState.READY
        cleared = "بلا موافقة (منخفض المخاطر)" if required == 0 else f"بـ{approvals} موافقة"
        reason = f"محروس ومُخلَّص للتنفيذ {cleared}"
        if warn_ids:
            reason += " — مع تحذيرات: " + "، ".join(warn_ids)
    else:
        state = DispatchState.PENDING_APPROVAL
        reason = (
            f"محروس لكن يحتاج موافقة بشريّة ({approvals}/{required}) "
            f"لمستوى المخاطر {risk_level or 'مجهول'}"
        )

    return DispatchDecision(
        state=state,
        recommendation_id=recommendation_id,
        action_type=action_type,
        field_id=field_id,
        risk_level=risk_level,
        required_approvals=required,
        approvals_collected=approvals,
        halt_breaches=halt_ids,
        warn_breaches=warn_ids,
        reason_ar=reason,
    )
