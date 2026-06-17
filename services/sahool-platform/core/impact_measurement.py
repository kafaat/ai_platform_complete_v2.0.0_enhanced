"""core/impact_measurement.py — قياس الأثر المُحقَّق للقرارات المُنفَّذة (نقيّ، الشريحة 8).

المرحلة C. الحلقة (A) تُنفِّذ وتُسجِّل (execution_ledger)، و(B) تُحوكِم وتُمثِّل، لكن يبقى
السؤال الأهمّ بلا جواب مُجمَّع: **هل نفع؟** كم ماء وُفِّر فعلاً؟ ما نسبة نجاح التنفيذ؟ هذه
الوحدة تقيس الأثر المُحقَّق من سجلّ التنفيذ (لا تقدير، لا تنبّؤ — قياس ما حدث): تُجمِّع
نتائج القرارات (نُفِّذ/فشل) والماء الموفَّر (المطلوب − المُطبَّق) في ملخّص أثر صادق.

نقيّ وحتميّ (لا I/O): يأخذ سجلّات مُطبَّعة (المُنادي يقرؤها من execution_ledger +
dispatch_decisions معزولةً بـRLS)، يُرجِع `ImpactSummary`. صدق: الماء الموفَّر يُحسَب فقط
حين تتوفّر الكمّيّتان (المطلوبة والمُطبَّقة)؛ غيابهما ⇒ يُستثنى من حساب الماء (لا تلفيق).
يُغذّي الذكاء الاقتصاديّ (الشريحة 10) والتعلُّم المستمرّ (الشريحة 9).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

# النتائج النهائيّة المعروفة (تطابق execution_ledger.outcome).
_EXECUTED = "executed"
_FAILED = "failed"


@dataclass
class ImpactRecord:
    """سجلّ أثر واحد مُطبَّع: نتيجة قرار + كمّيّات الماء (إن توفّرت)."""

    action_type: str
    outcome: str  # executed | failed
    water_requested_mm: float | None = None
    water_applied_mm: float | None = None


@dataclass
class ImpactSummary:
    """ملخّص الأثر المُحقَّق — قياس صادق لِما فعلته الحلقة فعلاً."""

    total_decisions: int = 0
    executed: int = 0
    failed: int = 0
    success_rate: float = 0.0  # executed / (executed+failed) — [0,1]
    water_requested_mm: float = 0.0
    water_applied_mm: float = 0.0
    water_saved_mm: float = 0.0
    water_records: int = 0  # عدد السجلّات التي أُحتسب لها الماء (شفافيّة التغطية)
    by_action: dict = field(
        default_factory=dict
    )  # {action_type: {executed, failed, water_saved_mm}}

    def to_dict(self) -> dict:
        return asdict(self)


def _to_float(v: Any) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def measure_impact(records: list[ImpactRecord]) -> ImpactSummary:
    """يُجمِّع سجلّات الأثر في ملخّص مُحقَّق (نقيّ) — انظر docstring الوحدة.

    success_rate = نُفِّذ / (نُفِّذ + فشل) النهائيّة. الماء الموفَّر يُجمَع فقط من السجلّات
    التي توفّرت لها الكمّيّتان (المطلوبة ≥ المُطبَّقة)؛ يُحسَب per-action أيضاً. صدق: لا
    اختلاق أثر لسجلّ ناقص — يُحتسَب في النتائج لا في الماء.
    """
    summary = ImpactSummary(total_decisions=len(records))
    by_action: dict[str, dict] = {}

    for r in records:
        action = r.action_type or "unknown"
        slot = by_action.setdefault(action, {"executed": 0, "failed": 0, "water_saved_mm": 0.0})
        outcome = (r.outcome or "").strip().lower()
        if outcome == _EXECUTED:
            summary.executed += 1
            slot["executed"] += 1
        elif outcome == _FAILED:
            summary.failed += 1
            slot["failed"] += 1

        req = _to_float(r.water_requested_mm)
        app = _to_float(r.water_applied_mm)
        # الماء الموفَّر يُحتسَب فقط للقرارات المُنفَّذة بكمّيّتين صالحتين (req ≥ app ≥ 0).
        if outcome == _EXECUTED and req is not None and app is not None and req >= app >= 0:
            saved = req - app
            summary.water_requested_mm += req
            summary.water_applied_mm += app
            summary.water_saved_mm += saved
            summary.water_records += 1
            slot["water_saved_mm"] += saved

    finalized = summary.executed + summary.failed
    summary.success_rate = round(summary.executed / finalized, 3) if finalized else 0.0
    summary.water_requested_mm = round(summary.water_requested_mm, 2)
    summary.water_applied_mm = round(summary.water_applied_mm, 2)
    summary.water_saved_mm = round(summary.water_saved_mm, 2)
    for slot in by_action.values():
        slot["water_saved_mm"] = round(slot["water_saved_mm"], 2)
    summary.by_action = by_action
    return summary
