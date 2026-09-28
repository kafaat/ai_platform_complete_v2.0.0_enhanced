#!/usr/bin/env python3
"""Guard that v9 keeps the runtime features promoted from unified/light.

The unified/light compose variants are being frozen. Any feature that only existed
there but is real code must remain present in docker-compose.v9.yml and nginx.v9.conf.
This guard is intentionally static so it can run without Docker.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COMPOSE = ROOT / "docker-compose.v9.yml"
NGINX = ROOT / "nginx" / "nginx.v9.conf"

compose = COMPOSE.read_text(encoding="utf-8")
nginx = NGINX.read_text(encoding="utf-8")

errors: list[str] = []


def require_text(label: str, haystack: str, needle: str) -> None:
    if needle not in haystack:
        errors.append(f"missing {label}: {needle}")


def require_service(name: str) -> None:
    if not re.search(rf"^  {re.escape(name)}:\s*$", compose, flags=re.M):
        errors.append(f"docker-compose.v9.yml missing service {name}")


# Services promoted into v9 runtime.
for svc in ["sahool-video-processor", "sahool-agriai-engine", "sahool-tts-service"]:
    require_service(svc)
    # nginx must wait for these services, otherwise v9 can start with routes pointing at unavailable upstreams.
    require_text("nginx depends_on", compose, f"      {svc}:\n        condition: service_healthy")

# Correct, non-drifting internal dependencies.
require_text("video edge URL", compose, "EDGE_INFERENCE_URL: http://sahool-edge:8100")
require_text("agriai edge URL", compose, "EDGE_INFERENCE_URL: http://sahool-edge:8100")
require_text("video MQTT URL", compose, "MQTT_BROKER_URL: mqtt://sahool-fastbee:1883")
require_text(
    "video Redis URL", compose, "REDIS_URL: redis://:${REDIS_PASSWORD}@sahool-redis:6379/3"
)
require_text("tts Redis URL", compose, "REDIS_URL: redis://:${REDIS_PASSWORD}@sahool-redis:6379/2")

# Nginx exposure/forwarding.
require_text("v9 nginx image supports upstream resolve", compose, "image: nginx:1.27.5-alpine")
require_text("v9 nginx Docker resolver", nginx, "resolver 127.0.0.11 valid=10s ipv6=off;")
for upstream in [
    "server sahool-tts-service:8000 resolve;",
    "server sahool-video-processor:8000 resolve;",
    "server sahool-agriai-engine:8000 resolve;",
]:
    require_text("v9 nginx dynamic upstream", nginx, upstream)

for loc in ["location /tts/", "location /api/video/", "location /api/agriai/"]:
    require_text("v9 nginx location", nginx, loc)

agriai_block = nginx.split("location /api/agriai/", 1)[1].split("location /api/", 1)[0]
require_text(
    "agriai service-token injection",
    agriai_block,
    'proxy_set_header X-Agent-Token "${SAHOOL_AGENT_TOKEN}";',
)

guardrails_block = nginx.split("location /api/guardrails/", 1)[1].split(
    "location /api/rag/", 1
)[0]
require_text(
    "guardrails caller-compatible proxy",
    guardrails_block,
    "proxy_pass http://guardrails_backend/;",
)
if "proxy_set_header X-Agent-Token" in guardrails_block:
    errors.append("public guardrails location must not inject the service token")

# TTS must no longer be a fake 503 feature.
tts_block = (
    nginx.split("location /tts/", 1)[1].split("location", 1)[0] if "location /tts/" in nginx else ""
)
if "return 503" in tts_block:
    errors.append("/tts/ still returns 503 instead of proxying to sahool-tts-service")
require_text("tts proxy pass", tts_block, "proxy_pass http://tts_backend")

# Preserve screen completeness fix discovered during UI/MapHub audit.
for domain in ["server.arcgisonline.com", "basemaps.cartocdn.com", "tile.openstreetmap.org"]:
    require_text("map CSP allowlist", nginx, domain)

if errors:
    print("v9-feature-transfer-gate: FAIL")
    for e in errors:
        print(f" - {e}")
    raise SystemExit(1)

print("v9-feature-transfer-gate: PASS")
