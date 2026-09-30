"""قبولُ E2E لمستشار الذكاء: النجاح = جوابٌ **و**أثرُ تدقيقٍ مُسجَّل — لا «وُجد المفتاح».

الكتلةُ المضمّنة القديمة في ``scripts/e2e/e2e_field_imagery_ai.sh`` كانت مقلوبة: ترفض
``validated_field_facts`` (الإيجابيّة الوحيدة المُتحقَّقة) وتقبل ``audit_event.status ==
"failed"``. هذه الاختبارات تُثبّت الحالتين الصحيحتين، وتُحمِّر غيابَ التسجيل، وتبني
أغلبَ الملاعيب من ``build_evidence_response`` الحقيقيّ عبر نقطة المنصّة الحقيقيّة
``internal_ai_advice_event`` (لا شكلاً مُتخيَّلاً).
"""

from __future__ import annotations

import copy
import importlib
import importlib.util
import json
import subprocess
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import AsyncMock

import httpx
import pytest

from services.ai_agronomist import ai_evidence_runtime as runtime
from services.ai_agronomist.ai_generation import GenResult
from services.ai_agronomist.main import AdvisorQuery
from tests_v9.test_b6m4_structured_advisory import FIELD, TENANT, document, state

pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/e2e/ai_evidence_acceptance.py"
E2E_SH = ROOT / "scripts/e2e/e2e_field_imagery_ai.sh"

_spec = importlib.util.spec_from_file_location("_ai_evidence_acceptance", SCRIPT)
acceptance = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(acceptance)


def _owner(monkeypatch, *, persisted: bool):
    monkeypatch.syspath_prepend(str(ROOT / "services/sahool-platform"))
    importlib.import_module("api.main")
    module = importlib.import_module("api.routers.internal_service")

    @asynccontextmanager
    async def connection(_):
        yield object()

    monkeypatch.setattr(module.main, "tenant_connection", connection)
    monkeypatch.setattr(module.main, "_assert_field_in_tenant", AsyncMock())
    monkeypatch.setattr(module, "_compose_canonical", AsyncMock(return_value=state()))
    monkeypatch.setattr(module.main, "_emit_domain_event", AsyncMock(return_value=persisted))
    return module


async def _real_response(
    monkeypatch,
    *,
    generated: str | None = None,
    persisted: bool = True,
    agent_token: str = "e2e-agent-token",
    platform_http_status: int = 200,
) -> dict:
    """ردٌّ من ``build_evidence_response`` الحقيقيّ؛ التسجيلُ يمرّ بغلاف المستهلك الحقيقيّ
    ``_record_ai_advice_event`` ثمّ بنقطة المنصّة الحقيقيّة ``internal_ai_advice_event``."""
    module = _owner(monkeypatch, persisted=persisted)
    monkeypatch.setattr(runtime, "AGENT_TOKEN", agent_token)
    monkeypatch.setattr(runtime, "_fetch_canonical_field_state", AsyncMock(return_value=state()))
    monkeypatch.setattr(runtime, "_generation_allowed", lambda _: generated is not None)
    monkeypatch.setattr(runtime.ai_generation, "resolve_generation", lambda _: None)
    monkeypatch.setattr(
        runtime.policy_envelope, "gate_generation", lambda *a, **k: {"decision": "allowed"}
    )
    if generated is not None:
        monkeypatch.setattr(
            runtime.ai_generation,
            "generate",
            AsyncMock(return_value=GenResult(text=generated, model="fixture", provider="local")),
        )

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/internal/events/ai-advice"):
            if platform_http_status >= 400:
                return httpx.Response(platform_http_status, text="platform unavailable")
            req = module.main.InternalAIAdviceEventRequest(**json.loads(request.content))
            return httpx.Response(200, json=await module.internal_ai_advice_event(req))
        return httpx.Response(200, json={"annotations": [], "edges": []})

    client = httpx.AsyncClient
    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: client(transport=transport, **kw))
    return await runtime.build_evidence_response(
        AdvisorQuery(question="ما قياسات الحقل؟", field_id=FIELD),
        endpoint_mode="chat",
        x_tenant_id=TENANT,
        save_agent_tool_audit=lambda _: None,
        save_pending_approval=lambda _: None,
    )


