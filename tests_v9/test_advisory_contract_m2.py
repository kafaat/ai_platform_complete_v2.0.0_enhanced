"""تحقّق M2 — مظروف الاستجابة الاستشاريّة المُهيكَل (advisory_contract) + وصله في main.

- الشكل ثابت ومُتحقَّق؛ القرار **لا يخترعه النموذج** (advisory_only افتراضاً؛ لا يُقبَل
  go/caution/no_go إلّا من مُستدعٍ موثوق).
- ``requires_human_review`` fail-safe (فعل/غموض/نقص دليل ⇒ مراجعة).
- ``evidence_used``/``evidence_missing`` من الأدلّة الفعليّة (لا تلفيق).
- لا مفاتيح قرار ممنوعة في المظروف (يبقى المستشار طبقة تفسير لا قرار).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.ai_agronomist.advisory_contract import build_advisory_envelope  # noqa: E402
from services.ai_agronomist.decision_contracts import has_decision_keys  # noqa: E402

_GOOD = {
    "answer_ar": "الحقل ضمن المدى الطبيعيّ لمؤشّر NDVI مع رطوبة كافية.",
    "confidence": 0.82,
    "evidence_ids": ["ndvi:2026-06", "weather:nasa_power"],
    "evidence_sources": ["rag", "kg"],
    "pending_approvals": [],
    "generation_provider": "openrouter",
    "decision_authority": "field_intelligence_coordinator",
}


def test_default_decision_is_advisory_only_and_shape_is_fixed():
    env = build_advisory_envelope(_GOOD)
    assert env["schema"] == "sahool.advisory_envelope/1"
    assert env["decision"] == "advisory_only"
    assert 0.0 <= env["confidence"] <= 1.0
    assert env["evidence_used"] == ["ndvi:2026-06", "weather:nasa_power"]
    assert isinstance(env["limitations"], list) and isinstance(env["evidence_missing"], list)
    assert env["decision_authority"] == "field_intelligence_coordinator"
    # جواب مؤرَّض كامل الثقة بلا فعل ⇒ لا مراجعة مطلوبة.
    assert env["requires_human_review"] is False


def test_model_cannot_inject_actionable_decision():
    # قيمة شاذّة/من النموذج ⇒ تُرفَض وتعود advisory_only.
    assert build_advisory_envelope(_GOOD, decision="go NOW!!")["decision"] == "advisory_only"
    assert build_advisory_envelope(_GOOD, decision="jailbreak")["decision"] == "advisory_only"
    # قيمة صحيحة من مُستدعٍ موثوق (محرّك قرار) ⇒ تُقبَل، وتستلزم مراجعة بشريّة.
    env = build_advisory_envelope(_GOOD, decision="caution")
    assert env["decision"] == "caution" and env["requires_human_review"] is True


def test_requires_review_failsafe_on_pending_low_conf_and_missing_evidence():
    assert (
        build_advisory_envelope({**_GOOD, "pending_approvals": [{"id": "a"}]})[
            "requires_human_review"
        ]
        is True
    )
    assert build_advisory_envelope({**_GOOD, "confidence": 0.3})["requires_human_review"] is True
    no_ev = build_advisory_envelope({**_GOOD, "evidence_ids": [], "evidence_sources": []})
    assert "no_grounding_evidence" in no_ev["evidence_missing"]
    assert no_ev["requires_human_review"] is True


def test_confidence_clamped_and_none_when_missing():
    assert build_advisory_envelope({**_GOOD, "confidence": 5.0})["confidence"] == 1.0
    assert build_advisory_envelope({**_GOOD, "confidence": None})["confidence"] is None
    assert build_advisory_envelope({**_GOOD, "confidence": None})["requires_human_review"] is True


def test_limitations_and_gaps_are_honest_not_fabricated():
    env = build_advisory_envelope(
        {
            **_GOOD,
            "generation_provider": None,  # لا نموذج ⇒ جواب من الأدلّة
            "knowledge_gaps": [{"key": "terrain", "reason": "no_terrain"}],
        }
    )
    assert "generation_disabled_evidence_only" in env["limitations"]
    assert "gap:terrain" in env["evidence_missing"]


def test_malformed_input_is_conservative():
    env = build_advisory_envelope(None)
    assert env["decision"] == "advisory_only" and env["requires_human_review"] is True
    assert env["summary"] == "" and env["evidence_used"] == []


def test_envelope_has_no_forbidden_decision_keys():
    # المستشار طبقة تفسير: لا يُصدِر مفاتيح توصية/وصفة/جرعة.
    assert has_decision_keys(build_advisory_envelope(_GOOD)) is False


def test_main_wires_advisory_envelope():
    # P1 decomposition: منطق الاستجابة انتقل إلى ai_evidence_runtime.py — نفحص الملفّين.
    txt = (ROOT / "services/ai_agronomist/main.py").read_text(encoding="utf-8") + (
        ROOT / "services/ai_agronomist/ai_evidence_runtime.py"
    ).read_text(encoding="utf-8")
    assert 'response["advisory"] = advisory_contract.build_advisory_envelope(response)' in txt
