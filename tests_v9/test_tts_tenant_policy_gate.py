"""بوّابةُ سياسة المستأجِر في tts — صفرُ نداءاتٍ خارجيّة حين تمنع السياسةُ أو يتعذّر تحديدُها.

TTS-LOCAL-ONLY-FALLS-BACK-TO-EXTERNAL-PROVIDER-01 · TTS-STREAM-BYPASSES-PROVIDER-SELECTION-01.

**حدُّ الإغلاق (قرار المالك):** طلبُ ``local_only`` مع تعذّر مزوّدٍ محلّيّ يفشل بـ503 مُسمّى،
واختبارٌ يُثبت **صفرَ استدعاءاتٍ خارجيّة** في مسارَي التركيب **والبثّ**؛ البثُّ يخضع للسياسة
واختيار المزوِّد نفسيهما، والبوّابةُ قبل بدء الاستجابة (503 حقيقيّ لا 200 يفشل في منتصفه).

**كيف تُعَدّ النداءاتُ الخارجيّة:** المزوّدُ الخارجيّ الوحيد edge — يُستبدَل تركيبُه
(``EdgeTTSProvider.synthesize``) وبثُّه (``main.edge_tts.Communicate``) بعدّادَين. سياسةُ
المنصّة تُحقَن عبر ``tts_tenant_policy._fetch_me`` (لا شبكة).
"""

from __future__ import annotations

import asyncio
import sys
import types
from pathlib import Path

import pytest

# قيمةُ الاختبار المشتركة من conftest — لا حرفيّةَ سرٍّ جديدة في التاريخ (gitleaks على #1122).
from conftest import TEST_JWT_SECRET as _JWT_SECRET

pytest.importorskip("fastapi")

pytestmark = [pytest.mark.unit, pytest.mark.security]

ROOT = Path(__file__).resolve().parents[1]
_SVC_DIR = ROOT / "services" / "tts-service"
_TENANT = "00000000-0000-0000-0000-0000000000a1"
_SIBLINGS = (
    "main",
    "router_registry",
    "routers",
    "routers.tts",
    "routers.health",
    "providers",
    "arabic_normalizer",
    "tts_tenant_policy",
)


def _load(monkeypatch):
    """يحمّل tts نظيفاً (تصادمُ اسم ``main``/``routers`` بين الخدمات معروف) ويُرجِع الوحدات."""
    monkeypatch.setenv("JWT_SECRET", _JWT_SECRET)
    monkeypatch.delenv("JWT_PUBLIC_KEY", raising=False)
    if "edge_tts" not in sys.modules:
        try:
            import edge_tts  # noqa: F401
        except ImportError:
            stub = types.ModuleType("edge_tts")
            stub.Communicate = object
            sys.modules["edge_tts"] = stub
    while str(_SVC_DIR) in sys.path:
        sys.path.remove(str(_SVC_DIR))
    sys.path.insert(0, str(_SVC_DIR))
    for name in _SIBLINGS:
        sys.modules.pop(name, None)
    import main
    import providers
    import tts_tenant_policy

    assert hasattr(main, "VOICES"), "استُورِد ``main`` خدمةٍ أخرى بدل tts"
    if not main.JWT_SECRET:
        pytest.skip("JWT_SECRET لم يُلتقَط عند التحميل")
    return main, providers, tts_tenant_policy


class _External:
    """عدّادُ كلِّ ما يغادر حدَّ المستأجِر عبر edge (تركيباً وبثّاً)."""

    def __init__(self) -> None:
        self.calls = 0

    def install(self, monkeypatch, main, providers) -> None:
        external = self

        async def synthesize(self_, text, voice, rate, pitch, volume):
            external.calls += 1
            return b"EDGE-AUDIO"

        class Communicate:
            def __init__(self, *a, **k):
                external.calls += 1

            async def stream(self):
                yield {"type": "audio", "data": b"EDGE-STREAM"}

        monkeypatch.setattr(providers.EdgeTTSProvider, "synthesize", synthesize)
        monkeypatch.setattr(providers.EdgeTTSProvider, "available", lambda self: True)
        monkeypatch.setattr(main.edge_tts, "Communicate", Communicate, raising=False)


def _no_local_providers(monkeypatch, providers) -> None:
    monkeypatch.setattr(providers.PiperProvider, "available", lambda self: False)
    monkeypatch.setattr(providers.XTTSProvider, "available", lambda self: False)


