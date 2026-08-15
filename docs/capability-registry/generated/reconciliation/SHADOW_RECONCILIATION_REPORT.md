# Shadow Reconciliation — canonical vs legacy

> Report-only. Findings never block; only report staleness blocks.
> The comparison plan is policy data (`field_authority_policy.json`).

- Capabilities: canonical **81** · legacy **81** · shared **81**
- Findings: **3** (identity 0 · field drift 3)
- Fields compared raw: id, domain, dependencies, maturity, evidence_level, owner
- Fields excluded (no raw normalization yet): title, apis, tests, runtime, evidence, rationale, status
- Evidence-maturity debt identities: **53**
- Identity ratchet: **PASS**

| Finding | Kind | Field | Canonical | Legacy | Authority |
|---|---|---|---|---|---|
| INT-004:evidence_level | field_drift | evidence_level | 3 | 1 | canonical_capability_definition |
| INT-004:maturity | field_drift | maturity | 3 | 1 | canonical_capability_definition |
| INT-004:owner | field_drift | owner | "sahool-platform" | "UNASSIGNED" | canonical_capability_definition |
