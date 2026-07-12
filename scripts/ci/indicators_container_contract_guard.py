#!/usr/bin/env python3
"""Guard the indicators-service contract-only container boundary.

The service publishes canonical ownership/catalog contracts and never computes
observed spectral products. It remains lightweight and infrastructure-free.
"""

from __future__ import annotations

import re
from pathlib import Path

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
    next_match = re.search(r"(?m)^  [a-zA-Z0-9_.-]+:\n", text[match.end() :])
    if next_match:
        return text[start : match.end() + next_match.start()]
    return text[start:]


def check_requirements_are_health_only() -> None:
    names = {name for line in read(REQ).splitlines() if (name := requirement_name(line))}
    forbidden = sorted(names & FORBIDDEN_RUNTIME_DEPS)
    if forbidden:
        fail(
            "indicators-service contract-only requirements include unused runtime dependencies: "
            + repr(forbidden)
        )
    unexpected = sorted(names - ALLOWED_REQUIREMENTS)
    if unexpected:
        fail(
            "indicators-service contract-only requirements include unexpected dependencies: "
            + repr(unexpected)
        )


def check_dockerfile_healthcheck_is_liveness() -> None:
    text = read(DOCKERFILE)
    if "http://localhost:8000/healthz" not in text:
        fail("indicators-service Dockerfile HEALTHCHECK must use /healthz for liveness")
    healthcheck_lines = "\n".join(
        line for line in text.splitlines() if "HEALTHCHECK" in line or "localhost:8000" in line
    )
    if "/readyz" in healthcheck_lines:
        fail("indicators-service Dockerfile must not use degraded /readyz as Docker liveness")
    for token in ["--timeout 300", "--retries 10", "https://pypi.org/simple"]:
        if token not in text:
            fail(f"indicators-service Dockerfile missing pip/container policy token: {token}")


def check_compose_is_not_blocked_on_unused_infra() -> None:
    block = compose_service_block("sahool-indicators-service")
    leaked_env = sorted(item for item in FORBIDDEN_COMPOSE_ENV if f"{item}:" in block)
    if leaked_env:
        fail(
            "indicators-service compose env exposes unused external dependencies: "
            + repr(leaked_env)
        )
    leaked_deps = sorted(item for item in FORBIDDEN_COMPOSE_DEPS if f"{item}:" in block)
    if leaked_deps:
        fail(
            "indicators-service contract-only compose must not depend_on unused infra: "
            + repr(leaked_deps)
        )
    if "INDICATORS_RUNTIME_MODE: contract-only" not in block:
        fail("indicators-service compose must declare INDICATORS_RUNTIME_MODE=contract-only")
    if "http://localhost:8000/healthz" not in block:
        fail("indicators-service compose healthcheck must use /healthz")


def check_main_is_honest_contract_only() -> None:
    text = read(MAIN)
    required = [
        '"status": "ready"',
        '"implemented_runtime": True',
        '"runtime_role": "contract-only"',
        '"spectral_compute": False',
        "status_code=409",
        '"indicator_compute": False',
    ]
    missing = [item for item in required if item not in text]
    if missing:
        fail("indicators-service main.py missing contract-only markers: " + repr(missing))
    forbidden = ['"health_only": True', '"implemented_runtime": False', "status_code=501"]
    present = [item for item in forbidden if item in text]
    if present:
        fail("indicators-service retains stale health-only markers: " + repr(present))


def main() -> None:
    check_requirements_are_health_only()
    check_dockerfile_healthcheck_is_liveness()
    check_compose_is_not_blocked_on_unused_infra()
    check_main_is_honest_contract_only()
    print("indicators_container_contract_guard_ok")


if __name__ == "__main__":
    main()
