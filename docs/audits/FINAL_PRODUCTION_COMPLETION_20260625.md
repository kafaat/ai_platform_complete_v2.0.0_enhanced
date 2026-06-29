# Final production completion layer — 2026-06-25

Implemented as dependency-light production contracts, without adding new package dependencies:

- ISOXML/VRT profile-aware export contract with machine/controller validation.
- Daily Agronomist brief at farm, field, and zone scopes.
- Harvest-grounded feedback evaluation using actual weighed harvest pairs.
- JSON-backed MLOps runtime contract for model cards, champion/challenger, and drift checks.

Decision boundary remains unchanged:

```text
Observation/Signal → Evidence/Provenance → Canonical Field State → Recommendation Engine → Human Review → Prescription/Task/Brief
```

RAG/KG/MCP/Artifacts remain context or annotations only, not decision authorities.
