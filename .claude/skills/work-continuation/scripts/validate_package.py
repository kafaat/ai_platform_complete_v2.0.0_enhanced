#!/usr/bin/env python3
"""Read-only integrity and contract checks for the UWRP skill package.

No network, Git API, subprocess, workspace mutations, or side effects.
Passing this tool is NOT evidence of a production agent/runtime integration.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

ORIGINAL_V2_1_SHA256 = "98b78578924584b550addc0f6bfc05e58ab3fa07c1bbbff07154a52008ddae2c"
CHECKED_TEMPLATE_NAMES = {
    "state.example.json", "shard-plan.example.json", "shard-receipt.example.json",
    "external-action.example.json", "journal-event.example.json",
    "retention-policy.example.json", "backup-plan.example.json",
}
UNSAFE_FILENAME_PARTS = {".env", "id_rsa", "secret.key", "credentials.json"}
BAD_EXAMPLES = (
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"\bghp_[A-Za-z0-9]{25,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{25,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def key_digest(components: dict[str, object]) -> str:
    """Stable digest of explicitly selected validity inputs (not proof of authenticity)."""
    canonical = json.dumps(components, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return "sha256:" + digest(canonical.encode("utf-8"))


def check_state_contract(data: dict) -> list[str]:
    """Small fail-closed semantic checks beyond the JSON schema."""
    issues: list[str] = []
    if data.get("schema_version") != "uwrp/state/v3":
        issues.append("invalid state schema version")
    if data.get("verification_status") == "VERIFIED_CURRENT" and not (
        data.get("source", {}).get("head") or data.get("source", {}).get("tree")
    ):
        # Non-Git use may rely on a document evidence record, not commit SHAs.
        if data.get("source", {}).get("kind") == "git":
            issues.append("verified Git state requires a recorded head or tree")
    backup = data.get("backup", {})
    if backup.get("status") == "BACKUP_VERIFIED" and not all(
        backup.get(k) for k in ("destination", "remote_sha256", "verified_at")
    ):
        issues.append("backup verified needs remote destination/digest/time")
    checkpoint = data.get("checkpoint", {})
    if checkpoint.get("status") == "DONE_VERIFIED" and data.get("verification_status") != "VERIFIED_CURRENT":
        issues.append("DONE_VERIFIED needs current verified evidence")
    return issues


def check_receipt(data: dict) -> list[str]:
    issues: list[str] = []
    if data.get("schema_version") != "uwrp/shard-receipt/v3":
        issues.append("invalid receipt version")
    if data.get("status") == "NOT_RUN":
        if data.get("exit_code") is not None or any(data.get("counts", {}).values()):
            issues.append("NOT_RUN receipt cannot have execution results")
    if data.get("status") == "PASSED":
        if data.get("exit_code") != 0:
            issues.append("PASSED receipt must have exit_code 0")
        if not (data.get("evidence_sha256") and data.get("finished_at") and data.get("validity_key")):
            issues.append("PASSED receipt requires evidence and validity")
        if data.get("counts", {}).get("failed", 0) or data.get("counts", {}).get("error", 0):
            issues.append("PASSED receipt cannot report failed/error cases")
    if data.get("contiguous_preflight_proven") and data.get("result_scope") != "CONTIGUOUS_PREFLIGHT":
        issues.append("contradiction: contiguous preflight asserted on sharded-only scope")
    return issues


def files_in_package(root: Path) -> list[Path]:
    return sorted(
        p for p in root.rglob("*")
        if p.is_file() and not set(p.relative_to(root).parts).intersection(
            {"__pycache__", ".pytest_cache", ".git"}
        )
    )


def check_manifest(root: Path) -> list[str]:
    problems: list[str] = []
    manifest = root / "SHA256SUMS"
    if not manifest.is_file():
        return ["missing SHA256SUMS"]
    entries: dict[str, str] = {}
    for line in manifest.read_text("utf-8").splitlines():
        match = re.fullmatch(r"([0-9a-f]{64})  ([^\\\x00\n]+)", line)
        if not match:
            problems.append("invalid SHA256SUMS entry")
            continue
        sha, rel = match.groups()
        if rel in entries:
            problems.append(f"duplicate manifest entry {rel}")
        entries[rel] = sha
    actual_files = {p.relative_to(root).as_posix() for p in files_in_package(root) if p.name != "SHA256SUMS"}
    if set(entries) != actual_files:
        problems.append(f"manifest mismatch missing={sorted(actual_files - set(entries))} extra={sorted(set(entries) - actual_files)}")
    for rel, sha in entries.items():
        p = root / rel
        if not p.is_file() or not p.resolve().is_relative_to(root.resolve()):
            problems.append(f"invalid manifest path {rel}")
        elif digest(p.read_bytes()) != sha:
            problems.append(f"changed: {rel}")
    return problems


def validate(root: Path, check_hashes: bool = True) -> list[str]:
    errors: list[str] = []
    root = root.resolve()
    skill = root / "SKILL.md"
    if not skill.is_file():
        return [f"no SKILL.md under {root}"]
    skill_text = skill.read_text("utf-8")
    if not skill_text.startswith("---\n") or not re.search(r"\n---\n", skill_text):
        errors.append("SKILL.md frontmatter missing")
    if not re.search(r"^name: work-continuation$", skill_text, re.M):
        errors.append("SKILL.md name mismatch")
    if not re.search(r"^description:\s*>-", skill_text, re.M):
        errors.append("description metadata missing")
    if len(skill_text.splitlines()) > 500:
        errors.append("SKILL.md > 500 lines; split progressive references")
    expected = root / "references" / "PROTOCOL_v2_1_ORIGINAL.md"
    if not expected.is_file() or digest(expected.read_bytes()) != ORIGINAL_V2_1_SHA256:
        errors.append("v2.1 baseline was modified or is absent")
    for file_ref in re.findall(r"`((?:references|templates|prompts|scripts)/[A-Za-z0-9_.\-]+(?:/[A-Za-z0-9_.\-]+)*)`", skill_text):
        if not (root / file_ref).is_file():
            errors.append(f"missing referenced file: {file_ref}")
    for name in sorted(CHECKED_TEMPLATE_NAMES):
        path = root / "templates" / name
        if not path.is_file():
            errors.append(f"missing template: {name}")
            continue
        try:
            data = json.loads(path.read_text("utf-8"))
        except (json.JSONDecodeError, UnicodeError) as exc:
            errors.append(f"bad JSON {name}: {exc}")
            continue
        if data.get("example_only") is not True and name != "state.example.json":
            errors.append(f"example flag missing for {name}")
        if name == "state.example.json":
            errors.extend(check_state_contract(data))
            if data.get("verification_status") != "RECORDED_UNVERIFIED":
                errors.append("sample state must not claim verified work")
        elif name == "shard-receipt.example.json":
            errors.extend(check_receipt(data))
        elif name == "external-action.example.json" and (data.get("authorization", {}).get("verified") or data.get("status") != "NOT_ATTEMPTED"):
            errors.append("example action must be unapproved and not attempted")
    for path in files_in_package(root):
        if any(part in {"__pycache__", ".git"} for part in path.parts) or path.suffix in {".pyc", ".log"}:
            errors.append(f"unexpected generated or raw log file: {path.relative_to(root)}")
        if any(part.lower() in UNSAFE_FILENAME_PARTS for part in path.parts):
            errors.append(f"suspicious filename: {path.relative_to(root)}")
        if path.suffix in {".md", ".py", ".json", ".txt"}:
            data = path.read_text("utf-8")
            for regex in BAD_EXAMPLES:
                if regex.search(data):
                    errors.append(f"possible exposed key in: {path.relative_to(root)}")
    if check_hashes:
        errors.extend(check_manifest(root))
    return errors


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    ap.add_argument("--skip-hashes", action="store_true", help="for local incremental work before building SHA256SUMS")
    args = ap.parse_args()
    problems = validate(args.root, not args.skip_hashes)
    if problems:
        for issue in problems:
            print("ERROR:", issue)
        return 1
    print("PASS: skill layout, unchanged v2.1, example contracts, secret heuristics and manifest")
    print("LIMIT: read-only package checks; not GitHub, CI, user authorization or production acceptance")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
