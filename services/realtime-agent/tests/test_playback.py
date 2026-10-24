import asyncio

import pytest
from realtime_agent.playback import NativePlayback, PlaybackUncertain


class Source:
    def __init__(self):
        self.started = asyncio.Event()
        self.complete = asyncio.Event()
        self.events = []
        self.capture_count = 0
        self.native_cancelled = False

    async def capture_frame(self, frame):
        self.capture_count += 1
        self.events.append("capture_started")
        self.started.set()
        try:
            await self.complete.wait()
            self.events.append("native_insert")
        except asyncio.CancelledError:
            self.native_cancelled = True
            raise

    def clear_queue(self):
        self.events.append("clear")

    async def wait_for_playout(self):
        self.events.append("played")


@pytest.mark.asyncio
async def test_interruption_waits_for_actual_native_ack_before_final_clear_and_reuse():
    source = Source()
    stop = asyncio.Event()
    muted = []
    playback = NativePlayback(source, stop, lambda: muted.append(1))
    first = asyncio.create_task(playback.publish(b"\0\0" * 960))
    await source.started.wait()
    first.cancel()
    await asyncio.sleep(0)
    assert source.events[-1] == "clear"
    assert not source.native_cancelled
    second = asyncio.create_task(playback.publish(b"\0\0" * 960))
    await asyncio.sleep(0)
    assert source.capture_count == 1, "New turn must wait behind the old native completion fence"
    source.complete.set()
    with pytest.raises(asyncio.CancelledError):
        await first
    await second
    first_insert = source.events.index("native_insert")
    next_capture = source.events.index("capture_started", 1)
    assert "clear" in source.events[first_insert + 1 : next_capture]
    assert not stop.is_set() and not muted
    await playback.close()


@pytest.mark.asyncio
async def test_uncertain_native_completion_mutes_and_ends_job_without_source_reuse():
    source = Source()
    stop = asyncio.Event()
    muted = []
    playback = NativePlayback(source, stop, lambda: muted.append(1), fence_timeout=0.01)
    task = asyncio.create_task(playback.publish(b"\0\0" * 960))
    await source.started.wait()
    task.cancel()
    with pytest.raises(PlaybackUncertain, match="completion_unconfirmed"):
        await task
    assert stop.is_set() and muted
    with pytest.raises(PlaybackUncertain, match="source_unusable"):
        await playback.publish(b"\0\0" * 960)
    assert source.capture_count == 1
    await playback.close()
    assert source.native_cancelled


@pytest.mark.asyncio
async def test_second_cancellation_cannot_bypass_capture_fence_and_reuse_source():
    source = Source()
    stop = asyncio.Event()
    muted = []
    playback = NativePlayback(source, stop, lambda: muted.append(1))
    task = asyncio.create_task(playback.publish(b"\0\0" * 960))
    await source.started.wait()
    task.cancel()
    await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(PlaybackUncertain, match="fence_interrupted"):
        await task
    assert stop.is_set() and muted
    with pytest.raises(PlaybackUncertain, match="source_unusable"):
        await playback.publish(b"\0\0" * 960)
    assert source.capture_count == 1
    await playback.close()
