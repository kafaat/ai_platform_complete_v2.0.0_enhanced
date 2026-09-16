"""Feature flags for the staged SAHOOL AI decision runtime.

Keep each default defined exactly once.  These are compatibility defaults, not a
production-readiness claim: guarded recommendation rollout remains explicitly staged.
"""

ENABLE_PONYTAIL_GUARDRAILS = False
ENABLE_LEGACY_RECOMMENDATION_FALLBACK = True
REQUIRE_CANONICAL_FIELD_STATE = True
REQUIRE_HUMAN_REVIEW_FOR_PESTICIDES = True
ENABLE_HUMAN_REVIEW_WORKFLOW = False
ENABLE_RAG_RERANKER = False
ENABLE_DECISION_AUTHORITY_CONTRACTS = True
ENABLE_JETSTREAM_RECOMMENDATION_EVENTS = False
ENABLE_RUNTIME_METRICS = True
ENABLE_RAG_QDRANT_INTEGRATION = False

GUARDRAIL_METRIC_NAMES = (
    "guardrail_trigger_total",
    "human_review_required_total",
    "recommendation_blocked_total",
    "evidence_missing_total",
)
