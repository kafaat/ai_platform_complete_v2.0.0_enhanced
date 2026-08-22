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
PQ = ROOT / "services/sahool-platform/core/rag/production_qdrant.py"
AUDIT = ROOT / "scripts/architecture/rag_live_corpus_audit.py"
PLAN = ROOT / "scripts/architecture/rag_logical_identity_migration_plan.py"
GUARD = ROOT / "scripts/architecture/rag_logical_identity_migration_plan_guard.py"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _modules(tag: str = "d12"):
    return (
        _load(PQ, f"test_rag_{tag}_pq"),
        _load(AUDIT, f"test_rag_{tag}_audit"),
        _load(PLAN, f"test_rag_{tag}_plan"),
    )


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _canonical_payload(
    *, tenant: str = "tenant-a", chunk_id: str = "c1", text: str = "wheat guidance"
) -> dict:
    return {
        "page_content": text,
        "metadata": {
            "chunk_id": chunk_id,
            "tenant_id": tenant,
            "source_type": "uploaded_document",
            "document_id": f"doc-{chunk_id}",
            "chunk_index": 0,
            "total_chunks": 1,
            "evidence_level": "document",
            "source_class": "tenant_document",
            "content_digest": _digest(text),
            "source_uri": f"sahool://{tenant}/{chunk_id}",
            "source_revision": "r1",
            "prescriptive_eligible": False,
        },
    }


def _legacy_root_chunk_id(payload: dict) -> dict:
    out = {"page_content": payload["page_content"], "metadata": dict(payload["metadata"])}
    out["chunk_id"] = out["metadata"].pop("chunk_id")
    return out


def _storage_fallback_only(payload: dict) -> dict:
    out = {"page_content": payload["page_content"], "metadata": dict(payload["metadata"])}
    out["metadata"].pop("chunk_id")
    return out


def _receipt(audit, pq, rows):
    return audit.build_receipt(
        pq,
        rows,
        exact_count=len(rows),
        subject_sha="a" * 40,
        subject_tree="b" * 40,
        collection="sahool_agri_kb",
        qdrant_identity="http://sahool-qdrant:6333",
        observed_at=datetime.now(UTC).isoformat(),
    )


def test_audit_projects_explicit_logical_identity_without_promoting_storage_uuid() -> None:
    pq, audit, _plan = _modules("d12_projection")
    canonical = audit.classify_point(pq, "storage-c", _canonical_payload(chunk_id="logical-c"))
    root = audit.classify_point(
        pq, "storage-r", _legacy_root_chunk_id(_canonical_payload(chunk_id="logical-r"))
    )
    fallback = audit.classify_point(
        pq, "storage-only", _storage_fallback_only(_canonical_payload(chunk_id="discarded"))
    )

    assert canonical["explicit_logical_chunk_id"] == "logical-c"
    assert canonical["logical_identity_source"] == "metadata.chunk_id"
    assert canonical["fallback_identity_used"] is False
    assert root["explicit_logical_chunk_id"] == "logical-r"
    assert root["logical_identity_source"] == "payload.chunk_id"
    assert root["fallback_identity_used"] is False
    assert fallback["explicit_logical_chunk_id"] is None
    assert fallback["logical_identity_source"] == "storage_fallback"
    assert fallback["fallback_identity_used"] is True


def test_storage_uuid_fallback_is_held_instead_of_becoming_canonical_identity() -> None:
    pq, audit, planner = _modules("d12_fallback")
    receipt = _receipt(
        audit,
        pq,
        [("storage-uuid-42", _storage_fallback_only(_canonical_payload(chunk_id="lost")))],
    )
    plan = planner.build_plan(receipt)
    row = plan["plan_rows"][0]
    assert row["action"] == "HOLD_IDENTITY_EVIDENCE"
    assert row["canonical_chunk_id"] is None
    assert row["canonical_writer_point_id"] is None
    assert plan["migration_candidate_count"] == 0
    assert plan["identity_evidence_required_count"] == 1


