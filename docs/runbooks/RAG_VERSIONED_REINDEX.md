# Versioned RAG shadow index and optional query profile

The default collection, unprefixed query encoding, and dense/sparse weights 0.7/0.3
remain unchanged. Creating a shadow index does not change an alias, collection
consumer, seed quarantine, or serving authority. Do not point a live consumer to a
candidate merely because preparation succeeded.

`services/qdrant-seed/reindex.py` accepts an explicit JSON specification containing
`source_collection`, a new `sahool_rag_reindex_*` target, immutable `revision`,
`model` (for example `nomic-embed-text:latest`), exact live `model_digest`, and the
reviewed complete `expected_source_payload_digest`. `max_points` is bounded.
Use `--inspect --spec <file> --output <new-private-file>` to obtain the complete
read-only source inventory, then pin that digest in the reviewed specification.
Use `--prepare-shadow` with another new output path to prepare and verify the
candidate. The command refuses existing outputs and targets. Partial failures
remain unserved and must be inspected; never reuse their names.

Operator-only variables (not automatically forwarded by Compose):

| Variable | Purpose |
| --- | --- |
| `RAG_REINDEX_QDRANT_URL` | Explicit Qdrant origin for the operator command |
| `RAG_REINDEX_QDRANT_API_KEY` | Optional private operator credential; do not commit it |
| `RAG_REINDEX_OLLAMA_URL` | Explicit Ollama origin for the pinned model |
| `RAG_REINDEX_PROFILE_MANIFEST` | Optional mounted serving receipt path; empty keeps legacy defaults |

The Nomic candidate requires `retrieval_profile: "nomic-ar-seed-v1"`,
`document_prefix: "search_document: "`, and model digest
`0a109f422b47e3a30ba2b10eca18548e944e8a23073ee3f3e947efcf3c45e59f`.
The completed receipt contains `query_prefix: "search_query: "`, Cosine/768,
dense/sparse weights 0.1/0.9, and full payload/vector fingerprints. The serving
adapter requires the mounted receipt, exact concrete `QDRANT_COLLECTION`, and
matching live `EMBEDDING_MODEL` digest. Untagged `nomic-embed-text` resolves to
`:latest`, whose digest is still checked. Missing/malformed/stale receipts,
vector-only drift, changed payloads, model or distance mismatches fail closed.
Shadow collections cannot silently fall back to a legacy encoder. Versioned
serving rejects incremental ingestion; prepare a new complete revision instead.

An admitted candidate must be write-frozen operationally: give serving credentials
read-only access, stop all other writers, and retain the prior consumer
configuration for rollback. Runtime audits detect drift but are not transactional
locks over external Qdrant writers. They read the complete bounded inventory;
this optional profile is not a high-throughput performance certification.
Any consumer switch needs the existing convergence admission and paired
query/document rollout; this change performs none.

The measured 0.1/0.9 choice was selected using 12 Arabic queries. The other 12
queries had already been inspected during prefix diagnosis, so their subsequent
metrics are **development validation, not an unseen holdout**. The corpus consists
of 64 repository passages with agent-authored relevance judgments, not expert
agronomic validation. It cannot authorize promotion of quarantined seed content.
Full model, corpus, scope, and ranking receipts are in
`certification/evidence/chatgpt_closure_nine_20261016/rag/`.

## Code ownership and packaging

`services/rag-retrieval/retrieval_profile.py` owns the optional serving admission
contract. `services/rag-retrieval/reindex_manifest.py` owns candidate preparation
and its receipt. Both live beside the canonical service transport and are copied
explicitly into its Docker image. The explicit `qdrant-seed/reindex.py` operator
command imports this owner directory relative to its own file, so invocation does
not depend on the shell working directory. Run it from a complete repository
checkout with its Python dependencies; the existing bootstrap seed image does
not contain this operator command. The default `qdrant-seed` bootstrap
image and command are unchanged. No reverse import from platform core, platform
module-budget increase, shared-service rollout or new retrieval authority is added.

Earlier runtime-provenance receipts retain their original source paths and hashes.
`module-owner-relocation.json` records their successor paths; historical evidence
is not relabeled as measurement of the relocated source.
