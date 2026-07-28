# CI-10 Knowledge Layer Closure — 2026-07-28

## Verdict

CI-10 is closed in code for governed crop knowledge composition.

## Implemented

- `crop_knowledge_snapshot.v1` deterministic product.
- Versioned crop-card and variety-card provenance.
- Parent-crop enforcement for varieties.
- Governed regional, field and community annotations.
- Fail-closed rejection of duplicate IDs, unsupported sources and unverified regional/field annotations.
- Unified epistemic confidence ceiling using `core.knowledge_levels`.
- Community knowledge may modify context but never override governing physics.
- Crop phenology maturity thresholds now resolve through the governed knowledge layer.
- Knowledge provenance is separated from weather/state evidence.

## Boundary

The knowledge layer is annotation and interpretation input. It is not a decision, does not promote policies, and does not learn automatically. Those concerns remain with CI-9, Decision Service and CI-11 respectively.

## Verification

- 75 focused integration tests passed.
- Python compilation passed for all modified modules.
