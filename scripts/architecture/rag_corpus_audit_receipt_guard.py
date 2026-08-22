#!/usr/bin/env python3
"""Validate a D08 live RAG corpus-audit receipt without promoting authority."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
STATE = ROOT / "docs/architecture/rag_authority_convergence.json"
SCHEMA = "sahool.rag-corpus-audit-receipt/v1"
_HEX40 = re.compile(r"^[0-9a-f]{40}$")
_CLASSIFICATIONS = {
    "CANONICAL_ACTIVE",
    "CANONICAL_GLOBAL_REFERENCE",
    "CANONICAL_QUARANTINE",
    "LEGACY_MIGRATABLE",
    "LEGACY_PROVENANCE_INCOMPLETE",
    "ORPHANED_UNATTRIBUTED",
    "INVALID",
    "UNCLASSIFIED",
}
_FORBIDDEN_RECORD_KEYS = {"page_content", "text", "payload", "document_body", "content"}
# المفرداتُ محصورة: مصدرٌ خارجها يعني مُنتِجاً لا يعرفه هذا العقد، فيُرفَض ولا يُخمَّن.
_LOGICAL_IDENTITY_SOURCES = {
    "metadata.chunk_id",
    "payload.chunk_id",
    "storage_fallback",
    "missing",
}


def _digest(records: list[dict[str, Any]]) -> str:
    raw = json.dumps(records, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    return hashlib.sha256(raw).hexdigest()


def _expected_payload_parity(receipt: dict[str, Any]) -> bool:
    records = receipt.get("point_records")
    if not isinstance(records, list):
        return False
    if receipt.get("exact_count") != receipt.get("scroll_count"):
        return False
    if receipt.get("unclassified_count") != 0:
        return False
    for row in records:
        if not isinstance(row, dict):
            return False
        if (
            row.get("serving_candidate") is True
            and row.get("canonical_serving_eligible") is not True
        ):
            return False
    return True


def findings(receipt: dict[str, Any], subject_sha: str, subject_tree: str) -> list[str]:
    # **حارسٌ يموت بـtraceback لا يُبلِغ.** كانت وثيقةُ الحالة تُقرأ بلا التقاط، فملفٌّ
    # مفقودٌ أو تالف — وهو شائعٌ عند تشغيل السكربت خارج الشجرة — يُخرِج انهياراً بدل
    # سطر فشلٍ مُنسَّق كبقيّة هذه الأداة. وهو صنفُ
    # `GUARD-DIES-PRINTING-ITS-OWN-SUCCESS-UNDER-C-LOCALE-01` من جهة أخرى: رمزُ خروجٍ
    # بلا سببٍ مقروء. أمسكه مراجعٌ آليّ على #884.
    #
    # ويفشل **مغلقاً**: تعذُّرُ قراءة شروط القبول لا يُقرَأ قبولاً.
    out: list[str] = []
    try:
        state = json.loads(STATE.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return [f"corpus audit acceptance contract unreadable: {exc}"]
    acceptance = state.get("corpus_audit_acceptance") or {}
    if receipt.get("schema") != acceptance.get("receipt_schema", SCHEMA):
        out.append("receipt schema mismatch")
    if receipt.get("subject_sha") != subject_sha:
        out.append("receipt subject SHA mismatch")
    if receipt.get("subject_tree") != subject_tree:
        out.append("receipt subject tree mismatch")
    if receipt.get("collection") != acceptance.get("collection", "sahool_agri_kb"):
        out.append("collection mismatch")
    if receipt.get("read_only") is not True or receipt.get("authority_promotion") is not False:
        out.append("receipt must be read-only/non-promoting")
    try:
        datetime.fromisoformat(str(receipt.get("observed_at")).replace("Z", "+00:00"))
    except Exception:
        out.append("invalid observed_at")

    exact = receipt.get("exact_count")
    scroll = receipt.get("scroll_count")
    records = receipt.get("point_records")
    if not isinstance(exact, int) or exact < 0:
        out.append("invalid exact_count")
    if not isinstance(scroll, int) or scroll < 0:
        out.append("invalid scroll_count")
    if isinstance(exact, int) and isinstance(scroll, int) and exact != scroll:
        out.append("exact/scroll count mismatch")
    if not isinstance(records, list):
        out.append("point_records missing")
        records = []
    if isinstance(scroll, int) and len(records) != scroll:
        out.append("point record count mismatch")

    ids: list[str] = []
    class_counts: dict[str, int] = {name: 0 for name in _CLASSIFICATIONS}
    for row in records:
        if not isinstance(row, dict):
            out.append("invalid point record")
            continue
        forbidden = _FORBIDDEN_RECORD_KEYS.intersection(row)
        if forbidden:
            out.append(f"document content leaked in point record: {sorted(forbidden)}")
        point_id = row.get("point_id")
        if not isinstance(point_id, str) or not point_id:
            out.append("point record missing point_id")
        else:
            ids.append(point_id)
        classification = row.get("classification")
        if classification not in _CLASSIFICATIONS:
            out.append(f"unknown classification: {classification}")
        else:
            class_counts[str(classification)] += 1
        # ── D12-PRE — مصدرُ الهويّة المنطقيّة مُعلَنٌ ومتّسق ─────────────────────
        #
        # إيصالٌ بلا هذين الحقلين يمرّ من هنا ثمّ **ينهار** في مخطِّط D12 عند أوّل صفٍّ
        # قانونيّ (`canonical point … lacks explicit logical chunk identity`). ورفضٌ
        # مُسمًّى هنا خيرٌ من انهيارٍ هناك: الحارسُ يقول ما ينقص، والانهيارُ يقول أين وقع.
        source = row.get("logical_identity_source")
        if source not in _LOGICAL_IDENTITY_SOURCES:
            out.append(f"unknown logical_identity_source: {source}")
        else:
            explicit = row.get("explicit_logical_chunk_id")
            has_explicit = isinstance(explicit, str) and explicit.strip() != ""
            if source in {"metadata.chunk_id", "payload.chunk_id"} and not has_explicit:
                out.append(f"declared logical identity source without an identity: {point_id}")
            if source in {"storage_fallback", "missing"} and has_explicit:
                out.append(f"logical identity present but declared absent: {point_id}")
            # **الاتّساق يُفرَض ولا يُفترَض:** الحقلان يصفان الحقيقةَ نفسها، فانحرافُهما
            # يعني أنّ أحدهما كُتِب بيدٍ أو اشتُقّ بمنطقٍ ثانٍ.
            if row.get("fallback_identity_used") is not (source == "storage_fallback"):
                out.append(f"fallback_identity_used disagrees with its source: {point_id}")
        if row.get("scope") == "quarantine" and row.get("serving_candidate") is not False:
            out.append("quarantine point marked serving_candidate")
        if row.get("canonical_serving_eligible") is True and classification not in {
            "CANONICAL_ACTIVE",
            "CANONICAL_GLOBAL_REFERENCE",
        }:
            out.append("noncanonical classification marked serving eligible")
    if len(ids) != len(set(ids)):
        out.append("duplicate point_id in receipt")

    declared_counts = receipt.get("classification_counts")
    if not isinstance(declared_counts, dict):
        out.append("classification_counts missing")
    else:
        for name in _CLASSIFICATIONS:
            if int(declared_counts.get(name, 0)) != class_counts[name]:
                out.append(f"classification count mismatch: {name}")
    if receipt.get("unclassified_count") != class_counts["UNCLASSIFIED"]:
        out.append("unclassified_count mismatch")
    if receipt.get("unclassified_count") != 0:
        out.append("unclassified points remain")

    if records and receipt.get("point_inventory_sha256") != _digest(records):
        out.append("point inventory digest mismatch")
    elif not records and receipt.get("point_inventory_sha256") != _digest([]):
        out.append("point inventory digest mismatch")

    expected = _expected_payload_parity(receipt)
    if receipt.get("canonical_payload_parity") is not expected:
        out.append("canonical_payload_parity inconsistent with inventory")
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--receipt", required=True)
    ap.add_argument("--subject-sha", required=True)
    ap.add_argument("--subject-tree", required=True)
    args = ap.parse_args(argv)
    subject_sha = args.subject_sha.lower()
    subject_tree = args.subject_tree.lower()
    if not _HEX40.fullmatch(subject_sha) or not _HEX40.fullmatch(subject_tree):
        print("rag_corpus_audit_receipt_fail invalid subject identity")
        return 1
    try:
        receipt = json.loads(Path(args.receipt).read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        print("rag_corpus_audit_receipt_fail unreadable receipt", exc)
        return 1
    problems = findings(receipt, subject_sha, subject_tree)
    if problems:
        for problem in problems:
            print("rag_corpus_audit_receipt_fail", problem)
        return 1
    print(
        "rag_corpus_audit_receipt_ok "
        f"points={receipt['scroll_count']} parity={str(receipt['canonical_payload_parity']).lower()} "
        f"unclassified={receipt['unclassified_count']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
