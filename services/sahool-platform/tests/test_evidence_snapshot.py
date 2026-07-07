"""تحقّق — تحضير لقطة رسم الأدلّة للاستمرار (منطق صرف: بصمة/تنقية أسرار/should_persist).

- لا لقطة بلا رسم أدلّة (evidence_count=0 و has_recommendation=False).
- بصمة القرار ثابتة لنفس المدخلات، وتتغيّر بتغيّرها.
- الأسرار (token/password/…) تُحذَف من الرسم/المصادر قبل التخزين.
- الفجوات (missing-with-reason) تبقى كما هي.
"""

from __future__ import annotations

from core.evidence_snapshot import (
    build_snapshot_payload,
    recommendation_hash,
    should_persist,
    strip_secrets,
)


def _graph(evidence_count=2, has_rec=True, nodes=None):
    return {
        "nodes": nodes
        or [
            {"id": "field", "type": "field"},
            {"id": "evidence:soil_baseline", "type": "soil_baseline", "source": "soilgrids"},
        ],
        "knowledge_gaps": [
            {"key": "terrain", "label": "التضاريس", "reason": "no_terrain_supplied"}
        ],
        "summary": {"evidence_count": evidence_count, "has_recommendation": has_rec},
    }


def _analyze(**over):
    base = {
        "confidence": 0.71,
        "correlation_id": "corr-1",
        "operational_truths": {"effective_status": "salinity_limited", "ndvi_trend": "decreasing"},
        "policy_decision": {"action_type": "soil_remediation"},
        "evidence_graph": _graph(),
    }
    base.update(over)
    return base


def test_should_persist_requires_real_graph():
    assert should_persist(_analyze()) is True
    assert should_persist({"evidence_graph": _graph(evidence_count=0, has_rec=False)}) is False
    assert should_persist({}) is False  # لا رسم ⇒ لا لقطة


def test_recommendation_hash_is_stable_and_sensitive():
    h1 = recommendation_hash(_analyze())
    h2 = recommendation_hash(_analyze())
    assert h1 == h2 and len(h1) == 16  # ثابت لنفس المدخلات
    # تغيّر الإجراء ⇒ بصمة مختلفة.
    changed = _analyze(policy_decision={"action_type": "investigate_stress"})
    assert recommendation_hash(changed) != h1
    # التوقيت العابر لا يؤثّر (غير داخل البصمة).
    assert recommendation_hash(_analyze(correlation_id="corr-999")) == h1


def test_strip_secrets_removes_tokens_anywhere():
    dirty = {
        "a": 1,
        "authorization": "Bearer x",
        "nested": {"api_key": "k", "ok": 2, "list": [{"token": "t", "keep": 3}]},
    }
    clean = strip_secrets(dirty)
    assert clean == {"a": 1, "nested": {"ok": 2, "list": [{"keep": 3}]}}


def test_payload_strips_secrets_and_keeps_gaps():
    nodes = [
        {"id": "field", "type": "field"},
        {"id": "evidence:latest_scene", "type": "satellite_scene", "source": "cdse", "token": "x"},
    ]
    a = _analyze(evidence_graph=_graph(nodes=nodes))
    p = build_snapshot_payload(a)
    assert p is not None
    assert p["recommendation_hash"] and p["confidence_score"] == 0.71
    assert p["analysis_id"] == "corr-1"
    # الأسرار محذوفة من الرسم المُخزَّن.
    scene = next(n for n in p["evidence_graph"]["nodes"] if n["id"] == "evidence:latest_scene")
    assert "token" not in scene and scene["source"] == "cdse"
    assert "cdse" in p["evidence_sources"]
    # الفجوات محفوظة بسببها.
    assert p["knowledge_gaps"][0]["reason"] == "no_terrain_supplied"


def test_payload_none_when_not_persistable():
    assert build_snapshot_payload({}) is None
