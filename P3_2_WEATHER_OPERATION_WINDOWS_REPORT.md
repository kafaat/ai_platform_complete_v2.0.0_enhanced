# P3.2 Weather Operation Windows — Implementation Report

## Scope

Implemented weather-derived agricultural operation windows inside `weather-service`.

## Added/changed

- `services/weather-service/operations.py`
  - Suitability rules for:
    - spraying
    - harvesting
    - sowing
    - fertilizing
    - irrigation
  - Score, suitability, limiting factors, and safe/unsafe output.
- `services/weather-service/main.py`
  - `GET /v1/weather/operation-window`
  - `GET /v1/weather/operation-plan`
  - `GET /v1/weather/operation-tile-data/{z}/{x}/{y}`

## Truthfulness rule

Operation scores are derived from explicit weather samples and remain explainable through `limiting_factors`; no recommendation is silently promoted without weather evidence.
