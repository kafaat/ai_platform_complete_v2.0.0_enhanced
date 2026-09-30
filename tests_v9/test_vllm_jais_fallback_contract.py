"""VLLM-JAIS-FALLBACK-UNPROVEN-01 — ماذا يحدث حين يغيب ``sahool-vllm-jais`` (تدقيق المالك §3.5).

**الادّعاء الذي اختُبِر:** المستهلكون المهيَّؤون بـ``AI_PROVIDER=vllm`` «يسقطون إلى Ollama» حين
لا يعمل الحاوي (خلف ``profiles: [vllm]``). قرارُ المالك (2026-09-30): الاختبارُ يحكم — السقوطُ
نظيفٌ إن تحقّقت الثلاثة من مسار المستهلك نفسِه: (١) لا استثناءَ يفلت، (٢) جوابٌ حقيقيٌّ غيرُ
فارغ **من الخلفيّة البديلة**، (٣) الخلفيّةُ التي أجابت تُعرَف **من الردّ نفسِه**.

**المقيس (a40f654b، بهذا الملفّ قبل الإصلاح):** (١) نجح في كلّ صنف فشل (رفضُ اتّصال · فشلُ
DNS · مهلة). (٢) رسب: لا مسارَ Ollama في الشيفرة أصلاً — ``resolve_generation`` يختار مزوّداً
واحداً من ``AI_PROVIDER``، و``generate`` يُعيد ``None`` عند أيّ فشل فيُعرَض جوابُ الأدلّة
المُعلَّب؛ Ollama لم يُنادَ في أيّ حالة. (٣) رسب: ``generation_provider=None`` ولا حقلَ يسمّي
الخلفيّةَ المُحاوَلة. ولقطةُ ``/healthz/ai-provider`` كانت تقول ``available: true`` والخادمُ غائب.

**فالحكمُ بقاعدة المالك: بوّابةٌ لا توثيقُ سقوط.** ما يُثبته هذا الملفّ بعدها:
  • لا بديلَ Ollama (يُثبَت أنّه **لا يُنادى** — كي لا يُدّعى لاحقاً بلا اختبار).
  • الردُّ يسمّي الخلفيّةَ التي فشلت (``generation_unavailable``) مع سبب الرصد.
  • اللقطةُ لا تدّعي التوافرَ إلّا بعد رصد خادمٍ يُجيب — وتتعافى حين يقوم (لا تعلق).
  • الضابط: خادمٌ حيّ ⇒ الخلفيّةُ ``vllm``/``jais-natural-farmer`` ظاهرةٌ في الردّ.

كلُّه عبر ``httpx.MockTransport`` — لا شبكة ولا GPU.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import httpx
import pytest

pytestmark = pytest.mark.unit

from services.ai_agronomist import ai_generation as G  # noqa: E402

VLLM_HOST = "sahool-vllm-jais"
OLLAMA_HOST = "sahool-ollama"
JAIS_MODEL = "jais-natural-farmer"
JAIS_TEXT = "جوابٌ من جيس: راقب رطوبة التربة قبل الريّ."
OLLAMA_TEXT = "جوابٌ من Ollama — إن ظهر هذا فقد وُجد سقوطٌ لم يُعلَن."
_REAL_ASYNC_CLIENT = httpx.AsyncClient  # قبل أيّ ترقيع — كي يُعاد التوجيه داخل الاختبار الواحد

# صنفُ الفشل ⇒ السببُ المُسمّى المتوقَّع في الرصد.
FAILURES = {
    "connection_refused": "vllm_unreachable",
    "dns_failure": "vllm_unreachable",
    "connect_timeout": "vllm_timeout",
}


def _failing(kind: str):
    def handler(request: httpx.Request) -> httpx.Response:
        if kind == "connection_refused":
            raise httpx.ConnectError("[Errno 111] Connection refused", request=request)
        if kind == "dns_failure":
            raise httpx.ConnectError("[Errno -2] Name or service not known", request=request)
        raise httpx.ConnectTimeout("timed out", request=request)

    return handler


def _completion(text: str, model: str) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "model": model,
            "choices": [
                {"message": {"role": "assistant", "content": text}, "finish_reason": "stop"}
            ],
        },
    )


def _serving(request: httpx.Request) -> httpx.Response:
    if request.url.path.endswith("/models"):
        return httpx.Response(200, json={"object": "list", "data": [{"id": JAIS_MODEL}]})
    return _completion(JAIS_TEXT, JAIS_MODEL)


@pytest.fixture(autouse=True)
def _vllm_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_PROVIDER", "vllm")
    monkeypatch.setenv("AI_GENERATION_ENABLED", "true")
    monkeypatch.setenv("VLLM_BASE_URL", "http://sahool-vllm-jais:8000/v1")
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://sahool-ollama:11434")
    for name in ("AI_MODEL", "AI_MODELS", "VLLM_MODEL", "VLLM_API_KEY", "LOCAL_LLM_MODEL"):
        monkeypatch.delenv(name, raising=False)
    # الرصدُ حالةُ عمليّة؛ كلُّ اختبارٍ يبدأ من «لم يُرصَد» (لا تسرُّبَ بين الاختبارات).
    G._observe_vllm({"status": "unobserved", "provider": "vllm"})


def _route(monkeypatch: pytest.MonkeyPatch, vllm_handler) -> list[httpx.Request]:
    """vLLM ⇒ ``vllm_handler`` · Ollama ⇒ جوابٌ حقيقيّ جاهز · غيرهما (RAG/KG/المنصّة) ⇒ فارغ."""
    seen: list[httpx.Request] = []
    real = _REAL_ASYNC_CLIENT

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.host == VLLM_HOST:
            return vllm_handler(request)
        if request.url.host == OLLAMA_HOST:
            return _completion(OLLAMA_TEXT, "llama3.2:3b")
        return httpx.Response(200, json={"annotations": [], "edges": []})

    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(handler), **kw)
    )
    return seen


def _hosts(seen: list[httpx.Request]) -> set[str]:
    return {r.url.host for r in seen}


async def _chat(monkeypatch: pytest.MonkeyPatch) -> dict:
    """المسارُ الحيّ لـ``/v1/chat`` — ``build_evidence_response`` بـ``generate`` الحقيقيّة."""
    from services.ai_agronomist import ai_evidence_runtime as runtime
    from services.ai_agronomist.main import AdvisorQuery

    monkeypatch.setattr(
        runtime, "_record_ai_advice_event", AsyncMock(return_value={"status": "recorded"})
    )
    return await runtime.build_evidence_response(
        AdvisorQuery(question="متى أروي؟"),
        endpoint_mode="chat",
        x_tenant_id="t1",
        save_agent_tool_audit=lambda value: None,
        save_pending_approval=lambda value: None,
    )


# ── المستهلك ١: ai_generation.generate ─────────────────────────────────────────


@pytest.mark.parametrize("kind", sorted(FAILURES))
async def test_generate_unreachable_vllm_does_not_raise_and_does_not_fall_back_to_ollama(
    monkeypatch, kind
) -> None:
    seen = _route(monkeypatch, _failing(kind))
    result = await G.generate("متى أروي؟", "أدلّة")  # (١) لا يرفع
    assert result is None, "لا بديلَ في الشيفرة: الفشلُ يُعيد None فيسقط المستدعي إلى الأدلّة"
    assert OLLAMA_HOST not in _hosts(seen), "Ollama نُودي — سقوطٌ لم يُعلَن ولم يُختبَر"
    assert _hosts(seen) == {VLLM_HOST}
    observed = G.vllm_runtime_state()
    assert observed["status"] == "failed"
    assert observed["reason"] == FAILURES[kind]
    assert "--profile vllm" in observed["hint_ar"]


async def test_generate_reachable_vllm_identifies_its_backend(monkeypatch) -> None:
    seen = _route(monkeypatch, _serving)
    result = await G.generate("متى أروي؟", "أدلّة")
    assert result is not None
    assert (result.provider, result.model, result.text) == ("vllm", JAIS_MODEL, JAIS_TEXT)
    assert _hosts(seen) == {VLLM_HOST}
    assert G.vllm_runtime_state() == {
        "status": "completed",
        "provider": "vllm",
        "model": JAIS_MODEL,
    }


async def test_generate_http_error_is_observed_as_a_named_failure(monkeypatch) -> None:
    _route(monkeypatch, lambda r: httpx.Response(503, json={"error": "loading"}))
    assert await G.generate("متى أروي؟", "أدلّة") is None
    observed = G.vllm_runtime_state()
    assert (observed["status"], observed["reason"], observed["http_status"]) == (
        "failed",
        "vllm_http_error",
        "503",
    )


# ── المستهلك ٢: مسار المحادثة (build_evidence_response) ──────────────────────


@pytest.mark.parametrize("kind", sorted(FAILURES))
async def test_chat_names_the_failed_backend_in_the_response_itself(monkeypatch, kind) -> None:
    seen = _route(monkeypatch, _failing(kind))
    out = await _chat(monkeypatch)  # (١) لا يرفع
    assert OLLAMA_HOST not in _hosts(seen)
    # الجوابُ جوابُ الأدلّة ولا يُنسَب لنموذج — ولا يدّعي توليداً.
    assert out["mode"] == "evidence_only"
    assert out["generation_status"] == "attempted_failed"
    assert out["generation_provider"] is None and out["generation_model"] is None
    # (٣) الخلفيّةُ التي حُووِلت وفشلت مُسمّاةٌ في الردّ، بسبب الرصد.
    unavailable = out["generation_unavailable"]
    assert unavailable["provider"] == "vllm"
    assert unavailable["model"] == JAIS_MODEL
    assert unavailable["runtime"]["status"] == "failed"
    assert unavailable["runtime"]["reason"] == FAILURES[kind]


async def test_chat_control_reachable_vllm_is_identified(monkeypatch) -> None:
    _route(monkeypatch, _serving)
    out = await _chat(monkeypatch)
    assert out["generation_unavailable"] is None
    # ``generation_attempted_*`` يفصل المحاولةَ عن النسبة في فرعٍ آخر؛ الضابطُ يقبل الاسمين.
    named = {out.get("generation_provider"), out.get("generation_attempted_provider")}
    assert "vllm" in named
    models = {out.get("generation_model"), out.get("generation_attempted_model")}
    assert JAIS_MODEL in models


# ── المستهلك ٣: لقطة /healthz/ai-provider (ادّعاء القدرة) ─────────────────────


def test_snapshot_does_not_claim_vllm_before_it_is_observed() -> None:
    snap = G.public_provider_snapshot()
    assert snap["provider"] == "vllm"
    assert snap["available"] is False
    assert snap["vllm_runtime"]["status"] == "unobserved"


@pytest.mark.parametrize("kind", sorted(FAILURES))
async def test_snapshot_does_not_claim_vllm_after_a_failed_attempt(monkeypatch, kind) -> None:
    _route(monkeypatch, _failing(kind))
    await G.generate("متى أروي؟", "أدلّة")
    snap = G.public_provider_snapshot()
    assert snap["available"] is False
    assert snap["vllm_runtime"]["reason"] == FAILURES[kind]


async def test_snapshot_follows_the_startup_probe(monkeypatch) -> None:
    _route(monkeypatch, _failing("dns_failure"))
    assert (await G.preload_local_generation())["reason"] == "vllm_unreachable"
    assert G.public_provider_snapshot()["available"] is False
    _route(monkeypatch, _serving)
    assert (await G.preload_local_generation())["status"] == "completed"
    assert G.public_provider_snapshot()["available"] is True


async def test_snapshot_recovers_when_vllm_comes_up_later(monkeypatch) -> None:
    """لا تعلق على فشلٍ قديم: خادمٌ يقوم بعد الإقلاع يُثبته أوّلُ توليدٍ ناجح."""
    _route(monkeypatch, _failing("connection_refused"))
    await G.generate("متى أروي؟", "أدلّة")
    assert G.public_provider_snapshot()["available"] is False
    _route(monkeypatch, _serving)
    assert (await G.generate("متى أروي؟", "أدلّة")) is not None
    assert G.public_provider_snapshot()["available"] is True


def test_snapshot_for_local_provider_is_unchanged(monkeypatch) -> None:
    monkeypatch.setenv("AI_PROVIDER", "local")
    snap = G.public_provider_snapshot()
    assert snap["available"] is True
    assert "vllm_runtime" not in snap
