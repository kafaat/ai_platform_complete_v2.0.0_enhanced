# SAHOOL — From Capability Growth to Data → Decision → Outcome Proof

**Decision date:** 2026-11-07. **Scope:** Additive, read-only strategy and evidence-integrity baseline. No production migration, activation, deployment or E2E certification. **Source:** [main@968726c1](https://github.com/kafaat/ai_platform_complete_v2.0.0_enhanced/commit/968726c1b6cd2b11d04047d9028362487fa5e9b5).

## Executive decision | القرار التنفيذي

Change the default question from “what capability can we add?” to **“can we reproduce an independently supported field decision and its verified result, end-to-end?”**. Prioritize one irrigated-field journey before expanding to plant disease, yield, remote sensing classification or a large agricultural model. Retain existing service ownership.

**Non-negotiables:** An observation is not execution. Intent is not a physical acknowledgement. A water ledger is derived, not an independent meter. A forecast is not an outcome. Missing irrigation ≠ measured zero. Hybrid RAG cannot authorize an actuator, mutate coefficients or become ground truth. Unit test PASS ≠ production E2E PASS. Missing receipt = NOT_RUN / UNKNOWN; it does not prove non-execution.

## Canonical journey and independent acceptance criteria

| Stage | Source/owner being reviewed | E3 evidence required |
|---|---|---|
| S01 EO | raster-service STAC/VRT and containment | radiometry, CRS, NoData, grids, scene lineage |
| S02 ET₀ | weather-service numerical owner | FAO-56 inputs, degradation and uncertainty |
| S03 Context | canonical field context and point-in-time guard | field/season/tenant binding; no future leakage |
| S04 Water | derived water_ledger, irrigation_runs | meter vs estimate vs unrecorded/inherited unknown |
| S05 Decision | candidate → approval | replay idempotency, human authorization and fail closed |
| S06 Execution | device ACK / manual confirmation | intent is not execution; no duplicate physical action |
| S07 Outcome | authoritative decision/outcome writer | independent water/soil/yield truth, late outcome replay |
| S08 Calibration | physical model and calibration ledger | ADR-0035 unlock, seasons, SIM-GOLDEN, OOD fallback |
| S09 Learning | dataset candidate, lab, model registry | verified receipts, field-held-out validation, human promotion |

The machine-readable source review is `config/proof/data_decision_outcome_v1.json`. Every stage starts at `e3_state=NOT_RUN`, despite reviewed source code. A source file is never an E3 receipt.

## Canonical authority; no shadow writers

- [SoR inventory](../audits/SOURCE_OF_TRUTH.md): `data_lineage` is a read-only assembler; cached `field_indicators` cannot replace NDVI time series.
- [ET₀ platform boundary](../audits/ET0_PLATFORM_BOUNDARY_20261023.md): `weather-service` owns numerical calculation; degraded ET₀ is advisory.
- [Decision SoR cutover](../architecture/DECISION_SERVICE_SOR_CUTOVER_READINESS.md): `sahool-platform` is interim writer; mirror acknowledgement does not attest authoritative persistence.
- [ADR-0035](../adr/ADR-0035-physics-ai-calibration.md): no new auto-tuner or production calibration before independently proved unlock. ML-quality bridge is DEV and read-only.
- `WATER_LEDGER_AUTO_ENABLED` and `WATER_DEFICIT_DECISION_BRIDGE_ENABLED` remain default-off. No runtime flags or device commands are changed.
- Element84 → VRT containment remains intact until its radiometry, band grid and NoData defects are separately proved corrected.

## Proof maturity — never inflate evidence

- **E1:** Source-reviewed contracts/code, immutable source SHA. No runtime claims.
- **E2:** Recorded deterministic test invocation and output on fixed source SHA. Not staging integration.
- **E3:** Real cross-service staging, PostGIS/Redis/NATS where relevant, tenant boundaries, artifact hashes and independent review.
- **E4:** Crash/retry/concurrency, dedup, offline replay, cutover, failover and rollback on immutable release candidate.
- **E5:** Independent field outcomes, measurement provenance, calibration limits and comparison with a field baseline.

The gate validates schema, repository source references and hashes of submitted artifact bytes. `e3_review_candidate=true` **does not mean acceptance**; it only means all files are present for **external** review. The gate always reports `complete_e3=false`. Sensor authenticity, scientific validity, receipt ownership and actual execution must be proved outside this script.

## First runnable slice

```bash
python3 scripts/ci/data_decision_outcome_proof_gate.py --root .
python3 -m unittest discover -s tests_v9 -p 'test_data_decision_outcome_proof_gate.py'
# Deliberately exits 2 until independent E3 acceptance is supported:
python3 scripts/ci/data_decision_outcome_proof_gate.py --root . --require-e3
```

The script is standard-library-only, read-only, and cannot issue network calls, database writes or actuator requests. Keep private farm records out of repository evidence; commit only redacted review artifacts and hashes.

## Two narrow experiments after G0 baseline

**EX-WATER-01:** Provider → ET₀ → crop Kc/root-zone → water ledger → governed decision → actual execution → independent soil/water measurement. Explicit negative cases: rain missing; Hargreaves fallback; no irrigation record; unknown volume; inherited unknown irrigation; cross-tenant read; duplicate request; lost ACK; late outcome. Never silently substitute unmeasured zero or auto-irrigate from a disputed deficit.

**EX-SCOUT-02:** Validated Sentinel scene → field-week vegetation indices → agronomic context → *advisory* scouting priority → field/photo/lab label → hold-out evaluation. Compare NDVI-only against multi-source on unseen fields/seasons, measuring false alerts, label coverage and missing data. Do not claim confirmed disease from an unverified photo.

## Gate ownership and sequence

| Gate | Owner | Required evidence |
|---|---|---|
| G0 | Source/control owner | SHA pin, PR collision inventory, source-writer mapping |
| G1 | Geo/Weather/Soil | Proven imagery geometry/radiometry, ET₀ and root-zone input quality |
| G2 | Decision/Water | Real PG acceptance for water provenance and fail-closed approval |
| G3 | Runtime/Devices | Actual ACK, no duplicate dispatch, replay and crash recovery |
| G4 | Science/Field | Independent measured outcomes, season and field split, bias assessment |
| G5 | Governance/Human | ADR-0035 unlock, model/calibration review, rollback proof |

For each gate bind source SHA, exact command, environment, case ID, observed times, evidence digest and independent verifier; do not treat a written claim or synthetic fixture as production proof. **No G5 before G1–G4** and ADR-0035.

## Isolation and merge policy

This PR changes only dedicated governance metadata, validator, tests and this document. Do not touch frozen GATE-01 files, migrations, runtime services, frontends, actuators or firmware. Maintain separation from existing PRs (particularly infrastructure/CI changes) and revalidate on the merge base. Absence of a receipt is not non-execution; do not re-dispatch physical actions to “fill a gap.”

**Definition of done for this slice:** valid nine-stage source map, local negative tests passing, E3 explicitly NOT_RUN. Actual cross-service/staging/field acceptance is a **subsequent gate**, not claimed here.
