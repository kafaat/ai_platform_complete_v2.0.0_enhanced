# SAHOOL Decision Fabric — source-level comparison (2026-09-16)

## Scope

This review compares the current `main` implementation with patterns found in LinkMind,
OpenAgentFlow, OM1 and WGAI.  The objective is **not** to import a generic agent framework.
SAHOOL remains a Farm OS whose agronomic engines own domain computation.

Baseline reviewed: `4bbb301f114da049688804c2f8ec10ac9c794401`.

## Finding 1 — do not add a second generic router

LinkMind centralizes model routing/failover behind configured route expressions.  SAHOOL
already has a stronger domain boundary: authoritative agronomic products are produced by
their owning engines, while Crop Intelligence is explicitly prevented from recomputing
ET0/GDD/raster/soil-water products. `crop_intelligence_boundary_gate.py` enforces that
boundary in CI.

The correct adaptation is therefore **authority routing**, not provider routing:

1. canonical deterministic agronomic product;
2. validated ML product where the capability owns ML inference;
3. RAG/KG as retrieval/context annotations;
4. generated language as explanation/advisory only;
5. decision candidate -> approval -> dispatch/execution through the existing decision path.

Adding a LinkMind-like agricultural router beside these paths would create a second source
of authority and is rejected by this review.

## Finding 2 — the Decision Envelope substrate already exists

`services/sahool-platform/api/crop_decision_bridge.py` already carries the important parts
of the proposed envelope: field/season identity, engine/schema versions, evidence ids,
confidence, limitations, GDD lineage, spectral provenance, candidate lineage,
`pending_approval`, and `approval_required=True`.

The candidate boundary is also guarded by
`scripts/ci/decision_candidate_boundary_gate.py`, which prevents candidate code from
approving, dispatching, executing, creating tasks, or issuing actuator commands.

Action: extend this existing candidate contract when a new domain needs additional
provenance. Do **not** create a parallel `DecisionEnvelope` runtime with separate semantics.

## Finding 3 — decision-service is not yet the authoritative SoR

`docs/architecture/DECISION_SERVICE_BOUNDARY_CONTRACT.md` explicitly records the current
interim bridge: `sahool-platform` remains the authoritative writer for loop tables and
`decision-service` is a best-effort non-authoritative mirror.  A future cutover is blocked
until persistence/RLS/outbox and the `recommendation_outcomes` deduplication prerequisite
are solved.

Any architecture drawing that labels decision-service as the current persistent SoR is
therefore incorrect.  The fabric must preserve the current fail-closed platform write until
the documented cutover gates are satisfied.

## Finding 4 — RAG/KG authority separation is implemented

`services/ai_agronomist/decision_contracts.py` gives RAG/KG lower evidence weights and
`recommendation_inputs_from_context()` excludes them from governing recommendation inputs.
`services/ai_agronomist/ai_evidence_runtime.py` only composes confidence from validated or
verified canonical soil/weather/spectral products; retrieval ranking and KG edges do not
become calibrated agronomic confidence.

This is the correct SAHOOL analogue of middleware routing: retrieval can improve recall and
explanation but cannot silently become agronomic authority.

## Finding 5 — guarded recommendation runtime is only partially integrated

`runtime_guardrail_adapter.py` requires canonical field state and strips RAG/KG from
governing inputs. `recommendation_runtime_pipeline.py` wraps this boundary and routes
pesticide/high-risk recommendations to review.  Repository search, however, finds runtime
construction of `RecommendationRuntimePipeline` in tests, not a production caller.

Therefore this pipeline must not be described as the universal live recommendation path
until a production call site and live certification prove it.

The current feature defaults reinforce the staged state:
`ENABLE_PONYTAIL_GUARDRAILS=False`, `ENABLE_LEGACY_RECOMMENDATION_FALLBACK=True`, and
`ENABLE_HUMAN_REVIEW_WORKFLOW=False`.

## Finding 6 — OM1 pattern belongs at the device boundary

OM1's useful pattern is modular inputs/actions around a HAL.  In SAHOOL the equivalent
should remain:

`driver -> device adapter -> canonical observation -> quality/calibration -> canonical field state -> decision`

No sensor driver should write a recommendation or execution command directly.  Existing
actuation/decision boundaries should be extended rather than introducing an OM1 runtime as
a second orchestrator.

Measured reason (OM1 @ `84e00a1672d17d012c24ae6b300365594265bd37`, 2026-09-15): OM1's core
loop hands the LLM's tool calls straight to the action executor
(`internal/runtime/runtime.go:506` `cortexLLM.Call` → `:530` `rt.executeActions`), i.e.
generated language *is* the action-selecting authority there. That is exactly what
Finding 1 rejects for SAHOOL, so confining the OM1 pattern to the device boundary is a
measured necessity, not caution. Two further corrections to the description above: OM1 is
Go (not Python) at that revision, and its ROS2 integration is via a Zenoh/CDR bridge — only
Zenoh appears in Go code (`plugins/actions/unitree/go2/autonomy/move.go`); the HAL itself is
assumed to be vendor-provided (`README.md:192-194`).

