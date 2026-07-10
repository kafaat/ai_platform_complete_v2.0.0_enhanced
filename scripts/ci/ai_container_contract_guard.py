#!/usr/bin/env python3
"""Guard AI-oriented containers for liveness/readiness and post-decomposition copy contracts."""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

AI_SERVICES = {
    "sahool-ai-agronomist": "services/ai_agronomist/Dockerfile",
    "sahool-agriai-engine": "services/agriai-engine/Dockerfile",
    "sahool-local-ai-rag": "services/local-ai-rag/Dockerfile",
    "sahool-rag-retrieval": "services/rag-retrieval/Dockerfile",
    "sahool-knowledge-graph": "services/knowledge-graph/Dockerfile",
    "sahool-supervisor-agent": "services/supervisor-agent/Dockerfile",
    "sahool-guardrails-engine": "services/guardrails-engine/Dockerfile",
    "sahool-edge": "services/edge-inference/Dockerfile.arm64",
    "sahool-sam2-inference": "services/sam2-inference/Dockerfile",
}

COMPOSE = ROOT / "docker-compose.v9.yml"
GENERATED_JSON = ROOT / "ai_container_audit.generated.json"
GENERATED_CSV = ROOT / "ai_container_audit.csv"


def _read(path: str | Path) -> str:
    return (
        (ROOT / path).read_text(encoding="utf-8")
        if not isinstance(path, Path)
        else path.read_text(encoding="utf-8")
    )


def _compose_block(service: str) -> str:
    text = COMPOSE.read_text(encoding="utf-8")
    pattern = rf"(?ms)^  {re.escape(service)}:\n(?P<body>.*?)(?=^  [a-zA-Z0-9_-]+:|\Z)"
    match = re.search(pattern, text)
    if not match:
        raise AssertionError(f"compose service missing: {service}")
    return match.group(0)


def _has_bad_inline_comment(path: Path) -> list[str]:
    bad: list[str] = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "#" in line and " #" not in line:
            bad.append(f"{path}:{lineno}:{line}")
    return bad


def _healthcheck_text(text: str) -> str:
    lines = text.splitlines()
    chunks: list[str] = []
    for i, line in enumerate(lines):
        if line.lstrip().startswith("HEALTHCHECK"):
            chunk = [line]
            j = i + 1
            while j < len(lines) and (lines[j].startswith(" ") or lines[j].startswith("\t")):
                chunk.append(lines[j])
                if not lines[j].rstrip().endswith("\\"):
                    break
                j += 1
            chunks.append("\n".join(chunk))
    return "\n".join(chunks)


def build_inventory() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for service, dockerfile in AI_SERVICES.items():
        docker = _read(dockerfile)
        docker_health = _healthcheck_text(docker)
        compose = _compose_block(service)
        rows.append(
            {
                "service": service,
                "dockerfile": dockerfile,
                "dockerfile_exists": (ROOT / dockerfile).exists(),
                "docker_health_uses_healthz": "/healthz" in docker_health,
                "docker_health_uses_readyz": "/readyz" in docker_health,
                "compose_health_uses_healthz": "/healthz" in compose,
                "compose_health_uses_readyz": "/readyz" in compose,
                "copies_shared": "COPY shared" in docker,
                "copies_service_dir": "COPY services/" in docker,
                "pip_timeout_retries": "--timeout 300" in docker and "--retries 10" in docker,
            }
        )
    return rows


def check(write: bool = False) -> list[dict[str, object]]:
    rows = build_inventory()
    failures: list[str] = []

    for row in rows:
        service = str(row["service"])
        if not row["compose_health_uses_healthz"]:
            failures.append(f"{service}: compose healthcheck must use /healthz for liveness")
        if row["compose_health_uses_readyz"]:
            failures.append(
                f"{service}: compose healthcheck must not use /readyz as Docker liveness"
            )
        if not row["docker_health_uses_healthz"]:
            failures.append(f"{service}: Dockerfile HEALTHCHECK must use /healthz")
        if row["docker_health_uses_readyz"]:
            failures.append(f"{service}: Dockerfile HEALTHCHECK must not use /readyz")
        if not row["pip_timeout_retries"]:
            failures.append(f"{service}: pip install must include --timeout 300 --retries 10")

    # Post-decomposition/import-copy contracts.
    ai_docker = _read("services/ai_agronomist/Dockerfile")
    if (
        "COPY services/ai_agronomist /app/ai_agronomist" not in ai_docker
        or "COPY shared /app/shared" not in ai_docker
    ):
        failures.append("ai_agronomist Dockerfile must copy service package and shared/")
    edge_docker = _read("services/edge-inference/Dockerfile.arm64")
    if "COPY services/edge-inference/ /app/" not in edge_docker:
        failures.append("edge-inference Dockerfile.arm64 must copy whole service directory")
    sam2_docker = _read("services/sam2-inference/Dockerfile")
    if "COPY services/sam2-inference/ /app/" not in sam2_docker:
        failures.append("sam2-inference Dockerfile must copy whole service directory")
    rag_docker = _read("services/rag-retrieval/Dockerfile")
    if (
        "COPY shared /app/shared" not in rag_docker
        or "COPY services/rag-retrieval/main.py /app/main.py" not in rag_docker
    ):
        failures.append("rag-retrieval Dockerfile must copy shared/ and main.py")
    kg_docker = _read("services/knowledge-graph/Dockerfile")
    if (
        "COPY shared /app/shared" not in kg_docker
        or "COPY services/knowledge-graph/main.py /app/main.py" not in kg_docker
    ):
        failures.append("knowledge-graph Dockerfile must copy shared/ and main.py")

    for req in [
        ROOT / "services/auth/requirements.txt",
        ROOT / "services/local-ai-rag/requirements.txt",
    ]:
        failures.extend(_has_bad_inline_comment(req))

    if write:
        GENERATED_JSON.write_text(
            json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        with GENERATED_CSV.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)

    if failures:
        raise SystemExit("\n".join(failures))
    return rows


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    check(write=args.write)
    print("ai_container_contract_guard_ok")


if __name__ == "__main__":
    main()
