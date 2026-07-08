# P0 Ownership Boundary Implementation Report

Implemented against the source tree to stop further `sahool-platform` growth before any extraction work.

## Added

- `docs/architecture/SERVICE_OWNERSHIP_MATRIX.md`
- `docs/architecture/PLATFORM_EXTRACTION_MAP.md`
- `docs/architecture/platform_extraction_map.json`
- `docs/architecture/db_ownership.yml`
- `services/sahool-platform/tests/test_p0_platform_route_ownership_guard.py`
- `services/sahool-platform/tests/test_p0_db_ownership_guard.py`
- `docs/architecture/platform_python_module_baseline.json`
- `services/sahool-platform/tests/test_p0_platform_module_growth_guard.py`

## Baseline

- Platform route budget baseline: `567` routes discovered under `services/sahool-platform/api/**/*.py`.
- DB ownership baseline: `202` tables discovered from migrations/storage SQL.

## Route ownership summary

| Target owner | Routes |
|---|---:|
| `sahool-platform` | 244 |
| `field-management-service` | 138 |
| `weather-service` | 42 |
| `agriai-engine` | 32 |
| `raster-service` | 27 |
| `soil-service` | 18 |
| `erp-bridge` | 17 |
| `learning-service-target` | 14 |
| `knowledge-graph` | 11 |
| `supervisor-agent` | 10 |
| `guardrails-engine` | 7 |
| `rag-retrieval` | 5 |
| `actuator-service` | 2 |

## Enforcement

- Platform Python module budget baseline: `578` non-test modules.
- New platform route without target owner fails CI.
- Platform route count growth above the baseline fails CI.
- New migration table without DB owner fails CI.
- Multiple DB writers are disallowed; writers must be exactly `[owner]`.
