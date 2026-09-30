"""``AI_PROVIDER=vllm`` بلا خادم vLLM حيّ ⇒ سببٌ مُسمّى في ``/readyz`` لا صمت (مراجعة v25).

**العطل:** ``docker-compose.v9.yml`` يضبط ``AI_PROVIDER: ${AI_PROVIDER:-local}`` لخدمتَي
المنصّة والمستشار، والحاوي ``sahool-vllm-jais`` لا يعمل إلّا تحت ``profiles: [vllm]``.
فاختيارُ vllm بلا الملفّ الشخصيّ كان يجعل فحصَ الإقلاع يُعيد ``not_requested`` —
``/readyz`` يقول «لم يُطلَب توليد» — ثمّ يسقط كلُّ نداءٍ حيٍّ بـ``ConnectError`` إلى جواب
الأدلّة صامتاً.

**ما يُثبِته هذا الملفّ** بـ``httpx.MockTransport`` (لا شبكة):
  • خادمٌ غيرُ قابلٍ للحلّ/الوصول ⇒ ``vllm_unreachable`` + تلميحٌ يُسمّي ``--profile vllm``.
  • مهلة ⇒ ``vllm_timeout`` · ردٌّ غيرُ 200 ⇒ ``vllm_http_error`` · نموذجٌ غيرُ مخدوم ⇒
    ``vllm_model_not_served`` · خادمٌ يخدمه ⇒ ``completed``.
  • الفحصُ ``GET /models`` بلا جسم — لا بياناتِ مستخدم ولا تركيب.
  • ``lifespan`` و``/readyz`` **الحقيقيّتان**: الإيصالُ الفاشل يظهر في ``/readyz``، والخدمةُ
    تبقى ``ready`` (التوليدُ اختياريٌّ بعقدٍ fail-safe) — لا 503 ولا انهيار.

**ما لا يفحصه، صراحةً:** لا يُشغّل vLLM حقيقيّاً. شكلُ ``GET /v1/models`` (``data[].id``)
مأخوذٌ من عقد OpenAI-compatible الذي يُعلنه vLLM، لا من قياسٍ حيٍّ في هذه الجلسة.
والمنصّةُ (``sahool-platform``) لا تنادي vLLM وقتَ التشغيل أصلاً — ``ai_provider_config``
يُغذّي كتالوجاً ثابتاً (``/api/v1/ai/models``) و``chat_proxy_reference`` ملفٌّ مرجعيّ غيرُ
مُركَّب — فلا فحصَ جاهزيّةٍ يُضاف لها.
"""

from __future__ import annotations

import asyncio
import types

import httpx
import pytest

pytestmark = pytest.mark.unit

from services.ai_agronomist import ai_generation as G  # noqa: E402

_MODEL = "jais-natural-farmer"


@pytest.fixture(autouse=True)
def _vllm_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_PROVIDER", "vllm")
    monkeypatch.setenv("AI_GENERATION_ENABLED", "true")
    monkeypatch.setenv("VLLM_BASE_URL", "http://sahool-vllm-jais:8000/v1")
    monkeypatch.setenv("VLLM_API_KEY", "probe-key")
    for name in ("AI_MODEL", "AI_MODELS", "VLLM_MODEL"):
        monkeypatch.delenv(name, raising=False)


def _route(monkeypatch: pytest.MonkeyPatch, handler) -> list[httpx.Request]:
    seen: list[httpx.Request] = []
    real = httpx.AsyncClient

    def recording(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(recording), **kw)
    )
    return seen


def _unreachable(request: httpx.Request) -> httpx.Response:
    # ما يقع فعلاً حين لا يعمل الحاوي: اسمُ الخدمة لا يُحَلّ على شبكة compose.
    raise httpx.ConnectError("[Errno -2] Name or service not known", request=request)


def _probe() -> dict[str, str]:
    return asyncio.run(G.preload_local_generation())


def test_unreachable_vllm_is_a_named_failure_with_the_profile_hint(monkeypatch) -> None:
    seen = _route(monkeypatch, _unreachable)
    receipt = _probe()
    assert receipt["status"] == "failed"
    assert receipt["provider"] == "vllm"
    assert receipt["reason"] == "vllm_unreachable"
    assert receipt["error"] == "ConnectError"
    assert receipt["model"] == _MODEL
    assert "--profile vllm" in receipt["hint_ar"]
    assert "sahool-vllm-jais" in receipt["hint_ar"]
    assert len(seen) == 1


