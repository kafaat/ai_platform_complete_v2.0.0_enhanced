"""صدقُ الإدامة والتأريض في مسار مستشار الذكاء (P0، التدقيق الموحَّد 2026-09-13).

١) ``_emit_domain_event`` يُعيد ``True`` حين كُتب الحدث و``False`` حين ابتُلع فشلٌ غير حرج،
   و``/internal/events/ai-advice`` يمرّر ذلك في ``ok``/``persisted`` بدل ``ok: True`` ثابتة.
٢) ``generated_grounded`` لا يُوسَم إلّا مع مقتطفات RAG فعليّة؛ نصٌّ مولَّد فوق صفر
   مقتطفات يُحجَب (``suppressed_ungrounded``) ويبقى جوابُ الأدلّة.
٣) ``guardrail_result`` يقول إنّ النصّ المولَّد لم يُفحَص بحاجز بدل عبارة «لا قرار» الثابتة.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
PLATFORM = ROOT / "services" / "sahool-platform"
INTERNAL_SERVICE = PLATFORM / "api" / "routers" / "internal_service.py"


@pytest.fixture(scope="module")
def main_mod():
    if str(PLATFORM) not in sys.path:
        sys.path.insert(0, str(PLATFORM))
    pytest.importorskip("fastapi")
    import api.main as main

    return main


class _Tx:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False


class _Conn:
    def transaction(self):
        return _Tx()


class _Bus:
    should_fail = False

    def __init__(self, *args, **kwargs):
        pass

    async def emit(self, **kwargs):
        if _Bus.should_fail:
            raise RuntimeError("outbox table missing")


@pytest.fixture
def bus(monkeypatch, main_mod):
    import api.event_bus as event_bus

    monkeypatch.setattr(event_bus, "EventBus", _Bus)
    monkeypatch.setattr(main_mod, "get_pool", lambda: None)
    _Bus.should_fail = False
    return _Bus


_USER = SimpleNamespace(tenant_id="11111111-1111-1111-1111-111111111111", user_id="u1")


@pytest.mark.asyncio
async def test_emit_returns_true_when_the_event_is_written(main_mod, bus):
    ok = await main_mod._emit_domain_event(
        _Conn(), _USER, "AI_SUGGESTION", "tenant", "t", {}, critical=False
    )
    assert ok is True


@pytest.mark.asyncio
async def test_emit_returns_false_when_a_non_critical_failure_is_swallowed(main_mod, bus):
    bus.should_fail = True
    ok = await main_mod._emit_domain_event(
        _Conn(), _USER, "AI_SUGGESTION", "tenant", "t", {}, critical=False
    )
    assert ok is False


@pytest.mark.asyncio
async def test_critical_failure_still_raises(main_mod, bus):
    bus.should_fail = True
    with pytest.raises(RuntimeError):
        await main_mod._emit_domain_event(
            _Conn(), _USER, "AI_SUGGESTION", "tenant", "t", {}, critical=True
        )


def test_ai_advice_endpoint_reports_the_real_persistence_outcome():
    src = INTERNAL_SERVICE.read_text(encoding="utf-8")
    start = src.index('@router.post("/internal/events/ai-advice")')
    body = src[start : start + 2500]
    assert "persisted = await main._emit_domain_event(" in body
    assert '"ok": bool(persisted)' in body
    assert '"persisted": bool(persisted)' in body
    assert '"ok": True,' not in body, "ok ثابتة عادت — الردّ يجب أن يعكس الإدامة الحقيقيّة"


# ── مسار ai_agronomist ───────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def runtime():
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    os.environ.setdefault("SAHOOL_ENV", "development")
    pytest.importorskip("httpx")
    from services.ai_agronomist import ai_evidence_runtime as rt

    return rt


def test_generation_is_grounded_only_with_rag_snippets(runtime):
    assert runtime._generation_is_grounded({"rag": [{"chunk_id": "c1", "text": "..."}]})
    assert not runtime._generation_is_grounded({"rag": []})
    assert not runtime._generation_is_grounded({"rag": [], "knowledge_graph": [{"e": 1}]})
    assert not runtime._generation_is_grounded({})


def test_guardrail_result_names_unchecked_generated_text(runtime):
    generated = runtime._guardrail_result("generated_grounded", "succeeded")
    assert generated["status"] == "not_executed"
    assert generated["generated_text_checked"] is False
    assert "guardrail" in generated["reason"]
    evidence_only = runtime._guardrail_result("evidence_only", "suppressed_ungrounded")
    assert evidence_only["generated_text_checked"] is None
    assert evidence_only["generation_status"] == "suppressed_ungrounded"


def test_chat_suppresses_generated_text_without_rag_grounding_in_source(runtime):
    src = Path(runtime.__file__).read_text(encoding="utf-8")
    assert "if _generation_is_grounded(annotations)" in src
    assert '"suppressed_ungrounded"' in src
    assert '"suppressed_unvalidated_output"' in src
    assert "answer_ar = gen.text" not in src, (
        "Unchecked free text cannot cross the publication gate"
    )


def test_metadata_only_rag_hits_do_not_ground_generation(runtime):
    """Copilot على #1001: مقتطف بلا نصّ ليس شاهداً — التأريض يشترط text/content/snippet غير فارغ."""
    assert not runtime._generation_is_grounded({"rag": [{"chunk_id": "c1"}]})
    assert not runtime._generation_is_grounded({"rag": [{"chunk_id": "c1", "text": "   "}]})
    assert not runtime._generation_is_grounded({"rag": ["not-a-dict"]})
    assert runtime._generation_is_grounded({"rag": [{"chunk_id": "c1", "snippet": "ريّ القمح"}]})
    assert runtime._generation_is_grounded({"rag": [{"id": "c2", "content": "نصّ"}]})
