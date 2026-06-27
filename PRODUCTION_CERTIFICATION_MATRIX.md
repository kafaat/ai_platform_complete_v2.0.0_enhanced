# SAHOOL Production Certification Matrix

This matrix separates what is proven by static/contract checks from what must be proven by live runtime and soak validation.

> **Last updated:** 2026-06-27 · **commit:** `main @ e230ecb` · full reproducible evidence
> and the Go/No-Go decision: [`FINAL_PRODUCTION_READINESS_REPORT.md`](FINAL_PRODUCTION_READINESS_REPORT.md).
>
> **Static/contract evidence (this cycle, reproducible):** migration manifest 130/0 ·
> RLS write-policy gate PASS (+ Phase-23 `v123` qual-preserving hardening) · inspector
> exit=0 (RLS 103 tables / 0 missing, **router wiring 146/0**, manifest 130/130) · platform
> unit tests **2928 passed / 0 failed** · app boot 493 routes · release checksums **2489 verified**.
>
> **Live runtime / soak columns remain PENDING by design** — they require a staging stack
> and elapsed soak time (owner: Ops/SRE). Integration/PostGIS is green via CI on every merge
> (#488–#501) but not re-run on a developer host.

| Capability | Static gates | Contract tests | Local runtime | Staging runtime | 7-day soak | 14-day soak | Status |
|---|---:|---:|---:|---:|---:|---:|---|
| Security / RLS roles | PASS | PASS | PENDING | PENDING | PENDING | PENDING | Ready for runtime validation |
| CI/CD / Supply chain | PASS | PASS | N/A | PENDING | N/A | N/A | Release-gated |
| Migrations manifest | PASS | PASS | PENDING | PENDING | PENDING | PENDING | Unified, needs DB execution proof |
| Observability assets | PASS | PASS | PENDING | PENDING | PENDING | PENDING | Dashboards/rules ready |
| Field / GIS / imagery path | PASS | PASS | PENDING | PENDING | PENDING | PENDING | Needs live raster/CDSE proof |
| CanonicalFieldState truth path | PASS | PASS | PENDING | PENDING | PENDING | PENDING | Audited as source of truth |
| Phase 9 autonomy governance | PASS | PASS | PENDING | PENDING | PENDING | PENDING | Safe by default |
| Phase 10 feature/model runtime | PASS | PASS | PENDING | PENDING | PENDING | PENDING | Foundation ready, serving proof pending |
| Phase 11 federated agents | PASS | PASS | PENDING | PENDING | PENDING | PENDING | Proposal-only governed |
| Phase 12 marketplace sandbox | PASS | PASS | PENDING | PENDING | PENDING | PENDING | Sandbox contracts ready, executor proof pending |
| Runtime workers side effects | PASS | PASS | PENDING | PENDING | PENDING | PENDING | Fail-closed, external ACK proof pending |
| Load / chaos / recovery | PASS | PASS | PENDING | PENDING | PENDING | PENDING | Harness ready, not certified |
| Long soak certification | PASS | PASS | PENDING | PENDING | PENDING | PENDING | Not yet production certified |

## Certification rule

The platform must not be described as `Zero Gaps` or `Production Certified` until all critical rows pass at least staging runtime and the 7-day soak. A stricter field deployment certification requires the 14-day soak.