def test_explicit_legacy_identity_can_be_planned_without_reusing_storage_id() -> None:
    pq, audit, planner = _modules("d12_explicit")
    receipt = _receipt(
        audit,
        pq,
        [("old-storage-id", _legacy_root_chunk_id(_canonical_payload(chunk_id="logical-7")))],
    )
    plan = planner.build_plan(receipt)
    row = plan["plan_rows"][0]
    assert row["action"] == "MIGRATION_CANDIDATE"
    assert row["canonical_chunk_id"] == "logical-7"
    assert row["canonical_chunk_id"] != row["point_id"]
    assert row["canonical_writer_point_id"] == pq.canonical_storage_point_id("logical-7")
    assert plan["migration_authorized"] is False
    assert plan["writes_performed"] is False


def test_provenance_incomplete_point_never_becomes_a_migration_candidate() -> None:
    pq, audit, planner = _modules("d12_provenance")
    broken = _canonical_payload(chunk_id="logical-p")
    broken["metadata"]["source_uri"] = ""
    receipt = _receipt(audit, pq, [("storage-p", broken)])
    assert receipt["point_records"][0]["classification"] == "LEGACY_PROVENANCE_INCOMPLETE"
    plan = planner.build_plan(receipt)
    row = plan["plan_rows"][0]
    assert row["action"] == "HOLD_PROVENANCE_EVIDENCE"
    assert row["canonical_writer_point_id"] is None
    assert plan["provenance_evidence_required_count"] == 1


def test_noncanonical_quarantine_is_held_for_separate_disposition() -> None:
    pq, audit, planner = _modules("d12_quarantine")
    q = _legacy_root_chunk_id(
        _canonical_payload(tenant="__seed_quarantine__", chunk_id="quarantine-logical")
    )
    receipt = _receipt(audit, pq, [("storage-q", q)])
    plan = planner.build_plan(receipt)
    assert plan["plan_rows"][0]["action"] == "HOLD_QUARANTINE"
    assert plan["migration_candidate_count"] == 0


def test_duplicate_logical_identity_is_held_instead_of_overwriting_by_order() -> None:
    pq, audit, planner = _modules("d12_collision")
    a = _legacy_root_chunk_id(_canonical_payload(chunk_id="same-logical"))
    b = _legacy_root_chunk_id(_canonical_payload(chunk_id="same-logical"))
    receipt = _receipt(audit, pq, [("storage-a", a), ("storage-b", b)])
    plan = planner.build_plan(receipt)
    assert {row["action"] for row in plan["plan_rows"]} == {"HOLD_LOGICAL_ID_COLLISION"}
    assert all(row["canonical_writer_point_id"] is None for row in plan["plan_rows"])
    assert plan["logical_id_collision_group_count"] == 1
    assert plan["logical_id_collision_point_count"] == 2
    assert plan["migration_candidate_count"] == 0


