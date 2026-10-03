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
    """``PiperVoice`` بواجهة 1.3+ — يسجّل التحميل والخيط والتزامن والتوقيت."""

    loads = 0
    corrupt = False
    load_delay = 0.0
    synth_delay = 0.05
    synth_error = False
    empty_output = False
    threads: list[int] = []
    spans: list[tuple[str, float, float]] = []
    active = 0
    max_active = 0
    lock = threading.Lock()

    @classmethod
    def reset(cls) -> None:
        cls.loads, cls.corrupt, cls.load_delay = 0, False, 0.0
        cls.synth_delay, cls.synth_error, cls.empty_output = 0.05, False, False
        cls.threads, cls.spans, cls.active, cls.max_active = [], [], 0, 0

    @classmethod
    def load(cls, path, config_path=None, use_cuda=False, **kwargs):
        with cls.lock:
            cls.loads += 1
        time.sleep(cls.load_delay)
        if cls.corrupt:
            raise ValueError("INVALID_PROTOBUF: Load model failed")
        return cls()

    def synthesize(self, text, syn_config=None, include_alignments=False):
        # 1.3+: مولِّدٌ لا يكتب شيئاً — النداءُ القديم ``synthesize(text, wav)`` ينتهي هنا.
        yield from ()

    def synthesize_wav(self, text, wav_file, syn_config=None, set_wav_format=True, **kwargs):
        cls = type(self)
        start = time.monotonic()
        with cls.lock:
            cls.active += 1
            cls.max_active = max(cls.max_active, cls.active)
            cls.threads.append(threading.get_ident())
        try:
            time.sleep(cls.synth_delay)
            if cls.synth_error:
                raise RuntimeError("onnxruntime: inference failed")
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(22050)
            if not cls.empty_output:
                wav_file.writeframes(b"\x01\x00" * 2205)
        finally:
            with cls.lock:
                cls.active -= 1
                cls.spans.append((text, start, time.monotonic()))


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
    monkeypatch.setattr(
        providers.PiperProvider, "_installed_version", staticmethod(lambda: "1.8.0"), raising=False
    )
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


# ── شروط المراجعة (المالك، 2026-10-03) ─────────────────────────────────────────


@pytest.mark.parametrize("installed", ["1.5.0", "1.9.0", None])
def test_only_the_target_version_is_accepted(piper_env, monkeypatch, installed):
    """وجودُ ``synthesize_wav`` لا يُثبت توافقَ كلّ ≥ 1.3 — المستهدفُ صريحٌ وغيرُه يُرفض بالاسم."""
    _main, providers, _ = piper_env
    monkeypatch.setattr(
        providers.PiperProvider, "_installed_version", staticmethod(lambda: installed)
    )
    with pytest.raises(providers.PiperLoadError, match=providers.PIPER_TTS_TARGET_VERSION):
        asyncio.run(providers.PiperProvider().synthesize("أ", "v", "+0%", "+0Hz", "+0%"))
    assert _FakeVoice.loads == 0


def test_two_simultaneous_first_requests_load_the_model_once(piper_env, monkeypatch):
    _main, providers, _ = piper_env
    monkeypatch.setenv("PIPER_MAX_CONCURRENCY", "2")
    _FakeVoice.load_delay = 0.2

    async def both():
        provider = providers.PiperProvider()
        await asyncio.gather(
            provider.synthesize("أ", "v", "+0%", "+0Hz", "+0%"),
            providers.PiperProvider().synthesize("ب", "v", "+0%", "+0Hz", "+0%"),
        )

    asyncio.run(both())
    assert _FakeVoice.loads == 1


def test_a_cancelled_request_keeps_its_slot_until_the_thread_finishes(piper_env, monkeypatch):
    """الإلغاءُ لا يوقف الخيط؛ فلا يبدأ تركيبٌ آخر بحدّ 1 قبل أن ينتهي الخيطُ الملغى طلبُه."""
    _main, providers, _ = piper_env
    monkeypatch.setenv("PIPER_MAX_CONCURRENCY", "1")
    _FakeVoice.synth_delay = 0.3

    async def scenario():
        provider = providers.PiperProvider()
        first = asyncio.create_task(provider.synthesize("first", "v", "+0%", "+0Hz", "+0%"))
        await asyncio.sleep(0.05)
        first.cancel()
        with pytest.raises(asyncio.CancelledError):
            await first
        await provider.synthesize("second", "v", "+0%", "+0Hz", "+0%")

    asyncio.run(scenario())
    spans = {text: (start, end) for text, start, end in _FakeVoice.spans}
    assert set(spans) == {"first", "second"}
    assert spans["second"][0] >= spans["first"][1], "بدأ الثاني قبل انتهاء خيط الأوّل الملغى"
    assert _FakeVoice.max_active == 1


def _wav(frames: int = 100) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(b"\x01\x00" * frames)
    return buf.getvalue()


def test_wav_integrity_checks_header_params_and_real_frames(piper_env):
    _main, providers, _ = piper_env
    providers._require_audible_wav(_wav())
    for bad, reason in (
        (b"OggS" + _wav()[4:], "ليس RIFF"),
        (_wav(0), "بلا إطارات"),
        (_wav(100)[:-50], "مقطوع"),
    ):
        with pytest.raises(providers.PiperLoadError):
            providers._require_audible_wav(bad)
        assert reason


@pytest.mark.parametrize("path", ["/v1/tts/synthesize", "/v1/tts/stream"])
@pytest.mark.parametrize("failure", ["synthesis", "empty_output", "wrong_version"])
def test_every_local_failure_is_a_named_503_with_zero_edge_calls(
    piper_env, monkeypatch, path, failure
):
    main, providers, tts_policy = piper_env
    ext = _local_only_piper(monkeypatch, main, providers, tts_policy)
    if failure == "synthesis":
        _FakeVoice.synth_error = True
    elif failure == "empty_output":
        _FakeVoice.empty_output = True
    else:
        monkeypatch.setattr(
            providers.PiperProvider, "_installed_version", staticmethod(lambda: "1.5.0")
        )
    resp = _client(main).post(path, json=_BODY, headers=_bearer(main))
    assert resp.status_code == 503, resp.text
    assert resp.json()["detail"]["error"] == "local_provider_failed"
    assert ext.calls == 0


def test_a_stream_that_fails_after_starting_is_logged_and_cut_not_relabelled(
    piper_env, monkeypatch, caplog
):
    """بعد إرسال الرؤوس لا 503 ممكناً: يُسجَّل الفشلُ ويُقطع النقلُ (لا ملفٌّ يبدو مكتملاً)."""
    main, providers, tts_policy = piper_env

    class Communicate:
        def __init__(self, *a, **k):
            pass

        async def stream(self):
            yield {"type": "audio", "data": b"FIRST-CHUNK"}
            raise ConnectionResetError("edge dropped mid-stream")

    monkeypatch.setattr(providers.EdgeTTSProvider, "available", lambda self: True)
    monkeypatch.setattr(main.edge_tts, "Communicate", Communicate, raising=False)
    _policy(monkeypatch, tts_policy, "full_external")
    with caplog.at_level("ERROR"), pytest.raises(ConnectionResetError):
        _client(main).post("/v1/tts/stream", json=_BODY, headers=_bearer(main))
    logged = [r.getMessage() for r in caplog.records]
    assert any("TTS stream aborted after start" in m and "bytes_sent=11" in m for m in logged)
