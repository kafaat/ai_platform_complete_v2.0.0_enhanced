"""Opt-in Xiaozhi terminal using SAHOOL's existing local, read-only voice path.

This separate entry point does not change LiveKit sessions. It is deliberately
single process: ephemeral five-minute leases do not survive a restart/reconnect.
FastAPI WebSocket APIs: https://fastapi.tiangolo.com/advanced/websockets/
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
from contextlib import asynccontextmanager
from urllib.parse import urlsplit

from fastapi import Depends, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field, StrictBool
from realtime_agent.turns import TurnRunner, VoiceActivity, guard_lease
from realtime_agent.xiaozhi_codec import OpusCodec, pack_audio, unpack_audio

from .body_limit import BodyLimitMiddleware
from .contracts import SessionError
from .xiaozhi_leases import DeviceLeases


class EnrollDevice(BaseModel):
    model_config = ConfigDict(extra="forbid")
    field_id: str = Field(min_length=1, max_length=128)
    device_id: str = Field(min_length=17, max_length=17)
    client_id: str = Field(min_length=36, max_length=36)
    consent: StrictBool
    voice_consent: StrictBool


def websocket_url(value: str) -> str:
    try:
        parsed = urlsplit(value)
        if (
            parsed.scheme != "wss"
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path != "/xiaozhi/v1/"
            or parsed.query
            or parsed.fragment
            or "\\" in value
            or any(ord(c) < 33 for c in value)
            or parsed.port == 0
        ):
            raise ValueError
    except (ValueError, TypeError):
        raise ValueError("xiaozhi_public_wss_url_required") from None
    return value


class DeviceConversation:
    def __init__(self, websocket, leases, lease, recognizer, providers, codec_factory=OpusCodec):
        self.ws, self.leases, self.lease = websocket, leases, lease
        self.recognizer, self.providers, self.codec_factory = recognizer, providers, codec_factory
        self.codec = None
        self.version = 1
        self.mode = "auto"
        self.listening = False
        self.vad = VoiceActivity()
        self.manual = bytearray()
        self._wire_lock = asyncio.Lock()
        self._epoch = 0
        self._wire_alive = True
        self._prelisten_packets = 0
        self._messages = 0
        self.runner = TurnRunner(
            self.fetch,
            recognizer,
            providers,
            self.publish,
            self.clear,
            on_error=self.failed_turn,
            publication_timeout_seconds=65,
        )

    async def fetch(self):
        return await self.leases.fetch(self.lease)

    async def send(self, payload):
        if not self._wire_alive or self.lease.stop.is_set():
            raise SessionError(401, "device_lease_unavailable")
        async with asyncio.timeout(3):
            async with self._wire_lock:
                # Authorization may expire while another frame owns the writer.
                if not self._wire_alive or self.lease.stop.is_set():
                    raise SessionError(401, "device_lease_unavailable")
                if isinstance(payload, bytes):
                    await self.ws.send_bytes(payload)
                else:
                    await self.ws.send_json({"session_id": self.lease.session_id, **payload})

    def clear(self):
        self._epoch += 1

    async def failed_turn(self, _code):
        await self.send(
            {
                "type": "alert",
                "status": "error",
                "emotion": "neutral",
                "message": "تعذرت الإجابة الصوتية. أعد المحاولة أو راجع سهول.",
            }
        )

    async def publish(self, pcm48: bytes):
        epoch = self._epoch
        # Codec work and the final authority round trip have their own budget,
        # before the first packet. They cannot consume the 45s audio allowance.
        async with asyncio.timeout(15):
            packets = await asyncio.to_thread(self.codec.encode, pcm48)
            await self.fetch()
        if epoch != self._epoch:
            return
        await self.send({"type": "tts", "state": "start"})
        try:
            start = asyncio.get_running_loop().time()
            for number, packet in enumerate(packets):
                if epoch != self._epoch or self.lease.stop.is_set():
                    return
                await self.send(pack_audio(packet, self.version, number * 60))
                # Real-time pacing avoids filling the device's audio queue and
                # keeps abort/revocation effective during playback.
                await asyncio.sleep(
                    max(0, start + (number + 1) * 0.06 - asyncio.get_running_loop().time())
                )
        finally:
            if self._wire_alive and not self.lease.stop.is_set() and epoch == self._epoch:
                with contextlib.suppress(Exception):
                    await self.send({"type": "tts", "state": "stop"})

    async def hello(self, value: dict, header_version: str):
        audio = value.get("audio_params")
        version = value.get("version")
        if (
            value.get("type") != "hello"
            or value.get("transport") != "websocket"
            or type(version) is not int
            or version not in {1, 2, 3}
            or header_version != str(version)
            or not isinstance(audio, dict)
            or audio.get("format") != "opus"
            or type(audio.get("sample_rate")) is not int
            or audio["sample_rate"] != 16000
            or type(audio.get("channels")) is not int
            or audio["channels"] != 1
            or type(audio.get("frame_duration")) is not int
            or audio["frame_duration"] not in {20, 40, 60}
        ):
            raise ValueError("unsupported_device_audio")
        self.version = version
        self.codec = self.codec_factory(audio["frame_duration"])
        await self.send(
            {
                "type": "hello",
                "transport": "websocket",
                "version": version,
                "audio_params": {
                    "format": "opus",
                    "sample_rate": 48000,
                    "channels": 1,
                    "frame_duration": 60,
                },
            }
        )

    async def receive(self):
        message = await self.ws.receive()
        if message["type"] == "websocket.disconnect":
            raise WebSocketDisconnect(message.get("code", 1000))
        self._messages += 1
        # Five-minute quota covers 20ms frames plus control messages. It also
        # bounds repeated empty/control messages in an authenticated connection.
        if self._messages > 16000:
            raise ValueError("device_message_quota_exhausted")
        if message.get("text") is not None:
            text = message["text"]
            if len(text.encode("utf-8")) > 4096:
                raise ValueError("device_message_too_large")
            value = json.loads(text)
            if not isinstance(value, dict):
                raise ValueError("device_object_required")
            return value
        data = message.get("bytes")
        if not isinstance(data, bytes) or len(data) > 4112:
            raise ValueError("device_message_too_large")
        return data

    async def control(self, value: dict):
        if value.get("session_id") != self.lease.session_id:
            raise ValueError("device_session_mismatch")
        kind = value.get("type")
        if kind == "abort":
            self.runner.interrupt()
            self.manual.clear()
            self.vad = VoiceActivity()
            await self.send({"type": "tts", "state": "stop"})
        elif kind == "listen":
            state = value.get("state")
            if state == "start":
                if value.get("mode") not in {"auto", "manual"}:
                    raise ValueError("full_duplex_not_enabled")
                self.runner.interrupt()
                self.mode = value["mode"]
                self.listening = True
                self._prelisten_packets = 0
                self.manual.clear()
                self.vad = VoiceActivity()
            elif state == "stop":
                self.listening = False
                if self.mode == "manual" and self.manual:
                    self.runner.submit(bytes(self.manual))
                self.manual.clear()
            elif state == "detect":
                # Wake clips/phrases are not conversational instructions and are
                # never forwarded to a model or stored by this gateway.
                self._prelisten_packets = 0
            else:
                raise ValueError("invalid_listen_state")
        elif kind == "mcp":
            # No device tool requests are issued in the read-only voice profile.
            # A device response/advertisement cannot create an actuator command.
            return
        else:
            raise ValueError("unsupported_device_message")

    async def audio(self, data: bytes):
        payload = unpack_audio(data, self.version)
        if not self.listening:
            self._prelisten_packets += 1
            if self._prelisten_packets > 100:
                raise ValueError("unsolicited_audio_limit")
            return
        pcm = self.codec.decode(payload)
        if self.mode == "manual":
            if len(self.manual) + len(pcm) > 16000 * 2 * 15:
                raise ValueError("utterance_too_long")
            self.manual.extend(pcm)
        else:
            onset, utterance = self.vad.feed(pcm)
            if onset:
                self.runner.interrupt()
            if utterance:
                self.runner.submit(utterance)

    async def run(self, header_version: str):
        guard = None
        reader = None
        stopper = None
        try:
            initial = await self.fetch()
            # Expiry/revocation guards start before the untrusted hello wait.
            guard = asyncio.create_task(guard_lease(self.fetch, initial, self.lease.stop))

            async def read_loop():
                async with asyncio.timeout(8):
                    hello = await self.receive()
                    if not isinstance(hello, dict):
                        raise ValueError("hello_required")
                    await self.hello(hello, header_version)
                while not self.lease.stop.is_set():
                    # The device sends no microphone frames while speaking. A
                    # valid turn may need 45s preparation + 65s codec/playback;
                    # inactivity must not truncate that turn at 30 seconds.
                    async with asyncio.timeout(120):
                        value = await self.receive()
                    if isinstance(value, bytes):
                        await self.audio(value)
                    else:
                        await self.control(value)

            reader = asyncio.create_task(read_loop())
            stopper = asyncio.create_task(self.lease.stop.wait())
            done, _ = await asyncio.wait({reader, stopper}, return_when=asyncio.FIRST_COMPLETED)
            if reader in done:
                await reader
        finally:
            self._wire_alive = False
            self.lease.stop.set()
            self.runner.interrupt()
            for task in (reader, stopper, guard):
                if task is not None:
                    task.cancel()
            await asyncio.gather(
                *(t for t in (reader, stopper, guard) if t is not None), return_exceptions=True
            )
            await self.runner.close()
            self.manual.clear()
            self.leases.revoke(self.lease.session_id)


def create_gateway(
    *,
    leases=None,
    recognizer=None,
    providers=None,
    public_url="wss://localhost/xiaozhi/v1/",
    codec_factory=OpusCodec,
):
    public_url = websocket_url(public_url)

    @asynccontextmanager
    async def lifespan(app):
        if leases is not None or os.getenv("SAHOOL_XIAOZHI_ENABLED", "0") != "1":
            yield
            return
        import httpx
        from realtime_agent.providers import HttpVoiceProviders
        from realtime_agent.speech import LocalWhisperSTT

        from .platform import PlatformAuthority

        client = httpx.AsyncClient(timeout=3, follow_redirects=False, trust_env=False)
        runtime_providers = None
        try:
            app.state.public_url = websocket_url(os.environ.get("XIAOZHI_PUBLIC_WSS_URL", ""))
            app.state.recognizer = LocalWhisperSTT(
                os.environ.get("REALTIME_STT_MODEL_PATH", ""),
                os.environ.get("REALTIME_STT_MODEL_SHA256", ""),
                os.environ.get("REALTIME_STT_BUNDLE_SHA256", ""),
            )
            runtime_providers = HttpVoiceProviders(
                os.environ.get("REALTIME_AI_ORIGIN", ""),
                os.environ.get("REALTIME_TTS_ORIGIN", ""),
                tts_provider=os.environ.get("REALTIME_TTS_PROVIDER", "piper"),
            )
            app.state.providers = runtime_providers
            app.state.leases = DeviceLeases(
                PlatformAuthority(os.environ.get("PLATFORM_API_URL", ""), client)
            )
            yield
        finally:
            if app.state.leases is not None:
                app.state.leases.close()
            app.state.leases = None
            if runtime_providers is not None:
                await runtime_providers.close()
            await client.aclose()

    app = FastAPI(
        title="SAHOOL Xiaozhi local voice gateway",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.state.leases, app.state.recognizer, app.state.providers = leases, recognizer, providers
    app.state.public_url = public_url
    security = HTTPBearer(auto_error=False)

    def active():
        if any(
            item is None for item in (app.state.leases, app.state.recognizer, app.state.providers)
        ):
            raise SessionError(503, "xiaozhi_disabled_or_not_ready")
        return app.state.leases

    async def bearer(
        request: Request, credentials: HTTPAuthorizationCredentials | None = Depends(security)
    ):
        if request.url.scheme != "https" or request.headers.get("origin"):
            raise HTTPException(403, "trusted_https_client_required")
        if (
            credentials is None
            or credentials.scheme.lower() != "bearer"
            or len(credentials.credentials) > 16384
        ):
            raise HTTPException(401, "authentication_required")
        return credentials.credentials

    @app.middleware("http")
    async def private_responses(request, call_next):
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["Pragma"] = "no-cache"
        return response

    @app.exception_handler(SessionError)
    async def session_error(_request, exc):
        return JSONResponse(status_code=exc.status, content={"detail": {"error": exc.code}})

    @app.exception_handler(RequestValidationError)
    async def invalid_request(_request, _exc):
        return JSONResponse(status_code=422, content={"detail": {"error": "invalid_request"}})

    @app.get("/healthz")
    async def health():
        return {"status": "ok"}

    @app.get("/readyz")
    async def ready():
        configured = all(
            item is not None
            for item in (app.state.leases, app.state.recognizer, app.state.providers)
        )
        # This is process/model readiness, not proof of a successful acoustic turn.
        return JSONResponse(
            status_code=200 if configured else 503,
            content={"local_stt_loaded": configured, "end_to_end_verified": False},
        )

    @app.post("/api/v1/realtime/xiaozhi/leases", status_code=201)
    async def enroll(body: EnrollDevice, token: str = Depends(bearer)):
        result = await active().create(token, **body.model_dump())
        return {
            **result,
            "websocket": {"url": app.state.public_url, "token": result["token"], "version": 1},
        }

    @app.delete("/api/v1/realtime/xiaozhi/leases/{session_id}")
    async def revoke(session_id: str, token: str = Depends(bearer)):
        return await active().close_owned(token, session_id)

    @app.websocket("/xiaozhi/v1/")
    async def connect(ws: WebSocket):
        lease = None
        try:
            registry = active()
            if ws.url.scheme != "wss" or ws.query_params or ws.headers.get("origin"):
                raise SessionError(403, "secure_device_transport_required")
            if any(
                len(ws.headers.getlist(key)) != 1
                for key in ("authorization", "device-id", "client-id", "protocol-version")
            ):
                raise SessionError(401, "device_headers_required")
            auth = ws.headers["authorization"]
            if not auth.startswith("Bearer "):
                raise SessionError(401, "device_authentication_required")
            lease = await registry.claim(auth[7:], ws.headers["device-id"], ws.headers["client-id"])
            await ws.accept()
            conversation = DeviceConversation(
                ws, registry, lease, app.state.recognizer, app.state.providers, codec_factory
            )
            await conversation.run(ws.headers["protocol-version"])
        except (WebSocketDisconnect, asyncio.CancelledError):
            return
        except (SessionError, ValueError, TimeoutError):
            with contextlib.suppress(RuntimeError, WebSocketDisconnect):
                await ws.close(code=1008, reason="device_session_rejected")
        except Exception:
            with contextlib.suppress(RuntimeError, WebSocketDisconnect):
                await ws.close(code=1011, reason="device_voice_unavailable")
        else:
            with contextlib.suppress(RuntimeError, WebSocketDisconnect):
                await ws.close(code=1000)
        finally:
            if lease is not None:
                registry.revoke(lease.session_id)

    app.add_middleware(BodyLimitMiddleware)
    return app
