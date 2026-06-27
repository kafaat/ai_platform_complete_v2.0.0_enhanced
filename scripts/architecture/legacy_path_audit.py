#!/usr/bin/env python3
"""Audit production runtime paths for unquarantined legacy/MVP markers.

The goal is not to ban historical reports. It scans only executable/runtime
areas and requires legacy markers to be explicitly quarantined with one of:
LEGACY_OK, LEGACY_QUARANTINED, DOC_ONLY, TEST_ONLY, COMPAT_ONLY.
"""
from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path

RUNTIME_DIRS = ("services", "shared", "scripts", ".github", "helm")
SKIP_DIRS = {"__pycache__", ".pytest_cache", "node_modules", ".git", "venv", ".venv", "build", "dist", "tests", "docs"}
TEXT_SUFFIXES = {".py", ".sh", ".yml", ".yaml", ".json", ".toml", ".ini", ".env", ".md", ".txt"}
QUARANTINE_TOKENS = ("LEGACY_OK", "LEGACY_QUARANTINED", "DOC_ONLY", "TEST_ONLY", "COMPAT_ONLY")
ALLOWLIST_FILE = "architecture/legacy_quarantine_allowlist.json"
PATTERNS = [
    ("mvp_in_memory", re.compile(r"\b(in[-_ ]memory|memory only|MVP)\b", re.I)),
    ("dev_hs256", re.compile(r"\bHS256\b.*\b(dev|secret|default)|\bdev secret\b", re.I)),
    ("mock_runtime", re.compile(r"\b(mock|stub|fake)\b.*\b(runtime|production|adapter|model|executor)", re.I)),
    ("prod_todo", re.compile(r"\bTODO\b.*\b(prod|production|runtime|security)", re.I)),
    ("unsafe_fallback", re.compile(r"\b(fallback)\b.*\b(fake|mock|stub|dev|in-memory)", re.I)),
]

@dataclass
class Finding:
    path: str
    line: int
    code: str
    text: str


def is_text_file(path: Path) -> bool:
    return path.suffix in TEXT_SUFFIXES or path.name in {"Dockerfile", ".env", ".env.example"}


def iter_files(root: Path):
    for base in RUNTIME_DIRS:
        base_path = root / base
        if not base_path.exists():
            continue
        for path in base_path.rglob("*"):
            if not path.is_file() or any(part in SKIP_DIRS for part in path.parts):
                continue
            rel = str(path.relative_to(root))
            if rel.startswith("scripts/architecture/"):
                continue
            if is_text_file(path):
                yield path


def line_quarantined(line: str) -> bool:
    return any(token in line for token in QUARANTINE_TOKENS)


def load_allowlist(root: Path) -> set[str]:
    path = root / ALLOWLIST_FILE
    if not path.exists():
        return set()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return set()
    return set(data.get("allowed", []))


def audit(root: Path) -> list[Finding]:
    findings: list[Finding] = []
    allowlist = load_allowlist(root)
    for path in iter_files(root):
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for idx, line in enumerate(text.splitlines(), start=1):
            if line_quarantined(line):
                continue
            for code, pattern in PATTERNS:
                if pattern.search(line):
                    rel = str(path.relative_to(root))
                    key = f"{rel}:{code}"
                    if key in allowlist:
                        continue
                    findings.append(Finding(rel, idx, code, line.strip()[:240]))
    return findings


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--format", choices=["text", "json"], default="text")
    parser.add_argument("--strict", action="store_true", help="exit non-zero when findings are present")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    findings = audit(root)
    payload = {"finding_count": len(findings), "findings": [asdict(f) for f in findings]}
    if args.format == "json":
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"legacy_path_audit: findings={len(findings)}")
        for f in findings[:100]:
            print(f"{f.path}:{f.line}: {f.code}: {f.text}")
        if len(findings) > 100:
            print(f"... truncated {len(findings)-100} additional findings")
    return 1 if args.strict and findings else 0

if __name__ == "__main__":
    raise SystemExit(main())
