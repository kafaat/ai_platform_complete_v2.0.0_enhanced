"""core/policy_registry.py — سجلّ سياسات القرار: حوكمة معلنة للحلقة (نقيّ، الشريحة 5).

المرحلة B. حتى الآن قواعد الحوكمة مبعثرة في الكود: طبقات الموافقة في decision_dispatch،
الحواجز في guardrails، عتبات الماء في المحركات. هذا يجعل «سياسة التشغيل» ضمنيّة وغير
قابلة للتهيئة لكلّ مستأجِر/محصول/موسم. سجلّ السياسات يجعلها **معلنة وقابلة للاستعلام
والتهيئة** دون نشر كود: لكلّ مستأجِر سياساتٌ ذات نطاق (action_type/risk_level/crop)
وأثر (auto_block / require_approvals / water_cap_pct)، تُستشار في مسار القرار الموحّد
والموزِّع المحروس فتُصقَل القرارات بشفافيّة.

نقيّة وحتميّة (لا I/O): تأخذ قائمة سياسات + سياق، تُرجِع `ResolvedPolicy` (الأثر المُجمَّع
+ أيّ سياسة طبّقته — للتدقيق). fail-safe: سياسة بأثر مجهول تُتجاهَل (لا تكسر القرار)؛
auto_block غالبٌ دائماً (تحفّظ). الترتيب بالأولويّة (priority desc) ثمّ آخر تطابق يفوز
في الحقول غير المتعارضة. لا تستبدل الحواجز (guardrails) — تكمّلها كطبقة حوكمة مُهيّأة.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Policy:
    """سياسة قرار واحدة: نطاق (متى تنطبق) + أثر (ماذا تفرض) + أولويّة."""

    policy_id: str
    name: str
    # النطاق: حقوله None ⇒ بدل (wildcard). تنطبق إن طابق كلّ حقل مُحدَّد السياقَ.
    scope: dict = field(default_factory=dict)  # {action_type?, risk_level?, crop?}
    # الأثر: auto_block (يحجب)، require_approvals (يرفع حدّ الموافقات)، water_cap_pct (سقف ماء).
    effect: dict = field(default_factory=dict)
    priority: int = 0  # الأعلى يُطبَّق أوّلاً
    enabled: bool = True


_SCOPE_KEYS = ("action_type", "risk_level", "crop")


def _norm(v: Any) -> str:
    return (str(v) if v is not None else "").strip().lower()


def policy_matches(policy: Policy, context: dict) -> bool:
    """هل تنطبق السياسة على السياق؟ (كلّ حقل نطاق مُحدَّد يطابق، None = بدل)، نقيّ."""
    if not policy.enabled:
        return False
    for key in _SCOPE_KEYS:
        want = policy.scope.get(key)
        if want is None or want == "":
            continue  # بدل — لا يقيّد
        if _norm(want) != _norm(context.get(key)):
            return False
    return True


@dataclass
class ResolvedPolicy:
    """نتيجة استشارة السجلّ: الأثر المُجمَّع + أثر التدقيق (أيّ سياسات طبّقت)."""

    auto_block: bool = False
    require_approvals: int | None = None  # حدّ أدنى للموافقات تفرضه السياسة (إن وُجد)
    water_cap_pct: float | None = None  # سقف نسبة ماء [0,100] (الأدنى يفوز — تحفّظ)
    applied_policy_ids: list[str] = field(default_factory=list)
    reasons_ar: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "auto_block": self.auto_block,
            "require_approvals": self.require_approvals,
            "water_cap_pct": self.water_cap_pct,
            "applied_policy_ids": self.applied_policy_ids,
            "reasons_ar": self.reasons_ar,
        }


def resolve_policies(policies: list[Policy], context: dict) -> ResolvedPolicy:
    """يُجمِّع أثر السياسات المنطبقة على السياق في قرار حوكمة واحد (نقيّ).

    الترتيب بالأولويّة (desc). الدمج التحفّظيّ: auto_block غالبٌ (أيّ سياسة تحجب ⇒ حجب)؛
    require_approvals = الأقصى (أكثر تحفّظاً)؛ water_cap_pct = الأدنى (أقسى سقف). كلّ
    سياسة مُطبَّقة تُسجَّل في applied_policy_ids + reasons_ar (صدق، لا حوكمة خفيّة).
    """
    matched = sorted(
        (p for p in policies if policy_matches(p, context)),
        key=lambda p: p.priority,
        reverse=True,
    )
    out = ResolvedPolicy()
    for p in matched:
        eff = p.effect or {}
        touched = False
        if eff.get("auto_block"):
            out.auto_block = True
            touched = True
        if "require_approvals" in eff and eff["require_approvals"] is not None:
            req = int(eff["require_approvals"])
            out.require_approvals = (
                req if out.require_approvals is None else max(out.require_approvals, req)
            )
            touched = True
        if "water_cap_pct" in eff and eff["water_cap_pct"] is not None:
            cap = float(eff["water_cap_pct"])
            out.water_cap_pct = cap if out.water_cap_pct is None else min(out.water_cap_pct, cap)
            touched = True
        if touched:
            out.applied_policy_ids.append(p.policy_id)
            out.reasons_ar.append(f"سياسة «{p.name}» طُبِّقت")
    return out
