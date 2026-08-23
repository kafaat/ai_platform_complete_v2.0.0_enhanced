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
        timeout=60,
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
        timeout=60,
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
        timeout=60,
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
        timeout=60,
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
        timeout=60,
    )
    assert proc.returncode == 1
    assert "receipt subject tree mismatch" in proc.stdout


# ── D12-PRE — مصدرُ الهويّة المنطقيّة: مُعلَنٌ، ومتّسق، ولا يُلفَّق ──────────────
#
# العطلُ الذي أوجب هذا: الإيصالُ كان يقول «هل استُعير مُعرِّفُ التخزين؟» ولا يقول «ما
# الهويّةُ ومن أين جاءت». فمخطِّطُ D12 يقرأ الحقلين، وعلى إيصالٍ بلا `explicit_…`
# يصير كلُّ صفٍّ عديمَ الهويّة ويسقط أوّلُ صفٍّ قانونيّ بـ`ValueError`.


def test_the_receipt_names_where_a_logical_identity_came_from() -> None:
    audit, pq = _modules()
    row = audit.classify_point(pq, "p-canonical", _canonical_payload(chunk_id="c-explicit"))
    assert row["logical_identity_source"] == "metadata.chunk_id"
    assert row["explicit_logical_chunk_id"] == "c-explicit"
    assert row["fallback_identity_used"] is False


def test_a_borrowed_storage_id_is_declared_absent_not_reported_as_identity() -> None:
    """الثابتُ الحاكم لـD12: UUID التخزين ليس هويّةً منطقيّة."""
    audit, pq = _modules()
    payload = _canonical_payload(chunk_id="c-drop")
    payload["metadata"].pop("chunk_id")
    point_id = "00000000-0000-0000-0000-0000000000ab"
    row = audit.classify_point(pq, point_id, payload)
    assert row["logical_identity_source"] == "storage_fallback"
    assert row["fallback_identity_used"] is True
    # ولا يُسرَّب مُعرِّفُ النقطة إلى خانة الهويّة المنطقيّة.
    assert row["explicit_logical_chunk_id"] is None


def test_a_root_level_identity_is_named_by_its_own_location() -> None:
    audit, pq = _modules()
    payload = _canonical_payload(chunk_id="c-root")
    payload["chunk_id"] = payload["metadata"].pop("chunk_id")
    row = audit.classify_point(pq, "p-root", payload)
    assert row["logical_identity_source"] == "payload.chunk_id"
    assert row["explicit_logical_chunk_id"] == "c-root"
    assert row["fallback_identity_used"] is False


def test_fallback_flag_is_read_from_the_source_not_derived_twice() -> None:
    """سلطةٌ واحدة: الحقلان يصفان الحقيقةَ نفسها فلا يجوز أن ينحرفا.

    يُقاس على الجداء الكامل — لا على حالةٍ مختارة.
    """
    audit, pq = _modules()
    seen = set()
    for nested, root in (
        (None, None),
        (None, "L-root"),
        ("L-nested", None),
        ("L-nested", "L-root"),
    ):
        payload = _canonical_payload(chunk_id="c-x")
        payload["metadata"].pop("chunk_id")
        if nested:
            payload["metadata"]["chunk_id"] = nested
        if root:
            payload["chunk_id"] = root
        row = audit.classify_point(pq, "00000000-0000-0000-0000-0000000000ab", payload)
        source = row["logical_identity_source"]
        seen.add(source)
        assert row["fallback_identity_used"] is (source == "storage_fallback")
    assert seen == {"storage_fallback", "payload.chunk_id", "metadata.chunk_id"}


def test_guard_refuses_a_receipt_that_would_crash_the_migration_planner(tmp_path: Path) -> None:
    """رفضٌ مُسمًّى هنا خيرٌ من انهيارٍ في المخطِّط."""
    audit, pq = _modules()
    receipt = _receipt(audit, pq, [("p1", _canonical_payload(chunk_id="c1"))])
    for row in receipt["point_records"]:
        row.pop("logical_identity_source")
        row.pop("explicit_logical_chunk_id")
    guard = _load(GUARD, "test_d12pre_guard")
    receipt["point_inventory_sha256"] = guard._digest(receipt["point_records"])
    problems = guard.findings(receipt, "a" * 40, "b" * 40)
    assert any("unknown logical_identity_source" in p for p in problems), problems


def test_guard_refuses_an_identity_that_contradicts_its_declared_source(tmp_path: Path) -> None:
    audit, pq = _modules()
    receipt = _receipt(audit, pq, [("p1", _canonical_payload(chunk_id="c1"))])
    row = receipt["point_records"][0]
    # ادّعاءُ الاستعارة مع بقاء الهويّة حاضرة — تلفيقٌ في الاتّجاه الخطر.
    row["logical_identity_source"] = "storage_fallback"
    guard = _load(GUARD, "test_d12pre_guard2")
    receipt["point_inventory_sha256"] = guard._digest(receipt["point_records"])
    problems = guard.findings(receipt, "a" * 40, "b" * 40)
    assert any("logical identity present but declared absent" in p for p in problems), problems
    assert any("fallback_identity_used disagrees with its source" in p for p in problems), problems


