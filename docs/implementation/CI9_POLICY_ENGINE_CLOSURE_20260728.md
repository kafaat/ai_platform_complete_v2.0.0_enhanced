# CI-9 Policy Engine Closure — 2026-07-28

## Judgment

CI-9 is closed in code for the Crop Intelligence boundary. Scientific products remain owned by their canonical engines; policy only maps exported facts to stress and urgency classifications. It does not dispatch actions or bypass Decision Service approval.

## Implementation

- Added `core/crop_intelligence/policy_engine.py`.
- Added six mandatory, versioned policy packs: crop, water, weather, regional, cultivar, and business.
- Added deterministic policy manifest and SHA-256 digest.
- Added explicit rule IDs, policy provenance evidence IDs, matched-rule output, and a non-decision boundary.
- Moved water deficit, spectral water stress, heat stress, frost risk, and urgency escalation out of hard-coded Crop Engine branching.
- Crop Engine now composes facts; Policy Engine evaluates them.
- Recommendation Context consumes the policy assessment instead of re-implementing urgency rules.

## Fail-closed guards

Evaluation fails for:

- missing mandatory pack types;
- duplicate pack types;
- duplicate rule IDs, including duplicates within a single pack;
- unsupported triggers;
- rules with no declared effect;
- missing policy IDs or versions.

## Compatibility

The public `stress_flags`, `urgency`, `urgent_factors`, and general `evidence_ids` contracts remain compatible. Policy lineage is exposed separately through `policy_assessment.evidence_ids` so state evidence and policy evidence do not become conflated.

## Verification

Focused and affected-boundary suite:

```text
93 passed, 0 failed
```

It covers Crop Intelligence phases, canonical input migration, Decision Bridge, decision candidate endpoint, capability closures, irrigation recommendation policy, and irrigation policy.

## Honest remainder

CI-9 does not close:

- CI-10 Knowledge Layer;
- CI-11 Crop Learning Engine;
- live Decision SoR cutover;
- runtime promotion or automatic policy activation.
