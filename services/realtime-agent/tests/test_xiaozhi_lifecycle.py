"""Regressions for independently reviewed cancellation and wire-send races."""

import asyncio
import json

import pytest
from realtime_agent.xiaozhi_codec import OpusCodec
from test_xiaozhi import (
    CLIENT,
    DEVICE,
    Authority,
    DeviceConversation,
    DeviceLeases,
    Providers,
    Recognizer,
    SessionError,
    enrollment,
    hello,
)


@pytest.mark.asyncio
async def test_cancelled_boundary_check_does_not_revoke_a_barge_in_lease():
    authority = Authority()
    registry = DeviceLeases(authority)
    data = await registry.create("user-token", **enrollment())
    lease = await registry.claim(data["token"], DEVICE, CLIENT)
    entered = asyncio.Event()

    async def suspended(_bearer):
        entered.set()
        await asyncio.Event().wait()

    authority.verified_identity = suspended
    check = asyncio.create_task(registry.fetch(lease))
    await entered.wait()
    check.cancel()
    with pytest.raises(asyncio.CancelledError):
        await check
    registry._live(lease)
    assert not lease.stop.is_set() and lease.bearer == "user-token"
    registry.close()


@pytest.mark.asyncio
async def test_queued_audio_is_rechecked_after_writer_lock_on_revocation():
    registry = DeviceLeases(Authority())
    data = await registry.create("user-token", **enrollment())
    lease = await registry.claim(data["token"], DEVICE, CLIENT)
    writes = []

    class Socket:
        async def send_bytes(self, value):
            writes.append(value)

    conversation = DeviceConversation(Socket(), registry, lease, Recognizer(), Providers())
    await conversation._wire_lock.acquire()
    sender = asyncio.create_task(conversation.send(b"private-audio"))
    await asyncio.sleep(0)
    registry.revoke(lease.session_id)
    conversation._wire_lock.release()
    with pytest.raises(SessionError):
        await sender
    assert writes == []
    await conversation.runner.close()


def test_stereo_opus_is_rejected_before_decoder_can_downmix():
    import av

    codec = av.CodecContext.create("libopus", "w")
    codec.sample_rate, codec.layout, codec.format = 48000, "stereo", "s16"
    codec.options = {"frame_duration": "60"}
    codec.open()
    frame = av.AudioFrame(format="s16", layout="stereo", samples=2880)
    frame.sample_rate = 48000
    frame.planes[0].update(bytes(frame.planes[0].buffer_size))
    packet = bytes(codec.encode(frame)[0])
    assert packet[0] & 0x04
    with pytest.raises(ValueError, match="mono_audio_required"):
        OpusCodec().decode(packet)


@pytest.mark.asyncio
async def test_quiet_device_is_not_disconnected_during_a_valid_long_turn(monkeypatch):
    """Scale idle deadlines: response beyond the old30s limit must finish."""
    registry = DeviceLeases(Authority())
    data = await registry.create("user-token", **enrollment())
    lease = await registry.claim(data["token"], DEVICE, CLIENT)
    incoming = asyncio.Queue()
    published = asyncio.Event()
    timeout = asyncio.timeout
    monkeypatch.setattr(
        asyncio, "timeout", lambda seconds: timeout({30: 0.02, 120: 0.20}.get(seconds, seconds))
    )

    class Socket:
        async def receive(self):
            return await incoming.get()

        async def send_json(self, value):
            pass

    class SlowProviders(Providers):
        async def answer(self, context, question):
            await asyncio.sleep(0.04)
            return await super().answer(context, question)

    class Conversation(DeviceConversation):
        async def publish(self, pcm):
            await asyncio.sleep(0.04)
            published.set()

    conversation = Conversation(Socket(), registry, lease, Recognizer(), SlowProviders())
    await incoming.put({"type": "websocket.receive", "text": json.dumps(hello())})
    task = asyncio.create_task(conversation.run("1"))
    await incoming.put(
        {
            "type": "websocket.receive",
            "text": json.dumps(
                {
                    "type": "listen",
                    "state": "start",
                    "mode": "manual",
                    "session_id": lease.session_id,
                }
            ),
        }
    )
    await incoming.put({"type": "websocket.receive", "bytes": OpusCodec.encode(b"\0\0" * 2880)[0]})
    await incoming.put(
        {
            "type": "websocket.receive",
            "text": json.dumps({"type": "listen", "state": "stop", "session_id": lease.session_id}),
        }
    )
    try:
        await asyncio.wait_for(published.wait(), 0.18)
        assert not task.done()
    finally:
        registry.revoke(lease.session_id)
        await asyncio.wait_for(task, 1)
