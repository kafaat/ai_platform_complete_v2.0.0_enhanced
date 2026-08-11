#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

SCHEMA = "sahool.evidence-manifest/v1"
TRANSPORT = [
    "live_pg_evidence.sha256",
    "live_pg_evidence.attestation.json",
    "live_pg_trusted_root.jsonl",
    "live_pg_verification_record.json",
]


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def build(args: argparse.Namespace) -> dict:
    files = []
    for raw in sorted(set(args.file)):
        p = Path(raw)
        if not p.is_file():
            raise SystemExit(f"MANIFEST_MISSING: {raw}")
        files.append({"path": raw, "sha256": digest(p), "size_bytes": p.stat().st_size})
    return {
        "schema": SCHEMA,
        "closure": {"mode": "exact", "transport_exclusions": list(TRANSPORT)},
        "tested_identity": {"commit_sha": args.tested_commit, "tree_sha": args.tested_tree},
        "source_identity": {"ref": args.source_ref},
        "release_binding": {
            "mode": args.binding_mode,
            "accepted_commit_sha": args.accepted_commit_sha,
            "accepted_tree_sha": args.accepted_tree_sha,
        },
        "files": files,
    }


def canonical_bytes(doc: dict) -> bytes:
    return (
        json.dumps(doc, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", required=True)
    ap.add_argument("--file", action="append", required=True)
    ap.add_argument("--tested-commit", required=True)
    ap.add_argument("--tested-tree", required=True)
    ap.add_argument("--source-ref", required=True)
    ap.add_argument(
        "--binding-mode",
        choices=["pending_final_rerun", "exact_commit", "exact_tree", "tested_merge_to_release"],
        required=True,
    )
    ap.add_argument("--accepted-commit-sha")
    ap.add_argument("--accepted-tree-sha")
    args = ap.parse_args(argv)
    if len(args.tested_commit) != 40 or len(args.tested_tree) != 40:
        raise SystemExit("SOURCE_IDENTITY_MISMATCH: commit/tree must be full SHA")
    if args.binding_mode == "exact_commit" and args.accepted_commit_sha != args.tested_commit:
        raise SystemExit("RELEASE_BINDING_MISMATCH: exact_commit")
    if args.binding_mode == "exact_tree" and args.accepted_tree_sha != args.tested_tree:
        raise SystemExit("RELEASE_BINDING_MISMATCH: exact_tree")
    Path(args.output).write_bytes(canonical_bytes(build(args)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
