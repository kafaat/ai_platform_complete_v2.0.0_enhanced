# Main review repairs — 2026-09-09

Reviewed base: `7407eae2ba006a4c4c07018988a0f680e176abea` (`main`).
Implementation: `f8086c1ff` on `fix/main-irrigation-guardrails-20260909`.

## Repaired behavior

| Finding | Source | Result and regression evidence |
| --- | --- | --- |
| JSONB strings crash hourly orchestration | `services/sahool-platform/api/irrigation_runtime_orchestrator.py` | Reuses `persisted_canonical_repositories.decode_jsonb` for capability payload, gate snapshot and blocking reasons. Object/list shapes are checked; malformed evidence returns a named blocked response. `services/sahool-platform/tests/test_irrigation_runtime_orchestrator.py` runs both decoded and asyncpg-default string records through the real orchestrator, plus ten malformed cases through HTTP. |
| Ledger Dr promotes client facts to operational candidates | `services/sahool-platform/api/routers/irrigation_mpc.py::irrigation_mpc_plan` | `/plan` remains available as simulation. Both manual and ledger-seeded plans reject submission independently of the bridge flag. `tests_v9/test_lexicographic_mpc_bridge.py` varies TAW and ET0 while holding ledger Dr constant and asserts the emitter is never called. |
| Missing rain becomes verified zero; invalid numbers/dates and fixed elevation enter water truth | `services/sahool-platform/api/canonical_water_state.py` | Requires explicit finite nonnegative rain, ET0 and depletion; validates optional confidence; rejects future ledger dates and stale/discontinuous forecast dates. Uses the provider's local calendar and the field's stored elevation. Missing elevation blocks instead of assuming 2000 m or sea level. `tests_v9/test_canonical_water_state_mpc.py` preserves explicit zero, a below-sea-level elevation and the existing stale-ledger degraded state. |
| Incomplete fertilizer recipe can pass Guardrails | `services/guardrails-engine/contracts.py` | Requires explicit N/P/K doses plus annual nitrogen and accumulated seasonal carbon, using existing numeric validation. `tests_v9/test_guardrails_contract.py` checks HTTP rejection and the engine's recheck after nested-dict mutation. Complete zero doses pass the actual tiers; excessive dose, annual nitrogen or carbon require human review. Existing agronomic thresholds are unchanged. |

## Validation

- Before implementation, the first regression run produced **53 failed, 111 passed, 1 skipped**. Failures reproduced the reviewed defects and related invalid-input cases.
- After implementation, the same suite produced **164 passed, 1 skipped** (7.72 seconds).
- The subsequent water/calendar, hourly-route ownership and canonical-knowledge-to-MPC suite produced **42 passed, 1 skipped** (8.28 seconds).
- `preflight.sh --fast --no-fetch` completed with **0 failures, 0 skipped gates**, including mutation planting for affected registered targets. This is not the default/full test suite.
- Default preflight completed on `bd7bca34b`: **6,610 unit tests passed, 30 skipped, 430 deselected**; **752 repository tests passed, 8 skipped**. The platform suite had 4,305 passes and one failure: its lexical weather-boundary guard matched a provider name in an explanatory comment.
- `73a67e3bd` describes that boundary in terms of `weather-service`. The Python AST of `canonical_water_state.py` is identical before and after this comment-only correction. The entire platform suite was rerun in its CI working directory with the pinned FastAPI version: **4,306 passed**, zero failures (63.16 seconds). The earlier default-preflight log remains a completed run with one subsequently resolved failure; it is not relabeled as a zero-failure run.
- Bandit over `services/ bots/ agents/` reported **0 HIGH-severity issues**. Irrigation ownership, lineage, root-zone, runtime orchestration and image-supply-chain guards passed. The handoff includes regeneration and release-integrity logs for the final documentation refresh.

## Validation repairs discovered while completing the gates

- `655903768` isolates the raster-fallback unit tests from the live indicators adapter. The previous attempt was interrupted when the fixture reached `http://indicators-service:8000`; it is not counted as a completed run. The fixture now supplies a controlled unavailable canonical adapter and asserts it was awaited. Its six tests passed, followed by the remaining unit-test tail (380 passed, 11 skipped, 8 deselected), then the complete unit suite above. Production vegetation code is unchanged.
- `cb0dc6cbd` consumes the existing drawing-schema authorization after the verified merge of [PR #990](https://github.com/kafaat/ai_platform_complete_v2.0.0_enhanced/pull/990). GitHub reported `merged_at=2026-09-09T13:25:56Z` and merge SHA `7407eae2ba006a4c4c07018988a0f680e176abea`; both authorized blob hashes exactly match that merge tree. Leaving the record `ISSUED` was blocking unrelated changes. Only its consumption evidence was updated; the frozen-path policy and authorized bytes are unchanged.

The skipped test is the pre-existing deferred daily canonical-water-to-MPC route wiring test. These repairs preserve its declared limitation; they do not implement the daily recommendation route's soil/weather adapters. The existing hourly recommendation remains the server-owned orchestration path.

## Deployment implications and limits

- Clients of legacy `/plan` using JSON body `submit: true` must use a server-owned recommendation route for operational proposals. Ledger Dr alone is insufficient authority for client-supplied TAW/weather.
- Operational water resolution requires a stored `fields.elevation_m`, dated weather covering the requested local days and explicit precipitation observations. Missing inputs now produce blocked responses and must be supplied by their actual source.
- Fertilizer callers must supply the actual N/P/K quantities and cumulative-use evidence; inserting fabricated zeroes is not a repair.
- Tests use controlled database/weather/HIL doubles around real production functions. No new live PostgreSQL, external weather, pump execution or production certification is claimed. Recommendation-only and human-approval boundaries remain in force.

## Delivery status

The branch is `fix/main-irrigation-guardrails-20260909`. A non-writing Git push check failed with `could not read Username for 'https://github.com': terminal prompts disabled`; no remote branch or pull request was created. The Git-bundle handoff preserves the original commits for import and publication from an authenticated clone and includes a prepared PR body with a computed capability-impact declaration. Live GitHub CI and review remain separate from the local verification above.
