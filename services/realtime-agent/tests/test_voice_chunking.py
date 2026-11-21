"""Long validated speech remains lossless, authorized and atomic before publication."""

import asyncio
import json

import httpx
import pytest
from realtime_agent.context import validate_context
from realtime_agent.providers import HttpVoiceProviders, VoiceProviderError, speech_chunks
from realtime_agent.turns import TurnRunner
from test_context import SID, context
from test_speech import wav
from test_turns import Recognizer


@pytest.mark.parametrize("length", [999, 1000, 1001, 7999, 8000])
def test_chunk_boundaries_preserve_every_character_and_numeric_token(length):
    prefix = "رطوبة الحقل ٢٢٫٥٪، لا تشغّل المضخة.\n"
    text = (prefix * (length // len(prefix) + 1))[:length]
    chunks = speech_chunks(text)
    assert "".join(chunks) == text
    assert all(0 < len(chunk) <= 1000 for chunk in chunks)
    # A token is never clipped to satisfy the transport bound.
    assert sum(chunk.count("٢٢٫٥٪") for chunk in chunks) == text.count("٢٢٫٥٪")


@pytest.mark.parametrize("text", ["x" * 1001, " " * 1001 + "حقل", "x " * 4001, "", " "])
def test_unrepresentable_text_is_refused_instead_of_truncated(text):
    with pytest.raises(VoiceProviderError, match="voice_answer"):
        speech_chunks(text)


async def test_http_chunks_keep_full_validation_context_and_no_store():
    calls = []
    text = "حرارة الحقل ٢٢. " * 80

    def handle(request):
        body = json.loads(request.content)
        calls.append(body)
        assert len(body["text"]) <= 1000
        assert body["validation_text"] == text
        assert body["no_store"] is True
        assert body["provider"] == "piper"
        assert request.headers["Authorization"] == "Bearer " + ctx["bearer"]
        return httpx.Response(
            200,
            content=wav(),
            headers={
                "Content-Type": "audio/wav",
                "Cache-Control": "no-store",
                "X-Cache": "BYPASS",
                "X-Speech-Validation": "full-context-v1",
            },
        )

    ctx = validate_context(context(), SID).provider_context()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        providers = HttpVoiceProviders("http://frontend", "http://frontend", client=client)
        for chunk in speech_chunks(text):
            await providers.synthesize_chunk(ctx, chunk, validation_text=text)
        with pytest.raises(VoiceProviderError, match="voice_answer"):
            await providers.synthesize(ctx, text)
    assert "".join(call["text"] for call in calls) == text


async def test_old_tts_service_cannot_silently_ignore_full_validation_context():
    ctx = validate_context(context(), SID).provider_context()
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(
                200,
                content=wav(),
                headers={
                    "Content-Type": "audio/wav",
                    "Cache-Control": "no-store",
                    "X-Cache": "BYPASS",
                },
            )
        )
    ) as client:
        providers = HttpVoiceProviders("http://frontend", "http://frontend", client=client)
        with pytest.raises(VoiceProviderError, match="voice_audio_rejected"):
            await providers.synthesize_chunk(
                ctx, "حرارة الحقل ٢٢. ", validation_text="حرارة الحقل ٢٢. " * 80
            )


class ChunkProviders:
    def __init__(self, text, *, fail_at=0):
        self.text = text
        self.chunks = []
        self.fail_at = fail_at

    async def answer(self, _context, _question):
        return self.text

    async def synthesize(self, _context, _text):
        raise AssertionError("long answers must use complete critical-validation context")

    async def synthesize_chunk(self, _context, text, *, validation_text):
        assert validation_text == self.text
        self.chunks.append(text)
        if len(self.chunks) == self.fail_at:
            raise RuntimeError("synthetic provider failure")
        return wav()


async def run_turn(providers, *, revoke_at=0):
    fetches = []
    published = []
    cleared = []

    async def fetch():
        fetches.append(1)
        if len(fetches) == revoke_at:
            raise RuntimeError("synthetic revocation")
        return validate_context(context(), SID)

    async def publish(pcm):
        published.append(pcm)

    runner = TurnRunner(fetch, Recognizer(), providers, publish, lambda: cleared.append(1))
    runner.submit(b"\0\0" * 320)
    await asyncio.wait_for(runner._task, 3)
    await runner.close()
    return published, fetches, cleared


async def test_long_answer_is_published_once_after_every_chunk_is_authorized():
    providers = ChunkProviders("حرارة الحقل ٢٢. " * 100)
    published, fetches, _ = await run_turn(providers)
    assert "".join(providers.chunks) == providers.text
    assert len(providers.chunks) > 1
    assert len(fetches) == len(providers.chunks) + 3
    assert len(published) == 1
    assert len(published[0]) == 9600 * len(providers.chunks)


async def test_later_chunk_failure_cannot_publish_partial_advisory():
    providers = ChunkProviders("حرارة الحقل ٢٢. " * 100, fail_at=2)
    published, _, cleared = await run_turn(providers)
    assert len(providers.chunks) == 2
    assert published == []
    assert cleared


async def test_revocation_between_chunks_prevents_next_request_and_publication():
    providers = ChunkProviders("حرارة الحقل ٢٢. " * 100)
    published, _, _ = await run_turn(providers, revoke_at=4)
    assert len(providers.chunks) == 1
    assert published == []


