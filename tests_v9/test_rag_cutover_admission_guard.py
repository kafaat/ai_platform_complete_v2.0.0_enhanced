from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.security]
ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/architecture/rag_cutover_admission_guard.py"


def _run(*args: str):
    p = subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
        timeout=60,
    )
    return p.returncode, json.loads(p.stdout)


def _receipt(tmp_path: Path, subject: str) -> Path:
    data = {
        "schema": "sahool.rag-live-parity-receipt/v1",
        "observed_at": datetime.now(UTC).isoformat(),
        "subject_sha": subject,
        "embedding_contract_sha256": hashlib.sha256(
            (ROOT / "docs/architecture/rag_embedding_contract.json").read_bytes()
        ).hexdigest(),
        "embedding_provider": "ollama",
        "embedding_model": "nomic-embed-text",
        "collection": "sahool_agri_kb",
        "vector_size": 768,
        "query_count": 5,
        "comparable_query_count": 5,
        "min_jaccard": 0.8,
        "mean_jaccard": 0.9,
        "read_only": True,
        "authority_promotion": False,
    }
    path = tmp_path / "receipt.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _corpus_receipt(tmp_path: Path, subject: str, tree: str, *, parity: bool = True) -> Path:
    records = [
        {
            "point_id": "p1",
            "tenant_id": "tenant-a",
            "scope": "tenant",
            "classification": "CANONICAL_ACTIVE" if parity else "LEGACY_MIGRATABLE",
            "parse_pass": True,
            "canonical_shape": parity,
            "current_dense_eligible": True,
            "current_sparse_eligible": True,
            "dense_sparse_divergent": False,
            "serving_candidate": True,
            "canonical_serving_eligible": parity,
            # D12-PRE: مصدرُ الهويّة المنطقيّة صار جزءاً من عقد الإيصال، والحارسُ يرفض
            # إيصالاً بدونه — فتجهيزةٌ يدويّةٌ ناقصةٌ تُدان بحقّ. وهذه نسخةٌ يدويّة من
            # شكل المُنتِج، وذلك سببُ انحرافها حين تحرّك المُنتِج.
            "explicit_logical_chunk_id": "c1",
            "logical_identity_source": "metadata.chunk_id",
            "fallback_identity_used": False,
            "reject_reason": None,
            "missing_fields": [],
            "source_type": "uploaded_document",
            "source_class": "tenant_document",
            "content_digest": "1" * 64,
            "source_uri_present": True,
            "source_revision_present": True,
        }
    ]
    raw = json.dumps(records, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    classifications = {
        "CANONICAL_ACTIVE": 1 if parity else 0,
        "CANONICAL_GLOBAL_REFERENCE": 0,
        "CANONICAL_QUARANTINE": 0,
        "LEGACY_MIGRATABLE": 0 if parity else 1,
        "LEGACY_PROVENANCE_INCOMPLETE": 0,
        "ORPHANED_UNATTRIBUTED": 0,
        "INVALID": 0,
        "UNCLASSIFIED": 0,
    }
    data = {
        "schema": "sahool.rag-corpus-audit-receipt/v1",
        "observed_at": datetime.now(UTC).isoformat(),
        "subject_sha": subject,
        "subject_tree": tree,
        "collection": "sahool_agri_kb",
        "qdrant_identity": "http://sahool-qdrant:6333",
        "read_only": True,
        "authority_promotion": False,
        "exact_count": 1,
        "scroll_count": 1,
        "physical_count_complete": True,
        "classification_counts": classifications,
        "rejection_reason_counts": {},
        "tenant_scope_counts": {"tenant-a": 1},
        "parse_pass": 1,
        "parse_fail": 0,
        "current_dense_eligible": 1,
        "current_sparse_eligible": 1,
        "dense_sparse_divergent": 0,
        "fallback_identity_used": 0,
        "serving_candidate_count": 1,
        "canonical_serving_eligible_count": 1 if parity else 0,
        "unclassified_count": 0,
        "canonical_payload_parity": parity,
        "duplicate_content_digest_cross_scope": {
            "digest_group_count": 0,
            "affected_point_count": 0,
            "scope_pair_group_counts": {},
            "bounded_samples": [],
        },
        "point_inventory_sha256": hashlib.sha256(raw).hexdigest(),
        "audit_tool_sha256": "2" * 64,
        "parser_sha256": "3" * 64,
        "point_records": records,
    }
    path = tmp_path / ("corpus-pass.json" if parity else "corpus-blocked.json")
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_admission_requires_live_receipt():
    rc, out = _run()
    assert rc == 2
    assert out["status"] == "EVIDENCE_REQUIRED"
    assert out["authority_changed"] is False


def test_valid_live_parity_is_still_blocked_by_revocation_readiness(tmp_path):
    subject = "b" * 40
    receipt = _receipt(tmp_path, subject)
    rc, out = _run("--receipt", str(receipt), "--subject-sha", subject)
    assert rc == 1
    assert out["status"] == "BLOCKED"
    assert out["cutover_capable"] is False
    assert "direct_qdrant_revocation_ready" in out["blocking_requirements"]
    assert "canonical_payload_parity" in out["blocking_requirements"]
    assert out["observed_requirements"]["collection_vector_schema_parity"] is True
    assert out["observed_requirements"]["canonical_payload_parity"] is False
    assert "direct_response_path_exception_present:local-ai-rag" in out["blocking_requirements"]
    assert out["authority_changed"] is False


def test_receipt_subject_mismatch_fails(tmp_path):
    receipt = _receipt(tmp_path, "c" * 40)
    rc, out = _run("--receipt", str(receipt), "--subject-sha", "d" * 40)
    assert rc == 1
    assert out["status"] == "FAILED"
    assert "live_parity_receipt_invalid" in out["findings"]


def test_live_receipt_does_not_claim_canonical_payload_parity(tmp_path):
    subject = "e" * 40
    receipt = _receipt(tmp_path, subject)
    rc, out = _run("--receipt", str(receipt), "--subject-sha", subject)
    assert rc == 1
    assert "canonical_payload_parity" in out["blocking_requirements"]
    assert out["observed_requirements"] == {
        "collection_vector_schema_parity": True,
        "canonical_payload_parity": False,
        "live_shadow_parity_receipt": True,
        "corpus_audit_receipt_present": False,
    }


def test_valid_corpus_receipt_is_the_only_path_that_can_raise_payload_parity(tmp_path):
    subject = "f" * 40
    tree = "1" * 40
    receipt = _receipt(tmp_path, subject)
    corpus = _corpus_receipt(tmp_path, subject, tree, parity=True)
    rc, out = _run(
        "--receipt",
        str(receipt),
        "--subject-sha",
        subject,
        "--subject-tree",
        tree,
        "--corpus-receipt",
        str(corpus),
    )
    assert rc == 1  # direct-Qdrant revocation remains intentionally open
    assert out["observed_requirements"]["canonical_payload_parity"] is True
    assert "canonical_payload_parity" not in out["blocking_requirements"]
    assert "direct_qdrant_revocation_ready" in out["blocking_requirements"]


def test_nonparity_corpus_receipt_is_valid_evidence_but_remains_blocking(tmp_path):
    subject = "1" * 40
    tree = "2" * 40
    receipt = _receipt(tmp_path, subject)
    corpus = _corpus_receipt(tmp_path, subject, tree, parity=False)
    rc, out = _run(
        "--receipt",
        str(receipt),
        "--subject-sha",
        subject,
        "--subject-tree",
        tree,
        "--corpus-receipt",
        str(corpus),
    )
    assert rc == 1
    assert out["observed_requirements"]["canonical_payload_parity"] is False
    assert "canonical_payload_parity" in out["blocking_requirements"]


def test_corpus_receipt_requires_subject_tree(tmp_path):
    subject = "3" * 40
    receipt = _receipt(tmp_path, subject)
    corpus = _corpus_receipt(tmp_path, subject, "4" * 40, parity=True)
    rc, out = _run(
        "--receipt", str(receipt), "--subject-sha", subject, "--corpus-receipt", str(corpus)
    )
    assert rc == 1
    assert out["status"] == "FAILED"
    assert "subject_tree_required_with_corpus_receipt" in out["findings"]
