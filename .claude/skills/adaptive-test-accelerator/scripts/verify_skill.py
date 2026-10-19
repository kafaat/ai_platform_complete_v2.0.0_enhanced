#!/usr/bin/env python3
"""Read-only integrity check for the Skill folder (local checksums, not signatures)."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = {"SKILL.md", "README_AR.md", "scripts/checkpoint_runner.py",
            "scripts/duration_planner.py", "scripts/resource_profile.py",
            "templates/plan.example.json", "templates/context.git.example.json",
            "adapters/AGENT_NEUTRAL_PROMPT_AR.md"}


def verify(root: Path = ROOT) -> dict:
    manifest = root / "SHA256SUMS"
    if not manifest.is_file():
        raise ValueError("SHA256SUMS missing")
    expected = {}
    for line in manifest.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            sha, rel = line.split("  ", 1)
        except ValueError as exc:
            raise ValueError("Invalid manifest line") from exc
        if len(sha) != 64 or any(c not in "0123456789abcdef" for c in sha) or rel in expected:
            raise ValueError("Invalid checksum or duplicate path")
        expected[rel] = sha
    actual_paths = {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()
                    and p.name != "SHA256SUMS" and "__pycache__" not in p.parts and p.suffix != ".pyc"}
    if not REQUIRED <= expected.keys():
        raise ValueError("Required files are missing from manifest")
    if set(expected) != actual_paths:
        raise ValueError("File inventory mismatch (missing or unexpected file)")
    for rel, sha in expected.items():
        path = (root / rel).resolve()
        if not path.is_relative_to(root.resolve()) or not path.is_file():
            raise ValueError("Manifest path escapes Skill")
        if hashlib.sha256(path.read_bytes()).hexdigest() != sha:
            raise ValueError("SHA256 mismatch: " + rel)
    for path in root.rglob("*.json"):
        json.loads(path.read_text(encoding="utf-8"))
    if not (root / "SKILL.md").read_text(encoding="utf-8").startswith("---\nname:"):
        raise ValueError("Skill header missing")
    return {"verified_file_count": len(expected), "integrity": "local SHA256 checksum only; not an attestation"}


if __name__ == "__main__":
    print(json.dumps(verify(), indent=2))
