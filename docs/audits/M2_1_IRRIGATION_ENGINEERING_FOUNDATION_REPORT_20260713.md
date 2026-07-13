# M2.1 Irrigation Engineering Foundation

Implemented the next ratchet after P1.1c canonical water truth.

## Delivered

- `v167_irrigation_engineering_foundation.sql`
- Manufacturer-neutral contracts for projects, sources, wells, pumps, mainlines, machines, controllers, and energy systems.
- Composite tenant-bound foreign keys.
- RLS + FORCE RLS on all eight tables.
- Separate design, commissioned, and live truth envelopes.
- SI units in field names.
- Controller credentials represented only by opaque external references.
- Solar, generator, and LiFePO4 battery primitives without dispatch automation.
- Static CI ratchet and focused contract tests.

## Deliberate boundaries

- No new HTTP routes; platform route budget remains unchanged.
- No control commands or automatic execution.
- No hydraulic solver yet.
- No raw credentials.
- No claim of real-PostgreSQL certification in this environment.

## Next ratchet

M2.2 Canonical Root-Zone Hydraulic Profile, followed by M2.3 Well/Water Source Digital Twin.
