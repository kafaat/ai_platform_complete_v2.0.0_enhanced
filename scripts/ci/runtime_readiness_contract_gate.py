#!/usr/bin/env python3
"""Static runtime-readiness contract gate.

Guards against runtime-readiness regressions:
- Qdrant must NOT declare an in-container healthcheck: qdrant/qdrant is distroless
  (no shell/curl), so any probe fails and marks it permanently unhealthy, which would
  deadlock every service_healthy dependent. Dependents (RAG/seed) gate on
  service_started; a real readiness gate belongs in a sidecar or the app's own retry.
- Long-running project workers must expose at least a process/env healthcheck.
- MapHub backfill polling must be abortable and retry transient status poll failures.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
COMPOSE_FILES = [ROOT / "docker-compose.v9.yml", ROOT / "docker-compose.fixed.yml"]
QDRANT_DEPENDENTS = ["sahool-local-ai-rag", "sahool-rag-retrieval", "sahool-qdrant-seed"]
WORKERS = [
    "sahool-raster-backfill-scan-worker",
    "sahool-raster-cache-invalidation-worker",
    "sahool-phase-runtime-outbox-worker",
    "sahool-plugin-runtime-worker",
    "sahool-model-registry-worker",
    "sahool-actuator-dispatch-worker",
]


def fail(msg: str) -> None:
    print(f"runtime-readiness contract: FAIL — {msg}", file=sys.stderr)
    sys.exit(1)


def load(path: Path) -> dict[str, Any]:
    if not path.exists():
        fail(f"missing compose file {path}")
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def has_healthcheck(service: dict[str, Any]) -> bool:
    hc = service.get("healthcheck")
    return isinstance(hc, dict) and bool(hc.get("test"))


def check_compose(path: Path) -> None:
    data = load(path)
    services = data.get("services") or {}
    # qdrant/qdrant is DISTROLESS (no shell/curl): a self-healthcheck can never run and
    # would mark the container permanently unhealthy, blocking every service_healthy
    # dependent. The correct contract is the INVERSE — qdrant must NOT declare an
    # in-container healthcheck, and its dependents gate on service_started.
    if "sahool-qdrant" in services and has_healthcheck(services["sahool-qdrant"]):
        fail(
            f"{path.name}: sahool-qdrant must NOT declare an in-container healthcheck "
            "(distroless image — probe can't run; use service_started + sidecar/app-level "
            "readiness if a true gate is needed)"
        )
    for name in QDRANT_DEPENDENTS:
        if name not in services:
            continue
        dep = (services[name].get("depends_on") or {}).get("sahool-qdrant")
        if isinstance(dep, dict) and dep.get("condition") == "service_healthy":
            fail(
                f"{path.name}: {name} must depend on sahool-qdrant with condition=service_started "
                "(qdrant is distroless / has no healthcheck; service_healthy would deadlock)"
            )
    for name in WORKERS:
        if name in services and not has_healthcheck(services[name]):
            fail(f"{path.name}: {name} must expose a healthcheck")


def check_maphub() -> None:
    src = (ROOT / "frontend/src/sections/MapHub.tsx").read_text(encoding="utf-8")
    required = [
        "backfillPollTokenRef",
        "transientErrors",
        "finalRefreshImageryTimeline",
        "fetchHistoricalImageryBackfillStatus(pollFieldId, runId)",
        "backfillPollTokenRef.current !== pollToken",
    ]
    missing = [needle for needle in required if needle not in src]
    if missing:
        fail("MapHub backfill polling lost abort/retry/final-sync contract: " + ", ".join(missing))


def main() -> int:
    for path in COMPOSE_FILES:
        check_compose(path)
    check_maphub()
    print("runtime-readiness contract: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