## Finding 7 — OpenAgentFlow pattern belongs in declarative validation, not authority

OpenAgentFlow's useful idea is a validated workflow/IR that catches invalid state flow before
execution. SAHOOL already has explicit workflow/decision boundaries and CI structural
guards.  The safe adaptation is to make agricultural workflows more declarative only where
it reduces duplicated state-transition logic; an LLM/agent workflow must never replace the
canonical agronomic engines or approval boundary.

## Finding 8 — WGAI pattern should be offline-first, not "no external APIs"

SAHOOL depends legitimately on external observation providers. The useful adaptation is an
external-dependency budget and explicit freshness/quality semantics: critical decisions use
canonical cached/local state only while it remains eligible; stale/missing evidence degrades
or blocks explicitly.  External-provider absence must never be rewritten as a measured zero.

## Immediate code correction made with this review

`config/guardrail_feature_flags.py` contained duplicate definitions of the same core
flags (the initial assignments and a later `globals().get` block).  The values happened to
agree, but the file had multiple textual sources of truth and could silently diverge in a
later edit.  This branch reduces every flag to one definition without changing defaults.

## Implementation order

1. Keep existing engine ownership and candidate boundary; do not introduce another router.
2. Close runtime identity/readiness/metrics blockers before enabling additional AI paths.
3. Wire the guarded recommendation pipeline only behind an explicit production call site,
   with canonical field state and tenant validation proven end-to-end.
4. Preserve RAG/KG as annotations and generated text as non-authoritative advice.
5. Complete the documented decision-service SoR prerequisites before changing ownership.
6. Add device adapters through canonical observations, not direct engine-specific payloads.
7. Certify each new path with lineage, freshness, approval, tenant-isolation and fail-closed
   tests before enabling its feature flag.

## External source references used for the comparison

Every reference is pinned to the exact commit that was read (shallow, read-only clones on
2026-09-16). Line numbers hold at these revisions only; a re-measurement script that fetches
each SHA by hash, detaches it, and asserts the cited evidence lives in
`docs/audits/DECISION_FABRIC_EXTERNAL_SOURCE_VERIFICATION_20260916.md` §8.

- LinkMind: `landingbj/LinkMind` @ `dc40c029d44abdb5056fe91aa4735c839749cbaa` (2026-09-16) —
  configured route expression `lagi-web/src/main/resources/lagi.yml:92`
  (`route: best((landing&qwen),(kimi|chatgpt))`), grammar `:326-333`;
  parser `lagi-core/src/main/java/ai/router/utils/RouteExprParser.java:37-38,83-84`;
  sequential failover `lagi-core/src/main/java/ai/router/FailOverRoute.java:29-46`.
  Failover also exists at backend level (`ai/llm/service/LlmRouteService.java:52-70`) and
  key-pool level (`ai/llm/adapter/impl/ProxyLlmAdapter.java:193-196`) — all provider
  routing, never authority routing.
- OpenAgentFlow: `OpenAgentFlow/OpenAgentFlow` @ `397e57ca0668e97669e850b277ed1878e580e7b4` (2026-08-02) —
  IR `spec/SPEC.md:16`; three-phase validator `spec/SEMANTICS.md:17-23`; graph checks
  `compiler/validator.js:417,480-494,591`. Compile-time structural only: `@min/@max` runtime
  bounds are TODO (`todo.md:10-12`); sole runtime target LangGraph (`validator.js:377-379`).
- OM1: `OpenMind/OM1` @ `84e00a1672d17d012c24ae6b300365594265bd37` (2026-09-15), Go —
  input/action registries `internal/inputs/sensor.go:59`, `internal/actions/action.go:47`;
  HAL is assumed to be vendor-provided (`README.md:192-194`); LLM → executor chain
  `internal/runtime/runtime.go:506 → :530`; Zenoh in code, ROS2 via bridge docs.
- WGAI: `dromara/wgai` @ `dbf8988b9167b09a7724ab49d39a14a3065d2b58` (2026-09-08) —
  offline deployment `README_EN.md:28`; in-JVM ONNX inference
  `wgai-module-system/wgai-system-biz/src/main/java/org/jeecg/modules/tab/AIModel/OnnxModelCacheService.java:3-5`;
  third-party API config `README_EN.md:98` (offline-capable, not offline-only). The
  advertised ChatGPT path is not locatable in Java/YAML at this revision (case-insensitive
  scan: 0 hits) — recorded as unmeasured, not absent.

These projects are architectural references only; no external source code is copied into
SAHOOL by this change.
