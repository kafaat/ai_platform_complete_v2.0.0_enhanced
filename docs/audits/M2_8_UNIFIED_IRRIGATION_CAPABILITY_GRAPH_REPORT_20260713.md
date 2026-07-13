# M2.8 Unified Irrigation Capability Graph — Completion Report

Date: 2026-07-13

## Scope

Implemented a deterministic, fail-closed capability graph that composes the governed irrigation engineering chain:

`Well -> Hydraulic Network -> Irrigation Machine -> Sprinkler/Runoff -> Energy -> Controller`

The graph is recommendation-only. It does not dispatch commands or mutate source capabilities.

## Added files

- `services/sahool-platform/api/canonical_irrigation_capability_graph.py`
- `migrations/v174_unified_irrigation_capability_graph.sql`
- `scripts/ci/irrigation_capability_graph_m2_8_guard.py`
- `tests_v9/test_canonical_irrigation_capability_graph.py`

## Implemented behavior

- Requires all six links to be `verified`, operationally eligible, and bound to a full SHA-256 digest.
- Detects cross-link identity mismatch between well, hydraulic target, machine, sprinkler package, and controller.
- Applies the weakest-link rule.
- Derives maximum deliverable flow from the minimum governed source/hydraulic/machine flow.
- Constrains event depth by both machine capacity and runoff-safe application depth.
- Combines hydraulic electrical power with hourly energy envelopes.
- Requires controller identity, certification, connection, fresh telemetry, and minimum capabilities:
  - `read_status`
  - `read_position`
  - `start_stop`
- Produces hourly feasible operating windows with energy cost and renewable fraction.
- Emits a complete capability digest covering all upstream link digests and graph results.
- Exposes only verified graph constraints through `irrigation_capability_graph_to_mpc_constraints()`.

## Persistence model

Migration `v174` adds:

- `canonical_irrigation_capability_graphs`
- `irrigation_capability_graph_nodes`
- `irrigation_capability_graph_edges`

All tables include tenant ownership, composite tenant-bound foreign keys, `ENABLE ROW LEVEL SECURITY`, `FORCE ROW LEVEL SECURITY`, and `USING`/`WITH CHECK` tenant policies.

## Verification

Focused M2.8 tests:

- 7 passed
- 0 failed

Combined irrigation truth, engineering, and MPC regression group:

- 84 passed
- 0 failed
- 14 existing FastAPI `on_event` deprecation warnings

Repository guards:

- M2.1 through M2.8: PASS
- Python compilation: PASS

## Explicit certification limits

Not certified in this environment:

- Real PostgreSQL application of migration v174.
- Live cross-tenant RLS denial test.
- Persistence/reload parity of graph snapshots.
- Live controller telemetry freshness and handshake.
- Operational-route assembly of all six source capabilities.
- End-to-end consumption by the production MPC recommendation route.
- Dispatch or physical execution.

## Next phase

M2.9 — Controller and Edge Adapter Framework:

- normalized controller identity and capability handshake;
- read-only telemetry adapters first;
- MQTT, Modbus TCP/RTU, HTTP/vendor API adapter contracts;
- freshness, sequence, receipt, and replay protection;
- no direct control until commissioning and authorization gates pass.
