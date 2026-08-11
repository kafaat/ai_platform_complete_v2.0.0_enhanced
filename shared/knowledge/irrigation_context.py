"""عقد سياق توصية الريّ — أوّل مُعلِنٍ فعليّ في الشجرة.

مقصورٌ على المفتاحين اللذين تُغلِقهما هذه الشريحة فعلاً. `field.geometry`
و`weather.et0` واردان في المقترح ولم يُعلَنا هنا: متطلَّبٌ يُعلَن بلا مُنتِجٍ
مُسجَّل ومستهلِكٍ مقيس يُنتِج عقداً يبدو أشمل ولا يفرض شيئاً — وهو بالضبط
«الطبقة المعماريّة التجميليّة» التي تستثنيها هذه الشريحة.

فحص صرف — ``pytest -m unit``.
"""

from __future__ import annotations

from .contracts import KnowledgeRequirement, TaskContextContract

IRRIGATION_RECOMMENDATION_CONTEXT = TaskContextContract(
    task="irrigation_recommendation",
    requirements=(
        KnowledgeRequirement(
            key="root_zone.root_zone_refill_cap_mm",
            source_of_truth="canonical_root_zone_profile",
            fail_closed=True,
        ),
        KnowledgeRequirement(
            key="root_zone.maximum_safe_depth_mm_event",
            source_of_truth="canonical_sprinkler_runoff_capability",
            fail_closed=True,
        ),
    ),
)
