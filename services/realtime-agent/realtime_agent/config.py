"""Explicit worker configuration; importing this module starts no connections."""

from __future__ import annotations

import ipaddress
import os
import re
from dataclasses import dataclass, field
from urllib.parse import urlsplit

_SERVICE_NAME = re.compile(r"[a-z](?:[a-z0-9-]{0,61}[a-z0-9])?")


def plaintext_host_allowed(hostname: str | None) -> bool:
    """Plaintext transport is only trusted inside the deployment network.

    Same rule as realtime-session's platform origin: loopback, single-label internal service
    names (``sahool-platform``, ``livekit``) and ``*.railway.internal``. These origins receive
    the worker secret and users' bearer JWTs, so every other host requires TLS.
    """
    host = (hostname or "").lower().rstrip(".")
    if not host:
        return False
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        pass
    return (
        host == "localhost"
        or _SERVICE_NAME.fullmatch(host) is not None
        or (host.endswith(".railway.internal") and host != ".railway.internal")
    )


def origin(value: str, *, websocket: bool = False) -> str:
    parsed = urlsplit(value)
    schemes = ("ws", "wss") if websocket else ("http", "https")
    if (
        parsed.scheme not in schemes
        or not parsed.hostname
        or (parsed.scheme in ("http", "ws") and not plaintext_host_allowed(parsed.hostname))
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in ("", "/")
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("invalid_trusted_origin")
    return value.rstrip("/")


@dataclass(frozen=True)
class Config:
    broker_origin: str
    worker_secret: str = field(repr=False)
    ai_origin: str
    tts_origin: str
    model_path: str
    model_sha256: str
    bundle_sha256: str
    livekit_url: str
    livekit_api_key: str = field(repr=False)
    livekit_api_secret: str = field(repr=False)
    tts_provider: str = "piper"

    @classmethod
    def from_env(cls) -> Config:
        secret = os.environ.get("REALTIME_WORKER_SECRET", "")
        if not secret.isascii() or not 32 <= len(secret) <= 256 or any(c.isspace() for c in secret):
            raise ValueError("invalid_worker_secret")
        for key in ("LIVEKIT_API_KEY", "LIVEKIT_API_SECRET", "REALTIME_STT_MODEL_PATH"):
            if not os.environ.get(key):
                raise ValueError("missing_worker_configuration")
        provider = os.environ.get("REALTIME_TTS_PROVIDER", "piper")
        if provider not in ("piper", "xtts"):
            raise ValueError("local_tts_provider_required")
        return cls(
            broker_origin=origin(os.environ.get("REALTIME_SESSION_ORIGIN", "")),
            worker_secret=secret,
            ai_origin=origin(os.environ.get("REALTIME_AI_ORIGIN", "")),
            tts_origin=origin(os.environ.get("REALTIME_TTS_ORIGIN", "")),
            model_path=os.environ["REALTIME_STT_MODEL_PATH"],
            model_sha256=os.environ.get("REALTIME_STT_MODEL_SHA256", ""),
            bundle_sha256=os.environ.get("REALTIME_STT_BUNDLE_SHA256", ""),
            livekit_url=origin(os.environ.get("LIVEKIT_URL", ""), websocket=True),
            livekit_api_key=os.environ["LIVEKIT_API_KEY"],
            livekit_api_secret=os.environ["LIVEKIT_API_SECRET"],
            tts_provider=provider,
        )