async def test_aggregate_audio_limit_is_not_multiplied_by_chunk_count(monkeypatch):
    providers = ChunkProviders("حرارة الحقل ٢٢. " * 100)
    # Each response is under 45 seconds; their aggregate exceeds the existing bound.
    monkeypatch.setattr("realtime_agent.turns.decode_audio", lambda _: b"\0\0" * 48000 * 24)
    published, _, _ = await run_turn(providers)
    assert len(providers.chunks) == 2
    assert published == []


async def test_optional_error_signal_is_stable_and_does_not_expose_provider_error():
    errors = []

    async def fetch():
        return validate_context(context(), SID)

    async def publish(_pcm):
        raise AssertionError("failed speech must not publish")

    async def on_error(code):
        errors.append(code)

    providers = ChunkProviders("حرارة الحقل ٢٢. " * 100, fail_at=2)
    runner = TurnRunner(fetch, Recognizer(), providers, publish, lambda: None, on_error=on_error)
    runner.submit(b"\0\0" * 320)
    await asyncio.wait_for(runner._task, 3)
    await runner.close()
    assert errors == ["voice_turn_failed"]


async def test_interruption_is_not_reported_as_a_failed_turn():
    errors = []
    entered = asyncio.Event()

    async def fetch():
        entered.set()
        await asyncio.Event().wait()

    async def publish(_pcm):
        raise AssertionError("interrupted speech must not publish")

    async def on_error(code):
        errors.append(code)

    runner = TurnRunner(
        fetch, Recognizer(), ChunkProviders("text"), publish, lambda: None, on_error=on_error
    )
    runner.submit(b"\0\0" * 320)
    await entered.wait()
    runner.interrupt()
    await runner.close()
    assert errors == []


@pytest.mark.parametrize("stage", ["preparation", "publication"])
async def test_both_stage_deadlines_clear_audio_and_emit_only_stable_failure(monkeypatch, stage):
    errors = []
    cleared = []
    published = []
    monkeypatch.setattr("realtime_agent.turns.PREPARATION_TIMEOUT_SECONDS", 0.03)
    monkeypatch.setattr("realtime_agent.turns.PUBLICATION_TIMEOUT_SECONDS", 0.03)

    class ShortProviders:
        async def answer(self, _ctx, _question):
            if stage == "preparation":
                await asyncio.Event().wait()
            return "حرارة الحقل ٢٢."

        async def synthesize(self, _ctx, _text):
            return wav()

    async def fetch():
        return validate_context(context(), SID)

    async def publish(_pcm):
        published.append(1)
        await asyncio.Event().wait()

    async def on_error(code):
        errors.append(code)

    runner = TurnRunner(
        fetch, Recognizer(), ShortProviders(), publish, lambda: cleared.append(1), on_error=on_error
    )
    runner.submit(b"\0\0" * 320)
    await asyncio.wait_for(runner._task, 2)
    await runner.close()
    assert errors == ["voice_turn_failed"]
    assert cleared
    assert len(published) == (1 if stage == "publication" else 0)


async def test_preparation_does_not_consume_paced_publication_budget(monkeypatch):
    monkeypatch.setattr("realtime_agent.turns.PREPARATION_TIMEOUT_SECONDS", 0.2)
    monkeypatch.setattr("realtime_agent.turns.PUBLICATION_TIMEOUT_SECONDS", 0.2)
    published = []
    errors = []

    class ShortProviders:
        async def answer(self, _ctx, _question):
            await asyncio.sleep(0.12)
            return "حرارة الحقل ٢٢."

        async def synthesize(self, _ctx, _text):
            return wav()

    async def fetch():
        return validate_context(context(), SID)

    async def publish(pcm):
        await asyncio.sleep(0.12)
        published.append(pcm)

    async def on_error(code):
        errors.append(code)

    runner = TurnRunner(
        fetch, Recognizer(), ShortProviders(), publish, lambda: None, on_error=on_error
    )
    runner.submit(b"\0\0" * 320)
    await asyncio.wait_for(runner._task, 2)
    await runner.close()
    assert len(published) == 1
    assert errors == []


async def test_superseded_task_finishing_cancellation_cannot_clear_newer_playback():
    old_entered = asyncio.Event()
    release_old = asyncio.Event()
    new_playing = asyncio.Event()
    release_new = asyncio.Event()
    cleared = []

    class OverlappingProviders:
        calls = 0

        async def answer(self, _ctx, _question):
            self.calls += 1
            if self.calls == 1:
                old_entered.set()
                try:
                    await asyncio.Event().wait()
                except asyncio.CancelledError:
                    # A native/provider cancellation can complete later than
                    # its replacement turn; its cleanup must stay in its epoch.
                    await release_old.wait()
                    raise
            return "حرارة الحقل ٢٢."

        async def synthesize(self, _ctx, _text):
            return wav()

    async def fetch():
        return validate_context(context(), SID)

    async def publish(_pcm):
        new_playing.set()
        await release_new.wait()

    runner = TurnRunner(
        fetch, Recognizer(), OverlappingProviders(), publish, lambda: cleared.append(1)
    )
    runner.submit(b"\0\0" * 320)
    old_task = runner._task
    await old_entered.wait()
    runner.submit(b"\0\0" * 320)
    await asyncio.wait_for(new_playing.wait(), 2)
    clear_count = len(cleared)
    release_old.set()
    with pytest.raises(asyncio.CancelledError):
        await old_task
    assert len(cleared) == clear_count
    release_new.set()
    await asyncio.wait_for(runner._task, 2)
    await runner.close()
