#!/usr/bin/env python3
"""Guard a D12 logical-identity migration plan against its D08 corpus receipt."""

from __future__ import annotations

import argparse
import functools
import hashlib
import importlib.util
import json
import pathlib
import re
import sys
from collections import Counter, defaultdict
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[2]
CORPUS_GUARD = ROOT / "scripts/architecture/rag_corpus_audit_receipt_guard.py"
PQ_PATH = ROOT / "services/sahool-platform/core/rag/production_qdrant.py"
SCHEMA = "sahool.rag-logical-identity-migration-plan/v1"
_HEX40 = re.compile(r"^[0-9a-f]{40}$")
_FORBIDDEN = {"page_content", "text", "payload", "document_body", "content"}


def _sha256_json(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    return hashlib.sha256(raw).hexdigest()


# التحميلُ مفصولٌ عن النداء ومخزَّن — انظر التعليق المقابل في المخطِّط: ٣٫٥٥ms لكلّ
# `exec_module` مقابل ٩٫٥µs للإسقاط، والنداءُ كان لكلّ صفّ.
@functools.lru_cache(maxsize=1)
def _load_pq():
    spec = importlib.util.spec_from_file_location("rag_d12_guard_pq", PQ_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load canonical retrieval module")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _writer_id(logical: str) -> str:
    """يُستورَد من الكاتب لا يُعاد كتابته — نسخةٌ ثالثة للصيغة تنحرف عن الاثنتين."""
    return _load_pq().canonical_storage_point_id(logical)


@functools.lru_cache(maxsize=1)
def _load_corpus_guard():
    spec = importlib.util.spec_from_file_location("rag_d12_guard_corpus", CORPUS_GUARD)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load corpus audit guard")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _expected_pre_collision(source: dict[str, Any]) -> tuple[str, str | None, str | None]:
    classification = source.get("classification")
    scope = source.get("scope")
    explicit = source.get("explicit_logical_chunk_id")
    explicit = str(explicit).strip() if explicit is not None else None
    explicit = explicit or None
    fallback = source.get("fallback_identity_used") is True
    if classification in {"CANONICAL_ACTIVE", "CANONICAL_GLOBAL_REFERENCE"}:
        return "NOOP_CANONICAL", explicit, None
    if classification == "CANONICAL_QUARANTINE":
        return "NOOP_QUARANTINE", explicit, None
    if classification == "LEGACY_MIGRATABLE":
        if scope == "quarantine":
            return "HOLD_QUARANTINE", None, None
        if fallback or explicit is None:
            return "HOLD_IDENTITY_EVIDENCE", None, None
        return "MIGRATION_CANDIDATE", explicit, _writer_id(explicit)
    if classification == "LEGACY_PROVENANCE_INCOMPLETE":
        return "HOLD_PROVENANCE_EVIDENCE", explicit, None
    if classification == "ORPHANED_UNATTRIBUTED":
        return "HOLD_UNATTRIBUTED", explicit, None
    if classification == "INVALID":
        return "HOLD_INVALID", explicit, None
    return "INVALID_SOURCE_CLASSIFICATION", explicit, None


def findings(
    plan: dict[str, Any], corpus: dict[str, Any], subject_sha: str, subject_tree: str
) -> list[str]:
    out: list[str] = []
    corpus_guard = _load_corpus_guard()
    source_problems = corpus_guard.findings(corpus, subject_sha, subject_tree)
    out.extend(f"source corpus receipt invalid: {problem}" for problem in source_problems)
    if plan.get("schema") != SCHEMA:
        out.append("plan schema mismatch")
    if plan.get("subject_sha") != subject_sha or plan.get("subject_tree") != subject_tree:
        out.append("plan subject identity mismatch")
    if plan.get("collection") != corpus.get("collection"):
        out.append("plan collection mismatch")
    if plan.get("corpus_receipt_sha256") != _sha256_json(corpus):
        out.append("corpus receipt digest mismatch")
    if plan.get("corpus_point_inventory_sha256") != corpus.get("point_inventory_sha256"):
        out.append("corpus point inventory binding mismatch")
    if (
        plan.get("read_only") is not True
        or plan.get("writes_performed") is not False
        or plan.get("migration_authorized") is not False
        or plan.get("authority_promotion") is not False
    ):
        out.append("D12 plan must be read-only/non-authorizing/non-promoting")

    source_rows = (
        corpus.get("point_records") if isinstance(corpus.get("point_records"), list) else []
    )
    plan_rows = plan.get("plan_rows") if isinstance(plan.get("plan_rows"), list) else []
    if plan.get("point_count") != len(plan_rows) or len(plan_rows) != len(source_rows):
        out.append("plan/source point count mismatch")
    by_source = {str(row.get("point_id")): row for row in source_rows if isinstance(row, dict)}
    by_plan = {str(row.get("point_id")): row for row in plan_rows if isinstance(row, dict)}
    if set(by_source) != set(by_plan) or len(by_plan) != len(plan_rows):
        out.append("plan point IDs do not exactly cover source inventory")

    expected: dict[str, tuple[str, str | None, str | None]] = {}
    logical_owners: dict[str, list[str]] = defaultdict(list)
    for point_id, source in by_source.items():
        action, logical, writer = _expected_pre_collision(source)
        expected[point_id] = (action, logical, writer)
        if logical and action in {"NOOP_CANONICAL", "MIGRATION_CANDIDATE"}:
            logical_owners[logical].append(point_id)
    collisions = {logical: ids for logical, ids in logical_owners.items() if len(ids) > 1}

    for point_id, row in by_plan.items():
        forbidden = _FORBIDDEN.intersection(row)
        if forbidden:
            out.append(f"document content leaked in migration row: {sorted(forbidden)}")
        source = by_source.get(point_id)
        if source is None:
            continue
        exp_action, exp_logical, exp_writer = expected[point_id]
        if exp_action == "MIGRATION_CANDIDATE" and exp_logical in collisions:
            exp_action, exp_writer = "HOLD_LOGICAL_ID_COLLISION", None
        if row.get("action") != exp_action:
            out.append(f"migration action mismatch: {point_id}")
        if row.get("canonical_chunk_id") != exp_logical:
            out.append(f"logical identity mismatch: {point_id}")
        if row.get("canonical_writer_point_id") != exp_writer:
            out.append(f"canonical writer point mismatch: {point_id}")
        # الثابتُ هنا «لا يُهاجَر ولا تُرقَّى هويّتُه»، لا «يُحتجَز بهذا الاسم بعينه».
        #
        # كان الشرطُ يفرض `HOLD_IDENTITY_EVIDENCE` حصراً، **فيُدين خطّةً صحيحة**: صفٌّ
        # باستعارةِ مُعرِّفٍ وتصنيفُه `ORPHANED_UNATTRIBUTED` يُنتِج المخطِّطُ له
        # `HOLD_UNATTRIBUTED` بحقّ — وهو احتجازٌ لا يقلّ منعاً — فيرفضه الحارس. قِيس
        # على هذه الشجرة قبل التبنّي: المخطِّطُ والحارسُ يتناقضان على مُدخَلٍ مشروع،
        # والحارسُ هو المخطئ. وحارسٌ يُحمِّر الصوابَ يُدرِّب قارئَه على تخطّيه.
        if source.get("fallback_identity_used") is True:
            if row.get("canonical_chunk_id") is not None:
                out.append(f"storage fallback promoted to logical identity: {point_id}")
            if row.get("action") == "MIGRATION_CANDIDATE":
                out.append(f"storage fallback marked migratable: {point_id}")
        if (
            source.get("classification") == "LEGACY_PROVENANCE_INCOMPLETE"
            and row.get("action") != "HOLD_PROVENANCE_EVIDENCE"
        ):
            out.append(f"provenance-incomplete point marked migratable: {point_id}")

    counts = Counter(str(row.get("action")) for row in plan_rows if isinstance(row, dict))
    if plan.get("action_counts") != dict(sorted(counts.items())):
        out.append("action_counts mismatch")
    if plan.get("migration_candidate_count") != counts["MIGRATION_CANDIDATE"]:
        out.append("migration_candidate_count mismatch")
    if plan.get("identity_evidence_required_count") != counts["HOLD_IDENTITY_EVIDENCE"]:
        out.append("identity_evidence_required_count mismatch")
    if plan.get("provenance_evidence_required_count") != counts["HOLD_PROVENANCE_EVIDENCE"]:
        out.append("provenance_evidence_required_count mismatch")
    if plan.get("logical_id_collision_group_count") != len(collisions):
        out.append("logical_id_collision_group_count mismatch")
    if plan.get("logical_id_collision_point_count") != sum(len(ids) for ids in collisions.values()):
        out.append("logical_id_collision_point_count mismatch")
    if plan.get("plan_rows_sha256") != _sha256_json(plan_rows):
        out.append("plan row digest mismatch")
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", required=True)
    ap.add_argument("--corpus-receipt", required=True)
    ap.add_argument("--subject-sha", required=True)
    ap.add_argument("--subject-tree", required=True)
    args = ap.parse_args(argv)
    subject_sha = args.subject_sha.lower()
    subject_tree = args.subject_tree.lower()
    if not _HEX40.fullmatch(subject_sha) or not _HEX40.fullmatch(subject_tree):
        print("rag_logical_identity_plan_guard_fail invalid subject identity")
        return 1
    try:
        plan = json.loads(pathlib.Path(args.plan).read_text(encoding="utf-8"))
        corpus = json.loads(pathlib.Path(args.corpus_receipt).read_text(encoding="utf-8"))
        problems = findings(plan, corpus, subject_sha, subject_tree)
    except Exception as exc:  # noqa: BLE001
        print(f"rag_logical_identity_plan_guard_fail {exc}")
        return 1
    if problems:
        for problem in problems:
            print("rag_logical_identity_plan_guard_fail", problem)
        return 1
    print(
        "rag_logical_identity_plan_guard_ok "
        f"points={plan['point_count']} candidates={plan['migration_candidate_count']} "
        f"identity_holds={plan['identity_evidence_required_count']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
