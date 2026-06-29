# GIS Phase 12 — Marketplace + Ecosystem + Developer Platform

## Implemented

- Plugin manifest parser and validator.
- Marketplace app registration lifecycle.
- Tenant-scoped app installation with declared permission enforcement.
- Plugin sandbox policy with fail-closed handling for sensitive scopes.
- Webhook subscription and HMAC delivery planning.
- Connector descriptor framework for ERP/equipment/weather/satellite/IoT/payment integrations.
- Public SDK manifest for Python/TypeScript/Flutter.
- GraphQL facade schema contract.
- Usage metering and quota enforcement.
- Developer portal index and SDK stubs.
- FastAPI facade endpoints.
- Migration v105 for marketplace, installations, webhooks, connectors, and usage records.

## Design Principle

Phase 12 does not allow third-party plugins to bypass SAHOOL's decision safety model. Sensitive permissions such as `actuator.write`, `autonomy.dispatch`, `model.promote`, and `tenant.admin` require elevated review and human approval paths before production activation.

## Verification

- Pure contract tests under `shared/test_marketplace_ecosystem_phase12.py`.
- API facade tests under `services/sahool-platform/tests/test_phase12_marketplace_ecosystem_api.py`.
- `py_compile` completed for new Python files.
