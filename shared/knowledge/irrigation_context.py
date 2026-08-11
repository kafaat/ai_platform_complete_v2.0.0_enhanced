"""عقودُ سياقِ مهامّ الريّ — **عقدٌ لكلّ مهمّة**، لا عقدٌ واحد للمجال.

**ولماذا فُصِلا:** أوّل صياغةٍ عندي جمعت مفتاحَي منطقةِ الجذر والمُجدوِل في عقدٍ
واحد اسمُه «توصية الريّ». ثمّ رُبِط المُنسِّق الحقيقيّ فظهر أنّ
`orchestrate_irrigation_recommendation` **لا يجلب مِلَفَّ منطقة الجذر أصلاً** —
فربطُ ذلك العقد كما هو كان **يحجب كلّ توصية**. أي أنّ العقد كان يصف مجالاً لا
مهمّة، وهذا ما تُظهِره ساعةُ الوصل لا ساعةُ الكتابة.

سقفُ الملء يخصّ مهمّةَ **بناء قدرة الرشّ**؛ وأقصى عمقِ الحدث يخصّ مهمّةَ
**الجدولة**. وخلطُهما يجعل مهمّةً تحمل عبء معرفةٍ لا تحتاجها.

فحص صرف — ``pytest -m unit``.
"""

from __future__ import annotations

from .contracts import KnowledgeRequirement, TaskContextContract

SPRINKLER_RUNOFF_CAPABILITY_CONTEXT = TaskContextContract(
    task="sprinkler_runoff_capability",
    requirements=(
        KnowledgeRequirement(
            key="root_zone.root_zone_refill_cap_mm",
            source_of_truth="canonical_root_zone_profile",
            fail_closed=True,
        ),
    ),
)

IRRIGATION_RECOMMENDATION_CONTEXT = TaskContextContract(
    task="irrigation_recommendation",
    requirements=(
        KnowledgeRequirement(
            key="irrigation.maximum_safe_depth_mm_event",
            source_of_truth="canonical_irrigation_capability_graph",
            fail_closed=True,
        ),
    ),
)
