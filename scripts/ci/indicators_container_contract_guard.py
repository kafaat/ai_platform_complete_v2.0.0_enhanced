#!/usr/bin/env python3
"""Guard the indicators-service container contract.

The service is intentionally health-only. Its container must therefore be
truthful and lightweight: no database/queue/cache runtime dependencies, no
Docker liveness check against degraded /readyz, and no compute implementation
that fabricates indicator results.
"""
from __future__ import annotations

from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
SERVICE = ROOT / "services" / "indicators-service"
DOCKERFILE = SERVICE / "Dockerfile"
REQ = SERVICE / "requirements.txt"
MAIN = SERVICE / "main.py"
COMPOSE = ROOT / "docker-compose.v9.yml"

ALLOWED_REQUIREMENTS = {"fastapi", "uvicorn"}
FORBIDDEN_RUNTIME_DEPS = {"asyncpg", "redis", "nats-py", "prometheus-client"}
FORBIDDEN_COMPOSE_ENV = {"DATABASE_URL", "REDIS_URL", "NATS_URL"}
FORBIDDEN_COMPOSE_DEPS = {"sahool-postgres", "sahool-redis", "sahool-nats"}


def fail(message: str) -> None:
    raise SystemExit("✗ " + message)


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def requirement_name(line: str) -> str | None:
    raw = line.strip()
    if not raw or raw.startswith("#"):
        return None
    raw = raw.split(";", 1)[0].strip()
    return re.split(r"[<>=!~\[]", raw, maxsplit=1)[0].strip().lower()


def compose_service_block(service_name: str) -> str:
    text = read(COMPOSE)
    match = re.search(rf"(?m)^  {re.escape(service_name)}:\n", text)
    if not match:
        fail(f"{service_name} missing from docker-compose.v9.yml")
    start = match.start()
    next_match = re.search(r"(?m)^  [a-zA-Z0-9_.-]+:\n", text[match.end():])
    if next_match:
        return text[start:match.end() + next_match.start()]
    return text[start:]


def check_requirements_are_health_only() -> None:
    names = {name for line in read(REQ).splitlines() if (name := requirement_name(line))}
    forbidden = sorted(names & FORBIDDEN_RUNTIME_DEPS)
    if forbidden:
        fail("indicators-service health-only requirements include unused runtime dependencies: " + repr(forbidden))
    unexpected = sorted(names - ALLOWED_REQUIREMENTS)
    if unexpected:
        fail("indicators-service health-only requirements include unexpected dependencies: " + repr(unexpected))


def check_dockerfile_healthcheck_is_liveness() -> None:
    text = read(DOCKERFILE)
    if "http://localhost:8000/healthz" not in text:
        fail("indicators-service Dockerfile HEALTHCHECK must use /healthz for liveness")
    healthcheck_lines = "\n".join(line for line in text.splitlines() if "HEALTHCHECK" in line or "localhost:8000" in line)
    if "/readyz" in healthcheck_lines:
        fail("indicators-service Dockerfile must not use degraded /readyz as Docker liveness")
    for token in ["--timeout 300", "--retries 10", "https://pypi.org/simple"]:
        if token not in text:
            fail(f"indicators-service Dockerfile missing pip/container policy token: {token}")


def check_compose_is_not_blocked_on_unused_infra() -> None:
    block = compose_service_block("sahool-indicators-service")
    leaked_env = sorted(item for item in FORBIDDEN_COMPOSE_ENV if f"{item}:" in block)
    if leaked_env:
        fail("indicators-service compose env exposes unused external dependencies: " + repr(leaked_env))
    leaked_deps = sorted(item for item in FORBIDDEN_COMPOSE_DEPS if f"{item}:" in block)
    if leaked_deps:
        fail("indicators-service health-only compose must not depend_on unused infra: " + repr(leaked_deps))
    if "INDICATORS_RUNTIME_MODE: health-only" not in block:
        fail("indicators-service compose must declare INDICATORS_RUNTIME_MODE=health-only")
    if "http://localhost:8000/healthz" not in block:
        fail("indicators-service compose healthcheck must use /healthz")


def check_main_is_honest_health_only() -> None:
    text = read(MAIN)
    required = [
        '"status": "degraded"',
        '"implemented_runtime": False',
        '"health_only": True',
        'status_code=501',
        '"indicator_compute": False',
    ]
    missing = [item for item in required if item not in text]
    if missing:
        fail("indicators-service main.py missing honest health-only markers: " + repr(missing))
    if '"status": "ready"' in text:
        fail("indicators-service must not report ready while health-only")


def main() -> None:
    check_requirements_are_health_only()
    check_dockerfile_healthcheck_is_liveness()
    check_compose_is_not_blocked_on_unused_infra()
    check_main_is_honest_health_only()
    print("indicators_container_contract_guard_ok")


if __name__ == "__main__":
    main()
