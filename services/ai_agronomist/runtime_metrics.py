"""قشرةُ إعادة تصدير — الوحدةُ انتقلت إلى `shared.ai.recommendation_runtime.runtime_metrics` (AI-RUNTIME-WIRING-01).

تبقى هنا كي لا يتغيّر مستهلكوها داخل هذه الخدمة واختباراتُها؛ لا منطقَ فيها.
"""

from shared.ai.recommendation_runtime.runtime_metrics import (
    RuntimeMetrics,
    runtime_metrics,
)

__all__ = [
    "RuntimeMetrics",
    "runtime_metrics",
]
