"""core/decision_learning.py — التعلُّم المستمرّ من أثر القرارات (نقيّ، الشريحة 9).

المرحلة C. قياس الأثر (الشريحة 8) يخبرنا «هل نفع؟»؛ هذه الوحدة تُغلِق حلقة التعلُّم:
تحوّل الأثر المُحقَّق إلى **اقتراحات معايرة** للقرارات المستقبليّة (رفع موافقات لإجراء
يفشل كثيراً، أو ترجيح كفاءة الماء لإجراء يوفّر باستمرار). صريحة ومُسنَدة بالأدلّة.

⚠ human-in-the-loop (مطابق لـcore.policy_learning): تُرجِع **اقتراحات لا تُطبَّق آليّاً**
أبداً — مدخلٌ لقرار بشريّ. لا تكتب سياسة ولا تغيّر وزناً؛ تقترح بشفافيّة مع الدليل.

نقيّ وحتميّ (لا I/O): يأخذ ملخّص أثر (ImpactSummary.by_action) + عتبات، يُرجِع قائمة
اقتراحات. عتبة عيّنة دنيا (min_sample) تمنع الضجيج من قِلّة البيانات (لا اقتراح على لا شيء).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

# عتبات المعايرة (صريحة، قابلة للمراجعة).
_MIN_SAMPLE_DEFAULT = 5  # أدنى عدد قرارات نهائيّة قبل أيّ اقتراح (يمنع الضجيج)
_LOW_SUCCESS = 0.6  # نسبة نجاح أدنى منها ⇒ اقتراح حذر (رفع موافقات/مراجعة)
_HIGH_SUCCESS = 0.9  # نسبة نجاح أعلى منها ⇒ ثقة (يمكن تخفيف الاحتكاك)


@dataclass
class LearningSuggestion:
    """اقتراح معايرة واحد — مُسنَد بالدليل، استشاريّ لا تنفيذيّ."""

    kind: str  # raise_approvals | relax_friction | favor_water_efficiency | review_failures
    action_type: str
    message_ar: str
    evidence: dict  # الأرقام التي بُني عليها الاقتراح (شفافيّة)
    confidence: float  # [0,1] — يزيد مع حجم العيّنة

    def to_dict(self) -> dict:
        return asdict(self)


def _confidence(sample: int) -> float:
    """ثقة بسيطة تتزايد مع العيّنة (تشبع عند 30) — لا ادّعاء يقين."""
    return round(min(1.0, sample / 30.0), 3)


def derive_learning_suggestions(
    by_action: dict[str, Any],
    *,
    min_sample: int = _MIN_SAMPLE_DEFAULT,
) -> list[LearningSuggestion]:
    """يشتقّ اقتراحات معايرة من أثر كلّ إجراء (نقيّ) — استشاريّة، لا تُطبَّق آليّاً.

    `by_action`: {action_type: {executed, failed, water_saved_mm}} من ImpactSummary.
    لكلّ إجراء بعيّنة كافية: نجاح منخفض ⇒ raise_approvals/review_failures؛ نجاح عالٍ ⇒
    relax_friction؛ توفير ماء مُتّسق ⇒ favor_water_efficiency. كلّ اقتراح يحمل دليله.
    """
    suggestions: list[LearningSuggestion] = []
    for action, stats in sorted(by_action.items()):
        executed = int(stats.get("executed", 0))
        failed = int(stats.get("failed", 0))
        sample = executed + failed
        if sample < min_sample:
            continue  # عيّنة غير كافية — لا اقتراح (صدق)
        success_rate = round(executed / sample, 3) if sample else 0.0
        water_saved = float(stats.get("water_saved_mm", 0.0))
        conf = _confidence(sample)
        evidence = {
            "executed": executed,
            "failed": failed,
            "sample": sample,
            "success_rate": success_rate,
            "water_saved_mm": round(water_saved, 2),
        }

        if success_rate < _LOW_SUCCESS:
            suggestions.append(
                LearningSuggestion(
                    kind="raise_approvals",
                    action_type=action,
                    message_ar=(
                        f"نسبة نجاح «{action}» منخفضة ({success_rate:.0%} على {sample} قراراً) — "
                        f"يُقترَح رفع الموافقات المطلوبة أو مراجعة أسباب الفشل."
                    ),
                    evidence=evidence,
                    confidence=conf,
                )
            )
        elif success_rate >= _HIGH_SUCCESS:
            suggestions.append(
                LearningSuggestion(
                    kind="relax_friction",
                    action_type=action,
                    message_ar=(
                        f"«{action}» ناجح باطّراد ({success_rate:.0%} على {sample} قراراً) — "
                        f"يمكن النظر في تخفيف الاحتكاك (موافقات أقلّ) بحذر."
                    ),
                    evidence=evidence,
                    confidence=conf,
                )
            )

        if water_saved > 0 and "irrig" in action:
            suggestions.append(
                LearningSuggestion(
                    kind="favor_water_efficiency",
                    action_type=action,
                    message_ar=(
                        f"وفّرت أمثَلة «{action}» {water_saved:.0f}مم تراكميّاً دون فشل ملحوظ — "
                        f"يُقترَح ترجيح كفاءة الماء افتراضاً لهذا الإجراء."
                    ),
                    evidence=evidence,
                    confidence=conf,
                )
            )

    return suggestions
