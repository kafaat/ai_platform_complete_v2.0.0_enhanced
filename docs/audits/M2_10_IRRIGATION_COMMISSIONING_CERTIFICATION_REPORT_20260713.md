# M2.10 Irrigation Commissioning & Certification

## Scope
Implemented a fail-closed commissioning and certification boundary that binds witnessed field evidence to one immutable irrigation capability graph snapshot. No command transport or actuator dispatch was added.

## Added
- `services/sahool-platform/api/irrigation_commissioning_certification.py`
- `migrations/v176_irrigation_commissioning_certification.sql`
- `tests_v9/test_irrigation_commissioning_certification.py`
- `scripts/ci/irrigation_commissioning_m2_10_guard.py`

## Required evidence
- installation identity
- pump flow test
- terminal pressure test
- controller handshake
- safety interlock test
- energy system test
- signed acceptance

All evidence is identity-bound, SHA-256 bound, witnessed/captured, status-controlled, and age checked.

## Safety gate
Required checks:
- emergency stop
- dry-run protection
- overpressure protection
- loss-of-communication safe state
- manual override

## Acceptance checks
- measured flow must meet the configured fraction of design flow
- measured terminal pressure must meet the configured fraction of design pressure
- measured power must remain within the certified limit
- controller handshake digest must be present
- certification must be signed, independently reviewed, current, and not revoked/superseded

## Executability gate
`apply_commissioning_executability_gate()` requires exact identity and digest binding between the certificate and the canonical irrigation capability graph. Any mismatch, expired certificate, blocked graph, stale/missing evidence, or failed safety check returns `execution_allowed=false`.

## Persistence
Migration v176 adds:
- `irrigation_commissioning_evidence`
- `irrigation_commissioning_certifications`
- `irrigation_executability_gates`

All tables have tenant-bound keys, `ENABLE ROW LEVEL SECURITY`, `FORCE ROW LEVEL SECURITY`, and `USING/WITH CHECK` tenant policies.

## Verification
- M2.10 focused tests: 8 passed
- Combined irrigation truth/engineering/MPC regression: 95 passed
- Deprecation warnings treated as errors: 0 warnings
- M2.1 through M2.10 static guards: passed
- Python compilation: passed

## Uncertified runtime boundaries
Not claimed in this environment:
- migration execution on live PostgreSQL
- cross-tenant RLS runtime proof
- real field signatures or evidence upload storage
- live pump/pressure/power commissioning instruments
- controller/PLC safety interlock field test
- command dispatch or actuator execution
