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


def require_mapping(value: object, reason: str) -> dict:
    """قاموسٌ أو سببٌ دقيق — لا `KeyError` يُبلَّغ عطلاً داخليّاً."""
    if not isinstance(value, dict):
        raise RuntimeError(reason)
    return value


def require_nonempty_str(mapping: dict, key: str, reason: str) -> str:
    value = mapping.get(key)
    if not isinstance(value, str) or not value:
        raise RuntimeError(reason)
    return value


def validate_policy(policy: dict) -> dict:
    """السياسة تُتحقَّق **قبل** بناء الأمر أو فحص الأداة.

    الفهرسة المباشرة تُحوِّل حقلاً ناقصاً إلى `KeyError` ⇒ `VERIFIER_INTERNAL_ERROR`،
    فيبحث قارئ السجلّ عن عطبٍ في المُصادِق بينما العطب في **السياسة**. والفشل
    مغلقٌ في الحالين، لكنّ السبب المبهم يُطيل التشخيص ويُخفي مَن يُصلِح.
    """
    require_mapping(policy, "POLICY_MISMATCH")
    for key in ("repository", "predicate_type", "signer_workflow", "oidc_issuer"):
        require_nonempty_str(policy, key, "POLICY_MISMATCH")
    gh_cli = require_mapping(policy.get("gh_cli"), "POLICY_MISMATCH")
    require_nonempty_str(gh_cli, "version", "POLICY_MISMATCH")
    return policy


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
    # الإغلاق عقدٌ يُتحقَّق، لا حقلٌ يُقرأ بافتراض شكله: `.get("closure", {})`
    # يبتلع قاموساً مفقوداً، و`set(...)` على غير قائمةٍ نصّيّة يرمي `TypeError`
    # فيُبلَّغ عطلاً داخليّاً. والوضع نفسه لم يكن مفحوصاً أصلاً رغم أنّ السياسة
    # تفترضه `exact`.
    closure = require_mapping(manifest.get("closure"), "MANIFEST_NON_CANONICAL")
    if closure.get("mode") != "exact":
        raise RuntimeError("MANIFEST_CLOSURE_MISMATCH")
    raw_exclusions = closure.get("transport_exclusions")
    if not isinstance(raw_exclusions, list):
        raise RuntimeError("MANIFEST_NON_CANONICAL")
    if any(not isinstance(x, str) or not x for x in raw_exclusions):
        raise RuntimeError("MANIFEST_NON_CANONICAL")
    if len(raw_exclusions) != len(set(raw_exclusions)):
        raise RuntimeError("MANIFEST_NON_CANONICAL")
    exclusions = set(raw_exclusions)
    # وملفٌّ لا يكون **موضوعاً موقَّعاً ومُستثنىً نقلاً** في آنٍ واحد: ذلك يُخرِج
    # بايتاته من الإغلاق بينما يُحسَب مُغطّىً.
    if exclusions & expected_paths:
        raise RuntimeError("MANIFEST_CLOSURE_MISMATCH")
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


