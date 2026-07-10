#!/usr/bin/env python3
"""Container fleet contract guard.

Guards the post-P0/P1/P2 container consistency fixes:
- Docker liveness probes must use /healthz, not dependency readiness /readyz.
- Dockerfiles must copy runtime helper modules they import at container startup.
- One-shot seed containers must copy their optional-but-real data modules.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

REQUIRED_SUBSTRINGS = {
    "services/auth/Dockerfile": [
        "COPY services/auth/mfa_runtime.py /app/mfa_runtime.py",
        "http://localhost:8000/healthz",
    ],
    "services/mcp_servers/Dockerfile": [
        "COPY services/mcp_servers/market_db_authz.py /app/",
    ],
    "services/qdrant-seed/Dockerfile": [
        "COPY services/qdrant-seed/aljawf_knowledge.py /app/aljawf_knowledge.py",
    ],
    "services/field-segmentation/Dockerfile": ["http://localhost:8000/healthz"],
    "services/soil-service/Dockerfile": ["http://localhost:8000/healthz"],
    "services/weather-service/Dockerfile": ["http://localhost:8000/healthz"],
    "services/supervisor-agent/Dockerfile": ["http://localhost:8000/healthz"],
    "services/sahool-platform/Dockerfile": ["CMD curl -sf http://localhost:8000/healthz || exit 1"],
    "services/sam2-inference/Dockerfile": ["http://localhost:8080/healthz"],
}

NO_READYZ_HEALTHCHECK = [
    "services/auth/Dockerfile",
    "services/field-segmentation/Dockerfile",
    "services/soil-service/Dockerfile",
    "services/weather-service/Dockerfile",
    "services/supervisor-agent/Dockerfile",
    "services/sahool-platform/Dockerfile",
    "services/sam2-inference/Dockerfile",
]


def _healthcheck_lines(text: str) -> list[str]:
    lines = text.splitlines()
    out: list[str] = []
    i = 0
    while i < len(lines):
        if lines[i].lstrip().startswith("HEALTHCHECK"):
            block = [lines[i]]
            while block[-1].rstrip().endswith("\\") and i + 1 < len(lines):
                i += 1
                block.append(lines[i])
            out.append("\n".join(block))
        i += 1
    return out


def main() -> int:
    errors: list[str] = []

    for rel, snippets in REQUIRED_SUBSTRINGS.items():
        path = ROOT / rel
        if not path.exists():
            errors.append(f"missing file: {rel}")
            continue
        text = path.read_text(encoding="utf-8")
        for snippet in snippets:
            if snippet not in text:
                errors.append(f"{rel}: missing required snippet: {snippet}")

    for rel in NO_READYZ_HEALTHCHECK:
        path = ROOT / rel
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        for block in _healthcheck_lines(text):
            if "/readyz" in block:
                errors.append(
                    f"{rel}: Docker HEALTHCHECK must use /healthz liveness, not /readyz readiness"
                )
            if "/healthz" not in block:
                errors.append(f"{rel}: Docker HEALTHCHECK must include /healthz")

    # Regression checks for known startup import failures.
    auth_main = (ROOT / "services/auth/main.py").read_text(encoding="utf-8")
    auth_docker = (ROOT / "services/auth/Dockerfile").read_text(encoding="utf-8")
    if "from mfa_runtime import" in auth_main and "mfa_runtime.py" not in auth_docker:
        errors.append("auth Dockerfile does not copy mfa_runtime.py imported by main.py")

    market_server = (ROOT / "services/mcp_servers/market_server.py").read_text(encoding="utf-8")
    mcp_docker = (ROOT / "services/mcp_servers/Dockerfile").read_text(encoding="utf-8")
    if (
        re.search(r"^import\s+market_db_authz\b", market_server, flags=re.M)
        and "market_db_authz.py" not in mcp_docker
    ):
        errors.append(
            "mcp_servers Dockerfile does not copy market_db_authz.py imported by market_server.py"
        )

    seed = (ROOT / "services/qdrant-seed/seed.py").read_text(encoding="utf-8")
    qdrant_docker = (ROOT / "services/qdrant-seed/Dockerfile").read_text(encoding="utf-8")
    if "from aljawf_knowledge import" in seed and "aljawf_knowledge.py" not in qdrant_docker:
        errors.append("qdrant-seed Dockerfile does not copy aljawf_knowledge.py used by seed.py")

    if errors:
        for err in errors:
            print(f"container_fleet_contract_error: {err}", file=sys.stderr)
        return 1

    print("container_fleet_contract_guard_ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
