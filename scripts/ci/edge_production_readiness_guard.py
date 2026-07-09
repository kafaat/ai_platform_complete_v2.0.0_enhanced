#!/usr/bin/env python3
"""Guard Edge production-readiness policy.

Edge may run in partial mode for development/optional deployments, but production-required
Edge must force strict readiness and must not be allowed to report ready without models.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MAIN = ROOT / "services" / "edge-inference" / "main.py"
COMPOSE = ROOT / "docker-compose.v9.yml"
TESTS = ROOT / "services" / "edge-inference" / "tests" / "test_edge_capabilities_and_fail_closed.py"


def main() -> None:
    main_text = MAIN.read_text(encoding="utf-8")
    compose_text = COMPOSE.read_text(encoding="utf-8")
    tests_text = TESTS.read_text(encoding="utf-8")
    errors: list[str] = []
    for token, where, text in [
        ("EDGE_PRODUCTION_REQUIRED", "edge main.py", main_text),
        ("EDGE_PRODUCTION_REQUIRED", "docker-compose.v9.yml", compose_text),
        ("EDGE_PRODUCTION_REQUIRED", "edge tests", tests_text),
    ]:
        if token not in text:
            errors.append(f"{token} missing from {where}")
    if 'EDGE_READINESS_MODE == "strict" or EDGE_PRODUCTION_REQUIRED' not in main_text:
        errors.append("production-required mode must force strict readiness")
    if "response.status_code = 503" not in main_text:
        errors.append("degraded strict/production readiness must return HTTP 503")
    if errors:
        raise SystemExit("Edge production readiness guard failed:\n" + "\n".join(errors))
    print("✓ edge production readiness guard passed")


if __name__ == "__main__":
    main()
