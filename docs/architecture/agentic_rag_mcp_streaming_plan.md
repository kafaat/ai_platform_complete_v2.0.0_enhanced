# Agentic Agricultural RAG hardening plan

Implemented primitives:

- Ponytail guardrails: reduce over-tooling and block precise advice without evidence.
- Field Context Coordinator: coordinates tools; does not decide.
- Decision Firewall: prevents RAG/KG from becoming governing inputs.
- Resumable Stream checkpoints: production implementation should back this with Redis.
- Read-only KG GraphQL facade: exploration only, reference confidence only.

Next production hardening:

1. Replace in-memory stream store with Redis.
2. Wrap weather/lab/rag/kg endpoints as MCP servers with tool descriptors.
3. Add SSE endpoints for Daily Brief and prescription generation.
4. Add a full GraphQL server only for read-only KG exploration.
5. Add UI artifacts as display-only Mermaid/HTML/Markdown outputs.
