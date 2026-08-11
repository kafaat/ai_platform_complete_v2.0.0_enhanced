#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

LEVELS = {"L0": 0, "L1": 1, "L2": 2, "L3": 3, "L4": 4, "L5": 5}
REASONS = {
    "MANIFEST_MISSING",
    "MANIFEST_NON_CANONICAL",
    "MANIFEST_CLOSURE_MISMATCH",
    "SUBJECT_DIGEST_MISMATCH",
    "MANIFEST_NOT_ATTESTED",
    "ATTESTATION_LOOKUP_UNAVAILABLE",
    "ATTESTATION_CRYPTO_INVALID",
    "TRUST_ROOT_INVALID",
    "SIGNER_REPOSITORY_MISMATCH",
    "SIGNER_WORKFLOW_MISMATCH",
    "OIDC_ISSUER_MISMATCH",
    "SOURCE_IDENTITY_MISMATCH",
    "RELEASE_BINDING_MISMATCH",
    "POLICY_MISMATCH",
    "TOOLCHAIN_MISMATCH",
    "VERIFIER_INTERNAL_ERROR",
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("document is not an object")
    return value


def canonical_manifest_bytes(doc: dict) -> bytes:
    return (
        json.dumps(doc, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def validate_manifest(manifest_path: Path, manifest: dict, artifact_files: list[Path]) -> None:
    if manifest.get("schema") != "sahool.evidence-manifest/v1":
        raise RuntimeError("POLICY_MISMATCH")
    if manifest_path.read_bytes() != canonical_manifest_bytes(manifest):
        raise RuntimeError("MANIFEST_NON_CANONICAL")
    entries = manifest.get("files")
    if not isinstance(entries, list) or not entries:
        raise RuntimeError("MANIFEST_MISSING")
    expected_paths = set()
    for item in entries:
        if not isinstance(item, dict) or not isinstance(item.get("path"), str):
            raise RuntimeError("MANIFEST_NON_CANONICAL")
        path = Path(item["path"])
        expected_paths.add(path.as_posix())
        if not path.is_file():
            raise RuntimeError("MANIFEST_MISSING")
        actual_digest = sha256(path)
        expected_digest = item.get("sha256")
        if actual_digest != expected_digest:
            raise RuntimeError("SUBJECT_DIGEST_MISMATCH")
        if path.stat().st_size != item.get("size_bytes"):
            raise RuntimeError("SUBJECT_DIGEST_MISMATCH")
    exclusions = set(manifest.get("closure", {}).get("transport_exclusions", []))
    allowed_paths = expected_paths | exclusions | {manifest_path.as_posix()}
    actual_paths = {p.as_posix() for p in artifact_files}
    if actual_paths != allowed_paths:
        raise RuntimeError("MANIFEST_CLOSURE_MISMATCH")


def build_gh_command(
    *,
    gh: str,
    subject: Path,
    bundle: Path,
    trusted_root: Path,
    policy: dict,
    tested_commit: str,
    source_ref: str,
) -> list[str]:
    return [
        gh,
        "attestation",
        "verify",
        str(subject),
        "--repo",
        policy["repository"],
        "--bundle",
        str(bundle),
        "--custom-trusted-root",
        str(trusted_root),
        "--predicate-type",
        policy["predicate_type"],
        "--signer-workflow",
        policy["signer_workflow"],
        "--cert-oidc-issuer",
        policy["oidc_issuer"],
        "--source-digest",
        tested_commit,
        "--source-ref",
        source_ref,
        "--deny-self-hosted-runners",
        "--format",
        "json",
    ]


def verify_subject(
    subject: Path,
    *,
    gh: str,
    bundle: Path,
    trusted_root: Path,
    policy: dict,
    tested_commit: str,
    source_ref: str,
) -> dict:
    proc = subprocess.run(
        build_gh_command(
            gh=gh,
            subject=subject,
            bundle=bundle,
            trusted_root=trusted_root,
            policy=policy,
            tested_commit=tested_commit,
            source_ref=source_ref,
        ),
        text=True,
        encoding="utf-8",
        capture_output=True,
    )
    returncode = proc.returncode
    if returncode != 0:
        raise RuntimeError("ATTESTATION_CRYPTO_INVALID")
    try:
        parsed = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("ATTESTATION_CRYPTO_INVALID") from exc
    if not isinstance(parsed, list) or not parsed:
        raise RuntimeError("ATTESTATION_CRYPTO_INVALID")
    return {"subject": str(subject), "gh_result_count": len(parsed)}


def release_bound(manifest: dict) -> bool:
    tested = manifest["tested_identity"]
    binding = manifest["release_binding"]
    mode = binding.get("mode")
    if mode == "pending_final_rerun":
        return False
    if mode == "exact_commit":
        return binding.get("accepted_commit_sha") == tested.get("commit_sha")
    if mode == "exact_tree":
        return binding.get("accepted_tree_sha") == tested.get("tree_sha")
    if mode == "tested_merge_to_release":
        return bool(
            binding.get("accepted_commit_sha")
            and binding.get("accepted_tree_sha")
            and binding.get("binding_evidence")
        )
    raise RuntimeError("RELEASE_BINDING_MISMATCH")


def evidence_passes() -> bool:
    try:
        ev = load_json(Path("live_pg_evidence.json"))
        role = load_json(Path("live_pg_role_closure.json"))
    except (OSError, ValueError, json.JSONDecodeError):
        return False
    return ev.get("verdict") == "PASS" and role.get("verdict") == "PASS"


def toolchain(gh: str, policy: dict) -> dict:
    proc = subprocess.run([gh, "--version"], text=True, encoding="utf-8", capture_output=True)
    if proc.returncode != 0:
        raise RuntimeError("TOOLCHAIN_MISMATCH")
    first = proc.stdout.splitlines()[0] if proc.stdout else ""
    expected = policy["gh_cli"]["version"]
    if f"gh version {expected}" not in first:
        raise RuntimeError("TOOLCHAIN_MISMATCH")
    return {"gh_version": first, "gh_binary_sha256": sha256(Path(gh))}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--policy", required=True)
    ap.add_argument("--bundle", required=True)
    ap.add_argument("--trusted-root", required=True)
    ap.add_argument("--artifact-file", action="append", required=True)
    ap.add_argument("--required-assurance", choices=list(LEVELS), default="L3")
    ap.add_argument("--output", required=True)
    ap.add_argument("--gh-bin")
    args = ap.parse_args(argv)

    record = {"verdict": "BLOCKED", "reason_codes": [], "assurance_level": "L0"}
    try:
        manifest_path, policy_path = Path(args.manifest), Path(args.policy)
        bundle, trusted_root = Path(args.bundle), Path(args.trusted_root)
        if not manifest_path.is_file():
            raise RuntimeError("MANIFEST_MISSING")
        if not bundle.is_file():
            raise RuntimeError("ATTESTATION_LOOKUP_UNAVAILABLE")
        if not trusted_root.is_file() or trusted_root.stat().st_size == 0:
            raise RuntimeError("TRUST_ROOT_INVALID")
        manifest, policy = load_json(manifest_path), load_json(policy_path)
        validate_manifest(manifest_path, manifest, [Path(x) for x in args.artifact_file])
        tested = manifest["tested_identity"]
        source_ref = manifest["source_identity"]["ref"]
        gh = args.gh_bin or shutil.which("gh")
        # يُحلّ إلى مسارٍ فعليّ قبل أيّ استعمال: البصمة جزءٌ من سجلّ التحقّق،
        # واسمُ أمرٍ لا يُبصَم. وتعذّرُ الحلّ عطلُ أداةٍ لا عطلٌ داخليّ.
        if gh:
            gh = shutil.which(gh) or (gh if Path(gh).is_file() else None)
        if not gh:
            raise RuntimeError("TOOLCHAIN_MISMATCH")
        tc = toolchain(gh, policy)
        subjects = [Path(x["path"]) for x in manifest["files"]] + [manifest_path]
        verified = [
            verify_subject(
                s,
                gh=gh,
                bundle=bundle,
                trusted_root=trusted_root,
                policy=policy,
                tested_commit=tested["commit_sha"],
                source_ref=source_ref,
            )
            for s in subjects
        ]
        level = "L3"
        if release_bound(manifest):
            level = "L4"
        if level == "L4" and evidence_passes():
            level = "L5"
        if LEVELS[level] < LEVELS[args.required_assurance]:
            raise RuntimeError("RELEASE_BINDING_MISMATCH")
        record.update(
            {
                "verdict": "VERIFIED",
                "reason_codes": [],
                "assurance_level": level,
                "manifest_sha256": sha256(manifest_path),
                "policy_sha256": sha256(policy_path),
                "trusted_root": {
                    "sha256": sha256(trusted_root),
                    "source": "gh attestation trusted-root",
                },
                "attestation_bundle_sha256": sha256(bundle),
                "verification_toolchain": tc,
                "verifier_sha256": sha256(Path(__file__)),
                "tested_identity": tested,
                "release_binding": manifest["release_binding"],
                "verified_subjects": verified,
            }
        )
    except RuntimeError as e:
        reason = str(e) if str(e) in REASONS else "VERIFIER_INTERNAL_ERROR"
        record["reason_codes"] = [reason]
    except Exception:
        record["reason_codes"] = ["VERIFIER_INTERNAL_ERROR"]

    Path(args.output).write_text(
        json.dumps(record, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return 0 if record["verdict"] == "VERIFIED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
