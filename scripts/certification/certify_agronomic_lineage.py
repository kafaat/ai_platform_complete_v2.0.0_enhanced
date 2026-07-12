#!/usr/bin/env python3
"""Apply/check decision migrations and run the real PostgreSQL agronomic-lineage proof.

Fail-closed by design: it refuses to certify without DATABASE_URL. Retain its output as
release evidence (AC-6.1 staging certification step).
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SERVICE = ROOT / "services" / "decision-service"


def main() -> int:
    if not os.getenv("DATABASE_URL", "").strip():
        print("CERTIFICATION FAILED: DATABASE_URL is required", file=sys.stderr)
        return 2

    env = os.environ.copy()
    env["PYTHONPATH"] = str(SERVICE) + os.pathsep + env.get("PYTHONPATH", "")
    # Certification IS the sanctioned migration path: allow the runner's schema gate and
    # exercise the authoritative (SoR) code paths the proof is about.
    env.setdefault("DECISION_SERVICE_ALLOW_SCHEMA_CHANGE", "true")
    env.setdefault("DECISION_SERVICE_SOR_ENABLED", "true")
    commands = [
        [sys.executable, str(SERVICE / "migration_runner.py"), "--apply"],
        [sys.executable, str(SERVICE / "migration_runner.py"), "--check"],
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            str(SERVICE / "tests" / "test_agronomic_lineage_integrity.py"),
        ],
    ]
    for command in commands:
        print("+", " ".join(command), flush=True)
        result = subprocess.run(command, cwd=ROOT, env=env, check=False)
        if result.returncode:
            return result.returncode
    print("AGRONOMIC LINEAGE POSTGRES CERTIFICATION: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
