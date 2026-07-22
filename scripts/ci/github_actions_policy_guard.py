#!/usr/bin/env python3
"""Enforce immutable third-party Actions and reject privileged workflow patterns."""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / ".github/workflows"
USE_RE = re.compile(r"\buses:\s*([^\s#]+)")
IMMUTABLE_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+@[0-9a-f]{40}$")


def main() -> int:
    errors: list[str] = []
    checked = 0
    for path in sorted(WORKFLOWS.glob("*.y*ml")):
        text = path.read_text(encoding="utf-8")
        rel = path.relative_to(ROOT)
        if "pull_request_target:" in text:
            errors.append(f"{rel}: privileged pull_request_target is forbidden")
        if re.search(r"(?m)^permissions:\s*write-all\s*$", text):
            errors.append(f"{rel}: permissions write-all is forbidden")
        for line_no, line in enumerate(text.splitlines(), 1):
            match = USE_RE.search(line)
            if not match:
                continue
            ref = match.group(1)
            if ref.startswith("./") or ref.startswith("docker://"):
                continue
            checked += 1
            if not IMMUTABLE_RE.fullmatch(ref):
                errors.append(f"{rel}:{line_no}: action is not pinned to a full commit SHA: {ref}")
    if errors:
        print("GitHub Actions policy guard: FAILED", file=sys.stderr)
        print("\n".join(f"- {error}" for error in errors), file=sys.stderr)
        return 1
    print(f"GitHub Actions policy guard: PASSED ({checked} immutable references)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

