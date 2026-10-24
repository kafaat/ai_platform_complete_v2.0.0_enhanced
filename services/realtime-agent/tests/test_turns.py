import asyncio
import time

import pytest
from realtime_agent.context import validate_context
from realtime_agent.turns import TurnRunner, guard_lease
from test_context import SID, context
from test_speech import wav


class Recognizer:
    async def transcribe(self, data, sample_rate):
        assert sample_rate == 16000
        return "ما حالة الحقل؟"


class Providers:
    def __init__(self):
        self.answer_calls = 0
        self.tts_calls = 0

    async def answer(self, value, text):
        self.answer_calls += 1
        return "قرينة ميدانية موثقة"

    async def synthesize(self, value, text):
        self.tts_calls += 1
        return wav()


async def finished(runner):
    await asyncio.wait_for(runner._task, timeout=3)


@pytest.mark.asyncio
async def test_pipeline_revalidates_each_provider_boundary_before_audio():
    calls = []

    async def fetch():
        calls.append(1)
        return validate_context(context(), SID)

    published = []

    async def publish(audio):
        published.append(audio)

    providers = Providers()
    runner = TurnRunner(fetch, Recognizer(), providers, publish, lambda: None)
    runner.submit(b"\0\0" * 320)
    await finished(runner)
    await runner.close()
    assert len(calls) == 4
    assert len(published) == 1 and len(published[0]) == 9600
    assert providers.answer_calls == providers.tts_calls == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("failure_at", [1, 2, 3, 4])
async def test_policy_revocation_at_every_stage_prevents_audio(failure_at):
    calls = 0

    async def fetch():
        nonlocal calls
        calls += 1
        if calls == failure_at:
            raise RuntimeError("revoked")
        return validate_context(context(), SID)

    published = []

    async def publish(audio):
        published.append(audio)

    runner = TurnRunner(fetch, Recognizer(), Providers(), publish, lambda: None)
    runner.submit(b"\0\0" * 320)
    await finished(runner)
    assert published == []
    await runner.close()


@pytest.mark.asyncio
async def test_interruption_clears_already_queued_audio_and_cancels_provider():
    entered = asyncio.Event()
    canceled = asyncio.Event()

    class Slow(Providers):
        async def answer(self, value, text):
            entered.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                canceled.set()
                raise

    async def fetch():
        return validate_context(context(), SID)

    cleared = []

    async def publish(audio):
        raise AssertionError("superseded audio must never publish")

    runner = TurnRunner(fetch, Recognizer(), Slow(), publish, lambda: cleared.append(1))
    runner.submit(b"\0\0" * 320)
    await entered.wait()
    runner.interrupt()
    await asyncio.wait_for(canceled.wait(), 1)
    await runner.close()
    assert len(cleared) >= 2


@pytest.mark.asyncio
async def test_lease_expiry_is_independent_of_slow_provider_or_context_fetch():
    stop = asyncio.Event()
    entered = asyncio.Event()

    async def stalled_fetch():
        entered.set()
        await asyncio.Event().wait()

    initial = validate_context(context(expires_at=time.time() + 0.03), SID)
    await asyncio.wait_for(guard_lease(stalled_fetch, initial, stop), 1)
    assert stop.is_set()


@pytest.mark.asyncio
async def test_lease_watch_revocation_stops_capture_before_expiry(monkeypatch):
    stop = asyncio.Event()

    async def refused():
        raise RuntimeError("revoked")

    original_sleep = asyncio.sleep

    async def fast_watch(seconds):
        return await original_sleep(0.001 if seconds == 2 else seconds)

    monkeypatch.setattr("realtime_agent.turns.asyncio.sleep", fast_watch)
    initial = validate_context(context(), SID)
    await asyncio.wait_for(guard_lease(refused, initial, stop), 1)
    assert stop.is_set()
