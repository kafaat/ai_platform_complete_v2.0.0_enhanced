# SAHOOL Remaining Gap Completion

Implemented closure items:

- Real MCP-style service descriptors for weather/lab/satellite/iot/rag/kg.
- Safe hybrid RAG retrieval with RRF, adjacent chunk expansion, reranking fallback, and tenant filters.
- Canonical Field State lock: only verified signals enter recommendation inputs; RAG/KG remain annotations.
- Full Daily AI Brief summarizer for weather/tasks/equipment/review queue.
- VRT exporters: GeoJSON and fail-closed ISOXML skeleton requiring machine profile.
- Conversation tree for branch/diff/rollback in agronomist review.

Decision invariant remains unchanged:

```text
Context / RAG / KG / MCP -> Canonical Field State -> Recommendation Engine -> Human Review -> Prescription/Task
```
