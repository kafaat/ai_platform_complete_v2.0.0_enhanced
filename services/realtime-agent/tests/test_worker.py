import asyncio
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from livekit import rtc
from realtime_agent.config import Config, origin
from realtime_agent.worker import AGENT_NAME, allowed_microphone, create_server, request_job


def test_disabled_process_exits_without_model_credentials_or_sdk_import():
    script = Path(__file__).resolve().parents[1] / "main.py"
    env = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith(("LIVEKIT_", "REALTIME_", "SAHOOL_REALTIME_"))
    }
    # -S removes site-packages entirely, proving disabled path has no SDK import.
    subprocess.run([sys.executable, "-S", str(script), "start"], env=env, check=True, timeout=3)


@pytest.mark.parametrize(
    "value",
    [
        "https://user:pass@host",
        "https://host/path",
        "https://host?token=x",
        "https://host#part",
        "file:///tmp/model",
        "",
    ],
)
def test_trusted_origin_rejects_untrusted_path_or_credentials(value):
    with pytest.raises(ValueError):
        origin(value)


def test_enabled_configuration_requires_secrets_and_local_provider(monkeypatch):
    for key in list(os.environ):
        if key.startswith(("REALTIME_", "LIVEKIT_")):
            monkeypatch.delenv(key)
    with pytest.raises(ValueError, match="worker_secret"):
        Config.from_env()
    monkeypatch.setenv("REALTIME_WORKER_SECRET", "s" * 32)
    with pytest.raises(ValueError, match="missing_worker"):
        Config.from_env()


def test_real_server_uses_named_dispatch_and_no_data_or_video_permission():
    config = Config(
        "http://sessions",
        "s" * 32,
        "http://frontend",
        "http://frontend",
        "/models/whisper",
        "0" * 64,
        "0" * 64,
        "ws://livekit:7880",
        "key",
        "s" * 64,
    )
    server = create_server(config)
    assert AGENT_NAME == "sahool-agronomist"
    assert server._permissions.can_publish_data is False
    assert server._permissions.can_update_metadata is False
    assert server._permissions.can_publish_sources == [rtc.TrackSource.SOURCE_MICROPHONE]


def test_only_assigned_participant_microphone_is_subscribed():
    good = SimpleNamespace(kind=rtc.TrackKind.KIND_AUDIO, source=rtc.TrackSource.SOURCE_MICROPHONE)
    camera = SimpleNamespace(kind=rtc.TrackKind.KIND_VIDEO, source=rtc.TrackSource.SOURCE_CAMERA)
    screen_audio = SimpleNamespace(
        kind=rtc.TrackKind.KIND_AUDIO, source=rtc.TrackSource.SOURCE_SCREENSHARE_AUDIO
    )
    assert allowed_microphone("farmer-a", good, "farmer-a")
    assert not allowed_microphone("farmer-b", good, "farmer-a")
    assert not allowed_microphone("farmer-a", camera, "farmer-a")
    assert not allowed_microphone("farmer-a", screen_audio, "farmer-a")


@pytest.mark.asyncio
async def test_native_audio_source_accepts_pcm_frame_and_can_clear_playout():
    source = rtc.AudioSource(48000, 1, queue_size_ms=100)
    try:
        await source.capture_frame(rtc.AudioFrame(b"\0\0" * 960, 48000, 1, 960))
        source.clear_queue()
        await asyncio.wait_for(source.wait_for_playout(), 1)
    finally:
        await source.aclose()


@pytest.mark.asyncio
async def test_actual_job_request_callback_refuses_unscoped_assignment():
    class Request:
        job = SimpleNamespace(metadata='{"room":"unsafe","bearer":"never"}')
        accepted = False
        rejected = False

        async def accept(self, **kwargs):
            self.accepted = True

        async def reject(self):
            self.rejected = True

    request = Request()
    await request_job(request)
    assert request.rejected and not request.accepted


@pytest.mark.asyncio
async def test_lease_shutdown_cancels_a_stalled_native_operation():
    from realtime_agent.context import LeaseRejected
    from realtime_agent.worker import while_live

    stop = asyncio.Event()
    entered = asyncio.Event()
    cancelled = asyncio.Event()

    async def operation():
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    task = asyncio.create_task(while_live(operation(), stop))
    await entered.wait()
    stop.set()
    with pytest.raises(LeaseRejected, match="session_stopped"):
        await asyncio.wait_for(task, 0.1)
    assert cancelled.is_set()


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["connect", "publish", "participant_wait"])
async def test_real_job_cleanup_on_expiry_during_each_setup_stage(monkeypatch, stage):
    import json
    import time

    from realtime_agent import worker
    from realtime_agent.context import LeaseRejected, validate_context
    from test_context import NONCE, SID, context
    from test_turns import Recognizer

    config = Config(
        "http://sessions",
        "s" * 32,
        "http://frontend",
        "http://frontend",
        "/models/whisper",
        "0" * 64,
        "0" * 64,
        "ws://livekit:7880",
        "key",
        "s" * 64,
    )
    initial = validate_context(context(expires_at=time.time() + 0.05), SID)
    closed = set()
    entered = set()

    class Lease:
        def __init__(self, *args):
            pass

        async def fetch(self):
            return initial

        async def close(self):
            closed.add("broker")

    class Providers:
        def __init__(self, *args, **kwargs):
            pass

        async def close(self):
            closed.add("providers")

    async def await_stage(name):
        entered.add(name)
        if name == stage:
            await asyncio.Event().wait()

    class LocalParticipant:
        async def publish_track(self, *args):
            await await_stage("publish")

    class Room:
        local_participant = LocalParticipant()
        remote_participants = {}

        def on(self, event):
            return lambda callback: callback

        async def disconnect(self):
            closed.add("room")

    class Job:
        room = SimpleNamespace(name=initial.room_name)
        metadata = json.dumps({"session_id": SID, "nonce": NONCE})

    class Context:
        job = Job()
        room = Room()
        proc = SimpleNamespace(userdata={"recognizer": Recognizer()})

        async def connect(self, **kwargs):
            assert kwargs["auto_subscribe"] == worker.AutoSubscribe.SUBSCRIBE_NONE
            await await_stage("connect")

        async def wait_for_participant(self, **kwargs):
            assert kwargs["identity"] == initial.participant_identity
            await await_stage("participant_wait")

    monkeypatch.setattr(worker.Config, "from_env", lambda: config)
    monkeypatch.setattr(worker, "BrokerLease", Lease)
    monkeypatch.setattr("realtime_agent.providers.HttpVoiceProviders", Providers)
    with pytest.raises(LeaseRejected, match="session_stopped"):
        await asyncio.wait_for(worker.run_job(Context()), 1)
    assert stage in entered
    assert closed == {"broker", "providers", "room"}
