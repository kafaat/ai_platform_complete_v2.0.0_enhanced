#!/usr/bin/env python3
"""Generate deterministic capability history from committed static baselines.

The history is descriptive only. It never infers runtime verification or production
certification, and it validates baseline identity before producing outputs.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
BASELINES = ROOT / "docs/capability-registry/release/baselines"
OUT = ROOT / "docs/capability-registry/generated/release-history"
REGISTRY = ROOT / "docs/capability-registry/generated/capability_registry.json"
SCHEMA_VERSION = "1.0.0"
OUTPUT_NAMES = (
    "capability_release_history.json",
    "capability_release_history.csv",
    "CAPABILITY_RELEASE_HISTORY.md",
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path}: expected JSON object")
    return data


def canonical_ids() -> set[str]:
    registry = load_json(REGISTRY)
    return {str(row["id"]) for row in registry.get("capabilities", [])}


def validate_baseline(path: Path, data: dict[str, Any], expected_ids: set[str]) -> dict[str, Any]:
    errors: list[str] = []
    if str(data.get("schema_version")) != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")
    sequence = data.get("sequence")
    if not isinstance(sequence, int) or sequence < 1:
        errors.append("sequence must be a positive integer")
    label = str(data.get("label") or "").strip()
    if not label:
        errors.append("label is required")
    constraints = data.get("constraints")
    if not isinstance(constraints, dict):
        errors.append("constraints must be a mapping")
        constraints = {}
    for key in ("runtime_claims", "production_certification_inferred"):
        if constraints.get(key) is not False:
            errors.append(f"constraints.{key} must be false")
    caps = data.get("capabilities")
    if not isinstance(caps, list):
        errors.append("capabilities must be a list")
        caps = []
    by_id: dict[str, dict[str, Any]] = {}
    for pos, row in enumerate(caps, start=1):
        if not isinstance(row, dict):
            errors.append(f"capabilities[{pos}] must be an object")
            continue
        cid = str(row.get("capability_id") or "")
        if not cid:
            errors.append(f"capabilities[{pos}].capability_id is required")
            continue
        if cid in by_id:
            errors.append(f"duplicate capability_id {cid}")
        by_id[cid] = row
        if row.get("runtime_verified") is not False:
            errors.append(f"{cid}: runtime_verified must remain false in static history")
        if row.get("production_certified") is not False:
            errors.append(f"{cid}: production_certified must remain false in static history")
        if not isinstance(row.get("mapped"), bool):
            errors.append(f"{cid}: mapped must be boolean")
        if not isinstance(row.get("human_adjudicated_evidence_count"), int):
            errors.append(f"{cid}: human_adjudicated_evidence_count must be integer")
    ids = set(by_id)
    if ids != expected_ids:
        errors.append(
            f"capability identity mismatch: missing={sorted(expected_ids - ids)} extra={sorted(ids - expected_ids)}"
        )
    summary = data.get("summary")
    if not isinstance(summary, dict):
        errors.append("summary must be a mapping")
        summary = {}
    if summary.get("capabilities") != len(expected_ids):
        errors.append(f"summary.capabilities must equal {len(expected_ids)}")
    if summary.get("runtime_verified") != 0:
        errors.append("summary.runtime_verified must be 0 for static history")
    if summary.get("production_certified") != 0:
        errors.append("summary.production_certified must be 0 for static history")
    source_hashes = data.get("source_hashes")
    if not isinstance(source_hashes, dict) or not source_hashes:
        errors.append("source_hashes must be a non-empty mapping")
    if errors:
        raise ValueError(f"{path.relative_to(ROOT)}:\n- " + "\n- ".join(errors))
    return {
        "sequence": sequence,
        "label": label,
        "source_ref": str(data.get("source_ref") or ""),
        "baseline_file": path.relative_to(ROOT).as_posix(),
        "sha256": sha256(path),
        "summary": summary,
        "capabilities": by_id,
    }


def load_baselines() -> list[dict[str, Any]]:
    if not BASELINES.is_dir():
        raise ValueError("capability release baseline directory is missing")
    expected_ids = canonical_ids()
    rows = [
        validate_baseline(path, load_json(path), expected_ids)
        for path in sorted(BASELINES.glob("*.json"))
    ]
    if len(rows) < 2:
        raise ValueError("at least two committed capability baselines are required")
    sequences = [row["sequence"] for row in rows]
    labels = [row["label"] for row in rows]
    if len(sequences) != len(set(sequences)):
        raise ValueError("baseline sequences must be unique")
    if len(labels) != len(set(labels)):
        raise ValueError("baseline labels must be unique")
    rows.sort(key=lambda row: row["sequence"])
    if [row["sequence"] for row in rows] != list(
        range(rows[0]["sequence"], rows[0]["sequence"] + len(rows))
    ):
        raise ValueError("baseline sequences must be contiguous")
    return rows


def build() -> dict[str, Any]:
    baselines = load_baselines()
    releases: list[dict[str, Any]] = []
    previous: dict[str, Any] | None = None
    for row in baselines:
        current = row["capabilities"]
        if previous is None:
            added = sorted(current)
            removed: list[str] = []
            modified: list[str] = []
        else:
            before = previous["capabilities"]
            added = sorted(set(current) - set(before))
            removed = sorted(set(before) - set(current))
            modified = sorted(
                cid for cid in set(before) & set(current) if before[cid] != current[cid]
            )
        summary = row["summary"]
        releases.append(
            {
                "sequence": row["sequence"],
                "label": row["label"],
                "source_ref": row["source_ref"],
                "baseline_file": row["baseline_file"],
                "sha256": row["sha256"],
                "capabilities": summary["capabilities"],
                "capabilities_mapped": summary["capabilities_mapped"],
                "capabilities_unmapped": summary["capabilities_unmapped"],
                "human_adjudications_applied": summary.get("human_adjudications_applied", 0),
                "average_assessed_maturity": summary["average_assessed_maturity"],
                "benchmarked": summary["benchmarked"],
                "roadmap_linked": summary["roadmap_linked"],
                "runtime_verified": summary["runtime_verified"],
                "production_certified": summary["production_certified"],
                "added_from_previous": added,
                "removed_from_previous": removed,
                "modified_from_previous": modified,
            }
        )
        previous = row
    return {
        "schema_version": SCHEMA_VERSION,
        "release_count": len(releases),
        "constraints": {
            "static_baselines_only": True,
            "runtime_claims": False,
            "production_certification_inferred": False,
            "baseline_identity_validated_against_registry": True,
        },
        "releases": releases,
    }


def render(data: dict[str, Any]) -> dict[str, bytes]:
    outputs: dict[str, bytes] = {}
    outputs["capability_release_history.json"] = (
        json.dumps(data, indent=2, ensure_ascii=False, sort_keys=False) + "\n"
    ).encode("utf-8")

    sio = io.StringIO(newline="")
    fields = [
        "sequence",
        "label",
        "source_ref",
        "baseline_file",
        "sha256",
        "capabilities",
        "capabilities_mapped",
        "capabilities_unmapped",
        "human_adjudications_applied",
        "average_assessed_maturity",
        "benchmarked",
        "roadmap_linked",
        "runtime_verified",
        "production_certified",
        "added_count",
        "removed_count",
        "modified_count",
    ]
    writer = csv.DictWriter(sio, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    for row in data["releases"]:
        writer.writerow(
            {
                **{key: row[key] for key in fields[:-3]},
                "added_count": len(row["added_from_previous"]),
                "removed_count": len(row["removed_from_previous"]),
                "modified_count": len(row["modified_from_previous"]),
            }
        )
    outputs["capability_release_history.csv"] = sio.getvalue().encode("utf-8")

    lines = [
        "# Capability Release History",
        "",
        "> Committed static baselines only. Runtime and production status are never inferred.",
        "",
        "| Seq | Release | Mapped | Benchmark | Roadmap | Adjudications | Added | Removed | Modified | Runtime | Production |",
        "|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in data["releases"]:
        lines.append(
            f"| {row['sequence']} | {row['label']} | {row['capabilities_mapped']}/{row['capabilities']} | "
            f"{row['benchmarked']}/{row['capabilities']} | {row['roadmap_linked']}/{row['capabilities']} | "
            f"{row['human_adjudications_applied']} | {len(row['added_from_previous'])} | "
            f"{len(row['removed_from_previous'])} | {len(row['modified_from_previous'])} | "
            f"{row['runtime_verified']} | {row['production_certified']} |"
        )
    outputs["CAPABILITY_RELEASE_HISTORY.md"] = ("\n".join(lines) + "\n").encode("utf-8")
    return outputs


def manifest(outputs: dict[str, bytes]) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "inputs": {
            path.relative_to(ROOT).as_posix(): sha256(path)
            for path in sorted(BASELINES.glob("*.json"))
        },
        "outputs": {
            name: hashlib.sha256(content).hexdigest() for name, content in sorted(outputs.items())
        },
    }


def write(outputs: dict[str, bytes]) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, content in outputs.items():
        (OUT / name).write_bytes(content)
    (OUT / "history_manifest.json").write_text(
        json.dumps(manifest(outputs), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def check(outputs: dict[str, bytes]) -> list[str]:
    errors: list[str] = []
    for name, content in outputs.items():
        path = OUT / name
        if not path.exists():
            errors.append(f"missing:{name}")
        elif path.read_bytes() != content:
            errors.append(f"drift:{name}")
    expected_manifest = manifest(outputs)
    path = OUT / "history_manifest.json"
    if not path.exists():
        errors.append("missing:history_manifest.json")
    elif load_json(path) != expected_manifest:
        errors.append("drift:history_manifest.json")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--generate", action="store_true")
    group.add_argument("--check", action="store_true")
    args = parser.parse_args()
    try:
        data = build()
        outputs = render(data)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    if args.generate:
        write(outputs)
        print(f"capability_release_history_ok releases={data['release_count']}")
        return 0
    errors = check(outputs)
    if errors:
        print("capability release history drift:\n- " + "\n- ".join(errors), file=sys.stderr)
        return 1
    print(f"capability_release_history_ok releases={data['release_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
