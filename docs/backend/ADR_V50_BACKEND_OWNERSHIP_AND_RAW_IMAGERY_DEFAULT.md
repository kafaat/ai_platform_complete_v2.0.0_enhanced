# ADR-v50: Backend Domain Ownership and Raw Imagery Default

## Status
Accepted

## Context
SAHOOL has a large modular-monolith core plus satellite microservices. The project now includes historical imagery, AI field memory, weather intelligence, drawing/zones, and multiple AI/RAG services. Without an ownership matrix, new capabilities risk being added to whichever service is convenient rather than the domain that owns the data.

## Decision
1. Keep **raw field satellite imagery / truecolor** as the default MapHub operator view. Weather and vegetation indices are overlays.
2. Maintain `SERVICE_REGISTRY.md` as the backend source-of-truth for service purpose, ownership, risk, and extraction seams.
3. Build new capabilities first as thin domain-oriented seams with contract tests.
4. Keep AI as a consumer of evidence and action tools, not as the canonical owner of field, imagery, weather, or operation records.

## Consequences
- The system can add intelligence without hiding data provenance.
- Refactoring out of `sahool-platform` becomes incremental and testable.
- Product decisions such as the raw imagery default are protected from accidental regression.