def _evidence_only(**overrides) -> dict:
    payload = {
        "status": "ok",
        "mode": "evidence_only",
        "generation_status": "not_attempted",
        "answer_ar": "لم تتوفر أدلة كافية للإجابة عن السؤال.",
        "annotations": {"rag": [], "knowledge_graph": []},
        "confidence": 0.0,
        "guardrail_result": {
            "status": "not_executed",
            "reason": "evidence-only endpoint; no decision emitted",
            "generated_text_checked": None,
            "generation_status": "not_attempted",
        },
        "advisory_validation": None,
        "audit_event": {"status": "recorded", "ok": True, "persisted": True, "reason": None},
        "decision_authority": "field_intelligence_coordinator",
    }
    payload.update(overrides)
    return payload


# ── الحالتان الصحيحتان من وقت التشغيل الحقيقيّ ────────────────────────────────


async def test_real_evidence_only_with_persisted_audit_is_accepted(monkeypatch):
    response = await _real_response(monkeypatch)
    assert response["mode"] == "evidence_only"
    assert response["generation_status"] == "not_attempted"
    assert response["audit_event"]["persisted"] is True
    ok, reason = acceptance.evaluate(response)
    assert ok, reason


async def test_real_correct_suppression_keeps_passing(monkeypatch):
    """الكبتُ الصحيح ليس فشلاً: نصٌّ مولَّد بلا مقتطفات RAG ⇒ suppressed_ungrounded مُسمّى."""
    response = await _real_response(monkeypatch, generated="نصّ حرّ غير مُهيكَل")
    assert response["mode"] == "evidence_only"
    assert response["generation_status"] == "suppressed_ungrounded"
    ok, reason = acceptance.evaluate(response)
    assert ok, reason


async def test_real_validated_field_facts_is_accepted(monkeypatch):
    """الإيجابيّةُ الوحيدة المُتحقَّقة — كانت الكتلة القديمة ترفضها."""
    response = await _real_response(monkeypatch, generated=json.dumps(document(state())))
    assert response["mode"] == "validated_field_facts"
    assert response["generation_status"] == "validated_structured_facts"
    assert response["advisory_validation"]["status"] == "verified"
    ok, reason = acceptance.evaluate(response)
    assert ok, reason


# ── غيابُ التسجيل يُحمِّر — من وقت التشغيل الحقيقيّ ─────────────────────────


@pytest.mark.parametrize(
    ("kwargs", "audit_status"),
    [
        ({"persisted": False}, "not_persisted"),
        ({"agent_token": ""}, "skipped"),
        ({"platform_http_status": 503}, "failed"),
    ],
    ids=["outbox_emit_failed", "agent_token_missing", "platform_http_error"],
)
async def test_real_missing_persistence_is_rejected(monkeypatch, kwargs, audit_status):
    response = await _real_response(monkeypatch, **kwargs)
    assert response["audit_event"]["status"] == audit_status
    ok, reason = acceptance.evaluate(response)
    assert not ok
    assert "not persisted" in reason


async def test_real_validated_facts_without_persistence_is_rejected(monkeypatch):
    response = await _real_response(
        monkeypatch, generated=json.dumps(document(state())), persisted=False
    )
    # وقتُ التشغيل نفسه يرفض الإيصال غير المُسجَّل، والقبولُ يرفض الردّ.
    assert response["mode"] == "evidence_only"
    ok, reason = acceptance.evaluate(response)
    assert not ok
    assert "not persisted" in reason


# ── ملاعيب مُصغَّرة: كلّ شرطٍ يُكسَر وحده ──────────────────────────────────


def test_minimal_evidence_only_fixture_is_accepted():
    ok, reason = acceptance.evaluate(_evidence_only())
    assert ok, reason


@pytest.mark.parametrize(
    "audit",
    [
        {"status": "failed", "reason": "boom"},
        {"status": "not_persisted", "ok": False, "persisted": False},
        {"status": "skipped", "reason": "SAHOOL_AGENT_TOKEN not configured"},
        {"status": "recorded"},  # منصّة أقدم بلا ``persisted`` — لا دليل تسجيل.
        {"status": "recorded", "persisted": "true"},
    ],
    ids=["failed", "not_persisted", "skipped", "no_persisted_field", "persisted_not_bool"],
)
def test_audit_not_persisted_is_rejected(audit):
    ok, reason = acceptance.evaluate(_evidence_only(audit_event=audit))
    assert not ok
    assert "not persisted" in reason


def test_missing_audit_event_is_rejected():
    payload = _evidence_only()
    del payload["audit_event"]
    ok, reason = acceptance.evaluate(payload)
    assert not ok
    assert "audit_event missing" in reason


