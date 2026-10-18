# Remaining allocation: partial source repairs and acceptance preparation

Base: `main@9f0bcece487a8e9e2fc1ea590af5f2af5ab17504`, the merged #1199 tree.
The allocation remains **19 fixed / 9 open / 0 verified**. No remaining gap is
closed by this follow-up. Historical #1199 preflight/CI does not validate this tree.

## Source changes

- Raster search retains selected assets' declared calibration context. The VRT
  helper accepts only explicit asset-bound coefficients, rejects inconsistent
  metadata and the unresolved legacy collection, and retains production containment.
  Its new metadata bridge is offline acceptance infrastructure, not live provider
  calibration. Sixteen new witnesses fail against the pinned base; the complete
  witness/containment selection passes 100 tests. See `radiometry/report.json`.
- Raster product transport preserves recorded provenance and quality without
  inventing a current algorithm identity for old COGs. Availability and mask
  claims are checked across persistence and rehydration; detailed final proof is
  in `vegetation/`. CDSE server-mask identity and canonical contract decisions
  remain unresolved. No Vegetation quality gate is relaxed.
- A tenant-scoped read-only inventory tool exposes unknown provider/version and
  truncated snapshots explicitly. Its 25 mocked driver-contract tests do not
  prove PostgreSQL syntax, RLS behavior or a production census. The red import
  witness proves the tool was absent, not that historical product damage was measured.

## Remaining acceptance boundaries

| Gap | Evidence still needed |
| --- | --- |
| ELEMENT84-VRT-REFLECTANCE-SCALE-NOT-APPLIED-01 | Actual provider/asset calibration resolving contradictory metadata; containment stays active |
| ELEMENT84-LEGACY-PRODUCTS-UNINVENTORIED-01 | Native SQL/RLS acceptance and authorized per-tenant production census |
| VEGETATION-ANALYZE-GATE-UNREACHABLE-FOR-CDSE-PRODUCTS-01 | Honest CDSE mask identity, explicit quality semantics, canonical scene/mask contract |
| REPORT3-RAG-01-01 / REPORT3-RAG-07-01 | Versioned real Nomic/Qdrant Arabic before/after experiment; 34 existing safety tests are not retrieval acceptance |
| CDSE-EMPTY-SCENE-HAS-NO-ATTRIBUTABLE-CAUSE-01 | Original historical evidence, which the current archive does not contain |
| DECISION-033-LEGACY-POLICY-UNION-01 | Committed staging 034 plus restricted-role isolation matrix |
| CORRELATION-ID-ABSENT-FROM-THE-THREE-TABLES-THAT-CARRY-THE-DECISION-CHAIN-01 | Select the actual owner-controlled chain before scoped migrations/writer changes; no approvals table is invented |
| TTS-PLATFORM-POLICY-CONTRACT-SKEW-IN-PRODUCTION-01 | Compatible deployed image pair, trusted policy origin and instrumented local-only speech acceptance |

`inventory/correlation-audit.md` describes the distinct decision/dispatch/run/receipt
chains. `rag/assessment.json` records unavailable local retrieval runtimes and the
existing governed seed identity. No prefix change, reseed, reindex or reserved RAG
work is performed.

The [runtime plan](../../../docs/runbooks/REMAINING_RUNTIME_ACCEPTANCE_20261016.md)
separates Decision034, U07v234 and TTS operations. Its 120 existing source tests
pass without skips; they do not apply migrations or prove live behavior. U07 was
already fixed in source, but the dated postmerge migrator logs reported apply=false.
No global migration flag, consumed GATE-01 grant, Railway branch or external speech
permission is changed. Full follow-up preflight and final-head CI remain separate
publication gates; their receipts must name the exact tested tree.
