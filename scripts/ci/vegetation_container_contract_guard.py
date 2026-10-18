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


def missing_local_imports(dockerfile: str, service_dir: Path = SERVICE_DIR) -> dict[str, list[str]]:
    """Service-local modules imported by code in the image but never COPY'd into it.

    Regression 20261018 (#1228): ``routers/insights.py`` imports ``weekly_insights`` and the
    Dockerfile did not copy it, so the router failed to import, ``/readyz`` stayed 503 and
    the Railway deploy timed out in both environments. ``vegetation_smoke.py`` now boots the
    image, but booting only reaches imports executed at startup. ``anomaly_store_pg`` is
    imported inside ``anomaly_runtime._make_backend`` and only when
    ``VEGETATION_ANOMALY_STORE=postgres``, so a dropped COPY for it passes the SQLite smoke,
    while a Postgres deployment fails ``routers.anomalies`` at startup (``anomaly_runtime``
    builds its backend at import). Static on purpose: every import,
    including function-level ones, is checked without dependencies or a Docker daemon.
    """
    prefix = "services/vegetation-analysis-service/"
    copied: set[str] = set()
    for line in dockerfile.splitlines():
        parts = line.split()
        if len(parts) < 3 or parts[0] != "COPY" or any(p.startswith("--") for p in parts):
            continue
        for src in parts[1:-1]:
            if src.startswith(prefix):
                copied.add(src[len(prefix) :].rstrip("/"))

    def in_image(rel: str) -> bool:
        return any(rel == c or rel.startswith(c + "/") for c in copied)

    local = {p.stem for p in service_dir.glob("*.py")} | {
        p.name for p in service_dir.iterdir() if p.is_dir() and any(p.glob("*.py"))
    }
    missing: dict[str, set[str]] = {}
    for path in service_dir.rglob("*.py"):
        rel = path.relative_to(service_dir).as_posix()
        if "tests" in path.parts or not in_image(rel):
            continue
        for node in ast.walk(ast.parse(_text(path), filename=str(path))):
            if isinstance(node, ast.Import):
                names = [alias.name.split(".")[0] for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names = [node.module.split(".")[0]]
            else:
                continue
            for name in names:
                if name in local and not (in_image(f"{name}.py") or in_image(name)):
                    missing.setdefault(name, set()).add(rel)
    return {name: sorted(users) for name, users in sorted(missing.items())}


def main() -> int:
    dockerfile = _text(DOCKERFILE)
    missing = missing_local_imports(dockerfile)
    if missing:
        raise SystemExit(
            "vegetation Dockerfile does not COPY service modules that image code imports "
            f"(the import fails inside the image when that code runs): {missing}"
        )
    if (
        "COPY services/vegetation-analysis-service/vegetation_runtime.py /app/vegetation_runtime.py"
        not in dockerfile
    ):
        raise SystemExit("vegetation Dockerfile does not copy vegetation_runtime.py")
    if "http://localhost:8000/healthz" not in dockerfile or "/readyz" in dockerfile:
        raise SystemExit("vegetation Docker HEALTHCHECK must use /healthz, not /readyz")
    if "gcc" in dockerfile or "libpq-dev" in dockerfile:
        raise SystemExit("vegetation Dockerfile regained unnecessary build/DB packages")

    req = _text(REQ)
    if "PyJWT==2.13.0#" in req:
        raise SystemExit("vegetation requirements has malformed inline PyJWT comment")
    # asyncpg is a deliberate, opt-in dependency of the RS-6 durable anomaly store
    # (anomaly_store_pg.py, selected by VEGETATION_ANOMALY_STORE=postgres for
    # horizontal scale). psycopg/redis remain forbidden — the service takes no
    # other DB/cache driver.
    for forbidden in ("psycopg", "redis"):
        if forbidden in req:
            raise SystemExit(f"vegetation requirements regained unused {forbidden!r} dependency")

    health_keys = _return_dict_for_handler(HEALTH, "healthz")
    ready_keys = _return_dict_for_handler(HEALTH, "readyz")
    if not {"status", "service"} <= health_keys:
        raise SystemExit("vegetation /healthz must return status + service")
    if not {"status", "service", "ready", "implemented_runtime", "dependencies"} <= ready_keys:
        raise SystemExit("vegetation /readyz schema missing required truth keys")

    # Container startup completeness: every module the Dockerfile copies into /app that reads a
    # sibling data file at import (Path(__file__).with_name("X")) must have that file COPY'd too,
    # otherwise the container dies with FileNotFoundError before serving (regression 20260712:
    # indicator_registry.py read indicator_capabilities.generated.json that was never copied).
    import re as _re

    copied_modules = _re.findall(
        r"COPY services/vegetation-analysis-service/(\S+\.py) /app/", dockerfile
    )
    for rel in copied_modules:
        mod = SERVICE_DIR / rel
        if not mod.exists():
            continue
        for data_file in _re.findall(r'\.with_name\(\s*"([^"]+)"\s*\)', _text(mod)):
            if data_file.endswith(".py"):
                continue  # sibling python modules are handled by their own COPY lines
            if f"/app/{data_file}" not in dockerfile:
                raise SystemExit(
                    f"vegetation Dockerfile copies {rel} which reads {data_file!r} at import "
                    f"but does not COPY {data_file} — container will FileNotFoundError on startup"
                )

    block = _compose_service_block("sahool-vegetation-analysis")
    if "depends_on:" in block and "sahool-nats" in block:
        raise SystemExit(
            "vegetation compose must not hard-block startup on NATS; publish is best-effort"
        )
    if "VEGETATION_NATS_PUBLISH_MODE" not in block:
        raise SystemExit("vegetation compose should document best-effort NATS publish mode")

    print("vegetation_container_contract_guard_ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
