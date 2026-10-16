# RAG01 / RAG07 evidence — 2026-10-16

Source baseline: `6e8cc0f9952c037550ae1644919f88c475dd89a7`.

## What was actually measured

The initial socket/DNS probe found no local runtime. That did **not** mean outbound
HTTP was unavailable. Ordinary HTTPS downloaded official Qdrant 1.19.2, Ollama
0.40.5 and the actual Nomic model. Local native processes then ran the experiment;
no Railway service, production corpus, seed, alias, or query configuration changed.

An initial ONNX attempt was blocked by automatic approval review because native
telemetry attempted `mobile.events.data.microsoft.com`. The successful run set
`ORT_DISABLE_TELEMETRY=1` **before process initialization**, as documented in
[ONNX Runtime Privacy](https://github.com/microsoft/onnxruntime/blob/main/docs/Privacy.md).
This disables the uploader itself; no rejected endpoint was allowlisted or contacted
through a workaround. `HF_HUB_DISABLE_TELEMETRY=1` was also set. The exact Ollama
comparison used local cached GGUF weights and `OLLAMA_NO_CLOUD=true`.

## Frozen Arabic passage-relevance set

`arabic-corpus-v1.json`: 64 existing repository seed passages and 24 Arabic queries,
12 selection / 12 acceptance. Its SHA256 was frozen before inference:
`c55729d21a1ba37fedb9b58b4f776c16b46a099365fbd31722517bc15b043d35`.
Every eligible passage has an explicit integer relevance grade. Queries, grades,
and split were not changed after observing results. These are agent-authored
**passage-relevance judgments**, not independent expert validation of agricultural
claims. Existing seed statements retain their unverified-source limitation.
They must not be promoted into governing agronomic knowledge because a retrieval
experiment used them.

Each raw/prefixed collection had 192 points: the 64 passages under a synthetic
experiment tenant, copies under another tenant, and copies in seed quarantine.
All four stages were measured separately, with Precision@5, Recall@5, MRR@5 and
nDCG@5. Full payload inventories matched between paired collections. Every stored
document vector was compared to the actual model response, accounting for Qdrant's
Cosine normalization. Every stage rejected tenant/quarantine/scope leakage.

`onnx-experiment-results.json` is actual unquantized Nomic ONNX via FastEmbed 0.9.0 /
ONNX Runtime 1.31.0, at Hugging Face revision
`e9b6763023c676ca8431644204f50c2b100d9aab`. It is explicitly **not Ollama evidence**.
`real-experiment-results.json` repeats the same frozen comparison on actual Ollama
0.40.5 and Nomic F16, manifest digest
`0a109f422b47e3a30ba2b10eca18548e944e8a23073ee3f3e947efcf3c45e59f`.

### Acceptance split on actual Ollama

| Stage | Raw nDCG@5 | Prefixed nDCG@5 |
|---|---:|---:|
| Dense | 0.251967 | 0.305550 |
| Sparse | 0.681842 | 0.681842 |
| Fusion | 0.418787 | 0.375443 |
| Expansion/rerank | 0.405017 | 0.327514 |

Final MRR@5 declined from 0.729167 to 0.604167. The prefix-only change therefore
has no end-to-end acceptance claim. No production prefix change was applied.
This is concrete counterevidence for REPORT3-RAG-01-01, not a green closure test.
Fusion/reranking ownership was preserved; no RAG02/05/06/08/12 or direct/canonical
semantic fix was introduced here.

## Selection-only diagnosis of the regression

`selection-weight-decision.json` explores nine candidate dense weights
0.1–0.9 using only the 12 selection queries; both dense and sparse channels remain
nonzero. Maximizing selection final nDCG@5 selected dense 0.1 / sparse 0.9, frozen
before the acceptance calculation. The original queries/grades were unchanged.
The subsequent development-validation calculation in `selection-weight-validation.json`
measured final nDCG@5 0.655787, MRR@5 0.812500, Recall@5 0.763889 and Precision@5
0.383333. These exceed the corresponding raw baseline aggregate values, but the
24-question corpus is small and agent-judged; this is a candidate, not a broad
Arabic quality guarantee. The weight-selection function did not use these queries, but this partition had already been inspected during prefix diagnosis. It is **development validation, not an unseen holdout**.

The diagnostic points to an interaction with the existing dense-heavy fusion
weights. The optional `nomic-ar-seed-v1` profile now binds this measured choice to a complete
reindex manifest, matching document/query prefixes, live Nomic digest, payload and
vector inventories, and Cosine/768 configuration. Legacy default weights and
query encoding remain unchanged; no live namespace or consumer was switched.
No reserved gap is claimed closed by this scoped opt-in profile. `selection_weight_probe.py` reproduces the
selection and subsequent frozen-choice validation against the existing local
experiment storage, verifying its payload fingerprint first.

## Complete shadow reindex capability

`services/qdrant-seed/reindex.py` now offers explicit `--inspect` and
`--prepare-shadow` operations. Bootstrap `seed.py` remains bootstrap. The new
operation reads **all stored documents**, not `KNOWLEDGE_BASE`; requires a pinned
source inventory, revision and live model digest; preserves every logical ID,
tenant, quarantine label and provenance field; and verifies the entire candidate's
payload and vectors. Ambiguous identity collisions require the existing migration
plan. Empty, truncated, drifting or stale inventories and existing candidates fail
closed. Partial failed candidates remain unserved for inspection; there is no
automatic deletion or serving cutover.

Qdrant alias batches are atomic but do not supply an expected-old-target CAS.
A read-old/delete/create sequence would not prove conditional safety. This tool
therefore changes **no alias or consumer authority**, and explicitly requires the
existing query-encoder and cutover admission separately. A shadow result is not
production acceptance or permission to expose a different vector namespace.

`native-reindex-witness.json` records actual native server behavior:

- Baseline: original main `seed.seed()` ran against a disposable 3-document corpus;
  it produced 66 points and reindexed **zero uploaded documents**. That fails the
  complete-reindex contract.
- Candidate: all 3 documents were re-embedded and independently read back, including
  both tenants and quarantine; all original source payloads remained unchanged.
- Reusing the candidate and providing a stale source digest were rejected.
- Actual tenant searches returned only their own points; aliases stayed unchanged.
- The operator CLI also executed against real servers and wrote a private `0600`
  receipt. No production data or runtime was contacted.

This proves complete **shadow preparation**. It does not prove real-tenant
production migration/cutover, a query-encoder rollout, or global corpus approval.
Do not claim those from this witness.

## Reproduce / resume

Keep the official native binaries and model cache outside the Git repository.
The workspace journal, download receipts, package logs and stdout are under
`evidence/closure-nine/rag/` in the continuation workspace. Native services and
clients must be launched in the same execution context when loopback namespaces
are isolated.

```bash
ORT_DISABLE_TELEMETRY=1 HF_HUB_DISABLE_TELEMETRY=1 \
  /path/to/rag-runtime/bin/python \
  certification/evidence/chatgpt_closure_nine_20261016/rag/native_reindex_witness.py \
  --runtime-root /path/to/runtime-root --work-dir /path/to/private-evidence
```

The runtime root contains `rag-runtime-native/qdrant`,
`rag-ollama-runtime/bin/ollama`, and `rag-ollama-runtime/models/`.
The witness starts isolated servers and stops them in `finally`.
`relevance_experiment.py` is the reusable **read-only** measurement tool for two
already prepared experiment collections. It never creates collections or reindexes
production. Supply its versioned manifest, explicit local URLs, and an output path.

Unit tests cover measurement arithmetic and reindex admission. Those unit tests
are not substitutes for the saved real-model/native-server measurements.

## Versioned query profile follow-up

`native-profile-reindex-witness.json` reruns the complete real Qdrant/Ollama
preparation with the explicit Nomic profile. Actual profile queries returned only
the requested tenant; a vector-only change with unchanged payload was rejected.
The operator CLI still preserves all source rows and aliases. The separate
`profile-red-green.json` executes the same absent-manifest admission witness
against actual main source (fails) and the candidate (passes).

The serving profile is opt-in and checks the live model digest, full payload and
vector fingerprints, Cosine/768, query/document prefixes and selected weights.
No serving environment variable was set and no live consumer was switched.
Runtime audits are not locks on external writers; write-freeze, read-only serving
credentials and existing convergence admission remain required. See
`docs/runbooks/RAG_VERSIONED_REINDEX.md` for operation and performance limits.

## Warm-route admission failure mapping

`profile-warm-route-verification.json` records actual authenticated HTTP tests.
After a successful query warms the sparse index, model/vector/payload drift and
transport failure now return a sanitized 503 with no annotations. The same four
witnesses fail against `b1ed5a0b` (500 instead of 503). Authentication and tenant
mismatch still return 403; an unrelated programming `ValueError` remains 500.
The final RAG and Qdrant regression suite passed 301 tests with no skips.
