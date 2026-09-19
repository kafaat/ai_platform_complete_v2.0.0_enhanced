"""قشرةُ إعادة تصدير — الوحدةُ انتقلت إلى `shared.ai.recommendation_runtime.recommendation_events` (AI-RUNTIME-WIRING-01).

تبقى هنا كي لا يتغيّر مستهلكوها داخل هذه الخدمة واختباراتُها؛ لا منطقَ فيها.
"""

from shared.ai.recommendation_runtime.recommendation_events import (
    RECOMMENDATION_STREAM,
    SUBJECTS,
    RecommendationEvent,
    RecommendationEventPublisher,
    utc_now,
)

__all__ = [
    "RECOMMENDATION_STREAM",
    "RecommendationEvent",
    "RecommendationEventPublisher",
    "SUBJECTS",
    "utc_now",
]
