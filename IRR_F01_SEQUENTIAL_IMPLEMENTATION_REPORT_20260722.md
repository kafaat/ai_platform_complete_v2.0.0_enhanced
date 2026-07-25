# IRR-FOUNDATION-01 — Sequential implementation report

Implemented on the SHA-256-identified source archive `194d2cc2211f27a2b94cc018ff7a15c333a74b7ce8cf39c36dded5ced071abc3`.

## Completed slices

1. v197 database hardening: project-coherent FKs, exclusive overlap exclusion, immutable capacity evaluations, immutable binding identity/history, terminal-node validation, and a legal reservation transition function with append-only events.
2. Authoritative resolver: target binding → v171 upstream path → governed node policy → fresh eligible v171 capability; caller-supplied resource/capacity/policy is no longer the authoritative entry point.
3. Governed orchestration entry point: intent resolution followed by the existing lock/evaluate/reserve/outbox transaction.
4. Reservation lifecycle/recovery adapter, including expiration of elapsed reserved intervals.
5. Dispatch relay runtime defect fixed: the default HTTP transport now returns `(status_code, payload)` as required by the relay contract.
6. Migration registered in both `migrations/MANIFEST.txt` and `scripts_v9/run_migrations.sql`.

## Validation run

- Python compilation of changed runtime modules: PASS.
- Focused IRR-F01 tests: 23 passed.

## Certification boundary

Live PostgreSQL 16/PostGIS, two-session concurrency, JetStream durability, decision-service fulfillment, and actuator receipt E2E were not available in this execution environment. The package therefore contains the implementation and static/unit proof, but does not claim live production certification.
