# Service consumer and route audit — 2026-07-23

## Verdict

The generated contract reports evidence for all 32 inventory entries, but that
does not prove 32 production consumers. After excluding self-references,
documentation, Compose-only references and tests:

- 28 runtime services have a demonstrable UI, gateway, platform, worker or
  service consumer.
- `qdrant-seed` is a one-shot job and correctly has a job contract rather than
  a downstream consumer.
- The three previously unresolved entries now have an explicit disposition:
  the Remote Sensing Workspace BFF has a real gateway/UI consumer; GIS is
  classified as a tested batch job/tool rather than a live service; AgriAI is
  an experimental model runtime guarded by scientific activation contracts,
  not falsely presented as a production-certified MCP consumer.

## Unconsumed or misclassified entries

| Entry | Finding | Required disposition |
| --- | --- | --- |
| `agriai-engine` | Its endpoints are REST and it is not an MCP server. PCSE remains uncalibrated pending SIM-GOLDEN. | Removed the dead `MCP_AGRIAI_URL` registration and classified the runtime as experimental with fail-closed activation evidence. |
| `remote-sensing-workspace-bff` | Aggregates indicators, anomalies, decisions and outcomes for a field/season. | Added an authenticated nginx route and a real `FieldWorkspaceImageryPanel` consumer that requires `season_id` and exposes partial/degraded state. |
| `gis-workflow-service` | CLI/batch publication renderer with no HTTP endpoint by design. | Reclassified as `batch-job-tool` and tied its contract to the tested `run_bundle` workflow/CI job. |

`scout-ingest-service` is not orphaned: `sahool-platform` consumes it through
the guarded `service_proxy` field-forms channel. Worker-only entries such as
`weather-polygon-worker`, `weather-signal-engine` and
`model-registry-adapter` have job/event consumers and are not expected to
expose user HTTP routes.

## Route review

- Static inventory: 1,094 declarations across 26 HTTP-bearing services.
- Six inventory entries correctly have no decorated HTTP routes because they
  are workers/jobs/tools.
- Live `sahool-platform` OpenAPI: 584 paths and 622 operations.
- Duplicate live `(method, path)` pairs: zero.
- The seven apparent static duplicates are not live conflicts:
  five are identical MCP paths in separate MCP processes; two are phase-local
  paths with different router prefixes.
- User-facing coverage after correction: 463 core endpoints; reverse coverage
  passes with 421 discovered core routes plus 50 explicit waivers.
- NATS publisher/consumer coverage tests pass; the known no-consumer subject is
  explicitly governed by its event-contract waiver.

## Corrections applied

1. Classified historical-weather and ERP reconciliation endpoints as internal
   machine/service contracts.
2. Classified Farmer Book endpoints as farmer-facing and added all five paths
   to the mandatory UI contract.
3. Wired the previously unused Farmer Book balances endpoint into
   `SimpleFarmBookPage`.
4. Updated the service-totality test to derive its count from the generated
   inventory instead of the stale literal `29`.
5. Updated the router registration guard for FastAPI 0.136 lazy
   `_IncludedRouter` wrappers. This removed the false report that all 165
   platform router modules were orphaned.
6. Added `/api/remote-sensing-workspace/` to production and frontend nginx,
   with production tenant derivation from the verified JWT identity.
7. Added a typed frontend BFF client and mounted its overview in the imagery
   workspace using the active `field_id + season_id`.
8. Removed the nonexistent AgriAI MCP path from the unified supervisor
   configuration; production model activation remains blocked until live
   scientific certification.

## Verification

- Previous consumer/route/NATS contract suite: 27 passed.
- Consumer-closure, BFF, service-contract and v9 regression suite: 16 passed.
- Endpoint UI, residual-route, NATS coverage and CI-wiring suite: 23 passed.
- Frontend TypeScript check: passed.
- Service-feature contracts: 32/32 passed.
- nginx/Compose DNS: 15 upstreams passed.
- Service-port, runtime-contract and v9-feature-transfer gates: passed.
- Endpoint UI forward and reverse gates: passed.
- Live OpenAPI duplicate check: zero duplicates.

This is source-level certification. It does not prove deployed traffic,
credentials, provider delivery, PCSE calibration or production request volume.
