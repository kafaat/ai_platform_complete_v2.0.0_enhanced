from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.security]
ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "scripts/architecture/rag_live_corpus_audit.py"
GUARD = ROOT / "scripts/architecture/rag_corpus_audit_receipt_guard.py"
PQ = ROOT / "services/sahool-platform/core/rag/production_qdrant.py"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _modules():
    return _load(AUDIT, "test_rag_live_audit"), _load(PQ, "test_rag_live_audit_pq")


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _canonical_payload(
    tenant: str = "tenant-a", *, chunk_id: str = "c1", text: str = "wheat guidance"
) -> dict:
    source_type = "uploaded_document"
    source_class = "tenant_document"
    meta = {
        "chunk_id": chunk_id,
        "tenant_id": tenant,
        "source_type": source_type,
        "document_id": f"doc-{chunk_id}",
        "chunk_index": 0,
        "total_chunks": 1,
        "evidence_level": "document",
        "source_class": source_class,
        "content_digest": _digest(text),
        "source_uri": f"sahool://{tenant}/{chunk_id}",
        "source_revision": "r1",
        "prescriptive_eligible": False,
    }
    return {"page_content": text, "metadata": meta}


def _global_payload(chunk_id: str = "g1", text: str = "FAO wheat guidance") -> dict:
    meta = {
        "chunk_id": chunk_id,
        "tenant_id": "__global__",
        "source_type": "external_reference",
        "document_id": f"doc-{chunk_id}",
        "chunk_index": 0,
        "total_chunks": 1,
        "evidence_level": "document",
        "source_class": "external_reference",
        "content_digest": _digest(text),
        "publisher": "FAO",
        "source_uri": "https://example.invalid/fao",
        "source_revision": "r1",
        "license": "test",
        "prescriptive_eligible": False,
    }
    return {"page_content": text, "metadata": meta}


def _receipt(audit, pq, rows, exact_count=None):
    return audit.build_receipt(
        pq,
        rows,
        exact_count=len(rows) if exact_count is None else exact_count,
        subject_sha="a" * 40,
        subject_tree="b" * 40,
        collection="sahool_agri_kb",
        qdrant_identity="http://sahool-qdrant:6333",
        observed_at=datetime.now(UTC).isoformat(),
    )


def test_full_audit_classifies_every_point_without_document_text() -> None:
    audit, pq = _modules()
    canonical = _canonical_payload()
    global_row = _global_payload()
    quarantine = _canonical_payload("__seed_quarantine__", chunk_id="q1")
    legacy = _canonical_payload("tenant-b", chunk_id="l1")
    meta = legacy.pop("metadata")
    legacy.update(
        {
            "tenant_id": meta.pop("tenant_id"),
            "chunk_id": meta.pop("chunk_id"),
            "source_type": meta.pop("source_type"),
            "document_id": meta.pop("document_id"),
            "metadata": meta,
        }
    )
    broken = _canonical_payload("tenant-c", chunk_id="p1")
    broken["metadata"]["source_uri"] = ""

    receipt = _receipt(
        audit,
        pq,
        [
            ("p-a", canonical),
            ("p-g", global_row),
            ("p-q", quarantine),
            ("p-l", legacy),
            ("p-p", broken),
        ],
    )
    assert receipt["scroll_count"] == 5 == receipt["exact_count"]
    assert sum(receipt["classification_counts"].values()) == 5
    assert receipt["classification_counts"]["CANONICAL_ACTIVE"] == 1
    assert receipt["classification_counts"]["CANONICAL_GLOBAL_REFERENCE"] == 1
    assert receipt["classification_counts"]["CANONICAL_QUARANTINE"] == 1
    assert receipt["classification_counts"]["LEGACY_MIGRATABLE"] == 1
    assert receipt["classification_counts"]["LEGACY_PROVENANCE_INCOMPLETE"] == 1
    assert receipt["dense_sparse_divergent"] == 2
    assert receipt["canonical_payload_parity"] is False
    serialized = json.dumps(receipt, ensure_ascii=False)
    assert "wheat guidance" not in serialized
    assert "FAO wheat guidance" not in serialized
    assert '"page_content"' not in serialized
    assert '"text"' not in serialized


def test_explicit_nonserving_quarantine_does_not_fake_an_active_blocker() -> None:
    audit, pq = _modules()
    quarantine_legacy = _canonical_payload("__seed_quarantine__", chunk_id="q1")
    meta = quarantine_legacy.pop("metadata")
    quarantine_legacy.update(
        {
            "tenant_id": meta.pop("tenant_id"),
            "chunk_id": meta.pop("chunk_id"),
            "source_type": meta.pop("source_type"),
            "document_id": meta.pop("document_id"),
            "metadata": meta,
        }
    )
    receipt = _receipt(audit, pq, [("q", quarantine_legacy)])
    assert receipt["classification_counts"]["LEGACY_MIGRATABLE"] == 1
    assert receipt["point_records"][0]["scope"] == "quarantine"
    assert receipt["point_records"][0]["serving_candidate"] is False
    assert receipt["canonical_payload_parity"] is True


