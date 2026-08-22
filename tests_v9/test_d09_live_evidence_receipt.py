"""عقد مُجمِّع إيصال الدليل الحيّ لـD09 — الأجزاء النقيّة تُكذَّب بلا بيئةٍ حيّة.

التجهيزاتُ هنا مدخلاتُ اختبارٍ للأداة، لا دليلاً تشغيليّاً: لا شيء منها يُكتَب
إيصالاً ولا يُقدَّم قياساً. القياسُ الحيّ يجري في بيئة المالك وحدها.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
COLLECTOR = ROOT / "scripts/architecture/d09_live_evidence_receipt.py"
PQ = ROOT / "services/sahool-platform/core/rag/production_qdrant.py"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def collector():
    return _load(COLLECTOR, "test_d09_collector")


@pytest.fixture(scope="module")
def pq():
    return _load(PQ, "test_d09_collector_pq")


def _identity(count=3, ids="a" * 64, content="b" * 64):
    return {"point_count": count, "id_set_digest": ids, "content_digest": content}


def test_identical_identities_match_on_all_three_fields(collector):
    match = collector.compare_identities(_identity(), _identity())
    assert match == {"point_count": True, "id_set_digest": True, "content_digest": True}


def test_a_content_only_drift_is_named_not_blended(collector):
    # نفسُ العدد ونفسُ المُعرِّفات ومحتوًى مختلف — عينُ ما صِيغت له D09-M.
    match = collector.compare_identities(_identity(), _identity(content="c" * 64))
    assert match["point_count"] and match["id_set_digest"]
    assert not match["content_digest"]


def test_an_empty_digest_never_matches_even_against_itself(collector):
    # «لم يُقَس» لا يساوي «لم يُقَس»: غيابُ البصمة ليس هويّةً تُطابَق.
    match = collector.compare_identities(_identity(ids=""), _identity(ids=""))
    assert not match["id_set_digest"]


def test_the_verdict_names_every_failing_item(collector):
    checklist = dict.fromkeys(collector.CHECKLIST_ITEMS, True)
    checklist["no_live_mutation"] = False
    checklist["readyz"] = False
    verdict = collector.derive_verdict(checklist)
    assert verdict == "FAIL: no_live_mutation,readyz"
    assert collector.derive_verdict(dict.fromkeys(collector.CHECKLIST_ITEMS, True)) == "PASS"


def test_d09_e_judgment_comes_from_the_canonical_pure_function(collector, pq):
    # المُجمِّع لا يملك حكمَ جاهزيّةٍ خاصّاً به: التقريرُ المقيس يُمرَّر إلى
    # `readiness_problems` القانونيّة، وسلوكُها هو الحكم.
    clean = pq.readiness_problems(
        {
            "noncanonical_serving_points": 0,
            "noncanonical_serving_samples": [],
            "corpus_identity": _identity(),
        }
    )
    assert clean == []
    dirty = pq.readiness_problems(
        {
            "noncanonical_serving_points": 2,
            "noncanonical_serving_samples": ["p1", "p2"],
            "corpus_identity": _identity(),
        }
    )
    assert any("NOT_READY" in p for p in dirty)
    unmeasured = pq.readiness_problems(
        {
            "noncanonical_serving_points": 0,
            "noncanonical_serving_samples": [],
            "corpus_identity": {},
        }
    )
    assert any("EVIDENCE_MISSING" in p for p in unmeasured)


def test_binding_is_mandatory_a_receipt_without_an_artifact_digest_refuses(collector, tmp_path):
    rc = collector.main(
        [
            "--subject-sha",
            "a" * 40,
            "--subject-tree",
            "b" * 40,
            "--deployment-artifact",
            "ghcr.io/example/rag:test",
            "--deployment-artifact-digest",
            "not-a-digest",
            "--search-tenant",
            "t1",
            "--search-query",
            "q",
            "--output",
            str(tmp_path / "r.json"),
        ]
    )
    assert rc == 1
    assert not (tmp_path / "r.json").exists()


def test_a_short_subject_sha_refuses_before_any_network_touch(collector, tmp_path):
    rc = collector.main(
        [
            "--subject-sha",
            "abc123",
            "--subject-tree",
            "b" * 40,
            "--deployment-artifact",
            "ghcr.io/example/rag:test",
            "--deployment-artifact-digest",
            "sha256:" + "0" * 64,
            "--search-tenant",
            "t1",
            "--search-query",
            "q",
            "--output",
            str(tmp_path / "r.json"),
        ]
    )
    assert rc == 1
    assert not (tmp_path / "r.json").exists()


def test_the_receipt_declares_itself_read_only_and_non_promoting(collector):
    m = {
        "receipt": {"physical_count_complete": True, "observed_at": "t"},
        "identity": _identity(),
        "exact_count": 3,
        "noncanonical_serving_points": 0,
        "noncanonical_serving_samples": [],
    }
    receipt = collector.build_evidence_receipt(
        subject_sha="a" * 40,
        subject_tree="b" * 40,
        deployment_artifact="ghcr.io/example/rag:test",
        deployment_artifact_digest="sha256:" + "0" * 64,
        qdrant_url="http://qdrant.internal:6333",
        collection="kb",
        m1=m,
        m2=m,
        m1_path="m1.json",
        m1_sha256="0" * 64,
        m2_path="m2.json",
        m2_sha256="0" * 64,
        d09e_problems=[],
        readyz_status=200,
        readyz_body={"status": "ready"},
        search_status=200,
        search_result_count=2,
        search_result_fingerprints=["ff" * 8],
        search_tenant="t1",
        search_query_sha256="0" * 64,
        settle_seconds=30,
    )
    assert receipt["read_only"] is True
    assert receipt["authority_promotion"] is False
    assert receipt["verdict"] == "PASS"
    assert receipt["qdrant_identity"] == "qdrant.internal"
    # صفرُ نتائج ليس مشاهدة: الاسترجاع الأخضر بلا صفوف لا يثبت مساراً حيّاً.
    checklist = collector.build_evidence_receipt(
        subject_sha="a" * 40,
        subject_tree="b" * 40,
        deployment_artifact="ghcr.io/example/rag:test",
        deployment_artifact_digest="sha256:" + "0" * 64,
        qdrant_url="http://qdrant.internal:6333",
        collection="kb",
        m1=m,
        m2=m,
        m1_path="m1.json",
        m1_sha256="0" * 64,
        m2_path="m2.json",
        m2_sha256="0" * 64,
        d09e_problems=[],
        readyz_status=200,
        readyz_body={"status": "ready"},
        search_status=200,
        search_result_count=0,
        search_result_fingerprints=[],
        search_tenant="t1",
        search_query_sha256="0" * 64,
        settle_seconds=30,
    )["checklist"]
    assert checklist["v1_search"] and not checklist["observation"]


def test_a_diverged_count_fails_no_live_mutation_even_with_matching_digests(collector):
    # بصمتان متطابقتان وعدٌّ دقيق تحرّك — سباقُ كتابةٍ أثناء القياس يُرى هنا.
    m1 = {
        "receipt": {"physical_count_complete": True, "observed_at": "t1"},
        "identity": _identity(),
        "exact_count": 3,
        "noncanonical_serving_points": 0,
        "noncanonical_serving_samples": [],
    }
    m2 = dict(m1, exact_count=4, receipt={"physical_count_complete": True, "observed_at": "t2"})
    receipt = collector.build_evidence_receipt(
        subject_sha="a" * 40,
        subject_tree="b" * 40,
        deployment_artifact="ghcr.io/example/rag:test",
        deployment_artifact_digest="sha256:" + "0" * 64,
        qdrant_url="http://q:6333",
        collection="kb",
        m1=m1,
        m2=m2,
        m1_path="m1.json",
        m1_sha256="0" * 64,
        m2_path="m2.json",
        m2_sha256="0" * 64,
        d09e_problems=[],
        readyz_status=200,
        readyz_body={"status": "ready"},
        search_status=200,
        search_result_count=1,
        search_result_fingerprints=[],
        search_tenant="t1",
        search_query_sha256="0" * 64,
        settle_seconds=30,
    )
    assert not receipt["checklist"]["no_live_mutation"]
    assert "no_live_mutation" in receipt["verdict"]
