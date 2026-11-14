# Shadow Reconciliation — canonical vs legacy

> Report-only. Findings never block; only report staleness blocks.
> The comparison plan is policy data (`field_authority_policy.json`).

- Capabilities: canonical **81** · legacy **81** · shared **81**
- Findings: **14** (identity 0 · field drift 14)
- Fields compared raw: id, domain, dependencies, maturity, evidence_level, owner, lifecycle
- Fields excluded (no raw normalization yet): title, apis, tests, runtime, evidence, rationale, status, confidence, competitive
- Evidence-maturity debt identities: **45**
- Identity ratchet: **BLOCK**

| Finding | Kind | Field | Canonical | Legacy | Authority |
|---|---|---|---|---|---|
| DEC-004:evidence_level | field_drift | evidence_level | 2 | 3 | canonical_capability_definition |
| DEC-004:maturity | field_drift | maturity | 2 | 3 | canonical_capability_definition |
| DEC-005:evidence_level | field_drift | evidence_level | 2 | 3 | canonical_capability_definition |
| DEC-005:maturity | field_drift | maturity | 2 | 3 | canonical_capability_definition |
| DEC-010:evidence_level | field_drift | evidence_level | 2 | 3 | canonical_capability_definition |
| DEC-010:maturity | field_drift | maturity | 2 | 3 | canonical_capability_definition |
| FM-008:evidence_level | field_drift | evidence_level | 2 | 3 | canonical_capability_definition |
| FM-008:maturity | field_drift | maturity | 2 | 3 | canonical_capability_definition |
| SAT-006:evidence_level | field_drift | evidence_level | 2 | 3 | canonical_capability_definition |
| SAT-006:maturity | field_drift | maturity | 2 | 3 | canonical_capability_definition |
| SAT-009:evidence_level | field_drift | evidence_level | 2 | 3 | canonical_capability_definition |
| SAT-009:maturity | field_drift | maturity | 2 | 3 | canonical_capability_definition |
| SEC-006:evidence_level | field_drift | evidence_level | 2 | 3 | canonical_capability_definition |
| SEC-006:maturity | field_drift | maturity | 2 | 3 | canonical_capability_definition |