def test_exact_scroll_mismatch_can_never_claim_payload_parity() -> None:
    audit, pq = _modules()
    receipt = _receipt(audit, pq, [("p1", _canonical_payload())], exact_count=2)
    assert receipt["physical_count_complete"] is False
    assert receipt["canonical_payload_parity"] is False


def test_cross_scope_duplicate_digest_is_measured_without_content() -> None:
    audit, pq = _modules()
    text = "same bytes"
    a = _canonical_payload("tenant-a", chunk_id="a", text=text)
    q = _canonical_payload("__seed_quarantine__", chunk_id="q", text=text)
    receipt = _receipt(audit, pq, [("a", a), ("q", q)])
    dup = receipt["duplicate_content_digest_cross_scope"]
    assert dup["digest_group_count"] == 1
    assert dup["affected_point_count"] == 2
    assert (
        "tenant-a|__seed_quarantine__" in dup["scope_pair_group_counts"]
        or "__seed_quarantine__|tenant-a" in dup["scope_pair_group_counts"]
    )
    assert text not in json.dumps(dup)


def test_guard_accepts_valid_nonpromoting_receipt_and_rejects_tamper(tmp_path: Path) -> None:
    audit, pq = _modules()
    receipt = _receipt(audit, pq, [("p1", _canonical_payload())])
    path = tmp_path / "audit.json"
    path.write_text(json.dumps(receipt), encoding="utf-8")
    proc = subprocess.run(
        [
            sys.executable,
            str(GUARD),
            "--receipt",
            str(path),
            "--subject-sha",
            "a" * 40,
            "--subject-tree",
            "b" * 40,
        ],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout
    assert "parity=true" in proc.stdout

    receipt["point_records"][0]["canonical_serving_eligible"] = False
    path.write_text(json.dumps(receipt), encoding="utf-8")
    proc = subprocess.run(
        [
            sys.executable,
            str(GUARD),
            "--receipt",
            str(path),
            "--subject-sha",
            "a" * 40,
            "--subject-tree",
            "b" * 40,
        ],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    assert proc.returncode == 1
    assert (
        "point inventory digest mismatch" in proc.stdout
        or "canonical_payload_parity inconsistent" in proc.stdout
    )


def test_guard_rejects_document_body_fields_even_if_digest_is_recomputed(tmp_path: Path) -> None:
    audit, pq = _modules()
    receipt = _receipt(audit, pq, [("p1", _canonical_payload())])
    receipt["point_records"][0]["text"] = "secret body"
    receipt["point_inventory_sha256"] = audit._sha256_json(receipt["point_records"])
    path = tmp_path / "audit.json"
    path.write_text(json.dumps(receipt), encoding="utf-8")
    proc = subprocess.run(
        [
            sys.executable,
            str(GUARD),
            "--receipt",
            str(path),
            "--subject-sha",
            "a" * 40,
            "--subject-tree",
            "b" * 40,
        ],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    assert proc.returncode == 1
    assert "document content leaked" in proc.stdout


def test_guard_rejects_exact_scroll_mismatch(tmp_path: Path) -> None:
    audit, pq = _modules()
    receipt = _receipt(audit, pq, [("p1", _canonical_payload())], exact_count=2)
    path = tmp_path / "mismatch.json"
    path.write_text(json.dumps(receipt), encoding="utf-8")
    proc = subprocess.run(
        [
            sys.executable,
            str(GUARD),
            "--receipt",
            str(path),
            "--subject-sha",
            "a" * 40,
            "--subject-tree",
            "b" * 40,
        ],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    assert proc.returncode == 1
    assert "exact/scroll count mismatch" in proc.stdout


def test_guard_rejects_wrong_subject_tree(tmp_path: Path) -> None:
    audit, pq = _modules()
    receipt = _receipt(audit, pq, [("p1", _canonical_payload())])
    path = tmp_path / "tree.json"
    path.write_text(json.dumps(receipt), encoding="utf-8")
    proc = subprocess.run(
        [
            sys.executable,
            str(GUARD),
            "--receipt",
            str(path),
            "--subject-sha",
            "a" * 40,
            "--subject-tree",
            "c" * 40,
        ],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    assert proc.returncode == 1
    assert "receipt subject tree mismatch" in proc.stdout
