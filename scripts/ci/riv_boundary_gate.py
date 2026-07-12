#!/usr/bin/env python3
from __future__ import annotations

import io
import json
import re
import subprocess
import sys
import tokenize
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OWN = json.loads((ROOT / "shared/contracts/indicator_ownership.json").read_text())
FLOW = json.loads((ROOT / "shared/contracts/indicator_product_flow.json").read_text())
PATTERNS = [
    re.compile(r"\b(?:B0?8|NIR)\s*-\s*(?:B0?4|RED)\b", re.I),
    re.compile(r"compute_ndvi_from_bands"),
]
ALLOW = tuple(OWN["policy"]["spectral_formula_allowlist"])
SKIP = {
    "tests",
    "test",
    "docs",
    ".git",
    ".pytest_cache",
    "node_modules",
    "dist",
    "build",
    "scripts",
    ".claude",
    ".venv",
    "venv",
}


def executable_text(path: Path) -> str:
    src = path.read_text(encoding="utf-8", errors="ignore")
    try:
        toks = tokenize.generate_tokens(io.StringIO(src).readline)
        return " ".join(t.string for t in toks if t.type not in {tokenize.STRING, tokenize.COMMENT})
    except tokenize.TokenError:
        return src


errors = []
for p in ROOT.rglob("*.py"):
    rel = p.relative_to(ROOT).as_posix()
    if any(part in SKIP or part.startswith("test_") for part in p.parts):
        continue
    if rel.startswith(ALLOW):
        continue
    text = executable_text(p)
    if any(rx.search(text) for rx in PATTERNS):
        errors.append(f"spectral executable outside raster boundary: {rel}")
products = [f["product"] for f in FLOW["flows"]]
if len(products) != len(set(products)):
    errors.append("duplicate product in indicator_product_flow.json")
for f in FLOW["flows"]:
    if not f.get("producer") or not f.get("consumers") or not f.get("storage_owner"):
        errors.append(f"incomplete flow: {f.get('product')}")
cp = subprocess.run(
    [sys.executable, str(ROOT / "scripts/ci/generate_indicator_artifacts.py"), "--check"],
    capture_output=True,
    text=True,
)
if cp.returncode:
    errors.append(cp.stdout + cp.stderr)
if errors:
    print("riv_boundary_gate FAILED")
    [print(" - " + e) for e in errors]
    raise SystemExit(1)
print("riv_boundary_gate_ok")