def test_guard_refuses_a_declared_source_with_no_identity_behind_it(tmp_path: Path) -> None:
    audit, pq = _modules()
    receipt = _receipt(audit, pq, [("p1", _canonical_payload(chunk_id="c1"))])
    row = receipt["point_records"][0]
    row["explicit_logical_chunk_id"] = "   "
    guard = _load(GUARD, "test_d12pre_guard3")
    receipt["point_inventory_sha256"] = guard._digest(receipt["point_records"])
    problems = guard.findings(receipt, "a" * 40, "b" * 40)
    assert any("declared logical identity source without an identity" in p for p in problems)


# ── D08-EXT — التقسيم الفيزيائيّ وعقد الهويّة المنطقيّة في الإيصال نفسه ──────────
#
# حادثة 199=128+64+7: بُعد التصادم جُمِع مرّةً كأنّه شريحة تقسيم، فحسب القارئ
# الجسم مرّتين. التقسيم الفيزيائيّ محوره النطاق وحده، وعدّادات التصادم محور آخر
# داخل `logical_identity` — والحَكم `production_qdrant.py` يفرض التفرّد المنطقيّ
# **قبل** استثناء الحجر، فالقياس هنا على كامل المجموعة بما فيها `__seed_quarantine__`.


def test_physical_partition_is_scope_only_and_sums_to_the_scroll() -> None:
    audit, pq = _modules()
    rows = [
        ("p1", _canonical_payload("tenant-a", chunk_id="c1")),
        ("p2", _canonical_payload("tenant-b", chunk_id="c2")),
        ("p3", _global_payload("g1")),
        ("p4", _canonical_payload("__seed_quarantine__", chunk_id="q1")),
        ("p5", {"page_content": "no tenant at all"}),
    ]
    receipt = _receipt(audit, pq, rows)
    part = receipt["physical_partition"]
    assert receipt["point_count"] == receipt["exact_count"]
    assert sum(part.values()) == receipt["scroll_count"] == 5
    assert part == {"global": 1, "quarantine": 1, "tenant": 2, "unknown": 1}
    banned = ("collision", "duplicate", "logical")
    assert not [k for k in part if any(w in k.lower() for w in banned)], (
        "بُعد التصادم ليس شريحة تقسيم — جمعه هنا يعدّ الجسم مرّتين"
    )


def test_logical_identity_collisions_count_the_quarantine_too() -> None:
    audit, pq = _modules()
    rows = [
        ("p1", _canonical_payload("tenant-a", chunk_id="dup-1")),
        ("p2", _canonical_payload("__seed_quarantine__", chunk_id="dup-1")),
        ("p3", _canonical_payload("tenant-b", chunk_id="solo-1")),
    ]
    receipt = _receipt(audit, pq, rows)
    li = receipt["logical_identity"]
    assert li["scope"] == "collection"
    assert li["quarantine_included"] is True
    assert li["collision_group_count"] == 1
    assert li["collision_point_count"] == 2
    sample = li["bounded_collision_samples"][0]
    assert sample["logical_chunk_id"] == "dup-1"
    assert "__seed_quarantine__" in sample["tenant_scopes"], (
        "العلَم وحده ليس سلوكاً: عضو الحجر يجب أن يظهر في مجموعة التصادم فعلاً"
    )


def test_points_without_identity_cannot_collide() -> None:
    audit, pq = _modules()
    rows = [
        ("p1", {"page_content": "a", "metadata": {"tenant_id": "tenant-a"}}),
        ("p2", {"page_content": "b", "metadata": {"tenant_id": "tenant-a"}}),
        ("p3", _canonical_payload("tenant-a", chunk_id="c1")),
    ]
    receipt = _receipt(audit, pq, rows)
    li = receipt["logical_identity"]
    assert li["collision_group_count"] == 0
    assert li["collision_point_count"] == 0
    assert li["identity_bearing_point_count"] == 1, "غياب الهويّة دَين يُعدّ غياباً، لا تصادماً ولا حضوراً"


def test_an_incomplete_scroll_does_not_balance_its_own_books() -> None:
    audit, pq = _modules()
    rows = [("p1", _canonical_payload("tenant-a", chunk_id="c1"))]
    receipt = _receipt(audit, pq, rows, exact_count=3)
    assert receipt["point_count"] == 3
    assert sum(receipt["physical_partition"].values()) == 1, (
        "مسحٌ ناقص يجب أن يظهر عجزُه في الجمع — لا أن يوازن دفاتره بنفسه"
    )
    assert receipt["physical_count_complete"] is False


def test_collision_samples_are_bounded_not_exhaustive() -> None:
    audit, pq = _modules()
    rows = []
    for g in range(7):
        for member in range(2):
            rows.append(
                (
                    f"p{g}-{member}",
                    _canonical_payload(f"tenant-{member}", chunk_id=f"dup-{g}"),
                )
            )
    receipt = _receipt(audit, pq, rows)
    li = receipt["logical_identity"]
    assert li["collision_group_count"] == 7
    assert li["collision_point_count"] == 14
    assert len(li["bounded_collision_samples"]) == 5, "عيّنات محدودة — الإيصال ليس مكبّ أدلّة"
