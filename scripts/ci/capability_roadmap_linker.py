#!/usr/bin/env python3
"""Validate and generate the curated roadmap-to-capability linkage.

The linker is deliberately static and fail-closed. It records declared architectural
relationships but never upgrades runtime verification, maturity, or production status.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path, PurePosixPath
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "docs/capability-registry"
SOURCE = BASE / "roadmap/roadmap_items.yaml"
REGISTRY = BASE / "generated/capability_registry.json"
OUTPUT_DIR = BASE / "generated/roadmap"

SCHEMA_VERSION = "1.0.0"
ALLOWED_STATUSES = {
    "planned",
    "in_progress",
    "partial",
    "implemented_static",
    "implemented_runtime",
    "blocked",
    "deferred",
    "cancelled",
}
ALLOWED_IMPACT_SCOPES = {"linked_capabilities", "all_capabilities", "none"}
ROADMAP_ID_RE = re.compile(r"^(?:WX|CI)-\d+$")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def safe_repo_path(raw: Any, *, field: str) -> str:
    value = str(raw or "").strip().replace("\\", "/")
    if not value:
        raise ValueError(f"{field}: path is required")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"{field}: path must stay inside the repository: {value}")
    normalized = path.as_posix().lstrip("./")
    if not normalized or normalized == ".":
        raise ValueError(f"{field}: invalid repository path: {value}")
    return normalized


def load_yaml(path: Path = SOURCE) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("roadmap source must be a YAML mapping")
    return data


def load_registry(path: Path = REGISTRY) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    capabilities = data.get("capabilities")
    if not isinstance(capabilities, list):
        raise ValueError("capability registry is missing capabilities[]")
    return data


def build(
    *,
    root: Path = ROOT,
    source_path: Path = SOURCE,
    registry_path: Path = REGISTRY,
) -> dict[str, Any]:
    document = load_yaml(source_path)
    registry = load_registry(registry_path)

    errors: list[str] = []
    if str(document.get("schema_version")) != SCHEMA_VERSION:
        errors.append(
            f"unsupported roadmap schema_version={document.get('schema_version')!r}; "
            f"expected {SCHEMA_VERSION}"
        )
    if document.get("source_policy") != "curated_only":
        errors.append("source_policy must be curated_only")

    known = {cap["id"]: cap for cap in registry["capabilities"]}
    items = document.get("items")
    if not isinstance(items, list) or not items:
        errors.append("roadmap items[] must be a non-empty list")
        items = []

    seen_ids: set[str] = set()
    reverse: dict[str, list[dict[str, str]]] = defaultdict(list)
    normalized_items: list[dict[str, Any]] = []
    source_hashes: dict[str, str] = {}

    for position, item in enumerate(items, start=1):
        prefix = f"items[{position}]"
        if not isinstance(item, dict):
            errors.append(f"{prefix}: item must be a mapping")
            continue

        roadmap_id = str(item.get("id") or "").strip()
        title = str(item.get("title") or "").strip()
        status = str(item.get("status") or "").strip()
        impact_scope = str(item.get("impact_scope") or "linked_capabilities").strip()

        if not ROADMAP_ID_RE.fullmatch(roadmap_id):
            errors.append(f"{prefix}: invalid roadmap id {roadmap_id!r}")
        elif roadmap_id in seen_ids:
            errors.append(f"{prefix}: duplicate roadmap id {roadmap_id}")
        seen_ids.add(roadmap_id)

        if not title:
            errors.append(f"{roadmap_id or prefix}: title is required")
        if status not in ALLOWED_STATUSES:
            errors.append(f"{roadmap_id or prefix}: unsupported status {status!r}")
        if impact_scope not in ALLOWED_IMPACT_SCOPES:
            errors.append(f"{roadmap_id or prefix}: unsupported impact_scope {impact_scope!r}")

        try:
            source_rel = safe_repo_path(item.get("source"), field=f"{roadmap_id}.source")
        except ValueError as exc:
            errors.append(str(exc))
            source_rel = ""
        source_file = root / source_rel if source_rel else root / "__missing__"
        source_anchor = str(item.get("source_anchor") or "").strip()
        if not source_file.is_file():
            errors.append(f"{roadmap_id or prefix}: missing source {source_rel or '<empty>'}")
        else:
            source_text = source_file.read_text(encoding="utf-8")
            source_hashes[source_rel] = sha256_file(source_file)
            if not source_anchor:
                errors.append(f"{roadmap_id}: source_anchor is required")
            elif source_anchor not in source_text:
                errors.append(f"{roadmap_id}: source_anchor not found in {source_rel}")
            if roadmap_id and source_anchor and roadmap_id not in source_anchor:
                errors.append(f"{roadmap_id}: source_anchor must contain the roadmap id")

        raw_links = item.get("capability_links", [])
        if not isinstance(raw_links, list):
            errors.append(f"{roadmap_id}: capability_links must be a list")
            raw_links = []
        links: list[dict[str, str]] = []
        seen_capabilities: set[str] = set()
        for link_position, link in enumerate(raw_links, start=1):
            link_prefix = f"{roadmap_id}.capability_links[{link_position}]"
            if not isinstance(link, dict):
                errors.append(f"{link_prefix}: link must be a mapping")
                continue
            capability_id = str(link.get("id") or "").strip()
            relation = str(link.get("relation") or "").strip()
            rationale = str(link.get("rationale") or "").strip()
            if capability_id not in known:
                errors.append(f"{link_prefix}: unknown capability {capability_id!r}")
            if capability_id in seen_capabilities:
                errors.append(f"{link_prefix}: duplicate capability {capability_id}")
            seen_capabilities.add(capability_id)
            if not relation or not re.fullmatch(r"[a-z][a-z0-9_]*", relation):
                errors.append(f"{link_prefix}: relation must be a lower_snake_case token")
            if len(rationale) < 12:
                errors.append(f"{link_prefix}: rationale must explain the curated relationship")
            if capability_id in known and relation and rationale:
                normalized = {
                    "capability_id": capability_id,
                    "relation": relation,
                    "rationale": rationale,
                }
                links.append(normalized)
                reverse[capability_id].append({"roadmap_id": roadmap_id, "relation": relation})

        raw_governance_scope = item.get("governance_scope", [])
        if not isinstance(raw_governance_scope, list):
            errors.append(f"{roadmap_id}: governance_scope must be a list")
            raw_governance_scope = []
        governance_scope: list[str] = []
        for scope_position, raw_scope in enumerate(raw_governance_scope, start=1):
            try:
                scope = safe_repo_path(
                    raw_scope, field=f"{roadmap_id}.governance_scope[{scope_position}]"
                )
            except ValueError as exc:
                errors.append(str(exc))
                continue
            if "generated" in PurePosixPath(scope).parts:
                errors.append(
                    f"{roadmap_id}: governance_scope must not target generated outputs: {scope}"
                )
            elif not (root / scope).exists():
                errors.append(f"{roadmap_id}: missing governance scope {scope}")
            governance_scope.append(scope)

        if not links and not governance_scope:
            errors.append(f"{roadmap_id}: item must link capabilities or governance scope")
        if impact_scope == "none" and (links or governance_scope):
            errors.append(f"{roadmap_id}: impact_scope=none cannot carry governed surfaces")
        if impact_scope == "all_capabilities" and not governance_scope:
            errors.append(f"{roadmap_id}: impact_scope=all_capabilities requires governance_scope")

        normalized_items.append(
            {
                "roadmap_id": roadmap_id,
                "title": title,
                "status": status,
                "source": source_rel,
                "source_anchor": source_anchor,
                "source_sha256": source_hashes.get(source_rel, ""),
                "impact_scope": impact_scope,
                "capabilities": sorted(seen_capabilities),
                "capability_links": sorted(
                    links, key=lambda row: (row["capability_id"], row["relation"])
                ),
                "governance_scope": sorted(set(governance_scope)),
            }
        )

    if errors:
        raise ValueError("\n".join(errors))

    capability_rows: list[dict[str, Any]] = []
    for capability_id, capability in sorted(known.items()):
        roadmap_items = sorted(
            reverse.get(capability_id, []),
            key=lambda row: (row["roadmap_id"], row["relation"]),
        )
        capability_rows.append(
            {
                "capability_id": capability_id,
                "domain": capability["domain"],
                "title": capability["title"]["en"],
                "roadmap_items": roadmap_items,
                "linked": bool(roadmap_items),
            }
        )

    linked_count = sum(row["linked"] for row in capability_rows)
    return {
        "schema_version": SCHEMA_VERSION,
        "constraints": {
            "curated_links_only": True,
            "relationship_rationale_required": True,
            "source_anchor_required": True,
            "runtime_claims": False,
            "production_certification": False,
        },
        "summary": {
            "roadmap_items": len(normalized_items),
            "linked_capabilities": linked_count,
            "unlinked_capabilities": len(capability_rows) - linked_count,
            "relationship_links": sum(len(item["capability_links"]) for item in normalized_items),
            "governance_only_items": sum(
                not item["capability_links"] and bool(item["governance_scope"])
                for item in normalized_items
            ),
            "by_status": dict(sorted(Counter(item["status"] for item in normalized_items).items())),
        },
        "roadmap_items": sorted(normalized_items, key=lambda row: row["roadmap_id"]),
        "capabilities": capability_rows,
    }


def render_outputs(data: dict[str, Any]) -> dict[str, bytes]:
    json_bytes = (json.dumps(data, indent=2, ensure_ascii=False, sort_keys=False) + "\n").encode(
        "utf-8"
    )

    csv_buffer = io.StringIO(newline="")
    writer = csv.DictWriter(
        csv_buffer,
        lineterminator="\n",
        fieldnames=[
            "roadmap_id",
            "title",
            "status",
            "source",
            "source_anchor",
            "impact_scope",
            "capabilities",
            "relations",
            "governance_scope",
        ],
    )
    writer.writeheader()
    for item in data["roadmap_items"]:
        writer.writerow(
            {
                "roadmap_id": item["roadmap_id"],
                "title": item["title"],
                "status": item["status"],
                "source": item["source"],
                "source_anchor": item["source_anchor"],
                "impact_scope": item["impact_scope"],
                "capabilities": ";".join(item["capabilities"]),
                "relations": ";".join(
                    f"{link['capability_id']}:{link['relation']}"
                    for link in item["capability_links"]
                ),
                "governance_scope": ";".join(item["governance_scope"]),
            }
        )
    csv_bytes = csv_buffer.getvalue().encode("utf-8")

    lines = [
        "# Roadmap-to-Capability Linkage",
        "",
        f"- Roadmap items: **{data['summary']['roadmap_items']}**",
        f"- Linked capabilities: **{data['summary']['linked_capabilities']} / {len(data['capabilities'])}**",
        f"- Curated relationship links: **{data['summary']['relationship_links']}**",
        f"- Governance-only items: **{data['summary']['governance_only_items']}**",
        "- Runtime claims: **false**",
        "- Production certification: **false**",
        "",
        "| Item | Status | Impact scope | Capability relationships |",
        "|---|---|---|---|",
    ]
    for item in data["roadmap_items"]:
        relationships = (
            ", ".join(
                f"{link['capability_id']} ({link['relation']})" for link in item["capability_links"]
            )
            or "governance-only"
        )
        lines.append(
            f"| {item['roadmap_id']} | {item['status']} | "
            f"{item['impact_scope']} | {relationships} |"
        )
    report_bytes = ("\n".join(lines) + "\n").encode("utf-8")

    return {
        "roadmap_capability_links.json": json_bytes,
        "roadmap_capability_links.csv": csv_bytes,
        "ROADMAP_CAPABILITY_LINKAGE_REPORT.md": report_bytes,
    }


def render_manifest(
    outputs: dict[str, bytes],
    *,
    root: Path = ROOT,
    source_path: Path = SOURCE,
    registry_path: Path = REGISTRY,
    data: dict[str, Any],
) -> bytes:
    input_paths = {
        source_path.relative_to(root).as_posix(),
        registry_path.relative_to(root).as_posix(),
    }
    input_paths.update(item["source"] for item in data["roadmap_items"])
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "inputs": {path: sha256_file(root / path) for path in sorted(input_paths)},
        "outputs": {name: sha256_bytes(content) for name, content in sorted(outputs.items())},
    }
    return (json.dumps(manifest, indent=2, sort_keys=False) + "\n").encode("utf-8")


def expected_files(
    *,
    root: Path = ROOT,
    source_path: Path = SOURCE,
    registry_path: Path = REGISTRY,
) -> tuple[dict[str, Any], dict[str, bytes]]:
    data = build(root=root, source_path=source_path, registry_path=registry_path)
    outputs = render_outputs(data)
    outputs["roadmap_manifest.json"] = render_manifest(
        outputs,
        root=root,
        source_path=source_path,
        registry_path=registry_path,
        data=data,
    )
    return data, outputs


def generate(
    *,
    root: Path = ROOT,
    source_path: Path = SOURCE,
    registry_path: Path = REGISTRY,
    output_dir: Path = OUTPUT_DIR,
) -> dict[str, Any]:
    data, files = expected_files(root=root, source_path=source_path, registry_path=registry_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    for name, content in files.items():
        (output_dir / name).write_bytes(content)
    return data


def check(
    *,
    root: Path = ROOT,
    source_path: Path = SOURCE,
    registry_path: Path = REGISTRY,
    output_dir: Path = OUTPUT_DIR,
) -> tuple[bool, list[str], dict[str, Any]]:
    data, expected = expected_files(root=root, source_path=source_path, registry_path=registry_path)
    drift: list[str] = []
    for name, content in expected.items():
        target = output_dir / name
        if not target.is_file():
            drift.append(f"missing:{name}")
        elif target.read_bytes() != content:
            drift.append(f"changed:{name}")
    unexpected = (
        sorted(
            path.name
            for path in output_dir.glob("*")
            if path.is_file() and path.name not in expected
        )
        if output_dir.exists()
        else []
    )
    drift.extend(f"unexpected:{name}" for name in unexpected)
    return not drift, drift, data


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--generate", action="store_true")
    mode.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)

    try:
        if args.generate:
            data = generate()
        else:
            ok, drift, data = check()
            if not ok:
                print(
                    "roadmap linkage drift; run --generate: " + ", ".join(drift),
                    file=sys.stderr,
                )
                return 1
    except (OSError, ValueError, json.JSONDecodeError, yaml.YAMLError) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(
        "capability_roadmap_linker_ok "
        f"items={data['summary']['roadmap_items']} "
        f"linked={data['summary']['linked_capabilities']} "
        f"relationships={data['summary']['relationship_links']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
