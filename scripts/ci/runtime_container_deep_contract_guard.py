#!/usr/bin/env python3
"""Runtime container deep contract guard for non-AI high-risk services.

This guards follow-up fixes discovered after container fleet review:
- Docker/Compose healthchecks must use liveness (/healthz or /health), not readiness (/readyz).
- raster-service image must use Python 3.11 with current rasterio pin, avoiding Python 3.12 build drift.
- raster-service requirements must not contain duplicate direct pins.
- notification-agent must expose /healthz if compose/docker probe it.
- platform requirements must not contain malformed inline comments that confuse tooling.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from typing import Any

import yaml
from generated_artifact_contract import (  # noqa: E402
    Artifact,
    enforce,
    render_csv,
    render_json,
)

ROOT = Path(__file__).resolve().parents[2]
COMPOSE = ROOT / "docker-compose.v9.yml"
GENERATED_JSON = ROOT / "runtime_container_deep_audit.generated.json"
GENERATED_CSV = ROOT / "runtime_container_deep_audit.csv"

LIVENESS_SERVICES = {
    "sahool-auth": "http://localhost:8000/healthz",
    "sahool-platform": "http://localhost:8000/healthz",
    "sahool-notification-agent": "http://localhost:8123/healthz",
    "sahool-soil-service": "http://localhost:8000/healthz",
    "sahool-field-segmentation": "http://localhost:8000/healthz",
}


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def _compose() -> dict[str, Any]:
    return yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))


def _test_string(test: Any) -> str:
    if test is None:
        return ""
    if isinstance(test, list):
        return " ".join(map(str, test))
    return str(test)


def _duplicate_pins(requirements: str) -> dict[str, list[str]]:
    seen: dict[str, list[str]] = {}
    for line in requirements.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        stripped = stripped.split(" #", 1)[0].strip()
        m = re.match(r"^([A-Za-z0-9_.-]+)==([^\s#]+)", stripped)
        if m:
            seen.setdefault(m.group(1).lower(), []).append(m.group(0))
    return {k: v for k, v in seen.items() if len(v) > 1}


def _bad_inline_comments(path: Path) -> list[str]:
    bad: list[str] = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "#" in line and " #" not in line:
            bad.append(f"{path.relative_to(ROOT)}:{lineno}:{line}")
    return bad


def build_inventory() -> list[dict[str, object]]:
    services = _compose().get("services", {})
    rows: list[dict[str, object]] = []
    for service, expected in LIVENESS_SERVICES.items():
        test = services.get(service, {}).get("healthcheck", {}).get("test")
        test_text = _test_string(test)
        rows.append(
            {
                "service": service,
                "expected_liveness_url": expected,
                "compose_healthcheck": test_text,
                "uses_healthz_or_health": expected in test_text,
                "uses_readyz": "/readyz" in test_text,
            }
        )
    return rows


def artifacts(rows: list[dict[str, Any]]) -> list[Artifact]:
    """المصنوعتان اللتان يملكهما هذا الحارس."""
    return [
        Artifact(GENERATED_JSON, render_json(rows)),
        Artifact(GENERATED_CSV, render_csv(rows, list(rows[0].keys()))),
    ]


def check(write: bool = False) -> None:
    failures: list[str] = []
    rows = build_inventory()

    for row in rows:
        if row["uses_readyz"]:
            failures.append(f"{row['service']}: compose Docker healthcheck must not use /readyz")
        if not row["uses_healthz_or_health"]:
            failures.append(
                f"{row['service']}: compose Docker healthcheck must use {row['expected_liveness_url']}"
            )

    notification_agent = _read("agents/notification/agent.py")
    notification_docker = _read("agents/notification/Dockerfile")
    if '@app.get("/healthz")' not in notification_agent:
        failures.append("notification-agent must expose /healthz when container probes it")
    if "http://localhost:8123/healthz" not in notification_docker:
        failures.append("notification-agent Dockerfile must probe /healthz")
    if "/readyz" in "\n".join(
        line
        for line in notification_docker.splitlines()
        if line.lstrip().startswith("CMD") or "HEALTHCHECK" in line
    ):
        failures.append("notification-agent Docker HEALTHCHECK must not probe /readyz")

    raster_docker = _read("services/raster-service/Dockerfile")
    raster_req = _read("services/raster-service/requirements.txt")
    if not raster_docker.startswith("FROM python:3.11-slim-bookworm"):
        failures.append(
            "raster-service Dockerfile must use python:3.11-slim-bookworm with rasterio==1.3.0"
        )
    dups = _duplicate_pins(raster_req)
    if dups:
        failures.append(f"raster-service requirements contain duplicate exact pins: {dups}")

    for req in [ROOT / "services/sahool-platform/api/requirements.txt"]:
        failures.extend(_bad_inline_comments(req))

    # كان يبني الجرد ويؤكّد قواعده عليه بلا نظرة واحدة إلى الملفّ المُلتزَم.
    enforce(artifacts(rows), write=write, label="runtime_container_deep_contract_guard")

    if failures:
        for failure in failures:
            print(f"runtime_container_deep_contract_error: {failure}", file=sys.stderr)
        raise SystemExit(1)


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    check(write=args.write)
    print("runtime_container_deep_contract_guard_ok")


if __name__ == "__main__":
    main()
