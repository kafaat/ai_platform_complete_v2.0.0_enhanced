# RAG01/RAG07 continuation — 2026-10-16

Base: `main@9f0bcece487a8e9e2fc1ea590af5f2af5ab17504`.

Both gaps remain **open**. No production source, prefix, seed, corpus, alias, or deployment was changed.

## Measured prerequisites

`runtime-availability.json` records missing local Ollama/Qdrant servers and model frameworks. The CI virtualenv has `qdrant_client`, which does not supply a Nomic embedding model or a Qdrant HTTP server. No real retrieval-quality experiment was run. The earlier HashEmbeddingProvider fixture remains synthetic evidence only.

## Source findings

- `production_qdrant.py:714` still sends raw text through one embed method. A candidate prefix change must first satisfy the explicit registry gate at rows RAG01/RAG07.
- `seed.py:43-44` already declares seed tenant and revision. `seed.py:268` selects static KNOWLEDGE_BASE; `seed.py:349-378` uses `seed:<id>` identities and metadata provenance. Existing revision/quarantine protection must be preserved. This is not evidence of complete tenant-aware reindexing.
- Canonical storage UUIDs are deliberately stable under the existing logical-identity migration contract. A casual switch to tenant/revision-based IDs would bypass the migration plan and might orphan earlier rows. A complete before/after inventory and explicit collision disposition are prerequisites.

## Existing checks

`baseline.xml` / `baseline.log`: **34 passed, 0 failed, 0 skipped**. They cover existing RAG03/04/11 safety and logical-identity planning, not closure of RAG01/RAG07. No red/green repair claim is made.

The repository already supplies `scripts/staging/ai_rag_live_acceptance.sh` and `scripts/architecture/rag_live_parity_probe.py`; they are reused as references, not duplicated or run against production. Neither is a replacement for the missing four-stage Arabic relevance benchmark. Optional generation/restart switches have side effects and were not invoked.

`assessment.json` records exact source hashes and the concrete prerequisites for the next experiment. In particular, versioned Arabic judgments, exact model digest, same-corpus candidate collections, all four retrieval-stage outputs, multiple ranking metrics, tenant/quarantine safety and an explicit acceptance interpretation are still required. No fabricated thresholds, results or new gap IDs were introduced.
