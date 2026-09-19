"""قشرةُ إعادة تصدير — الوحدةُ انتقلت إلى `shared.ai.recommendation_runtime.multi_tenant_runtime_validator` (AI-RUNTIME-WIRING-01).

تبقى هنا كي لا يتغيّر مستهلكوها داخل هذه الخدمة واختباراتُها؛ لا منطقَ فيها.
"""

from shared.ai.recommendation_runtime.multi_tenant_runtime_validator import (
    MultiTenantRuntimeValidator,
    TenantIsolationViolation,
    validate_tenant_payload,
)

__all__ = [
    "MultiTenantRuntimeValidator",
    "TenantIsolationViolation",
    "validate_tenant_payload",
]
