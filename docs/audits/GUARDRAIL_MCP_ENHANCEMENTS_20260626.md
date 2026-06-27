# Guardrail/MCP Enhancements — 2026-06-26

Implemented without adding dependencies:

- Configurable `GuardrailPolicy` for Ponytail rules.
- `GuardrailTrace` and `PonytailDecision` for explainability.
- In-memory `GuardrailEventPublisher` for future NATS/JetStream publishing.
- `ConfidenceComposer` with evidence weights: lab/weather > satellite > KG/RAG.
- MCP registry health, latency, cost metadata and circuit breaker.
- Recursive forbidden-key scan to avoid false positives from text values.
- `recommendation_inputs()` helper excludes RAG/KG annotation-only context.

Invariant preserved: tools and coordinators produce observations/signals/context only; final decisions still require Canonical Field State + Recommendation Engine.