def _policy(monkeypatch, tts_policy, mode=None, *, tenant=_TENANT, raises=False):
    """يحقن ردَّ ``/api/v1/me`` بغلافٍ بالوضع المُعطى، ويُرجِع عدّادَ قراءات المنصّة."""
    monkeypatch.setenv("PLATFORM_API_URL", "http://sahool-platform:8000")
    asked = {"n": 0}

    async def fake_fetch(url, authorization):
        asked["n"] += 1
        assert url == "http://sahool-platform:8000/api/v1/me"
        assert authorization.startswith("Bearer ")
        if raises:
            raise TimeoutError("platform unreachable")
        return {
            "tenant_id": _TENANT,
            "ai_policy_envelope": {"policy_mode": mode, "tenant_id": tenant},
        }

    monkeypatch.setattr(tts_policy, "_fetch_me", fake_fetch)
    return asked


def _bearer(main, tenant=_TENANT):
    from jose import jwt

    token = jwt.encode(
        {"sub": "user-1", "iss": "sahool-auth", "tenant_id": tenant, "aud": "sahool"},
        main.JWT_SECRET,
        algorithm="HS256",
    )
    return {"Authorization": f"Bearer {token}"}


def _client(main):
    from fastapi.testclient import TestClient

    return TestClient(main.app)


_BODY = {"text": "نصّ نصيحةٍ فيه سياقُ المزرعة", "voice": "yemeni_male"}


def _assert_blocked(resp, mode):
    assert resp.status_code == 503, resp.text
    detail = resp.json()["detail"]
    assert detail["error"] == "local_provider_unavailable_for_policy"
    assert detail["policy_mode"] == mode


# ── السياسةُ تمنع ⇒ 503 مُسمّى، صفرُ نداءاتٍ خارجيّة — في المسارين ─────────────────────


@pytest.mark.parametrize("path", ["/v1/tts/synthesize", "/v1/tts/stream"])
@pytest.mark.parametrize("mode", ["local_only", "redacted_external"])
def test_a_policy_that_forbids_raw_text_out_makes_zero_external_calls(monkeypatch, path, mode):
    main, providers, tts_policy = _load(monkeypatch)
    ext = _External()
    ext.install(monkeypatch, main, providers)
    _no_local_providers(monkeypatch, providers)
    _policy(monkeypatch, tts_policy, mode)
    resp = _client(main).post(path, json=_BODY, headers=_bearer(main))
    _assert_blocked(resp, "local_only" if mode == "local_only" else mode)
    assert ext.calls == 0


@pytest.mark.parametrize("path", ["/v1/tts/synthesize", "/v1/tts/stream"])
def test_an_unreadable_policy_fails_closed_with_zero_external_calls(monkeypatch, path):
    main, providers, tts_policy = _load(monkeypatch)
    ext = _External()
    ext.install(monkeypatch, main, providers)
    _no_local_providers(monkeypatch, providers)
    asked = _policy(monkeypatch, tts_policy, raises=True)
    resp = _client(main).post(path, json=_BODY, headers=_bearer(main))
    _assert_blocked(resp, "local_only")
    assert asked["n"] == 1 and ext.calls == 0


@pytest.mark.parametrize("path", ["/v1/tts/synthesize", "/v1/tts/stream"])
def test_an_envelope_for_another_tenant_fails_closed(monkeypatch, path):
    main, providers, tts_policy = _load(monkeypatch)
    ext = _External()
    ext.install(monkeypatch, main, providers)
    _no_local_providers(monkeypatch, providers)
    _policy(monkeypatch, tts_policy, "full_external", tenant="ffffffff-0000-0000-0000-000000000000")
    resp = _client(main).post(path, json=_BODY, headers=_bearer(main))
    _assert_blocked(resp, "local_only")
    assert ext.calls == 0


@pytest.mark.parametrize("path", ["/v1/tts/synthesize", "/v1/tts/stream"])
def test_no_platform_url_fails_closed_without_asking(monkeypatch, path):
    main, providers, tts_policy = _load(monkeypatch)
    ext = _External()
    ext.install(monkeypatch, main, providers)
    _no_local_providers(monkeypatch, providers)
    asked = _policy(monkeypatch, tts_policy, "full_external")
    monkeypatch.delenv("PLATFORM_API_URL")
    resp = _client(main).post(path, json=_BODY, headers=_bearer(main))
    _assert_blocked(resp, "local_only")
    assert asked["n"] == 0 and ext.calls == 0


@pytest.mark.parametrize("path", ["/v1/tts/synthesize", "/v1/tts/stream"])
def test_the_service_token_has_no_tenant_and_is_most_restrictive(monkeypatch, path):
    """``__service__``: لا مستأجِرَ موثَّقاً تُقرأ سياستُه — حتّى لو كانت المنصّةُ ستقول full."""
    main, providers, tts_policy = _load(monkeypatch)
    monkeypatch.setenv("SAHOOL_AGENT_TOKEN", "svc-shared-secret-0001")
    ext = _External()
    ext.install(monkeypatch, main, providers)
    _no_local_providers(monkeypatch, providers)
    asked = _policy(monkeypatch, tts_policy, "full_external")
    resp = _client(main).post(path, json=_BODY, headers={"X-Agent-Token": "svc-shared-secret-0001"})
    _assert_blocked(resp, "local_only")
    assert asked["n"] == 0 and ext.calls == 0


