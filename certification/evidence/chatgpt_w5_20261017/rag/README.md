# Yemeni Arabic evaluation v1.0.0 — baseline only

`evaluation-v1.json` freezes 32 identified queries: 24 existing Arabic queries
and eight candidate Yemeni colloquial paraphrases (الجوف، البر، البير، ماء الري،
التربة والتخزين). Each has complete graded relevance judgments over the same
64 repository passages. The existing corpus is referenced by path and SHA256;
it is not reseeded. The historical 24 questions have been used in earlier
experiments and **are not an unseen holdout**. The eight paraphrases inherit
their parent judgments and require independent Yemeni/domain review.

Judgments measure passage relevance only. Unverified source attribution and
agronomic statements in the existing seed corpus are not endorsed. These data
are not suitable for prescribing irrigation, pesticides, fertilizer or prices.

## Current-stack measurement

```bash
python certification/evidence/chatgpt_w5_20261017/rag/baseline_readonly.py \
  --qdrant-url http://127.0.0.1:6333 --ollama-url http://127.0.0.1:11434
```

Observed exit code: **2 (BLOCKED)**. Both loopback dependency probes failed with
connection refusal; raw access probe records are in `../access-probes.json`.
`baseline-command.txt` and `baseline-results.json` retain the command result,
source/evaluation digests and every query/stage status. All 32 current-stack
queries are BLOCKED; dense, sparse, fusion, expansion and post-expansion rerank
have **null**, not zero, scores. There is no measured current dense/fusion/
expansion quality baseline in this environment. No dummy embedding, hash vector,
new model, prefix repair, model pull or reseed substitutes for that missing run.

The harness imports `services/sahool-platform/core/rag/production_qdrant.py`.
It observes the existing `retrieve` stages rather than reimplementing ranking.
Its defaults match `docker-compose.v9.yml:2058-2063`: existing `sahool_agri_kb`,
Ollama `nomic-embed-text`, no reindex profile. It permits loopback only, rejects
mutating Qdrant operations, caps corpus pagination, records model discovery,
and requires the observed eligible corpus's identities **and text** to match
the frozen judgments before reporting ranking metrics. A changed corpus needs
new, versioned judgments; it must not be silently treated as irrelevant.

## Separate offline diagnostic

The real current BM25 implementation was run in memory over the historical
64-passage fixture, treated explicitly as a single diagnostic corpus. Macro
averages across 32 queries at k=5:

| Precision | Recall | MRR | nDCG |
| --- | --- | --- | --- |
| 0.2625 | 0.5781 | 0.7578 | 0.5751 |

Per-query ranked IDs and metric values are under `offline_snapshot_sparse`.
This diagnostic changes no Qdrant data. It does not measure current tenant
visibility, quarantine eligibility, embedding provenance or the live hybrid
pipeline. It must not fill the missing current-stack sparse cell above.

## Decisions held until baseline is available

- REPORT3-RAG-02-01: inspect live tenant/quarantine visibility before changing prefixes.
- REPORT3-RAG-05-01: bind corpus, model digest and document/query encoding contracts; dimensions alone are insufficient.
- REPORT3-RAG-06-01: measure local-ai-rag's independent reader separately; this canonical-retriever harness does not prove its parity.
- REPORT3-RAG-08-01: compare stage IDs and graded ranking metrics, not a dense score to final RRF/rerank order.
- REPORT3-RAG-12-01: no prefix/model improvement claim or selection from this blocked baseline.

Remaining acceptance: provide an existing local stack and an explicitly scoped
corpus with matching adjudicated qrels; run unchanged baseline; retain model
digest, Qdrant/corpus identity and all raw stage results; only then propose a
paired repair experiment to the owner. Staging and production were not queried.