@pytest.mark.parametrize("status", [None, "", "succeeded", "whatever"])
def test_annotations_present_but_generation_status_unnamed_is_rejected(status):
    payload = _evidence_only(generation_status=status)
    if status is None:
        del payload["generation_status"]
    ok, reason = acceptance.evaluate(payload)
    assert not ok
    assert "unnamed generation_status" in reason


def test_suppression_without_named_reason_is_rejected():
    payload = _evidence_only(
        generation_status="suppressed_ungrounded",
        guardrail_result={"status": "not_executed", "generation_status": "suppressed_ungrounded"},
    )
    ok, reason = acceptance.evaluate(payload)
    assert not ok
    assert "without a named guardrail reason" in reason


def test_reviewer_fixture_is_rejected():
    """الملعوب الذي طبعت عليه الكتلة القديمة «ai evidence flow ok»."""
    reviewer = {
        "mode": "evidence_only",
        "annotations": [],
        "decision_authority": "field_intelligence_coordinator",
        "generation_status": "suppressed_ungrounded",
        "confidence": 0,
        "audit_event": {"status": "failed"},
    }
    ok, reason = acceptance.evaluate(reviewer)
    assert not ok
    assert "not persisted" in reason
    # وحتّى لو اكتملت بقيّة الحقول، فالتسجيلُ الفاشل وحده يُسقطه.
    completed = _evidence_only(
        generation_status="suppressed_ungrounded",
        confidence=0,
        audit_event={"status": "failed"},
        guardrail_result={
            "status": "not_executed",
            "reason": "evidence-only endpoint; no decision emitted",
            "generation_status": "suppressed_ungrounded",
        },
    )
    ok, reason = acceptance.evaluate(completed)
    assert not ok
    assert "not persisted" in reason


def test_validated_mode_requires_verified_receipt_and_matching_status():
    base = _evidence_only(
        mode="validated_field_facts",
        generation_status="validated_structured_facts",
        advisory_validation={
            "status": "verified",
            "executes_action": False,
            "creates_decision": False,
        },
    )
    base["audit_event"] = {
        **base["audit_event"],
        "advisory_validation": base["advisory_validation"],
    }
    ok, reason = acceptance.evaluate(base)
    assert ok, reason

    blocked = copy.deepcopy(base)
    blocked["advisory_validation"] = {"status": "blocked"}
    assert not acceptance.evaluate(blocked)[0]

    wrong_status = copy.deepcopy(base)
    wrong_status["generation_status"] = "suppressed_ungrounded"
    assert not acceptance.evaluate(wrong_status)[0]

    unpersisted = copy.deepcopy(base)
    unpersisted["audit_event"]["persisted"] = False
    assert not acceptance.evaluate(unpersisted)[0]


def test_unknown_mode_is_rejected():
    ok, reason = acceptance.evaluate(_evidence_only(mode="generated_grounded"))
    assert not ok
    assert "unknown mode" in reason


# ── السطح التنفيذيّ: الـCLI والـ.sh ─────────────────────────────────────────


def _run_cli(tmp_path, payload) -> subprocess.CompletedProcess:
    path = tmp_path / "ai.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return subprocess.run(
        [sys.executable, str(SCRIPT), str(path)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )


def test_cli_exits_nonzero_with_reason_when_persistence_is_missing(tmp_path):
    proc = _run_cli(tmp_path, _evidence_only(audit_event={"status": "failed"}))
    assert proc.returncode == 1
    assert "not persisted" in proc.stderr
    assert "ok" not in proc.stdout


def test_cli_exits_zero_on_accepted_response(tmp_path):
    proc = _run_cli(tmp_path, _evidence_only())
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.startswith("ai evidence flow ok")


def test_e2e_script_delegates_to_acceptance_and_drops_inverted_assertion():
    text = E2E_SH.read_text(encoding="utf-8")
    assert "ai_evidence_acceptance.py" in text, "القبول يجب أن يمرّ بالوحدة المُختبَرة"
    assert "AI must stay evidence_only" not in text, (
        "الكتلة القديمة ترفض validated_field_facts — الإيجابيّة الوحيدة المُتحقَّقة"
    )
    assert "'audit_event' in j" not in text, (
        "وجودُ المفتاح ليس تسجيلاً: كان يقبل audit_event.status == 'failed'"
    )
