#!/usr/bin/env python3
"""Guard vegetation-analysis-service container/runtime contract.

The service is a lightweight vegetation estimate + raster pass-through facade.
It must ship the P1 runtime module, keep Docker liveness on /healthz, expose a
truthful /readyz schema, and avoid hard startup coupling to NATS because publish
is best-effort/fail-soft inside the runtime.
"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SERVICE_DIR = ROOT / "services/vegetation-analysis-service"
DOCKERFILE = SERVICE_DIR / "Dockerfile"
REQ = SERVICE_DIR / "requirements.txt"
HEALTH = SERVICE_DIR / "routers/health.py"
COMPOSE = ROOT / "docker-compose.v9.yml"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _compose_service_block(service_name: str) -> str:
    lines = _text(COMPOSE).splitlines()
    marker = f"  {service_name}:"
    start = next((i for i, line in enumerate(lines) if line == marker), None)
    if start is None:
        raise SystemExit(f"missing compose service: {service_name}")
    end = len(lines)
    for i in range(start + 1, len(lines)):
        if lines[i].startswith("  ") and not lines[i].startswith("    ") and lines[i].endswith(":"):
            end = i
            break
    return "\n".join(lines[start:end])


def _return_dict_for_handler(path: Path, fn_name: str) -> set[str]:
    tree = ast.parse(_text(path), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == fn_name:
            for child in ast.walk(node):
                if isinstance(child, ast.Return) and isinstance(child.value, ast.Dict):
                    keys = set()
                    for key in child.value.keys:
                        if isinstance(key, ast.Constant) and isinstance(key.value, str):
                            keys.add(key.value)
                    return keys
    raise SystemExit(f"handler {fn_name} not found or does not return a literal dict")


def main() -> int:
    dockerfile = _text(DOCKERFILE)
    if "COPY services/vegetation-analysis-service/vegetation_runtime.py /app/vegetation_runtime.py" not in dockerfile:
        raise SystemExit("vegetation Dockerfile does not copy vegetation_runtime.py")
    if "http://localhost:8000/healthz" not in dockerfile or "/readyz" in dockerfile:
        raise SystemExit("vegetation Docker HEALTHCHECK must use /healthz, not /readyz")
    if "gcc" in dockerfile or "libpq-dev" in dockerfile:
        raise SystemExit("vegetation Dockerfile regained unnecessary build/DB packages")

    req = _text(REQ)
    if "PyJWT==2.13.0#" in req:
        raise SystemExit("vegetation requirements has malformed inline PyJWT comment")
    for forbidden in ("asyncpg", "psycopg", "redis"):
        if forbidden in req:
            raise SystemExit(f"vegetation requirements regained unused {forbidden!r} dependency")

    health_keys = _return_dict_for_handler(HEALTH, "healthz")
    ready_keys = _return_dict_for_handler(HEALTH, "readyz")
    if not {"status", "service"} <= health_keys:
        raise SystemExit("vegetation /healthz must return status + service")
    if not {"status", "service", "ready", "implemented_runtime", "dependencies"} <= ready_keys:
        raise SystemExit("vegetation /readyz schema missing required truth keys")

    block = _compose_service_block("sahool-vegetation-analysis")
    if "depends_on:" in block and "sahool-nats" in block:
        raise SystemExit("vegetation compose must not hard-block startup on NATS; publish is best-effort")
    if "VEGETATION_NATS_PUBLISH_MODE" not in block:
        raise SystemExit("vegetation compose should document best-effort NATS publish mode")

    print("vegetation_container_contract_guard_ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
