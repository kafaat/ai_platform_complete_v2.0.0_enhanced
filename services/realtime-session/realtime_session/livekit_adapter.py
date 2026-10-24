"""Official LiveKit API boundary; participant grants never carry SAHOOL identity.

SDK 1.2.2 generates ``nbf``/``exp`` from its own UTC clock, without ``iat``.
The signed result is verified by the SDK before its deadline fields are inspected.
JWT expiry governs admission, not an already connected participant's lifetime.
Self-hosted deployments must enforce ``room.auto_create: false`` and deny users
``roomCreate``; deleting a room alone does not revoke a still-valid token.
"""

from __future__ import annotations

import base64
import json
import time
from datetime import timedelta
from urllib.parse import urlsplit

import aiohttp
from livekit import api
from livekit.api.twirp_client import TwirpErrorCode

from .contracts import Session, SessionError


class LiveKitGateway:
    def __init__(self, http_url: str, api_key: str, api_secret: str):
        parsed = urlsplit(http_url)
        internal = parsed.hostname in {"livekit", "localhost", "127.0.0.1", "::1"} or (
            parsed.hostname or ""
        ).endswith(".railway.internal")
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or (parsed.scheme == "http" and not internal)
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
            or parsed.path not in {"", "/"}
            or not api_key.strip()
            or len(api_secret) < 32
        ):
            raise ValueError("Invalid LiveKit backend configuration")
        self._api_key = api_key
        self._api_secret = api_secret
        self._client = api.LiveKitAPI(
            http_url.rstrip("/"),
            api_key=api_key,
            api_secret=api_secret,
            timeout=aiohttp.ClientTimeout(total=5),
            failover=False,
        )

    async def create_room(self, session: Session) -> None:
        try:
            await self._client.room.create_room(
                api.CreateRoomRequest(
                    name=session.room_name,
                    max_participants=2,
                    empty_timeout=30,
                    departure_timeout=5,
                )
            )
        except Exception:
            raise SessionError(503, "livekit_unavailable") from None

    def participant_token(self, session: Session, now: int, ttl: int) -> str:
        if (
            isinstance(now, bool)
            or not isinstance(now, int)
            or isinstance(ttl, bool)
            or not isinstance(ttl, int)
            or not 1 <= ttl <= 60
            or session.status not in {"PENDING", "ACTIVE"}
        ):
            raise SessionError(409, "session_not_joinable")
        deadline = min(now + ttl, session.expires_at)
        # Round conservatively because the SDK reads its own wall clock twice.
        remaining = deadline - int(time.time()) - 1
        if remaining <= 0:
            raise SessionError(409, "session_expired")
        try:
            token = (
                api.AccessToken(self._api_key, self._api_secret)
                .with_identity(f"participant-{session.session_id}")
                .with_grants(
                    api.VideoGrants(
                        room_join=True,
                        room=session.room_name,
                        room_create=False,
                        room_list=False,
                        room_admin=False,
                        room_record=False,
                        ingress_admin=False,
                        can_publish=True,
                        can_publish_sources=["microphone"],
                        can_subscribe=True,
                        can_publish_data=False,
                        can_update_own_metadata=False,
                        can_manage_agent_session=False,
                        agent=False,
                        recorder=False,
                    )
                )
                .with_ttl(timedelta(seconds=remaining))
                .to_jwt()
            )
            # SDK Claims deliberately drops exp/nbf. Inspect only after the SDK
            # verifies signature/issuer; this is not a replacement token verifier.
            api.TokenVerifier(self._api_key, self._api_secret, leeway=timedelta(seconds=0)).verify(
                token
            )
            encoded = token.split(".")[1]
            claims = json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))
            if (
                type(claims.get("exp")) is not int
                or type(claims.get("nbf")) is not int
                or claims["exp"] > deadline
                or claims["exp"] <= now
                or claims["nbf"] > int(time.time())
                or claims["nbf"] >= claims["exp"]
            ):
                raise ValueError("SDK clock exceeded the lease")
            return token
        except Exception:
            raise SessionError(503, "livekit_token_unavailable") from None

    async def delete_room(self, room_name: str) -> None:
        try:
            await self._client.room.delete_room(api.DeleteRoomRequest(room=room_name))
        except api.TwirpError as exc:
            if exc.code == TwirpErrorCode.NOT_FOUND and exc.status == 404:
                return
            raise SessionError(503, "livekit_unavailable") from None
        except Exception:
            raise SessionError(503, "livekit_unavailable") from None

    async def ready(self) -> bool:
        try:
            # Narrowed query avoids returning every room during health checks.
            await self._client.room.list_rooms(
                api.ListRoomsRequest(names=["sahool-realtime-readiness-probe"])
            )
            return True
        except Exception:
            return False

    async def close(self) -> None:
        await self._client.aclose()
