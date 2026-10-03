"""مزوّدُ Piper على واجهة ``piper-tts`` ≥ 1.3 — TTS-PIPER-PROVIDER-CALLS-THE-PRE-1.3-API-01.

``piper-tts`` 1.3 جعل ``PiperVoice.synthesize(text, syn_config=None)`` مولِّدَ ``AudioChunk``
ونقل كتابةَ WAV إلى ``synthesize_wav(text, wav_file)`` (مقيس على الإصدار 1.8.0). النداءُ القديم
``synthesize(text, wav)`` يُمرِّر ملفَّ WAV مكانَ الإعدادات فلا يُكتب إطار.

الوحدةُ المزيّفة أدناه تُحاكي **تلك الواجهة بعينها** (مولِّدٌ لا يكتب، و``synthesize_wav`` يكتب)،
فاختبارُ التركيب يحمرّ على النداء القديم. لا مكتبةَ حقيقيّة ولا نموذج: التركيبُ الحقيقيّ بنموذجٍ
عربيّ ببصمةٍ ثابتة اختبارٌ منفصل بعد حسم الترخيص.
"""

from __future__ import annotations

import asyncio
import io
import sys
import threading
import time
import types
import wave

import pytest

pytest.importorskip("fastapi")

from tests_v9.test_tts_tenant_policy_gate import (  # noqa: E402 - بعد importorskip
    _BODY,
    _bearer,
    _client,
    _External,
    _load,
    _no_local_providers,
    _policy,
)

pytestmark = [pytest.mark.unit, pytest.mark.security]


class _FakeVoice:
    """``PiperVoice`` بواجهة 1.3+ — يسجّل التحميل والخيط والتزامن."""

    loads = 0
    corrupt = False
    threads: list[int] = []
    active = 0
    max_active = 0
    lock = threading.Lock()

    @classmethod
    def reset(cls) -> None:
        cls.loads, cls.corrupt, cls.threads, cls.active, cls.max_active = 0, False, [], 0, 0

    @classmethod
    def load(cls, path, config_path=None, use_cuda=False, **kwargs):
        cls.loads += 1
        if cls.corrupt:
            raise ValueError("INVALID_PROTOBUF: Load model failed")
        return cls()

    def synthesize(self, text, syn_config=None, include_alignments=False):
        # 1.3+: مولِّدٌ لا يكتب شيئاً — النداءُ القديم ``synthesize(text, wav)`` ينتهي هنا.
        yield from ()

    def synthesize_wav(self, text, wav_file, syn_config=None, set_wav_format=True, **kwargs):
        cls = type(self)
        with cls.lock:
            cls.active += 1
            cls.max_active = max(cls.max_active, cls.active)
            cls.threads.append(threading.get_ident())
        try:
            time.sleep(0.05)
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(22050)
            wav_file.writeframes(b"\x01\x00" * 2205)
        finally:
            with cls.lock:
                cls.active -= 1


@pytest.fixture
def piper_env(monkeypatch, tmp_path):
    """مكتبةٌ مزيّفة بواجهة 1.3+ + ملفُّ نموذجٍ موجود — ويُرجِع (main, providers, tts_policy)."""
    main, providers, tts_policy = _load(monkeypatch)
    module = types.ModuleType("piper")
    module.PiperVoice = _FakeVoice
    monkeypatch.setitem(sys.modules, "piper", module)
    monkeypatch.setattr(providers, "_PIPER_LIB_AVAILABLE", True)
    model = tmp_path / "ar_JO-kareem-medium.onnx"
    model.write_bytes(b"fake-onnx")
    monkeypatch.setenv("PIPER_VOICE_PATH", str(model))
    monkeypatch.setattr(providers.PiperProvider, "_voices", {}, raising=False)
    _FakeVoice.reset()
    return main, providers, tts_policy


def _frames(audio: bytes) -> int:
    with wave.open(io.BytesIO(audio), "rb") as w:
        return w.getnframes()


def test_synthesis_goes_through_synthesize_wav_and_is_decodable(piper_env):
    _main, providers, _ = piper_env
    audio = asyncio.run(providers.PiperProvider().synthesize("مرحباً", "v", "+0%", "+0Hz", "+0%"))
    assert _frames(audio) == 2205


def test_the_model_loads_once_per_process(piper_env):
    _main, providers, _ = piper_env

    async def twice():
        provider = providers.PiperProvider()
        await provider.synthesize("أ", "v", "+0%", "+0Hz", "+0%")
        await providers.PiperProvider().synthesize("ب", "v", "+0%", "+0Hz", "+0%")
        await provider.synthesize("ج", "v", "+0%", "+0Hz", "+0%")

    asyncio.run(twice())
    assert _FakeVoice.loads == 1


