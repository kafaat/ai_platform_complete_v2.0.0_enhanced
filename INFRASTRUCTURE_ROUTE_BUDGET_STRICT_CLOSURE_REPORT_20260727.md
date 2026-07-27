# SAHOOL Infrastructure Route Budget — Strict Closure

Date: 2026-07-27

## Decision

Choose: **Exclude infra from budget**.

`GET /runtime-identity` is retained as an infrastructure/provenance endpoint. It is tracked in the raw platform route inventory and excluded from the platform domain-route budget only through the canonical exact method-and-normalized-path allowlist.

## Canonical implementation

- `scripts/ci/platform_route_classification.py`
- AST extraction records method, literal path, source file, line, and function.
- Non-literal route paths fail closed.
- Every allowlist entry must exist in the actual sahool-platform inventory.
- Case and URL encoding are not normalized; only structural slashes are normalized.

## Verified inventory

- Raw routes: 630
- Infrastructure routes: 4
- Domain-budget routes: 626
- Domain maximum: 629

Actual infrastructure routes:

- `GET /healthz`
- `GET /readyz`
- `GET /metrics`
- `GET /runtime-identity`

## Ratchet guarantees

- The raw count remains visible.
- The domain maximum remains 629.
- `POST /runtime-identity` remains counted.
- `GET /fields/runtime-identity` remains counted.
- `GET /runtime-identity/export` remains counted.
- Unused allowlist entries fail.
- Dynamic/non-literal route declarations fail.
