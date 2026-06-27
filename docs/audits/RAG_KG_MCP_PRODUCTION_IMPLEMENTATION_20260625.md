# RAG/KG/MCP production implementation

Implemented as an overlay that does not break the existing SAHOOL core:

- `services/rag-retrieval`: production-shaped Qdrant HTTP dense retrieval + local BM25 sparse index + tenant metadata filters + neighbor expansion + rerank fallback.
- `services/knowledge-graph`: persistent SQLite-backed agricultural graph store with read-only GraphQL-like facade. Edges are reference-only and non-prescriptive.
- `services/mcp_servers/generic_context_server.py`: independent MCP-style servers for field/weather/lab/satellite/iot/rag/kg. They emit only Observation/Signal/Annotation.
- `docker-compose.rag-kg-mcp.yml`: deploys RAG, KG, and independent MCP instances beside `docker-compose.v9.yml`.

Decision boundary preserved:

```text
MCP/RAG/KG -> Observation|Signal|Annotation only
Evidence/Provenance -> Canonical Field State
Canonical Field State -> Recommendation Engine
Recommendation Engine -> Human Review -> Prescription/Task
```

No new dependency was added to the existing monolith path. New service dependencies are isolated in their own Dockerfiles.
