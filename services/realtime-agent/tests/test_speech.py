import hashlib
import io
import wave

import pytest
from realtime_agent.speech import decode_audio, verified_model
from realtime_agent.turns import VoiceActivity


def model_bundle(tmp_path):
    for name, content in {
        "model.bin": b"model",
        "config.json": b"{}",
        "tokenizer.json": b"{}",
    }.items():
        (tmp_path / name).write_bytes(content)
    digest = hashlib.sha256()
    for entry in sorted(tmp_path.iterdir()):
        digest.update(entry.name.encode() + b"\n")
        digest.update(hashlib.sha256(entry.read_bytes()).hexdigest().encode() + b"\n")
    return hashlib.sha256(b"model").hexdigest(), digest.hexdigest()


def wav(rate=16000, seconds=0.1):
    out = io.BytesIO()
    with wave.open(out, "wb") as file:
        file.setnchannels(1)
        file.setsampwidth(2)
        file.setframerate(rate)
        file.writeframes(b"\x00\x01" * int(rate * seconds))
    return out.getvalue()


def test_offline_bundle_requires_exact_weights_and_all_local_files(tmp_path):
    weights, bundle = model_bundle(tmp_path)
    assert verified_model(str(tmp_path), weights, bundle) == tmp_path
    (tmp_path / "config.json").write_text('{"changed":true}', encoding="utf-8")
    with pytest.raises(ValueError, match="bundle_checksum"):
        verified_model(str(tmp_path), weights, bundle)
    with pytest.raises(ValueError, match="explicit_model_checksums"):
        verified_model("hub/model", "", "")
    with pytest.raises(ValueError, match="weights_checksum"):
        verified_model(str(tmp_path), "0" * 64, bundle)


def test_symlink_model_artifacts_never_escape_pinned_bundle(tmp_path):
    weights, bundle = model_bundle(tmp_path)
    (tmp_path / "external").symlink_to(tmp_path / "model.bin")
    with pytest.raises(ValueError, match="symlink"):
        verified_model(str(tmp_path), weights, bundle)


def test_actual_pyav_decode_and_resample_to_livekit_pcm():
    pcm = decode_audio(wav())
    assert len(pcm) == 4800 * 2
    assert pcm != wav()


@pytest.mark.parametrize("audio", [b"", b"invalid-codec", b"\x00" * 8192])
def test_invalid_tts_never_reaches_the_native_track(audio):
    with pytest.raises(ValueError):
        decode_audio(audio)


def test_tts_duration_is_bounded_after_decompression():
    with pytest.raises(ValueError, match="too_long|duration"):
        decode_audio(wav(seconds=2), max_seconds=1)


def test_vad_onset_interrupts_before_utterance_and_silence_ends_turn():
    vad = VoiceActivity()
    speech = b"\x00\x10" * 320
    silence = b"\x00\x00" * 320
    assert vad.feed(speech) == (False, None)
    assert vad.feed(speech) == (True, None)
    for _ in range(34):
        assert vad.feed(silence) == (False, None)
    started, turn = vad.feed(silence)
    assert not started and turn
    assert len(turn) <= 15 * 16000 * 2


def test_vad_continuous_speech_and_silence_memory_are_bounded():
    vad = VoiceActivity()
    for _ in range(1000):
        assert vad.feed(b"\0\0" * 320) == (False, None)
    result = None
    for _ in range(750):
        onset, result = vad.feed(b"\x00\x10" * 320)
    assert len(result) == 15 * 16000 * 2


@pytest.mark.asyncio
async def test_superseded_queued_native_stt_never_runs_after_lock_release():
    import asyncio
    import threading
    from concurrent.futures import ThreadPoolExecutor

    from realtime_agent.speech import LocalWhisperSTT

    class Model:
        calls = 0

        def transcribe(self, *args, **kwargs):
            self.calls += 1
            return [], None

    recognizer = LocalWhisperSTT.__new__(LocalWhisperSTT)
    recognizer._model = Model()
    recognizer._lock = threading.Lock()
    recognizer._executor = ThreadPoolExecutor(max_workers=1)
    recognizer._lock.acquire()
    try:
        task = asyncio.create_task(recognizer.transcribe(b"\0\0" * 320))
        await asyncio.sleep(0.01)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        recognizer._lock.release()
        # A sentinel waits behind any submitted work in the actual executor.
        await asyncio.get_running_loop().run_in_executor(recognizer._executor, lambda: None)
        assert recognizer._model.calls == 0
    finally:
        if recognizer._lock.locked():
            recognizer._lock.release()
        recognizer._executor.shutdown(wait=True, cancel_futures=True)


def test_stt_constructor_uses_only_pinned_local_cpu_model(tmp_path, monkeypatch):
    import faster_whisper
    from realtime_agent.speech import LocalWhisperSTT

    weights, bundle = model_bundle(tmp_path)
    observed = {}

    def model(path, **kwargs):
        observed.update(path=path, **kwargs)
        return object()

    monkeypatch.setattr(faster_whisper, "WhisperModel", model)
    recognizer = LocalWhisperSTT(str(tmp_path), weights, bundle)
    try:
        assert observed == {
            "path": str(tmp_path),
            "device": "cpu",
            "compute_type": "int8",
            "cpu_threads": 2,
            "num_workers": 1,
            "local_files_only": True,
        }
    finally:
        recognizer._executor.shutdown(wait=True, cancel_futures=True)
