"""قشرةُ إعادة تصدير — الوحدةُ انتقلت إلى `shared.ai.recommendation_runtime.recommendation_runtime_pipeline` (AI-RUNTIME-WIRING-01).

تبقى هنا كي لا يتغيّر مستهلكوها داخل هذه الخدمة واختباراتُها؛ لا منطقَ فيها.
"""

from shared.ai.recommendation_runtime.recommendation_runtime_pipeline import (
    RecommendationRuntimePipeline,
    RuntimePipelineResult,
)

__all__ = [
    "RecommendationRuntimePipeline",
    "RuntimePipelineResult",
]
