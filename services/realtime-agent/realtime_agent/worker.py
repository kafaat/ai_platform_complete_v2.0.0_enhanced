"""Actual AgentServer worker: assigned microphone in, governed audio out."""

from __future__ import annotations

import asyncio
from contextlib import suppress

from livekit import rtc
from livekit.agents import (
    AgentServer,
    AutoSubscribe,
    JobContext,
    JobProcess,
    JobRequest,
    WorkerPermissions,
)

from .config import Config
from .context import BrokerLease, LeaseRejected, parse_job
from .playback import NativePlayback
from .speech import LocalWhisperSTT
from .turns import TurnRunner, VoiceActivity, guard_lease

AGENT_NAME = "sahool-agronomist"


def allowed_microphone(participant_identity: str, publication, assigned_identity: str) -> bool:
    return (
        participant_identity == assigned_identity
        and publication.kind == rtc.TrackKind.KIND_AUDIO
        and publication.source == rtc.TrackSource.SOURCE_MICROPHONE
    )


async def while_live(awaitable, stop: asyncio.Event):
    """Lease shutdown wins even while a native connect/publish await is stalled."""
    operation = asyncio.ensure_future(awaitable)
    stopped = asyncio.create_task(stop.wait())
    try:
        done, _ = await asyncio.wait({operation, stopped}, return_when=asyncio.FIRST_COMPLETED)
        if stopped in done:
            raise LeaseRejected("session_stopped")
        return await operation
    finally:
        operation.cancel()
        stopped.cancel()
        await asyncio.gather(operation, stopped, return_exceptions=True)


def preload(proc: JobProcess) -> None:
    config = Config.from_env()
    proc.userdata["recognizer"] = LocalWhisperSTT(
        config.model_path, config.model_sha256, config.bundle_sha256
    )


async def request_job(request: JobRequest) -> None:
    try:
        session_id, _ = parse_job(request.job.metadata)
    except Exception:
        await request.reject()
        return
    await request.accept(identity="sahool-agent-" + session_id, name="SAHOOL")


async def run_job(ctx: JobContext) -> None:
    from .providers import HttpVoiceProviders

    config = Config.from_env()
    session_id, nonce = parse_job(ctx.job.metadata)
    lease = BrokerLease(config.broker_origin, config.worker_secret, session_id, nonce)
    providers = HttpVoiceProviders(
        config.ai_origin, config.tts_origin, tts_provider=config.tts_provider
    )
    source = None
    playback = None
    reader_tasks: dict[str, asyncio.Task] = {}
    all_readers: set[asyncio.Task] = set()
    streams: dict[str, rtc.AudioStream] = {}
    stop = asyncio.Event()
    runner = None
    guard_task = None
    selected_track: str | None = None
    try:
        context = await lease.fetch()
        if ctx.job.room.name != context.room_name:
            return
        recognizer = ctx.proc.userdata.get("recognizer")
        if recognizer is None:
            raise RuntimeError("local_stt_not_preloaded")
        source = rtc.AudioSource(48000, 1, queue_size_ms=100)

        outgoing = rtc.LocalAudioTrack.create_audio_track("sahool-voice", source)
        playback = NativePlayback(source, stop, outgoing.mute)
        runner = TurnRunner(
            lease.fetch, recognizer, providers, playback.publish, source.clear_queue
        )

        async def read_track(track: rtc.RemoteAudioTrack, publication) -> None:
            vad = VoiceActivity()
            stream = rtc.AudioStream(
                track, sample_rate=16000, num_channels=1, frame_size_ms=20, capacity=50
            )
            streams[publication.sid] = stream
            try:
                async for event in stream:
                    onset, utterance = vad.feed(bytes(event.frame.data))
                    if onset:
                        runner.interrupt()
                    if utterance:
                        runner.submit(utterance)
            except asyncio.CancelledError:
                raise
            except Exception:
                stop.set()
            finally:
                runner.interrupt()
                await stream.aclose()
                streams.pop(publication.sid, None)

        @ctx.room.on("track_published")
        def on_published(publication, participant) -> None:
            nonlocal selected_track
            allowed = allowed_microphone(
                participant.identity, publication, context.participant_identity
            )
            if allowed and selected_track is None:
                selected_track = publication.sid
            publication.set_subscribed(allowed and publication.sid == selected_track)

        @ctx.room.on("track_subscribed")
        def on_subscribed(track, publication, participant) -> None:
            if (
                allowed_microphone(participant.identity, publication, context.participant_identity)
                and publication.sid == selected_track
                and publication.sid not in reader_tasks
            ):
                task = asyncio.create_task(read_track(track, publication))
                reader_tasks[publication.sid] = task
                all_readers.add(task)
                task.add_done_callback(all_readers.discard)
            else:
                publication.set_subscribed(False)

        @ctx.room.on("track_unsubscribed")
        def on_unsubscribed(track, publication, participant) -> None:
            nonlocal selected_track
            task = reader_tasks.pop(publication.sid, None)
            if task is not None:
                task.cancel()
                runner.interrupt()
            if publication.sid == selected_track:
                selected_track = None

        @ctx.room.on("track_unpublished")
        def on_unpublished(publication, participant) -> None:
            on_unsubscribed(None, publication, participant)

        @ctx.room.on("participant_disconnected")
        def on_participant_disconnected(participant) -> None:
            if participant.identity == context.participant_identity:
                stop.set()

        @ctx.room.on("disconnected")
        def on_disconnected(*args) -> None:
            stop.set()

        guard_task = asyncio.create_task(guard_lease(lease.fetch, context, stop))
        async with asyncio.timeout(15):
            await while_live(ctx.connect(auto_subscribe=AutoSubscribe.SUBSCRIBE_NONE), stop)
        await while_live(lease.fetch(), stop)
        async with asyncio.timeout(10):
            await while_live(
                ctx.room.local_participant.publish_track(
                    outgoing, rtc.TrackPublishOptions(source=rtc.TrackSource.SOURCE_MICROPHONE)
                ),
                stop,
            )
        for participant in ctx.room.remote_participants.values():
            for publication in participant.track_publications.values():
                on_published(publication, participant)
        # A separately dispatched worker may arrive first; wait only a bounded time.
        await while_live(
            asyncio.wait_for(
                ctx.wait_for_participant(identity=context.participant_identity), timeout=15
            ),
            stop,
        )
        await stop.wait()
    finally:
        stop.set()
        if runner is not None:
            await runner.close()
        for task in all_readers:
            task.cancel()
        await asyncio.gather(*all_readers, return_exceptions=True)
        if guard_task is not None:
            guard_task.cancel()
            with suppress(asyncio.CancelledError):
                await guard_task
        if playback is not None:
            await playback.close()
        if source is not None:
            source.clear_queue()
            await source.aclose()
        await providers.close()
        await lease.close()
        await ctx.room.disconnect()


def create_server(config: Config | None = None) -> AgentServer:
    config = config or Config.from_env()
    server = AgentServer(
        ws_url=config.livekit_url,
        api_key=config.livekit_api_key,
        api_secret=config.livekit_api_secret,
        num_idle_processes=1,
        initialize_process_timeout=90,
        shutdown_process_timeout=10,
        session_end_timeout=10,
        drain_timeout=30,
        setup_fnc=preload,
        permissions=WorkerPermissions(
            can_publish=True,
            can_subscribe=True,
            can_publish_data=False,
            can_update_metadata=False,
            can_publish_sources=[rtc.TrackSource.SOURCE_MICROPHONE],
        ),
        log_level="WARN",
    )
    server.rtc_session(agent_name=AGENT_NAME, on_request=request_job)(run_job)
    return server
