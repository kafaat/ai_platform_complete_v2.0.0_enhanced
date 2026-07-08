# P6 Gateway Split Contract

Implemented as an architectural routing contract.

## Added

- `docs/architecture/GATEWAY_SPLIT_CONTRACT.md`
- `services/sahool-platform/tests/test_p6_gateway_split_contract_guard.py`

## Target routing

- `frontend → gateway → raster-service`
- `frontend → gateway → weather-service`
- `frontend → gateway → decision-service`
- `frontend → gateway → sahool-platform` only for BFF/orchestration/legacy compatibility.

## Guard

The guard verifies that the gateway split contract exists and prevents new raster/weather/decision routes from being routed back into `sahool-platform` without explicit legacy/BFF designation.
