# SAHOOL Capability Registry Model v1.0

This directory is the stable, service-independent capability source of truth. A capability represents a durable business ability; services, routers, user interfaces, mobile clients, engines, tests, and runtime evidence are implementation links that may change without changing the capability identity.

## Hierarchy

`Capability → Domain → Business Workflow → Backend → Frontend → Mobile → Decision Engine → Evidence`

## Identity

Capability IDs are immutable. Renaming or moving a service must not change the capability ID. IDs use the domain prefix declared in `capability_index.yaml` and a three-digit sequence. Historical IDs with the `INT` prefix remain valid only where explicitly listed in `accepted_prefixes`; they are preserved to maintain immutable references and must not be reused for new capabilities.

## Maturity

| Level | Meaning |
|---:|---|
| 0 | Missing |
| 1 | Informational |
| 2 | Analytical |
| 3 | Operational |
| 4 | Closed Workflow |
| 5 | Closed Loop |

Maturity is not production certification. Runtime verification and production certification remain separate, evidence-gated properties.

## Evidence precedence

Repository evidence is ordered from weakest to strongest: documentation, implementation link, API, tests, runtime evidence, production evidence. Missing evidence is represented explicitly; it is never inferred from marketing or naming.

## Governance

All edits must pass `scripts/ci/capability_registry_v1.py --check`. Domain files are canonical. Generated merged outputs are derived artifacts and must not be edited manually. Competitor scores marked `unverified_external_benchmark` are placeholders carried from previous inventory and are not accepted benchmark evidence.
