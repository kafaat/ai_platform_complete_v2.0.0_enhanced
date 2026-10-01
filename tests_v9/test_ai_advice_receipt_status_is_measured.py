"""إيصالُ حفظ نصيحة الذكاء يُقرأ من ``persisted`` الذي تُعيده المنصّة — لا من صمتها.

AI-GENERATION-ATTRIBUTED-TO-SUPPRESSED-OUTPUT-01 (الصنفُ نفسُه، بقرار المالك يُدرَج معه):
``_record_ai_advice_event`` كان يقرأ ردّاً بلا ``persisted`` «recorded» (افتراضُ ``ok``
ثمّ ``True``)، ومفتاحُ ``status`` في الردّ كان يَغلِب الحكم. يُقاس هنا عبر الدالّة
الحقيقيّة و``httpx.MockTransport`` (لا شبكة).
"""

from __future__ import annotations

import httpx
import pytest

from services.ai_agronomist import ai_evidence_runtime as runtime

pytestmark = pytest.mark.unit


async def _record(monkeypatch, reply: dict) -> dict:
    monkeypatch.setattr(runtime, "AGENT_TOKEN", "agent-token-for-test")
    real = httpx.AsyncClient
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json=reply))
    monkeypatch.setattr(runtime.httpx, "AsyncClient", lambda **kw: real(transport=transport, **kw))
    return await runtime._record_ai_advice_event(
        tenant_id="00000000-0000-0000-0000-000000000001",
        field_id="fld-1",
        question="q",
        evidence_ids=[],
        confidence=0.0,
        selected_imagery_date=None,
        endpoint_mode="chat",
    )


@pytest.mark.parametrize(
    ("reply", "status"),
    [
        ({"ok": True, "persisted": True}, "recorded"),
        (
            {"ok": True, "persisted": False, "reason": "outbox_emit_failed_non_critical"},
            "not_persisted",
        ),
        ({"ok": True}, "unconfirmed"),
        ({}, "unconfirmed"),
        ({"ok": True, "persisted": "yes"}, "unconfirmed"),
    ],
)
async def test_the_receipt_status_is_what_the_platform_confirmed(monkeypatch, reply, status):
    assert (await _record(monkeypatch, reply))["status"] == status


async def test_a_status_key_in_the_reply_cannot_override_the_verdict(monkeypatch):
    out = await _record(monkeypatch, {"persisted": False, "status": "recorded"})
    assert out["status"] == "not_persisted"