def release_bound(manifest: dict, policy: dict, source_ref: str) -> bool:
    """أهذا الدليل **مربوطٌ بإصدار**؟ — والمرجع شرطٌ أوّل لا تفصيلٌ أخير.

    الضمان دالّةٌ في **من أين** جاء الدليل، لا في اتّساق بصماته وحده. وكان هذا
    الفحص يقيس تطابق الالتزام/الشجرة ولا يسأل عن المرجع إطلاقاً، فبلغت دفعةٌ إلى
    فرع عملٍ غير محميّ المستوى **L5**: ‏`push` + `exact_commit` + أدلّة حيّة ناجحة
    ⇒ L5، على `refs/heads/claude/…`. مقيسٌ بالحادثة لا مُفترَضاً:
    ‏`attestation/40374289` على `ffc29415` (‏`UNPROTECTED-BRANCH-CAN-ATTAIN-L5-01`).

    والقائمة تُقرأ من **السياسة المُصدَّرة** لا من YAML: شرطٌ في `ci.yml` وحده
    يحرس مساراً واحداً، ويستطيع أيّ workflow آخر تمرير `exact_commit` من فرعٍ غير
    معتمد. والحكم داخل الحارس يسري على كلّ من يستدعيه.

    و`tested_merge_to_release` يُقاس بمرجعه المقبول لا بمصدره — لأنّ غرض الوضع أنّ
    المصدر **ليس** الإصدار. وغيابُ ذلك المرجع رفضٌ لا تساهُل: وضعٌ يعجز عن تسمية
    إصداره لا يُمنَح ضمانَ إصدار.
    """
    tested = manifest["tested_identity"]
    binding = manifest["release_binding"]
    mode = binding.get("mode")
    if mode == "pending_final_rerun":
        return False

    release_refs = policy.get("release_refs")
    if not isinstance(release_refs, list) or not release_refs:
        # سياسةٌ بلا قائمة مراجع لا تُقرَأ «كلّ المراجع مقبولة» — تُقرَأ عقداً ناقصاً.
        raise RuntimeError("RELEASE_REF_POLICY_MISSING")
    # **حقلٌ متقاطعٌ مخالف يُرفض ولو لم يُستعمَل في هذا الوضع.** بيانٌ يقول
    # «الالتزام مطابق» ويحمل شجرةً مخالفة متناقضٌ داخليّاً؛ وسكوتُ الحارس عنه
    # يجعل التناقض يمرّ لأنّه لا يقرأ ذلك الحقل — والمُصادِق لا يفترض أنّ البيان
    # جاء من الأداة الرسميّة.
    if mode in ("exact_commit", "exact_tree"):
        # هذان الوضعان يقولان «المصدر المُختبَر **هو** الإصدار» — فيُقاسان بمرجعه.
        if source_ref not in release_refs:
            return False
    if mode == "exact_commit":
        if binding.get("accepted_commit_sha") != tested.get("commit_sha"):
            return False
        other = binding.get("accepted_tree_sha")
        return other is None or other == tested.get("tree_sha")
    if mode == "exact_tree":
        if binding.get("accepted_tree_sha") != tested.get("tree_sha"):
            return False
        other = binding.get("accepted_commit_sha")
        return other is None or other == tested.get("commit_sha")
    if mode == "tested_merge_to_release":
        # غرض الوضع أنّ المصدر ليس الإصدار، فالمقياس مرجعُ الإصدار الذي يسمّيه هو.
        return bool(
            binding.get("accepted_ref") in release_refs
            and binding.get("accepted_commit_sha")
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


def resolve_executable(value: str | None) -> str:
    """يحلّ الأداة إلى **مسارٍ فعليّ** مرّةً واحدة قبل أيّ استعمال.

    البصمة جزءٌ من سجلّ التحقّق، واسمُ أمرٍ لا يُبصَم: `--gh-bin gh` ينجح عبر
    `PATH` في `subprocess` ثمّ يسقط في `sha256(Path("gh"))`، فيُبلَّغ خطأً
    داخليّاً وسببُه أنّ الأداة لم تُحلَّ. و`resolve()` يفكّ الوصلات الرمزيّة
    فتصير **البايتات المُبصَمة عين ما استُدعي** — لا ملفّاً يشير إليه.
    """
    candidate = value or "gh"
    if "/" in candidate:
        path = Path(candidate).resolve()
        if not path.is_file():
            raise RuntimeError("TOOLCHAIN_MISMATCH")
        return str(path)
    resolved = shutil.which(candidate)
    if not resolved:
        raise RuntimeError("TOOLCHAIN_MISMATCH")
    return str(Path(resolved).resolve())


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
        manifest = load_json(manifest_path)
        policy = validate_policy(load_json(policy_path))
        validate_manifest(manifest_path, manifest, [Path(x) for x in args.artifact_file])
        tested = require_mapping(manifest.get("tested_identity"), "SOURCE_IDENTITY_MISMATCH")
        source = require_mapping(manifest.get("source_identity"), "SOURCE_IDENTITY_MISMATCH")
        require_nonempty_str(tested, "commit_sha", "SOURCE_IDENTITY_MISMATCH")
        source_ref = require_nonempty_str(source, "ref", "SOURCE_IDENTITY_MISMATCH")
        gh = resolve_executable(args.gh_bin)
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
        if release_bound(manifest, policy, source_ref):
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