def test_plan_guard_rejects_storage_fallback_promoted_by_tamper(tmp_path: Path) -> None:
    pq, audit, planner = _modules("d12_guard")
    receipt = _receipt(
        audit,
        pq,
        [("storage-uuid-42", _storage_fallback_only(_canonical_payload(chunk_id="lost")))],
    )
    plan = planner.build_plan(receipt)
    plan["plan_rows"][0]["action"] = "MIGRATION_CANDIDATE"
    plan["plan_rows"][0]["canonical_chunk_id"] = "storage-uuid-42"
    plan["plan_rows"][0]["canonical_writer_point_id"] = pq.canonical_storage_point_id(
        "storage-uuid-42"
    )
    plan["action_counts"] = {"MIGRATION_CANDIDATE": 1}
    plan["migration_candidate_count"] = 1
    plan["identity_evidence_required_count"] = 0
    plan["plan_rows_sha256"] = planner._sha256_json(plan["plan_rows"])
    corpus_path = tmp_path / "corpus.json"
    plan_path = tmp_path / "plan.json"
    corpus_path.write_text(json.dumps(receipt), encoding="utf-8")
    plan_path.write_text(json.dumps(plan), encoding="utf-8")
    proc = subprocess.run(
        [
            sys.executable,
            str(GUARD),
            "--plan",
            str(plan_path),
            "--corpus-receipt",
            str(corpus_path),
            "--subject-sha",
            "a" * 40,
            "--subject-tree",
            "b" * 40,
        ],
        cwd=ROOT,
        text=True,
        # الترميزُ صريحٌ والمهلةُ معه: `text=True` وحدها تفكّ بترميز الآلة، فتحت
        # `LC_ALL=C` ينهار الاستخراجُ على المخرَج العربيّ. والسابقةُ في هذا المستودع
        # تُقرِن الاثنين — أمسك المراجعُ الآليّ نصفَها وحده على #884.
        encoding="utf-8",
        timeout=60,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    assert proc.returncode == 1
    assert (
        "storage fallback promoted to logical identity" in proc.stdout
        or "migration action mismatch" in proc.stdout
    )


def test_plan_guard_rejects_authorizing_or_write_claims(tmp_path: Path) -> None:
    pq, audit, planner = _modules("d12_guard_authority")
    receipt = _receipt(
        audit,
        pq,
        [("old-storage", _legacy_root_chunk_id(_canonical_payload(chunk_id="logical-auth")))],
    )
    plan = planner.build_plan(receipt)
    plan["migration_authorized"] = True
    corpus_path = tmp_path / "corpus.json"
    plan_path = tmp_path / "plan.json"
    corpus_path.write_text(json.dumps(receipt), encoding="utf-8")
    plan_path.write_text(json.dumps(plan), encoding="utf-8")
    proc = subprocess.run(
        [
            sys.executable,
            str(GUARD),
            "--plan",
            str(plan_path),
            "--corpus-receipt",
            str(corpus_path),
            "--subject-sha",
            "a" * 40,
            "--subject-tree",
            "b" * 40,
        ],
        cwd=ROOT,
        text=True,
        # الترميزُ صريحٌ والمهلةُ معه: `text=True` وحدها تفكّ بترميز الآلة، فتحت
        # `LC_ALL=C` ينهار الاستخراجُ على المخرَج العربيّ. والسابقةُ في هذا المستودع
        # تُقرِن الاثنين — أمسك المراجعُ الآليّ نصفَها وحده على #884.
        encoding="utf-8",
        timeout=60,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    assert proc.returncode == 1
    assert "read-only/non-authorizing/non-promoting" in proc.stdout


def test_plan_guard_rejects_a_plan_bound_to_another_corpus_receipt(tmp_path: Path) -> None:
    pq, audit, planner = _modules("d12_guard_digest")
    receipt = _receipt(
        audit,
        pq,
        [("old-storage", _legacy_root_chunk_id(_canonical_payload(chunk_id="logical-digest")))],
    )
    plan = planner.build_plan(receipt)
    plan["corpus_receipt_sha256"] = "0" * 64
    corpus_path = tmp_path / "corpus.json"
    plan_path = tmp_path / "plan.json"
    corpus_path.write_text(json.dumps(receipt), encoding="utf-8")
    plan_path.write_text(json.dumps(plan), encoding="utf-8")
    proc = subprocess.run(
        [
            sys.executable,
            str(GUARD),
            "--plan",
            str(plan_path),
            "--corpus-receipt",
            str(corpus_path),
            "--subject-sha",
            "a" * 40,
            "--subject-tree",
            "b" * 40,
        ],
        cwd=ROOT,
        text=True,
        # الترميزُ صريحٌ والمهلةُ معه: `text=True` وحدها تفكّ بترميز الآلة، فتحت
        # `LC_ALL=C` ينهار الاستخراجُ على المخرَج العربيّ. والسابقةُ في هذا المستودع
        # تُقرِن الاثنين — أمسك المراجعُ الآليّ نصفَها وحده على #884.
        encoding="utf-8",
        timeout=60,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    assert proc.returncode == 1
    assert "corpus receipt digest mismatch" in proc.stdout


def test_plan_guard_accepts_a_valid_non_authorizing_plan(tmp_path: Path) -> None:
    pq, audit, planner = _modules("d12_guard_green")
    receipt = _receipt(
        audit,
        pq,
        [("old-storage", _legacy_root_chunk_id(_canonical_payload(chunk_id="logical-green")))],
    )
    plan = planner.build_plan(receipt)
    corpus_path = tmp_path / "corpus.json"
    plan_path = tmp_path / "plan.json"
    corpus_path.write_text(json.dumps(receipt), encoding="utf-8")
    plan_path.write_text(json.dumps(plan), encoding="utf-8")
    proc = subprocess.run(
        [
            sys.executable,
            str(GUARD),
            "--plan",
            str(plan_path),
            "--corpus-receipt",
            str(corpus_path),
            "--subject-sha",
            "a" * 40,
            "--subject-tree",
            "b" * 40,
        ],
        cwd=ROOT,
        text=True,
        # الترميزُ صريحٌ والمهلةُ معه: `text=True` وحدها تفكّ بترميز الآلة، فتحت
        # `LC_ALL=C` ينهار الاستخراجُ على المخرَج العربيّ. والسابقةُ في هذا المستودع
        # تُقرِن الاثنين — أمسك المراجعُ الآليّ نصفَها وحده على #884.
        encoding="utf-8",
        timeout=60,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout
    assert "candidates=1" in proc.stdout


def test_canonical_writer_storage_id_is_a_one_way_projection_from_logical_id() -> None:
    pq, _audit, _planner = _modules("d12_writer")

    class Client(pq.QdrantHttpClient):
        def __init__(self):
            super().__init__("http://qdrant", "c", vector_size=2)
            self.body = None

        def _request(self, method, path, payload=None):
            self.body = payload
            return {}

    chunk = pq.KnowledgeChunk(
        chunk_id="logical-writer",
        tenant_id="tenant-a",
        text="wheat",
        source_type="uploaded_document",
        document_id="doc-1",
        chunk_index=0,
        total_chunks=1,
        metadata={
            "evidence_level": "document",
            "source_uri": "sahool://tenant-a/logical-writer",
            "source_revision": "r1",
            "prescriptive_eligible": False,
        },
    )
    client = Client()
    client.upsert([chunk], [[0.1, 0.2]])
    expected = str(
        __import__("uuid").uuid5(__import__("uuid").NAMESPACE_URL, "sahool-rag:logical-writer")
    )
    assert pq.canonical_storage_point_id("logical-writer") == expected
    assert client.body["points"][0]["id"] == expected
    with pytest.raises(ValueError):
        pq.canonical_storage_point_id("")


def test_every_writer_of_qdrant_points_projects_identity_identically() -> None:
    """صيغةُ الإسقاط واحدةٌ عبر كلّ من يكتب نقاطاً — أو تحمرّ.

    D12 يحسب وجهةَ الهجرة بالصيغة نفسها التي يكتب بها الكاتبُ القانونيّ. وقد كشف
    قياسُ هذه الشريحة **نسخةً رابعة** في `services/qdrant-seed/seed.py` — خدمةٍ
    محاويَةٍ مستقلّة لا ترى `core.rag` وقتَ التشغيل، ففرضُ الاستيراد عليها يكسر
    حاويتَها ويكون العلاجُ أسوأ من العطل.

    فالاقترانُ يُترَك، ويُفرَض **التطابق**: تبديلُ الفضاء أو البادئة في أحدهما دون
    الآخر يجعل الباذرَ يكتب نقاطاً عند مُعرِّفاتٍ لا يحسبها المسترجِع ولا يقصدها
    المخطِّط — انحرافٌ صامتٌ في مسارٍ لا اختبارَ فيه يسأل عنه.

    والاستخراجُ نصّيٌّ بالقصد: استيرادُ `seed.py` يتطلّب `qdrant_client` وهو غيرُ
    مثبَّتٍ في جناح الوحدة، فتُقرَأ صيغتُه من مصدرها ويُتحقَّق أنّها هي.
    """
    import re

    pq = _load(PQ, "test_rag_d12_writer_parity_pq")
    seed = ROOT / "services/qdrant-seed/seed.py"
    source = seed.read_text(encoding="utf-8")
    matches = re.findall(
        r"uuid\.uuid5\(\s*uuid\.(?P<ns>NAMESPACE_\w+)\s*,\s*f\"(?P<prefix>[^\"{]*)\{", source
    )
    assert matches, "لم يعد الباذرُ يشتقّ مُعرِّفَ نقطةٍ بهذه الصيغة — أعِد قياسَ العقد"
    for namespace, prefix in matches:
        assert namespace == "NAMESPACE_URL", f"فضاءٌ مختلف في الباذر: {namespace}"
        assert prefix == "sahool-rag:", f"بادئةٌ مختلفة في الباذر: {prefix!r}"

    # والسلطةُ القانونيّة تستعمل الاثنين نفسَهما — يُقرَأ من مصدرها لا يُفترَض.
    canonical_source = PQ.read_text(encoding="utf-8")
    assert 'uuid.uuid5(uuid.NAMESPACE_URL, f"sahool-rag:{logical}")' in canonical_source
    # وشاهدٌ سلوكيّ فوق الشاهد النصّيّ: القيمةُ نفسها فعلاً.
    assert pq.canonical_storage_point_id("c1") == str(
        __import__("uuid").uuid5(__import__("uuid").NAMESPACE_URL, "sahool-rag:c1")
    )


def test_a_canonical_row_without_an_explicit_identity_fails_the_plan_closed() -> None:
    """تناقضٌ في الإيصال يُوقِف الخطّة، ولا يُرقَّع باستعارةِ مُعرِّف التخزين.

    صفٌّ مُصنَّفٌ قانونيّاً يجب أن يملك هويّتَه في حمولته — فإن لم يملكها فالمُنتِجُ
    معطوب، والجوابُ فشلٌ مُسمًّى. ولو استعار المخطِّطُ `point_id` هنا لأنتج خطّةً
    **تبدو سليمة** فوق إيصالٍ متناقض، وهو أخفى من التوقّف وأسوأ منه.

    وكُتِب هذا الاختبار لأنّ المكنسة أثبتت أنّ الطفرةَ تنجو بدونه: القاعدةُ كانت
    قائمةً في الشيفرة وغيرَ محروسةٍ بشاهد.
    """
    _pq, _audit, plan = _modules("d12_canonical_without_identity")
    with pytest.raises(ValueError, match="lacks explicit logical chunk identity"):
        plan._base_row(
            {
                "point_id": "00000000-0000-0000-0000-0000000000ab",
                "classification": "CANONICAL_ACTIVE",
                "scope": "tenant",
                "explicit_logical_chunk_id": None,
                "fallback_identity_used": True,
            }
        )


def test_plan_guard_rederives_collisions_and_rejects_an_unheld_candidate(tmp_path: Path) -> None:
    """الحارسُ يُعيد حسابَ التصادم بنفسه — لا يثق بأنّ الخطّة حسبته.

    خطّةٌ تُرشِّح صفّاً للهجرة إلى هويّةٍ يملكها صفٌّ قانونيٌّ آخر تعني كتابةً فوق
    المالك. فإن عمي الحارسُ عن التصادم صار يقيس عقداً غير الذي يُنفِّذه المخطِّط.

    وكُتِب هذا الاختبار لأنّ المكنسة أثبتت نجاةَ الطفرة: تجهيزةُ «خطّةٍ صالحة» لم
    تكن تحوي تصادماً أصلاً، فتعطيلُ إعادة الحساب لم يغيّر حكمها.
    """
    pq, audit, plan = _modules("d12_collision_rederive")
    guard = _load(GUARD, "test_rag_d12_collision_guard")
    shared = "c-shared"
    rows = [
        ("p-canonical", _canonical_payload(chunk_id=shared)),
        ("p-legacy", _legacy_root_chunk_id(_canonical_payload(chunk_id=shared, text="legacy"))),
    ]
    receipt = _receipt(audit, pq, rows)
    built = plan.build_plan(receipt)
    held = [r for r in built["plan_rows"] if r["action"] == "HOLD_LOGICAL_ID_COLLISION"]
    assert held, f"التجهيزة يجب أن تُنتِج تصادماً فعليّاً: {built['action_counts']}"
    assert guard.findings(built, receipt, "a" * 40, "b" * 40) == []

    # والآن تُزوَّر الخطّة: يُرفَع الاحتجاز ويُعاد الترشيح — الحارسُ يجب أن يُدين.
    tampered = json.loads(json.dumps(built))
    for row in tampered["plan_rows"]:
        if row["action"] == "HOLD_LOGICAL_ID_COLLISION":
            row["action"] = "MIGRATION_CANDIDATE"
            row["canonical_writer_point_id"] = pq.canonical_storage_point_id(shared)
    counts: dict[str, int] = {}
    for row in tampered["plan_rows"]:
        counts[row["action"]] = counts.get(row["action"], 0) + 1
    tampered["action_counts"] = dict(sorted(counts.items()))
    tampered["migration_candidate_count"] = counts.get("MIGRATION_CANDIDATE", 0)
    tampered["logical_id_collision_group_count"] = 0
    tampered["logical_id_collision_point_count"] = 0
    tampered["plan_rows_sha256"] = plan._sha256_json(tampered["plan_rows"])
    problems = guard.findings(tampered, receipt, "a" * 40, "b" * 40)
    assert any("migration action mismatch" in p for p in problems), problems


def test_plan_guard_names_a_promoted_storage_fallback_even_on_an_inconsistent_receipt() -> None:
    """ترقيةُ المستعار تُسمّى في مستوى الخطّة، لا في مستوى الإيصال وحده.

    إيصالٌ متناقض (يدّعي الاستعارة وهويّتُه حاضرة) يُدينه حارسُ D08. لكنّ الخطّة
    المبنيّة فوقه تحمل الهويّةَ المُرقّاة في صفوفها، فيلزم أن يقولها حارسُ D12 بلسانه
    — وإلّا قُرِئ العطلُ عيباً في الإيصال فقط، وهو في الخطّة أيضاً.

    والشرطُ هنا «لا تُرقَّى ولا يُهاجَر»، لا «يُحتجَز باسمٍ بعينه»: صفٌّ مستعارٌ
    مُصنَّفٌ `ORPHANED_UNATTRIBUTED` يُحتجَز بـ`HOLD_UNATTRIBUTED` بحقّ.
    """
    _pq, _audit, plan = _modules("d12_promoted_fallback")
    guard = _load(GUARD, "test_rag_d12_promoted_guard")
    source = {
        "point_id": "p-promoted",
        "classification": "ORPHANED_UNATTRIBUTED",
        "scope": "tenant",
        "explicit_logical_chunk_id": "c-promoted",
        "logical_identity_source": "storage_fallback",
        "fallback_identity_used": True,
    }
    row = plan._base_row(source)
    # المخطِّطُ يحتجزه — والاحتجازُ ليس بالضرورة `HOLD_IDENTITY_EVIDENCE`.
    assert row["action"] == "HOLD_UNATTRIBUTED"
    assert row["canonical_writer_point_id"] is None
    # لكنّ الهويّةَ المُرقّاة عبرت إلى الخطّة، فيجب أن يسمّيها الحارس.
    assert row["canonical_chunk_id"] == "c-promoted"
    corpus = {"point_records": [source], "collection": "sahool_agri_kb"}
    built = {"plan_rows": [row], "point_count": 1}
    problems = guard.findings(built, corpus, "a" * 40, "b" * 40)
    assert any("storage fallback promoted to logical identity" in p for p in problems), problems


def test_a_held_fallback_row_is_never_condemned_for_the_name_of_its_hold() -> None:
    """الحارسُ لا يُحمِّر صواباً — الشرطُ الذي كان يفعل ذلك مُصلَحٌ ومقيس."""
    _pq, _audit, plan = _modules("d12_hold_name")
    guard = _load(GUARD, "test_rag_d12_hold_name_guard")
    for classification, expected in (
        ("ORPHANED_UNATTRIBUTED", "HOLD_UNATTRIBUTED"),
        ("INVALID", "HOLD_INVALID"),
        ("LEGACY_PROVENANCE_INCOMPLETE", "HOLD_PROVENANCE_EVIDENCE"),
    ):
        source = {
            "point_id": f"p-{classification}",
            "classification": classification,
            "scope": "tenant",
            "explicit_logical_chunk_id": None,
            "logical_identity_source": "storage_fallback",
            "fallback_identity_used": True,
        }
        row = plan._base_row(source)
        assert row["action"] == expected
        corpus = {"point_records": [source], "collection": "sahool_agri_kb"}
        built = {"plan_rows": [row], "point_count": 1}
        problems = guard.findings(built, corpus, "a" * 40, "b" * 40)
        assert not any("storage fallback" in p for p in problems), (classification, problems)
