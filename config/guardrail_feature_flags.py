"""Feature flags for the staged SAHOOL AI decision runtime — re-exported from `shared/`.

`GUARDRAIL-FLAGS-FILE-NOT-IN-ANY-IMAGE-01`: this file lives at the repository root and no
service image copies `config/`, so every container silently fell back to hard-coded
defaults and no flag could be flipped at runtime. The single definition of each default
now lives in `shared/ai/recommendation_runtime/flags.py` (copied into every image) and
reads `SAHOOL_<FLAG>` from the environment. This module stays as the documented entry
point for repository-root readers and tests; it defines nothing itself.

These remain compatibility defaults, not a production-readiness claim: guarded
recommendation rollout stays explicitly staged.
"""

from shared.ai.recommendation_runtime.flags import (
    ENABLE_DECISION_AUTHORITY_CONTRACTS,
    ENABLE_HUMAN_REVIEW_WORKFLOW,
    ENABLE_JETSTREAM_RECOMMENDATION_EVENTS,
    ENABLE_LEGACY_RECOMMENDATION_FALLBACK,
    ENABLE_PONYTAIL_GUARDRAILS,
    ENABLE_RAG_QDRANT_INTEGRATION,
    ENABLE_RAG_RERANKER,
    ENABLE_RUNTIME_METRICS,
    GUARDRAIL_METRIC_NAMES,
    REQUIRE_CANONICAL_FIELD_STATE,
    REQUIRE_HUMAN_REVIEW_FOR_PESTICIDES,
)

__all__ = [
    "ENABLE_DECISION_AUTHORITY_CONTRACTS",
    "ENABLE_HUMAN_REVIEW_WORKFLOW",
    "ENABLE_JETSTREAM_RECOMMENDATION_EVENTS",
    "ENABLE_LEGACY_RECOMMENDATION_FALLBACK",
    "ENABLE_PONYTAIL_GUARDRAILS",
    "ENABLE_RAG_QDRANT_INTEGRATION",
    "ENABLE_RAG_RERANKER",
    "ENABLE_RUNTIME_METRICS",
    "GUARDRAIL_METRIC_NAMES",
    "REQUIRE_CANONICAL_FIELD_STATE",
    "REQUIRE_HUMAN_REVIEW_FOR_PESTICIDES",
]
