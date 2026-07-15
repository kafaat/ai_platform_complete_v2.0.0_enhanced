#!/usr/bin/env python3
"""Guard the VEGETATION_REAL_ONLY fail-closed posture across compose files.

Governance: a field with no real processed observation must fail closed (HTTP 424,
never a synthetic NDVI) in production/staging. Development may opt into soft-fail
(HTTP 200 {available:false, synthetic:false}) — but ONLY via an explicit dev override,
never as the production default.

Two guarantees:
  1. Production compose (docker-compose.v9.yml, docker-compose.fixed.yml) must declare
     VEGETATION_REAL_ONLY with a FAIL-CLOSED default: `${VEGETATION_REAL_ONLY:-1}`.
     A literal "0"/"false" or a `:-0`/`:-false` default is rejected — production must
     not silently degrade.
  2. The development override (docker-compose.dev.yml) MAY set it to "0" explicitly
     (soft-fail is a deliberate dev choice, isolated to that file).
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

PRODUCTION_COMPOSE = [
    ROOT / "docker-compose.v9.yml",
    ROOT / "docker-compose.fixed.yml",
]
DEV_OVERRIDE = ROOT / "docker-compose.dev.yml"
ENV_EXAMPLE = ROOT / ".env.example"

_FAIL_CLOSED = re.compile(r"VEGETATION_REAL_ONLY:\s*\$\{VEGETATION_REAL_ONLY:-1\}")
_SOFT_DEFAULT = re.compile(r"VEGETATION_REAL_ONLY:\s*(\"?0\"?|\"?false\"?|\$\{[^}]*:-(0|false)\})")


def fail(message: str) -> None:
    raise SystemExit("✗ " + message)


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def check_production_defaults_fail_closed() -> None:
    for compose in PRODUCTION_COMPOSE:
        text = read(compose)
        if "VEGETATION_REAL_ONLY" not in text:
            continue
        if _SOFT_DEFAULT.search(text):
            fail(
                f"{compose.name}: VEGETATION_REAL_ONLY must not default to soft-fail (0/false) "
                "in a production compose — use ${VEGETATION_REAL_ONLY:-1}"
            )
        if not _FAIL_CLOSED.search(text):
            fail(
                f"{compose.name}: VEGETATION_REAL_ONLY must be the fail-closed default "
                "${VEGETATION_REAL_ONLY:-1} (no processed observation ⇒ 424, never synthetic)"
            )


def check_env_example_is_fail_closed() -> None:
    for line in read(ENV_EXAMPLE).splitlines():
        stripped = line.strip()
        if stripped.startswith("VEGETATION_REAL_ONLY="):
            value = stripped.split("=", 1)[1].strip().strip('"').lower()
            if value in ("0", "false", ""):
                fail(
                    ".env.example (production template) must set VEGETATION_REAL_ONLY=1 "
                    "(fail-closed); dev soft-fail belongs in docker-compose.dev.yml"
                )
            return
    fail(".env.example must declare VEGETATION_REAL_ONLY (fail-closed production template)")


def check_dev_override_may_soft_fail() -> None:
    # The dev override is the ONE sanctioned place to relax to soft-fail; assert it
    # exists and explicitly sets 0 so the posture split stays documented and testable.
    if not DEV_OVERRIDE.exists():
        fail("docker-compose.dev.yml (sanctioned dev soft-fail override) is missing")
    if not re.search(r'VEGETATION_REAL_ONLY:\s*"0"', read(DEV_OVERRIDE)):
        fail('docker-compose.dev.yml must set VEGETATION_REAL_ONLY: "0" (explicit dev soft-fail)')


def main() -> int:
    check_production_defaults_fail_closed()
    check_env_example_is_fail_closed()
    check_dev_override_may_soft_fail()
    print("vegetation_real_only_posture_guard_ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
