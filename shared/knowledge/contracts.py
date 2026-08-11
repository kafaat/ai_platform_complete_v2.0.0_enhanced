"""عقود طبقة المعرفة التشغيليّة — `KNOWLEDGE-CANONICAL-CONSUMPTION-01`.

**ما تحلّه هذه الطبقة:** الشجرة تحمل مُنتِجاتٍ قانونيّة كثيرة (`canonical_*`)،
لكنّ استهلاكها اتّفاقٌ ضمنيّ: من يكتب مستهلِكاً جديداً لا يجد ما يقول له «هذه
القيمة لها مُنتِجٌ قانونيّ، ولا يجوز اشتقاقها من الخام». فيشتقّها بحسن نيّة،
ويُنتِج رقماً معقولاً من مصدرٍ غير قانونيّ — **فيبدو النجاح**.

فالعقد هنا يجعل التبعيّة **مُعلَنةً وقابلةً للفحص** بدل أن تبقى في رأس كاتبها.

**ولماذا `dataclass` لا `BaseModel`:** الجيران المباشرون لهذه الطبقة —
`canonical_root_zone_profile` و`canonical_sprinkler_runoff_capability` وأمثالهما —
كلّهم `@dataclass(frozen=True)`. وطبقةُ ربطٍ تُخالِف أسلوب ما تربطه تضيف ترجمةً
عند كلّ حدّ. ولا تحتاج هذه العقود تحقّقاً تشغيليّاً من الأنواع: الحارس الساكن
يفحص الإعلان، والمُحلِّل يفحص القيم عند الحلّ.

فحص صرف بلا خدمات — ``pytest -m unit``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

SCHEMA_VERSION = "knowledge_context_contract.v1"


class ContextResolutionError(RuntimeError):
    """يُرفَع حين يتعذّر الوفاء بمتطلّبٍ **حاجب** (`fail_closed`).

    استثناءٌ خاصّ لا `RuntimeError` عامّ: المستهلك يجب أن يستطيع تمييز «المعرفة
    ناقصة فأحجب» عن «انهار شيءٌ في المُحلِّل» — والخلط بينهما هو الصنف الذي
    كلّفنا `VERIFIER_INTERNAL_ERROR` في بوّابة المنشأ.
    """


@dataclass(frozen=True)
class KnowledgeRequirement:
    """متطلَّبٌ معرفيّ واحد: مفتاحٌ ومصدرُ حقيقته.

    `source_of_truth` ليس تعليقاً: الحارس يقارنه بالسجلّ القانونيّ، فإعلانُ مصدرٍ
    غير مُسجَّل يُحجَب — وهو ما يمنع «مصدرَ حقيقةٍ ظلّاً» يولد بإعلانٍ في مِلَفّ.
    """

    key: str
    source_of_truth: str
    required: bool = True
    max_age_seconds: int | None = None
    fail_closed: bool = False


@dataclass(frozen=True)
class TaskContextContract:
    """ما تحتاجه مهمّةٌ بعينها من معرفةٍ قانونيّة، مُعلَناً في مكانٍ واحد."""

    task: str
    requirements: tuple[KnowledgeRequirement, ...]

    def requirement(self, key: str) -> KnowledgeRequirement | None:
        for req in self.requirements:
            if req.key == key:
                return req
        return None

    @property
    def keys(self) -> tuple[str, ...]:
        return tuple(req.key for req in self.requirements)


@dataclass(frozen=True)
class KnowledgeValue:
    """غلافُ نَسَبٍ موحَّد: القيمة **ومن أين جاءت**.

    الفرق بين ‏`et0 = 5.2` و‏`et0 = 5.2 من CanonicalWeatherState، مقيسة، منذ ثانيتين`
    هو الفرق بين رقمٍ وقرار. وطبقةُ القرار لا تستطيع أن تزن الثاني إن لم تَرَ إلّا
    الأوّل.
    """

    value: Any
    source_of_truth: str
    producer: str
    producer_version: str | None = None
    observed_at: str | None = None
    effective_at: str | None = None
    quality: str | None = None
    evidence_refs: tuple[str, ...] = ()


@dataclass(frozen=True)
class ResolvedContext:
    """نتيجةُ حلّ عقد. `require` تُخرِج القيمة، و`blocking_reasons` تشرح المنع."""

    task: str
    values: dict[str, KnowledgeValue] = field(default_factory=dict)
    blocking_reasons: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()

    @property
    def satisfied(self) -> bool:
        return not self.blocking_reasons

    def require(self, key: str) -> Any:
        """يُخرِج القيمة أو **يرفع**؛ ولا يُرجِع `None` صامتاً أبداً.

        الإرجاع الصامت هو ما يجعل مُستهلِكاً يكتب `value or fallback` — أي
        الالتفاف الذي وُجِدت هذه الطبقة لمنعه. فالغياب هنا صوتٌ لا صمت.
        """
        if key not in self.values:
            raise ContextResolutionError(
                f"{self.task}: المفتاح «{key}» غير محلول"
                + (f" — {'؛ '.join(self.blocking_reasons)}" if self.blocking_reasons else "")
            )
        return self.values[key].value

    def provenance(self, key: str) -> KnowledgeValue:
        if key not in self.values:
            raise ContextResolutionError(f"{self.task}: لا نَسَب للمفتاح «{key}»")
        return self.values[key]
