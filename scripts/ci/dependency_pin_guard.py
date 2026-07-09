#!/usr/bin/env python3
"""Fail on unpinned Python service dependencies across the monorepo.

This is a direct-dependency guard, not a transitive resolver. It prevents reintroducing
floating/ranged pins in any service requirements file. The generated dependency inventory
remains the auditable source for exactly what each service declares.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SERVICES = ROOT / "services"
PIN_RE = re.compile(r"^[A-Za-z0-9_.-]+(?:\[[^\]]+\])?==[^=].+$")
BAD_RE = re.compile(r"^[A-Za-z0-9_.-]+(?:\[[^\]]+\])?\s*(?:>=|~=|>|<|!=|===)")


def meaningful(line: str) -> str:
    return line.split("#", 1)[0].strip()


def iter_requirement_files() -> list[Path]:
    return sorted(SERVICES.glob("*/requirements*.txt")) + sorted(SERVICES.glob("*/*/requirements*.txt"))


def main() -> None:
    bad: list[str] = []
    for path in iter_requirement_files():
        for idx, raw in enumerate(path.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
            line = meaningful(raw)
            if not line or line.startswith("-") or line.startswith("--"):
                continue
            if BAD_RE.match(line) or not PIN_RE.match(line):
                bad.append(f"{path.relative_to(ROOT)}:{idx}: {raw}")
    if bad:
        raise SystemExit("Unpinned service dependency lines:\n" + "\n".join(bad))
    print("✓ monorepo service dependency pin guard passed")


if __name__ == "__main__":
    main()
