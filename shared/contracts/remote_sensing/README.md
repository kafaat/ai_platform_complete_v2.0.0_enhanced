# SAHOOL Remote Sensing Contracts v1

Ownership-safe, reference-only Pydantic v2 contracts for the RS-1A increment.

This package defines raster asset, canonical observation, evidence, signal anomaly,
diagnosis hypothesis, decision referral, and strongly typed event envelopes. It does
not contain persistence, service calls, raster computation, prescriptions, execution,
or outcome logic.

Key invariants:

- cross-service artifacts are opaque URNs, never object-store paths;
- field IDs use the existing `fld_*` form;
- tenant IDs use the current canonical UUID type;
- asset season context is optional, observation season context is required;
- models are frozen, strict, and reject unknown fields;
- timestamps are timezone-aware UTC values;
- event types are statically bound to payload types;
- signal anomalies cannot contain diagnosis or prescription fields.
