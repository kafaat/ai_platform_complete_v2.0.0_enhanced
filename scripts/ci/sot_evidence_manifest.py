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
        # هويّةُ التشغيل المُنتِج تُكتَب **في الموضوع الموقَّع نفسه**: الشهادة تشهد
        # للبايتات، والبايتات تحمل مَن أنتجها (run_id · run_attempt · الحدث · مسار
        # الـworkflow). فيستطيع المُعتمِد لاحقاً إغلاق الهويّة على الـtuple الكاملة
        # بين هذا البيان وخلاصة التشغيل المقروءة من الواجهة — لا على SHA وحده.
        "producer_identity": {
            "repository": args.producer_repository,
            "workflow_path": args.producer_workflow_path,
            "run_id": args.producer_run_id,
            "run_attempt": args.producer_run_attempt,
            "event": args.producer_event,
        },
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
        # `tested_merge_to_release` منزوعٌ عمداً: الحارس يشترط له `binding_evidence`
        # وهذه الأداة لا تُنتِجه قطّ، فالوضع كان **غير قابل للبلوغ** — خيارٌ يَعِد
        # بضمانٍ لا يُمنَح. يعود حين يُصمَّم دليلُ الربط، لا قبله.
        choices=["pending_final_rerun", "exact_commit", "exact_tree"],
        required=True,
    )
    ap.add_argument("--accepted-commit-sha")
    ap.add_argument("--accepted-tree-sha")
    # هويّة المُنتِج إلزاميّة لا اختياريّة: بيانٌ بلا مُنتِجٍ مُسمّى لا يقبل إغلاقَ
    # هويّة التشغيل لاحقاً، وجعلُها اختياريّة يعيد فتح الثغرة التي تُغلَق هنا.
    ap.add_argument("--producer-repository", required=True)
    ap.add_argument("--producer-workflow-path", required=True)
    ap.add_argument("--producer-run-id", required=True)
    ap.add_argument("--producer-run-attempt", required=True)
    ap.add_argument("--producer-event", required=True)
    args = ap.parse_args(argv)
    if len(args.tested_commit) != 40 or len(args.tested_tree) != 40:
        raise SystemExit("SOURCE_IDENTITY_MISMATCH: commit/tree must be full SHA")
    # قيمُ البيئة تُقاس قبل أن تُوقَّع: `GITHUB_RUN_ID` غير مضبوطة تصل "unset" أو
    # فارغة، وتوقيعُ هويّةٍ فارغة يجعل الإغلاق اللاحق يطابق فراغاً بفراغ.
    if not args.producer_run_id.isdigit() or not args.producer_run_attempt.isdigit():
        raise SystemExit("PRODUCER_IDENTITY_INVALID: run_id/run_attempt must be numeric")
    if "/" not in args.producer_repository:
        raise SystemExit("PRODUCER_IDENTITY_INVALID: repository must be owner/name")
    if not args.producer_workflow_path or not args.producer_event:
        raise SystemExit("PRODUCER_IDENTITY_INVALID: workflow_path/event must be non-empty")
    # **الحقلُ غير المستعمَل في وضعٍ ما ليس حرّاً.** الفحص القديم كان يتأكّد من
    # الحقل الذي يقرؤه الحارس وحده، فيُنتِج بياناً **متناقضاً داخليّاً**: يقول
    # «الالتزام مطابق» ويحمل شجرةً مخالفة، ويمرّ لأنّ أحداً لا يقرؤها. والبيان
    # وثيقةٌ تُقرأ كاملةً لاحقاً، لا مُدخَلاً لدالّةٍ واحدة.
    if args.binding_mode == "pending_final_rerun":
        if args.accepted_commit_sha is not None or args.accepted_tree_sha is not None:
            raise SystemExit("RELEASE_BINDING_MISMATCH: pending_final_rerun")
    elif args.binding_mode == "exact_commit":
        if args.accepted_commit_sha != args.tested_commit:
            raise SystemExit("RELEASE_BINDING_MISMATCH: exact_commit")
        if args.accepted_tree_sha is not None and args.accepted_tree_sha != args.tested_tree:
            raise SystemExit("RELEASE_BINDING_MISMATCH: exact_commit tree")
    elif args.binding_mode == "exact_tree":
        if args.accepted_tree_sha != args.tested_tree:
            raise SystemExit("RELEASE_BINDING_MISMATCH: exact_tree")
        if args.accepted_commit_sha is not None and args.accepted_commit_sha != args.tested_commit:
            raise SystemExit("RELEASE_BINDING_MISMATCH: exact_tree commit")
    Path(args.output).write_bytes(canonical_bytes(build(args)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
