# Weather Redis Integration

`weather-service` uses Redis when `WEATHER_REDIS_URL` or `REDIS_URL` is configured.
If Redis is unavailable, the service falls back to memory cache and reports the backend in
`/v1/weather/tile-cache/stats`.

Configuration:

```bash
WEATHER_REDIS_URL=redis://redis:6379/0
WEATHER_CACHE_TTL_S=600
WEATHER_CACHE_STALE_TTL_S=3600
```

Local optional integration test:

```bash
WEATHER_REDIS_INTEGRATION_URL=redis://localhost:6379/0 pytest -q services/weather-service/tests/test_weather_redis_live_optional.py
```

CI helper:

```bash
scripts/ci/run_weather_redis_integration.sh
```
