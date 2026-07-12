#!/usr/bin/env python3
"""Phase C certification runner: prove no future data can leak into agronomic contexts.

Fail-closed: refuses to certify without DATABASE_URL. Runs the migration check plus the
randomized no-leakage property sweep on a real PostgreSQL. Retain output as release
evidence (master-plan Phase C exit criterion).
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
    env.setdefault("DECISION_SERVICE_SOR_ENABLED", "true")
    commands = [
        [sys.executable, str(SERVICE / "migration_runner.py"), "--check"],
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            str(SERVICE / "tests" / "test_no_leakage_certification.py"),
        ],
    ]
    for command in commands:
        print("+", " ".join(command), flush=True)
        result = subprocess.run(command, cwd=ROOT, env=env, check=False)
        if result.returncode:
            return result.returncode
    print("NO-LEAKAGE POSTGRES CERTIFICATION: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
