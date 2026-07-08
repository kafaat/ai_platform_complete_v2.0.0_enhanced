# P5 Service Registry Hardening

Implemented as a service-domain ownership contract.

## Added

- `docs/architecture/SERVICE_REGISTRY_HARDENING_CONTRACT.json`
- `services/sahool-platform/tests/test_p5_service_registry_hardening_guard.py`

## Declared single-owner domains

- Raster → `raster-service`
- Weather → `weather-service`
- Decision / Outcome / Learning → `decision-service`
- Fields → `field-management-service`
- Segmentation → `field-segmentation-service`
- Advisory → `agriai-engine`
- Tool orchestration → `supervisor-agent`

## Duplicate/stub services documented

- `indicators-service`
- `raster-tiler-service`
- `ai_agronomist`
- `supervisor-agent`
