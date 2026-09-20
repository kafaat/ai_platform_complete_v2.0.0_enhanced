"""رايات خطّ التوصية المحروس — تُقرأ من البيئة، وافتراضاتُها معرَّفة هنا مرّةً واحدة.

`GUARDRAIL-FLAGS-FILE-NOT-IN-ANY-IMAGE-01`: كانت الرايات في `config/guardrail_feature_flags.py`
بجذر المستودع، ولا تنسخ أيُّ صورةٍ `config/`، فكان مستهلكوها يسقطون إلى افتراضاتٍ صامتة في
**كلّ** حاوية ولا تُقلَب رايةٌ في التشغيل بأيّ وسيلة. هنا: الافتراضاتُ نفسُها، والقيمةُ
تُقرأ من `SAHOOL_<FLAG>` عند الاستيراد، و`shared/` تنسخها الصورتان (المنصّة وai_agronomist).
ليست إعلانَ جاهزيّة: التفعيلُ المرحليّ يبقى قراراً يُقاس بشهادةٍ حيّة قبل قلب أيّ راية.
"""

from __future__ import annotations

import os

_TRUE = {"1", "true", "yes", "on"}
_FALSE = {"0", "false", "no", "off"}


def flag(name: str, default: bool) -> bool:
    """قيمةُ الراية من `SAHOOL_<name>`؛ قيمةٌ غيرُ مفهومة تُعدّ الافتراضَ لا تفعيلاً."""
    raw = os.getenv(f"SAHOOL_{name}")
    if raw is None:
        return default
    value = raw.strip().lower()
    if value in _TRUE:
        return True
    if value in _FALSE:
        return False
    return default


ENABLE_PONYTAIL_GUARDRAILS = flag("ENABLE_PONYTAIL_GUARDRAILS", False)
ENABLE_LEGACY_RECOMMENDATION_FALLBACK = flag("ENABLE_LEGACY_RECOMMENDATION_FALLBACK", True)
REQUIRE_CANONICAL_FIELD_STATE = flag("REQUIRE_CANONICAL_FIELD_STATE", True)
REQUIRE_HUMAN_REVIEW_FOR_PESTICIDES = flag("REQUIRE_HUMAN_REVIEW_FOR_PESTICIDES", True)
ENABLE_HUMAN_REVIEW_WORKFLOW = flag("ENABLE_HUMAN_REVIEW_WORKFLOW", False)
ENABLE_RAG_RERANKER = flag("ENABLE_RAG_RERANKER", False)
ENABLE_DECISION_AUTHORITY_CONTRACTS = flag("ENABLE_DECISION_AUTHORITY_CONTRACTS", True)
ENABLE_JETSTREAM_RECOMMENDATION_EVENTS = flag("ENABLE_JETSTREAM_RECOMMENDATION_EVENTS", False)
ENABLE_RUNTIME_METRICS = flag("ENABLE_RUNTIME_METRICS", True)
ENABLE_RAG_QDRANT_INTEGRATION = flag("ENABLE_RAG_QDRANT_INTEGRATION", False)
#: `AI-RUNTIME-WIRING-01` الخطوة ②: يبلغ المستهلكُ الإنتاجيُّ `RecommendationRuntimePipeline`.
#: مطفأةٌ افتراضاً، وقلبُها **لا يُقاس جاهزيّةً**: بندُ الإغلاق يشترط شهادةً حيّةً على
#: القاعدة قبل التفعيل. وجودُ الراية يجعل القلبَ ممكناً في الحاوية — لا واقعاً.
ENABLE_RUNTIME_PIPELINE_CONSUMER = flag("ENABLE_RUNTIME_PIPELINE_CONSUMER", False)

GUARDRAIL_METRIC_NAMES = (
    "guardrail_trigger_total",
    "human_review_required_total",
    "recommendation_blocked_total",
    "evidence_missing_total",
)