# ── السياسةُ تسمح أو يتوفّر محلّيّ ⇒ يعمل ──────────────────────────────────────────


def test_full_external_synthesizes_through_edge(monkeypatch):
    main, providers, tts_policy = _load(monkeypatch)
    ext = _External()
    ext.install(monkeypatch, main, providers)
    _policy(monkeypatch, tts_policy, "full_external")
    resp = _client(main).post("/v1/tts/synthesize", json=_BODY, headers=_bearer(main))
    assert resp.status_code == 200, resp.text
    assert resp.content == b"EDGE-AUDIO" and ext.calls == 1


def test_full_external_streams_through_edge(monkeypatch):
    main, providers, tts_policy = _load(monkeypatch)
    ext = _External()
    ext.install(monkeypatch, main, providers)
    _policy(monkeypatch, tts_policy, "full_external")
    resp = _client(main).post("/v1/tts/stream", json=_BODY, headers=_bearer(main))
    assert resp.status_code == 200, resp.text
    assert resp.content == b"EDGE-STREAM" and ext.calls == 1


@pytest.mark.parametrize("path", ["/v1/tts/synthesize", "/v1/tts/stream"])
def test_local_only_uses_an_available_local_provider_and_never_edge(monkeypatch, path):
    main, providers, tts_policy = _load(monkeypatch)
    ext = _External()
    ext.install(monkeypatch, main, providers)
    _no_local_providers(monkeypatch, providers)
    monkeypatch.setattr(providers.PiperProvider, "available", lambda self: True)

    spoken: list[str] = []

    async def piper(self, text, voice, rate, pitch, volume):
        spoken.append(text)
        return b"RIFF-LOCAL-WAV"

    monkeypatch.setattr(providers.PiperProvider, "synthesize", piper)
    _policy(monkeypatch, tts_policy, "local_only")
    raw = "مـرحـبـاً بالمزارع"
    resp = _client(main).post(
        path, json={**_BODY, "text": raw, "normalize": True}, headers=_bearer(main)
    )
    assert resp.status_code == 200, resp.text
    assert resp.content == b"RIFF-LOCAL-WAV" and ext.calls == 0
    # مراجعة #1122: المسارُ المحلّيّ يحمل التطبيعَ في البثّ كما في التركيب، ويُعلِن وعاءَ
    # المزوّد الفعليّ (Piper يكتب WAV) لا ``audio/mpeg`` ثابتاً.
    expected = main.ArabicTextNormalizer().normalize(raw)
    assert expected != raw, "نصُّ الاختبار يجب أن يتغيّر بالتطبيع كي يكون الفحصُ ذا معنى"
    assert spoken == [expected]
    assert resp.headers["content-type"].startswith("audio/wav")


# ── المنطقُ النقيّ ────────────────────────────────────────────────────────────


def test_only_full_external_allows_raw_text_out(monkeypatch):
    _main, _providers, tts_policy = _load(monkeypatch)
    assert tts_policy.external_allowed("full_external")
    assert not tts_policy.external_allowed("redacted_external")
    assert not tts_policy.external_allowed("local_only")
    assert not tts_policy.external_allowed("anything-else")


def test_policy_mode_from_me_rejects_malformed_or_foreign_payloads(monkeypatch):
    _main, _providers, tts_policy = _load(monkeypatch)
    ok = {
        "tenant_id": "t",
        "ai_policy_envelope": {"tenant_id": "t", "policy_mode": "full_external"},
    }
    assert tts_policy.policy_mode_from_me(ok, "t") == "full_external"
    assert tts_policy.policy_mode_from_me(ok, "other") == "local_only"
    assert tts_policy.policy_mode_from_me({"tenant_id": "t"}, "t") == "local_only"
    bad_mode = {"tenant_id": "t", "ai_policy_envelope": {"tenant_id": "t", "policy_mode": "x"}}
    assert tts_policy.policy_mode_from_me(bad_mode, "t") == "local_only"
    assert tts_policy.policy_mode_from_me(None, "t") == "local_only"


def test_resolve_without_bearer_never_asks_the_platform(monkeypatch):
    _main, _providers, tts_policy = _load(monkeypatch)
    asked = _policy(monkeypatch, tts_policy, "full_external")
    mode = asyncio.run(tts_policy.resolve_policy_mode({"tenant_id": _TENANT}, None))
    assert mode == "local_only" and asked["n"] == 0
