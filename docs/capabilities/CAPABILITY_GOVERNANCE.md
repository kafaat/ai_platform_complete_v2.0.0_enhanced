# SAHOOL Capability Governance

`capabilities/registry/capabilities.json` is the canonical capability source of truth.

## Evidence levels

- E0 idea
- E1 design/documentation
- E2 implementation
- E3 tests
- E4 runtime evidence
- E5 production evidence and measured outcome

## Non-negotiable rules

1. Capability IDs are stable and unique.
2. Dependencies must reference existing capabilities and remain acyclic.
3. Maturity 4 requires at least one behavioral test path.
4. Production certification requires maturity 5, evidence level 5, metrics, traces, receipts and audit events.
5. Repository evidence paths must exist.
6. A blank competitor field means unverified, not absent.

## Commands

```bash
python scripts/ci/capability_registry_guard.py --check
python scripts/ci/capability_registry_guard.py --generate
python scripts/ci/capability_impact.py services/weather-service/main.py --json
python scripts/ci/capability_release_report.py before.json after.json
```

Generated outputs live under `capabilities/generated/` and must not be used as the source of truth.

## Deterministic repository linkage

The registry is linked conservatively from repository inventories with:

```bash
python scripts/ci/capability_linker.py --apply --threshold 2
python scripts/ci/capability_linker.py --check --threshold 2
```

`--check` is the CI ratchet. It fails when the canonical registry differs from the deterministic linker output. The linker never raises maturity or production certification; it only records traceability surfaces and explicit dependency edges.

Generated linkage evidence:

- `capabilities/generated/capability_link_candidates.csv`
- `capabilities/generated/capability_traceability.csv`
- `capabilities/generated/capability_traceability_summary.json`
- `capabilities/generated/CAPABILITY_TRACEABILITY_REPORT.md`

A blank UI/mobile surface is not automatically a defect because some capabilities are backend-only. Runtime certification still requires metrics, traces, receipts and audit evidence.
