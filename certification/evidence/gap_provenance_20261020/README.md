# Historical closure provenance, 2026-10-20

Base: `b7d7652362768320e5a9dfa96b7d7303a4bae6f8` (#1248).

The full-history measurement reproduced the authentic Capability Governance artifact: 64 unreconciled fixed records. This change adds canonical merge links to **59** records and leaves **5** unresolved. It does not change any gap state: **95 open / 469 fixed / 3 verified** unique IDs, including section-only records. These are provenance corrections, not 59 newly repaired defects or production certifications.

## Evidence and method

[audit.json](audit.json) records all 64 decisions, the exact GitHub `commits/{sha}/pulls` queries, returned merged PR identities, canonical merge SHAs, and exceptions. Every accepted merge was checked as an ancestor of the pinned base and against its PR-number commit subject. The source ZIP was artifact 12273225399 from successful run 39436293583, with SHA-256 `a683e189d6d1e0b9a9e8bfd55a2aad14dc5413652ae2ca0e645071f8dbba6f86`; its source-file hashes match this base.

49 records have direct mappings for every unmatched commit token. Ten further records required distinguishing source repairs from tree hashes, deployment identifiers, an upstream SAM2 pin, superseded unpublished references, or a deployment-only branch. Those distinctions are recorded per row. Raster/CDSE's six recorded source/test hashes were independently compared with the actual PR #1185 merge: all six match. The unavailable local integration commit is not claimed as reachable. TiTiler's temporary CI merge and tested PR head share a tree; Vegetation's tested head and canonical merge also share a tree.

The original status prose, repair references, and operational limits are retained verbatim. No parser rule or allowlist is relaxed. A canonical link proves a historical Git relationship within its stated evidence; it does not prove present runtime health or eliminate later regressions. The measurement itself accepts a reachable canonical link per record, so the extra per-reference audit is necessary to avoid masking unresolved history.

## Five unresolved records

| Gap | Remaining provenance work |
| --- | --- |
| ELEMENT84-VRT-REFLECTANCE-SCALE-NOT-APPLIED-01 | Local repair SHA is unavailable on GitHub. Five of seven recorded source hashes match #1201; two changed during integration. Review those deltas before establishing the replacement mapping. |
| VEGETATION-ANALYZE-GATE-UNREACHABLE-FOR-CDSE-PRODUCTS-01 | Local repair SHA is unavailable. Seven of nine review hashes match #1201; two differ. Do not claim whole-tree equivalence. |
| REPORT3-RAG-01-01 | Local repair SHA is unavailable; the older profile review manifest does not wholly match #1201. Trace the later review and integration deltas. |
| REPORT3-RAG-07-01 | Same integration lineage needs tracing, including reindex.py. A related merged PR or matching subset is insufficient. |
| NATS-BROKER-HAS-NO-AUTHENTICATION-SO-ACTUATOR-COMMANDS-ARE-UNGUARDED-01 | Published repair d2faac8e4 maps to #1205, but historical 96f6a034 has no associated PR and differs in NATS configuration/test blobs. Establish its supersession explicitly rather than hide it under one valid link. |

Partial comparisons are included to explain the remaining work, not to certify it. None of these unresolved relationships proves that the repair is absent or broken. Railway staging NATS acceptance remains a separate gap.

## Reproduce

With full Git history, run `python3 scripts/ci/gap_registry_measure.py --json sahool-brain/gaps/registry.md`. On the base it reports 64; with this registry delta it reports 5. All other measurement fields except the affected fixed-record prose remain identical. Focused validation: 77 tests passed across test_gap_registry_measure.py, test_brain_state_consistency.py and test_gap_registry_claim_guard.py. An additional exact-text check proves that removing only the 59 appended canonical fragments restores every original registry line, and that the five unresolved statuses are byte-preserved. The full pre-push result is reported separately on the review branch.

No application code, deployment settings, migrations, credentials, or production services are changed. The incident freeze remains in force.
