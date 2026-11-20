#!/usr/bin/env python3
"""Inventory direct manifest declarations in a deterministic pre-build CycloneDX SBOM.

This does not resolve or install dependencies, evaluate environment markers, or
inventory transitive/locked dependencies. Python input is PEP 508 requirement
lines; unsupported pip directives fail explicitly instead of disappearing.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from urllib.parse import quote

NPM_VERSION = re.compile(
    r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)"
    r"(?:-(?P<prerelease>[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
)


def _ref(kind: str, name: str, version: str) -> str:
    return "urn:uuid:" + hashlib.sha256(f"{kind}:{name}:{version}".encode()).hexdigest()[:32]


def _python_requirement(
    raw: str, manifest: str, line: int
) -> tuple[str, str | None, dict[str, object]]:
    # Keep --help usable without the generation dependency installed.
    try:
        from packaging.requirements import InvalidRequirement, Requirement
        from packaging.utils import canonicalize_name
        from packaging.version import InvalidVersion
    except ImportError as exc:
        raise RuntimeError("SBOM generation requires the public 'packaging' package") from exc

    try:
        requirement = Requirement(raw.strip())
    except InvalidRequirement:
        # Pip-style inline comments; a URL fragment or valid quoted marker is
        # preserved by trying the full PEP 508 declaration first.
        try:
            requirement = Requirement(re.split(r"\s+#", raw.strip(), maxsplit=1)[0])
        except InvalidRequirement as exc:
            raise ValueError(
                f"{manifest}:{line}: expected a PEP 508 requirement; "
                "pip options, includes and continuation lines are unsupported"
            ) from exc

    pins = sorted(
        spec.version
        for spec in requirement.specifier
        if spec.operator in {"==", "==="}
        and not (spec.operator == "==" and spec.version.endswith(".*"))
    )
    version = None
    for pin in pins:
        try:
            if requirement.specifier.contains(pin, prereleases=True):
                version = pin
                break
        except InvalidVersion:
            # An arbitrary equality combined with incompatible PEP 440 bounds
            # is still a declaration, not evidence of an installable version.
            continue

    return (
        canonicalize_name(requirement.name),
        version,
        {
            "manifest": manifest,
            "line": line,
            "raw": raw,
            "extras": sorted(canonicalize_name(extra) for extra in requirement.extras),
            "specifier": str(requirement.specifier),
            "marker": str(requirement.marker) if requirement.marker else None,
            "url": requirement.url,
        },
    )


def _npm_pin(declaration: str) -> str | None:
    match = NPM_VERSION.fullmatch(declaration)
    if match is None:
        return None
    prerelease = match.group("prerelease") or ""
    if any(
        part.isdigit() and len(part) > 1 and part.startswith("0") for part in prerelease.split(".")
    ):
        return None
    return declaration


def collect(root: Path) -> list[dict[str, object]]:
    found: dict[tuple[str, str, str], tuple[str | None, set[str], set[str]]] = {}

    def add(kind: str, name: str, version: str | None, declaration: dict[str, object]) -> None:
        constraint = (
            {"raw": declaration["raw"]}
            if kind == "npm"
            else {key: declaration[key] for key in ("extras", "specifier", "marker", "url")}
        )
        identity = (
            version
            if version is not None
            else "declaration:" + json.dumps(constraint, sort_keys=True)
        )
        _, manifests, declarations = found.setdefault(
            (kind, name, identity), (version, set(), set())
        )
        manifests.add(str(declaration["manifest"]))
        declarations.add(json.dumps(declaration, sort_keys=True))

    for path in sorted(root.rglob("requirements*.txt")):
        if any(p in {".git", "node_modules", ".venv", "venv"} for p in path.parts):
            continue
        for line, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not raw.strip() or raw.lstrip().startswith("#"):
                continue
            name, version, declaration = _python_requirement(
                raw, path.relative_to(root).as_posix(), line
            )
            add("pypi", name, version, declaration)
    for path in sorted(root.rglob("package.json")):
        if "node_modules" in path.parts:
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        manifest = path.relative_to(root).as_posix()
        if not isinstance(data, dict):
            raise ValueError(f"{manifest}: expected a JSON object")
        for section in ("dependencies", "devDependencies"):
            dependencies = data.get(section) or {}
            if not isinstance(dependencies, dict):
                raise ValueError(f"{manifest}: {section} must be an object")
            for name, raw in dependencies.items():
                if not isinstance(raw, str):
                    raise ValueError(f"{manifest}: {section}.{name} must be a string")
                add(
                    "npm",
                    name,
                    _npm_pin(raw),
                    {"manifest": manifest, "section": section, "raw": raw},
                )
    rows = []
    for (kind, name, identity), (version, manifests, declarations) in sorted(found.items()):
        row: dict[str, object] = {
            "type": "library",
            "bom-ref": _ref(kind, name, identity),
            "name": name,
            "properties": [
                {
                    "name": "sahool:version-status",
                    "value": "declared-pin" if version is not None else "unresolved",
                },
                *({"name": "sahool:source-manifest", "value": p} for p in sorted(manifests)),
                *(
                    {"name": "sahool:dependency-declaration", "value": p}
                    for p in sorted(declarations)
                ),
            ],
        }
        if version is not None:
            row["version"] = version
            row["purl"] = f"pkg:{kind}/{quote(name, safe='/')}@{quote(version, safe='')}"
        rows.append(row)
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--output", default="release/SBOM_DEPENDENCIES.cdx.json")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    try:
        components = collect(root)
    except (ValueError, RuntimeError) as exc:
        parser.error(str(exc))
    payload = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.6",
        "version": 1,
        "metadata": {
            "lifecycles": [{"phase": "pre-build"}],
            "properties": [
                {"name": "sahool:dependency-resolution", "value": "not-performed"},
                {
                    "name": "sahool:inventory-scope",
                    "value": "Direct declarations in requirements*.txt and package.json dependencies/devDependencies; "
                    "environment markers are retained, not evaluated; no locked, installed or transitive inventory",
                },
            ],
            "component": {
                "type": "application",
                "name": "sahool",
                "version": (root / "VERSION").read_text(encoding="utf-8").strip(),
            },
        },
        "components": components,
    }
    output = root / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"dependency SBOM generated: {len(components)} components")
    return 0 if components else 1


if __name__ == "__main__":
    raise SystemExit(main())
