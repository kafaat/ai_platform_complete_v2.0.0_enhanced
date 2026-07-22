#!/usr/bin/env python3
"""Generate a deterministic CycloneDX dependency SBOM from repository manifests."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

REQ = re.compile(r"^([A-Za-z0-9_.-]+)==([^ ;#]+)")


def _ref(kind: str, name: str, version: str) -> str:
    return "urn:uuid:" + hashlib.sha256(f"{kind}:{name}:{version}".encode()).hexdigest()[:32]


def collect(root: Path) -> list[dict[str, object]]:
    found: dict[tuple[str, str, str], set[str]] = {}
    for path in sorted(root.rglob("requirements*.txt")):
        if any(p in {".git", "node_modules", ".venv", "venv"} for p in path.parts):
            continue
        for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
            match = REQ.match(raw.strip())
            if match:
                name, version = match.groups()
                found.setdefault(("pypi", name.lower(), version), set()).add(str(path.relative_to(root)))
    for path in sorted(root.rglob("package.json")):
        if "node_modules" in path.parts:
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue
        for section in ("dependencies", "devDependencies"):
            for name, version in (data.get(section) or {}).items():
                clean = str(version).lstrip("~^=v")
                found.setdefault(("npm", name, clean), set()).add(str(path.relative_to(root)))
    rows = []
    for (kind, name, version), manifests in sorted(found.items()):
        rows.append({
            "type": "library", "bom-ref": _ref(kind, name, version), "name": name,
            "version": version, "purl": f"pkg:{kind}/{name}@{version}",
            "properties": [{"name": "sahool:source-manifest", "value": p} for p in sorted(manifests)],
        })
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--output", default="release/SBOM_DEPENDENCIES.cdx.json")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    components = collect(root)
    payload = {
        "bomFormat": "CycloneDX", "specVersion": "1.6", "version": 1,
        "metadata": {"component": {"type": "application", "name": "sahool",
                    "version": (root / "VERSION").read_text().strip()}},
        "components": components,
    }
    output = root / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"dependency SBOM generated: {len(components)} components")
    return 0 if components else 1


if __name__ == "__main__":
    raise SystemExit(main())
