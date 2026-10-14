# Qdrant tenant payload index repair — offline evidence

Repair commit: `f0f2ee711e4426451d7708b03479affbe34b41e2`. Base: `53652e02b3c80fa5747a0ad0e7c6f7ed9c408d4b`.
Source tree: `516a4a08fdb23ef36a712edad65364d851bdc7ea`.

The source repair adds and verifies the `metadata.tenant_id` keyword index for
existing and new collections. It preserves a compatible existing index and
never deletes or recreates an existing collection. Automatic reconciliation
runs during ingest; search/readiness and the separate seed path do not invoke it.

## Measured evidence

- `qdrant_index_old_red.xml`: both regression cases fail on the unmodified base.
- `qdrant_index_related_green.xml`: 176 related tests pass on the reviewed source hashes.
- `qdrant_index_new_green.xml`: 45 focused tests pass; these are included in the 176.
- `qdrant_verify_b_review.json`: independent review, with 63 v9 and 6 legacy tests passing in separate processes.
- `qdrant_verify_b_api_witness.json`: seven injected-response API cases return 502 without point, BM25, cache or readiness mutations. The real authentication middleware and a real Qdrant server were not exercised.
- `qdrant_verify_b_tests.xml` and `qdrant_verify_b_baseline_tests.xml`: mixed-suite import failures retained honestly; the same two failures and four skips reproduce on the base.
- `qdrant_open_b_resume.xml`: 45 focused cases pass after resumption on identical source/test hashes.

These counts overlap; do not add them as a unique test total. None is evidence
of final-head CI, deployment, a live index or improved query latency. The repair
does not enable `is_tenant`, rebuild HNSW or initialize every seeded/read-only
collection merely by deploying code.

## Provenance and sanitization

Historical receipts retain their pre-commit state and paths as recorded at test
time. `provenance.json` binds their exact source hashes to the real repair SHA.
The source status described in old receipts is historical, not current branch
publication state. Absolute scratch roots and XML hostnames were sanitized as
listed in `provenance.json`; original and copied hashes are in
`evidence_manifest.json`. Test outcomes, timestamps and assertions are retained.
The witness script is historical text (`.py.txt`), not a newly installed runner.

## PR publication reference

Draft PR #1181 was opened at `663ed97d1bfeb5783fdb5550f23bdff73459ff2f` with repair `f0f2ee711e4426451d7708b03479affbe34b41e2`.
This records PR creation, not merge, service deployment, live index verification
or final-head CI success. Final artifact generation and required gates remain
pending after this provenance edit. Prior no-PR journal entries describe evidence
preparation; the appended publication entries record the later state.

The historical repair patch path in the receipt remains a historical reference;
source bytes are recoverable from the immutable repair commit. The redundant
patch is not included in this evidence directory.

Actual main was integrated from #1180 at `421a0e7afcecf1de967bf4a26ea9d64788baf1e1`.
The original wave-zero draft #1179 is closed; its source repair remains
`959e9730a5770e3728a3ce504522615820cb7991`. This changes provenance only.

## Canonical merge and observed deployment disposition

PR #1181 merged by squash at `e849f3279a56b2a7c80f399f1e5c746d7ff5abe9`.
Its tree is identical to reviewed PR head `733c5be65c55a3677191cfc149873d8cadfb2767`.
The copied PR-head CI snapshot records 69 successes, two expected skips and all
20 required checks successful. It is not a statement about the later main CI
run or this CDSE candidate. The copied Railway snapshot records 24 SKIPPED
merge records and unchanged settled deployment identifiers in the 43-entry
inventory. No live index creation or performance improvement is established.

`postmerge_evidence_copy_manifest.json` binds the two copied provider receipts
to their reviewed snapshot hashes. Original scratch filenames are mutable;
the immutable copied bytes and hashes identify this snapshot. Earlier draft
and pending-gate statements above describe their historical preparation stage.
