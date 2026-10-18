# Nine assigned gaps: integrated source repairs and remaining acceptance

Base: `6e8cc0f9952c037550ae1644919f88c475dd89a7` (merged #1200).
Reviewed source integration: `4e796243344a1cba08e38c4775779cba1376b8da`.
The final generated tree, complete preflight and final-head CI must be validated
separately. This document does not assert those future results.

## Source changes

| Gap | State at this source candidate | Evidence |
| --- | --- | --- |
| ELEMENT84-VRT-REFLECTANCE-SCALE-NOT-APPLIED-01 | fixed for supported C1; legacy contradictions remain rejected | [provider replay](radiometry/report.json) |
| VEGETATION-ANALYZE-GATE-UNREACHABLE-FOR-CDSE-PRODUCTS-01 | fixed native QA and canonical producer lineage; no live CDSE certificate | [imagery receipts](imagery/README.md) |
| REPORT3-RAG-01-01 | fixed explicit optional versioned query/document profile; legacy configuration remains compatible | [profile](rag/profile-verification.json) |
| REPORT3-RAG-07-01 | fixed complete, revisioned, tenant-preserving shadow preparation; no serving cutover | [native reindex](rag/native-reindex-witness.json) |
| CORRELATION-ID-ABSENT-FROM-THE-THREE-TABLES-THAT-CARRY-THE-DECISION-CHAIN-01 | open pending native PostgreSQL acceptance of integrated migrations and writers | [chain evidence](inventory_correlation/README.md) |
| ELEMENT84-LEGACY-PRODUCTS-UNINVENTORIED-01 | open; bounded inventory hardened, actual tenant census not run | [catalog observation](integration/staging-inventory-catalog-observation.json) |
| DECISION-033-LEGACY-POLICY-UNION-01 | open; scoped atomic 033/034 executor prepared, committed staging application not performed | [migration evidence](decision/README.md) |
| TTS-PLATFORM-POLICY-CONTRACT-SKEW-IN-PRODUCTION-01 | open; source contract hardening and local socket tests cannot replace paired deployment acceptance | [TTS evidence](tts/acceptance-summary.json) |
| CDSE-EMPTY-SCENE-HAS-NO-ATTRIBUTABLE-CAUSE-01 | open; original discarded bytes and cause remain unknown | [historical limits](imagery/README.md) |

The 28-gap allocation is **23 fixed / 5 open / 0 verified** on this candidate,
including the 19 already fixed in the base. No remaining identity is invented,
silently dropped, or called verified. Source states on this branch do not imply
that main or a deployed service contains these changes.

## Measured integrated validation

- Raster quality gate: **613 passed, 2 skipped**. The two PostgreSQL-dependent
  tests are not executed by this local run; [raw log](integration/combined-raster-gate.log).
- Complete `tests_v9/test_rag_*`: **251 passed, zero skipped** on integrated final
  RAG bytes; [raw log](integration/integrated-rag-suite.log).
- Independent final RAG review: **58 passed, zero skipped**, including relocated
  adapter, bounded scans and tenant/quarantine probe;
  [byte-bound review](integration/rag-profile-review.json).
- Subsequent warm-profile handling: four red route witnesses, then **301 RAG and
  Qdrant tests passed, zero skipped** on the author's exact source. Known drift
  returns a sanitized 503; authentication, tenant isolation and unexpected
  programming failures retain their distinct behavior. See
  [review](integration/profile-warm-route-independent-review.json).
- Actual canonical timeline/bundle builders preserve the previous full payload
  when raster provenance is absent. Two red witnesses precede the narrow
  serializer fix; **42 focused tests passed**, plus **4 independent checks**.
  Present measured provenance remains included and strict validation is retained;
  [compatibility review](integration/lineage-compatibility-review.json).
- Focused main-red/candidate-green tests and actual native Qdrant/Ollama receipts
  are linked from the domain evidence directories. Overlapping counts are not summed.
- Native PostgreSQL is a separate CI gate. The v235 subset adds 17 collected native cases alongside 033/034/036 and inventory; collection is not execution. PGlite proofs are explicitly limited
  WASM/subset evidence, not a PostgreSQL server certificate.

The frozen Arabic passage set has 64 passages and 24 agent-judged questions.
Prefix-only final retrieval regressed. The optional measured 0.1/0.9 profile
improved aggregate development metrics; its acceptance partition was already
observed during diagnosis. It is **development validation, not an unseen holdout**,
independent agronomic validation, or a reason to promote quarantined seeds.
No live alias, consumer, tenant corpus or deployment was changed.

## Governance and operational boundaries

GATE-01 stays globally CLOSED. New `GATE01-ADJ-2026-10-16-002` is an agent-authored
record of the owner's current delegation, bound to the reviewed correlation
paths/bytes; the consumed U07 grant is not reused. Its source-integration scope
does not certify runtime migration application. See
[guard result](integration/integration-gate01.log).

Both exported observation schemas are regenerated from actual models. The new
field is omitted when absent, preserving legacy output. Old strict consumers
reject present new provenance; deploy compatible consumers before producers
that emit it. The indicators producer is not present in
the observed Railway inventory, so its live rollout is unverified.

[Observed deployment impact](integration/expected-deployment-impact.json): a main
merge matches 9 staging services plus 3 conditional repository-link cases and 10
production services. Frontend does not match the changed paths. Both platform
environments and staging TTS are pinned to other branches. Decision checks all
own migrations at readiness, while the staging journal stops at 032; do not
assume a new revision is ready without an explicit migration/deployment sequence.
No migration apply flag, SoR publisher or physical actuator was enabled.

The staging-only metadata probe used a restricted identity and read no product
rows. It was deleted after evidence capture; [cleanup](integration/temporary-probe-cleanup.json).
Catalog visibility is not a production product census.
The [operational feasibility audit](integration/operational-feasibility-audit.json)
found no authoritative staging tenant identity in the existing receipts and no
database restore-point operation in the exposed Railway capability set. Synthetic
fixture IDs and deployment rollback snapshots are not substitutes for those inputs.

Preflight diagnostics and targeted repairs are recorded in `integration/preflight-repairs/`. The first broad diagnostic snapshot was not green; its failures drove source/test fixes and regenerated artifacts. Router ceilings were lowered after extraction; YAML ownership assertions preserve exact semantic values and test 25 invalid mutations. Only the later exact-tree full preflight receipt may authorize publication.
