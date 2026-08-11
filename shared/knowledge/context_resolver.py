"""مُحلِّل سياق المهمّة — يحوّل عقداً مُعلَناً إلى سياقٍ محلولٍ أو حجبٍ مُعلَّل.

**القاعدة التي يفرضها:** لا يُسلِّم قيمةً بلا نَسَب، ولا يُسلِّم `None` صامتاً.
والقيمة الناقصة تُغري بارتدادٍ إلى الخام عند المستهلك — وهو ما تمنعه هذه
الشريحة أصلاً — فالغياب هنا **حجبٌ مُعلَّل** لا قيمةٌ ناقصة.

**ودورُ العَلَمين مضبوطٌ بدقّة** لأنّ الخلط بينهما يجعل أحدهما زينة:

- `required` (افتراضُه `True`) يحكم **الحاجة**: مفتاحٌ مطلوبٌ غيابُه يحجب.
- `fail_closed` (افتراضُه `False`) يحكم **حالة الشكّ**: يحجب حتّى ما كان
  `required=False`. أي أنّه المُميِّز الوحيد لمتطلَّبٍ اختياريٍّ **لا يُتسامَح
  في غيابه** — وبدونه يصير `required` وحده كافياً والعَلَم حِلية.

فالشرط `fail_closed or required` ليس ترخيّاً بل تعبيرٌ عن هذين الدورين. وهذا
مقيسٌ لا مُدَّعى: نزعُ `fail_closed` من الشرط ترك الجناح **أخضر بالكامل** حتّى
أُضيف `test_fail_closed_blocks_even_an_optional_requirement` — فكان العَلَم غير
مُثبَتٍ بشيء، وهو الصنف الذي يطارده هذا المستودع كلّه.

فحص صرف — ``pytest -m unit``.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping

from .contracts import (
    KnowledgeRequirement,
    KnowledgeValue,
    ResolvedContext,
    TaskContextContract,
)
from .source_registry import KnowledgeSource, RegistryError, registry

Provider = Callable[[KnowledgeRequirement], KnowledgeValue | None]


def _age_seconds(value: KnowledgeValue, now_epoch: float | None) -> float | None:
    """عمرُ القيمة بالثواني، أو `None` إن تعذّر قياسه."""
    if now_epoch is None or not value.observed_at:
        return None
    from datetime import datetime

    try:
        observed = datetime.fromisoformat(value.observed_at.replace("Z", "+00:00"))
    except ValueError:
        return None
    if observed.tzinfo is None:
        return None
    return now_epoch - observed.timestamp()


class ContextResolver:
    """يحلّ عقداً عبر مُزوِّدين مُسجَّلين بمفتاح المصدر القانونيّ.

    المُزوِّد يُسجَّل **باسم مصدر الحقيقة** لا باسم المفتاح: فمصدرٌ واحد يخدم
    مفاتيح كثيرة، وربطُ المُزوِّد بالمفتاح كان سيُكرِّر الوصلة عند كلّ حقل.
    """

    def __init__(
        self,
        providers: Mapping[str, Provider],
        sources: Mapping[str, KnowledgeSource] | None = None,
    ) -> None:
        self._providers = dict(providers)
        self._sources = dict(sources) if sources is not None else None

    def _sources_map(self) -> Mapping[str, KnowledgeSource]:
        if self._sources is not None:
            return self._sources
        return registry()

    def resolve(
        self,
        contract: TaskContextContract,
        *,
        now_epoch: float | None = None,
    ) -> ResolvedContext:
        try:
            sources = self._sources_map()
        except RegistryError as exc:
            # سجلٌّ لا يُقرأ ⇒ حجبٌ كامل. «لم يُعرَف» ليس «لا قيد».
            return ResolvedContext(
                task=contract.task,
                blocking_reasons=(f"KNOWLEDGE_REGISTRY_UNREADABLE: {exc}",),
            )

        values: dict[str, KnowledgeValue] = {}
        blocking: list[str] = []
        limits: list[str] = []

        for req in contract.requirements:
            source = sources.get(req.key)
            if source is None:
                blocking.append(f"UNREGISTERED_KNOWLEDGE_KEY: {req.key}")
                continue
            if source.source_of_truth != req.source_of_truth:
                # العقد يُسمّي مصدراً غير المُسجَّل ⇒ مصدر حقيقةٍ ظلّ.
                blocking.append(
                    f"SHADOW_SOURCE_OF_TRUTH: {req.key} "
                    f"({req.source_of_truth} ≠ {source.source_of_truth})"
                )
                continue

            provider = self._providers.get(req.source_of_truth)
            if provider is None:
                self._record_absence(req, "NO_PROVIDER_REGISTERED", blocking, limits)
                continue

            value = provider(req)
            if value is None:
                self._record_absence(req, "KNOWLEDGE_UNAVAILABLE", blocking, limits)
                continue
            if value.source_of_truth != req.source_of_truth:
                # مُزوِّدٌ يُسلّم قيمةً منسوبةً إلى مصدرٍ آخر: النَّسَب يكذب.
                blocking.append(
                    f"PROVENANCE_MISMATCH: {req.key} "
                    f"({value.source_of_truth} ≠ {req.source_of_truth})"
                )
                continue

            if req.max_age_seconds is not None:
                age = _age_seconds(value, now_epoch)
                if age is None:
                    self._record_absence(req, "FRESHNESS_UNMEASURABLE", blocking, limits)
                    continue
                if age > req.max_age_seconds:
                    self._record_absence(req, "KNOWLEDGE_STALE", blocking, limits)
                    continue

            values[req.key] = value

        return ResolvedContext(
            task=contract.task,
            values=values,
            blocking_reasons=tuple(sorted(set(blocking))),
            limitations=tuple(sorted(set(limits))),
        )

    @staticmethod
    def _record_absence(
        req: KnowledgeRequirement,
        reason: str,
        blocking: list[str],
        limits: list[str],
    ) -> None:
        """غيابٌ يُحجَب أو يُقيَّد — **ولا يُهمَل**.

        يُحجَب متى كان المتطلَّب **مطلوباً** (`required`) أو **حاجباً عند الشكّ**
        (`fail_closed`) — والثاني هو ما يجعل متطلَّباً اختياريّاً يحجب رغم
        اختياريّته. ولا يمرّ الغياب صامتاً في الحالة الثالثة: حتّى ما ليس مطلوباً
        ولا حاجباً يترك أثراً في `limitations`، لأنّ سياقاً ينقصه شيءٌ ولا يقول
        ذلك يُقرأ سياقاً كاملاً.
        """
        if req.fail_closed or req.required:
            blocking.append(f"{reason}: {req.key}")
        else:
            limits.append(f"{reason}: {req.key}")