def test_the_probe_is_a_bodyless_get_models_with_the_configured_auth(monkeypatch) -> None:
    """لا تركيبَ ولا بياناتِ مستخدم — ``GET /v1/models`` فقط، وبمفتاح المشغّل إن ضُبط."""
    seen = _route(
        monkeypatch,
        lambda r: httpx.Response(200, json={"object": "list", "data": [{"id": _MODEL}]}),
    )
    receipt = _probe()
    assert receipt == {"status": "completed", "provider": "vllm", "model": _MODEL}
    (request,) = seen
    assert request.method == "GET"
    assert request.url.path == "/v1/models"
    assert request.content == b""
    assert request.headers["authorization"] == "Bearer probe-key"


@pytest.mark.parametrize(
    ("handler", "reason", "extra"),
    [
        pytest.param(
            lambda r: (_ for _ in ()).throw(httpx.ReadTimeout("slow", request=r)),
            "vllm_timeout",
            {"error": "ReadTimeout"},
            id="مهلة",
        ),
        pytest.param(
            lambda r: httpx.Response(401, json={"error": "unauthorized"}),
            "vllm_http_error",
            {"http_status": "401"},
            id="401 — مفتاحٌ خاطئ",
        ),
        pytest.param(
            lambda r: httpx.Response(200, text="<html>not vllm</html>"),
            "vllm_invalid_response",
            {},
            id="ليس JSON",
        ),
        pytest.param(
            lambda r: httpx.Response(200, json={"data": [{"id": "other-model"}]}),
            "vllm_model_not_served",
            {"served_models": "other-model"},
            id="نموذجٌ آخر مخدوم",
        ),
    ],
)
def test_each_failure_class_has_its_own_named_reason(monkeypatch, handler, reason, extra) -> None:
    _route(monkeypatch, handler)
    receipt = _probe()
    assert receipt["status"] == "failed" and receipt["provider"] == "vllm"
    assert receipt["reason"] == reason
    for key, value in extra.items():
        assert receipt[key] == value


def test_generation_disabled_does_not_probe_vllm(monkeypatch) -> None:
    monkeypatch.setenv("AI_GENERATION_ENABLED", "false")
    seen = _route(monkeypatch, _unreachable)
    assert _probe() == {"status": "not_requested"}
    assert seen == [], "vLLM لا يُستعمَل حين التوليدُ مُعطَّل — فلا فحص"


def test_the_real_lifespan_and_readyz_report_the_named_reason_without_503(monkeypatch) -> None:
    """الشاهدُ الطرفيّ: ``lifespan`` تُشغّل الفحصَ الحقيقيّ و``/readyz`` تكشف إيصالَه.

    الاعتماديّاتُ الصلبة (RAG/KG/guardrails) جاهزة، وvLLM غيرُ قابلٍ للحلّ. المتوقَّع:
    ``ready`` (التوليد اختياريّ بعقد) **و** ``generation_startup.reason == vllm_unreachable``.
    """
    pytest.importorskip("fastapi")
    from services.ai_agronomist import main as M

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/readyz"):
            return httpx.Response(200, json={"status": "ready"})
        return _unreachable(request)

    seen = _route(monkeypatch, handler)
    monkeypatch.setattr(M, "_GENERATION_RETRY_DELAYS", (0.0,))

    async def scenario() -> dict:
        app = types.SimpleNamespace(state=types.SimpleNamespace())
        monkeypatch.setattr(M, "app", app)
        async with M.lifespan(app):
            for _ in range(400):
                models_calls = [r for r in seen if r.url.path.endswith("/models")]
                if len(models_calls) >= 2:  # الفحصُ الأوّل + إعادةٌ واحدة من الجدول
                    break
                await asyncio.sleep(0.005)
            await asyncio.sleep(0.01)
            return await M.readyz()

    body = asyncio.run(scenario())
    assert body["status"] == "ready"
    startup = body["generation_startup"]
    assert startup["status"] == "failed"
    assert startup["reason"] == "vllm_unreachable"
    assert "--profile vllm" in startup["hint_ar"]
    assert sum(1 for r in seen if r.url.path.endswith("/models")) == 2, (
        "الفشلُ يُعاد فحصُه بجدول AI_GENERATION_PRELOAD_RETRY_DELAYS نفسِه"
    )
