#!/usr/bin/env bash
set -euo pipefail

# Optional live Redis integration. Requires Docker Compose availability.
docker compose -f docker-compose.test.yml up -d test-redis
cleanup() { docker compose -f docker-compose.test.yml stop test-redis >/dev/null 2>&1 || true; }
trap cleanup EXIT

for i in $(seq 1 30); do
  if docker compose -f docker-compose.test.yml exec -T test-redis redis-cli -a test_redis_pass PING >/dev/null 2>&1; then
    break
  fi
  sleep 1
  if [ "$i" = "30" ]; then
    echo "Redis did not become ready" >&2
    exit 1
  fi
done

WEATHER_REDIS_INTEGRATION_URL=redis://:test_redis_pass@127.0.0.1:6380/0 \
  pytest -q services/weather-service/tests/test_weather_redis_live_optional.py
