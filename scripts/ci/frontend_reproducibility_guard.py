#!/usr/bin/env python3
"""Guard deterministic, lifecycle-safe frontend dependency installation."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LOCK = ROOT / "frontend/package-lock.json"
WORKFLOWS = [
    ROOT / ".github/workflows/ci.yml",
    ROOT / ".github/workflows/field-workspace-production-closure.yml",
]


def main() -> int:
    errors: list[str] = []
    if not LOCK.is_file():
        errors.append("frontend/package-lock.json is missing")
    else:
        data = json.loads(LOCK.read_text(encoding="utf-8"))
        if int(data.get("lockfileVersion", 0)) < 3:
            errors.append("frontend lockfileVersion must be 3 or newer")
        if not data.get("packages"):
            errors.append("frontend lockfile has no resolved package graph")
    install_count = 0
    for path in WORKFLOWS:
        text = path.read_text(encoding="utf-8")
        for line in text.splitlines():
            if "npm ci" in line and not line.lstrip().startswith("#"):
                install_count += 1
                for flag in ("--ignore-scripts", "--no-audit", "--no-fund"):
                    if flag not in line:
                        errors.append(f"{path.relative_to(ROOT)}: npm ci missing {flag}")
            if "run: npm install" in line:
                errors.append(f"{path.relative_to(ROOT)}: npm install is non-deterministic; use npm ci")
    if install_count < 3:
        errors.append(f"expected at least 3 guarded npm ci installs, found {install_count}")
    if errors:
        print("frontend reproducibility guard: FAILED", file=sys.stderr)
        print("\n".join(f"- {e}" for e in errors), file=sys.stderr)
        return 1
    print(f"frontend reproducibility guard: PASSED ({install_count} npm ci installs)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

