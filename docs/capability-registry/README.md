# Capability Registry

This directory is the stable, service-independent capability source of truth.

## Canonical sources

- `capability_index.yaml`: domains, prefixes, maturity model, and controlled vocabularies.
- `domains/*.yaml`: canonical capability cards.
- `schema/capability-card.schema.json`: machine-readable capability-card contract.

## Derived governance layers

- `generated/`: deterministic merged registry and graph.
- `generated/mapping/`: conservative repository-to-capability static evidence mapping.
- `generated/evidence/`: fail-closed static maturity baseline; not runtime proof.
- `benchmark/`: canonical competitor evidence, scoring rubric, and approved investment-source records.
- `generated/benchmark/`: provisional parity, investment matrix, and domain heat map.

## Commands

```bash
python scripts/ci/capability_registry_v1.py --generate
python scripts/ci/capability_mapping_engine.py --generate
python scripts/ci/capability_evidence_maturity_engine.py --generate
python scripts/ci/capability_parity_investment_engine.py --generate

python scripts/ci/capability_registry_v1.py --check
python scripts/ci/capability_mapping_engine.py --check
python scripts/ci/capability_evidence_maturity_engine.py --check
python scripts/ci/capability_parity_investment_engine.py --check
```

## Evidence boundary

Generated files are outputs, never independent evidence. Official competitor pages prove cited product claims, not numeric maturity scores. Only direct canonical evidence may affect parity. Runtime verification and production certification remain separate and fail closed.