def test_synthesis_runs_off_the_event_loop_thread(piper_env):
    _main, providers, _ = piper_env

    async def run():
        loop_thread = threading.get_ident()
        await providers.PiperProvider().synthesize("أ", "v", "+0%", "+0Hz", "+0%")
        return loop_thread

    loop_thread = asyncio.run(run())
    assert _FakeVoice.threads and loop_thread not in _FakeVoice.threads


@pytest.mark.parametrize(("limit", "expected"), [("1", 1), ("2", 2)])
def test_concurrency_is_bounded(piper_env, monkeypatch, limit, expected):
    _main, providers, _ = piper_env
    monkeypatch.setenv("PIPER_MAX_CONCURRENCY", limit)

    async def burst():
        provider = providers.PiperProvider()
        await asyncio.gather(
            *(provider.synthesize(str(i), "v", "+0%", "+0Hz", "+0%") for i in range(4))
        )

    asyncio.run(burst())
    assert _FakeVoice.max_active == expected


def test_a_library_without_synthesize_wav_is_refused_by_name(piper_env, monkeypatch):
    _main, providers, _ = piper_env

    class Pre13Voice:
        @classmethod
        def load(cls, path, **kwargs):
            return cls()

        def synthesize(self, text, wav_file):
            pass

    monkeypatch.setattr(sys.modules["piper"], "PiperVoice", Pre13Voice)
    with pytest.raises(providers.PiperLoadError, match="synthesize_wav"):
        asyncio.run(providers.PiperProvider().synthesize("أ", "v", "+0%", "+0Hz", "+0%"))


# ── عبر المسارات القائمة: صوتٌ محلّيّ حقيقيّ البنية، وفشلٌ مُسمّى بلا edge ─────────────


def _local_only_piper(monkeypatch, main, providers, tts_policy) -> _External:
    ext = _External()
    ext.install(monkeypatch, main, providers)
    monkeypatch.setattr(providers.XTTSProvider, "available", lambda self: False)
    _policy(monkeypatch, tts_policy, "local_only")
    return ext


@pytest.mark.parametrize("path", ["/v1/tts/synthesize", "/v1/tts/stream"])
def test_local_only_gets_a_decodable_wav_from_piper_and_zero_edge_calls(
    piper_env, monkeypatch, path
):
    main, providers, tts_policy = piper_env
    ext = _local_only_piper(monkeypatch, main, providers, tts_policy)
    resp = _client(main).post(path, json=_BODY, headers=_bearer(main))
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"].startswith("audio/wav")
    assert _frames(resp.content) == 2205
    assert ext.calls == 0


@pytest.mark.parametrize("path", ["/v1/tts/synthesize", "/v1/tts/stream"])
def test_a_corrupt_model_is_a_named_503_and_never_edge(piper_env, monkeypatch, path):
    main, providers, tts_policy = piper_env
    ext = _local_only_piper(monkeypatch, main, providers, tts_policy)
    _FakeVoice.corrupt = True
    resp = _client(main).post(path, json=_BODY, headers=_bearer(main))
    assert resp.status_code == 503, resp.text
    detail = resp.json()["detail"]
    assert (detail["error"], detail["provider"]) == ("local_provider_failed", "piper")
    assert ext.calls == 0


@pytest.mark.parametrize("path", ["/v1/tts/synthesize", "/v1/tts/stream"])
def test_a_missing_model_file_is_unavailable_and_never_edge(piper_env, monkeypatch, tmp_path, path):
    main, providers, tts_policy = piper_env
    ext = _local_only_piper(monkeypatch, main, providers, tts_policy)
    monkeypatch.setenv("PIPER_VOICE_PATH", str(tmp_path / "absent.onnx"))
    resp = _client(main).post(path, json=_BODY, headers=_bearer(main))
    assert resp.status_code == 503, resp.text
    assert resp.json()["detail"]["error"] == "local_provider_unavailable_for_policy"
    assert ext.calls == 0 and _FakeVoice.loads == 0


def test_no_local_provider_keeps_the_existing_named_503(piper_env, monkeypatch):
    """ضابط: حين لا مزوّدَ محلّيّاً مسموحاً تبقى رسالةُ #1122 كما هي."""
    main, providers, tts_policy = piper_env
    ext = _External()
    ext.install(monkeypatch, main, providers)
    _no_local_providers(monkeypatch, providers)
    _policy(monkeypatch, tts_policy, "local_only")
    resp = _client(main).post("/v1/tts/synthesize", json=_BODY, headers=_bearer(main))
    assert resp.status_code == 503
    assert resp.json()["detail"]["error"] == "local_provider_unavailable_for_policy"
    assert ext.calls == 0
