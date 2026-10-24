"""Tenant-bound room leases. Media/AI execution is outside this control plane."""

from __future__ import annotations

import asyncio
import time
import uuid

from .contracts import Session, SessionError


class SessionService:
    def __init__(
        self,
        authority,
        store,
        gateway,
        wss_url: str,
        session_ttl: int = 300,
        token_ttl: int = 60,
        clock=time.time,
    ):
        # A conservative drain window, NOT a credential revocation proof: LiveKit
        # refreshes connected participants' JWTs. Actual room.auto_create=false and
        # join-only grants are mandatory to prevent rejoining deleted rooms.
        if not 1 <= token_ttl <= 60 or not token_ttl + 120 <= session_ttl <= 300:
            raise ValueError("invalid realtime lease bounds")
        self.authority = authority
        self.store = store
        self.gateway = gateway
        self.wss_url = wss_url
        self.session_ttl = session_ttl
        self.token_ttl = token_ttl
        self.clock = clock
        # One process/worker only. This serializes in-flight room creation against
        # the cleanup loop; the persistent store independently enforces admission.
        self._operations = asyncio.Lock()

    async def create(self, bearer: str, field_id: str, consent: bool) -> dict:
        if consent is not True:
            raise SessionError(403, "consent_required")
        principal = await self.authority.identity(bearer)
        await self.authority.authorize_field(bearer, principal, field_id)
        async with self._operations:
            now = int(self.clock())
            session_id = uuid.uuid4().hex
            session = Session(
                session_id=session_id,
                room_name=f"sr_{uuid.uuid4().hex}",
                tenant_id=principal.tenant_id,
                user_id=principal.user_id,
                field_id=field_id,
                created_at=now,
                expires_at=now + self.session_ttl,
                status="PENDING",
            )
            await self.store.reserve(session, now)
            try:
                await asyncio.wait_for(self.gateway.create_room(session), timeout=5)
                now = int(self.clock())
                session = await self.store.activate(session_id, now)
                token = self.gateway.participant_token(session, now, self.token_ttl)
                if (
                    not isinstance(token, str)
                    or not token
                    or int(self.clock()) >= session.expires_at
                ):
                    raise SessionError(503, "participant_token_unavailable")
                return {
                    **session.public(),
                    "url": self.wss_url,
                    "participant_token": token,
                    # SDK uses its own clock. This is an upper bound, not a claim
                    # that expiration disconnects an already connected participant.
                    "token_expires_at": min(now + self.token_ttl, session.expires_at),
                }
            except (asyncio.CancelledError, Exception) as exc:
                # A failed RPC can have committed remotely. Retain quota and a
                # durable cleanup obligation, including on client cancellation.
                await asyncio.shield(self.store.closing(session_id))
                if isinstance(exc, asyncio.CancelledError):
                    raise
                if isinstance(exc, SessionError):
                    raise
                raise SessionError(503, "room_creation_unavailable") from None

    async def _owned(self, bearer: str, session_id: str) -> Session:
        principal = await self.authority.identity(bearer)
        session = await self.store.get(session_id)
        if session is None or (session.tenant_id, session.user_id) != (
            principal.tenant_id,
            principal.user_id,
        ):
            raise SessionError(404, "session_not_found")
        return session

    async def get(self, bearer: str, session_id: str) -> dict:
        return (await self._owned(bearer, session_id)).public()

    async def close(self, bearer: str, session_id: str) -> dict:
        # Terminating one's own session remains possible after FIELD_VIEW removal.
        await self._owned(bearer, session_id)
        async with self._operations:
            session = await self.store.closing(session_id)
            if session.status == "CLOSED":
                return session.public()
            try:
                await asyncio.wait_for(self.gateway.delete_room(session.room_name), timeout=5)
            except Exception:
                raise SessionError(503, "room_closure_unavailable") from None
            if int(self.clock()) >= session.expires_at:
                session = await self.store.closed(session_id)
            return session.public()

    async def cleanup(self) -> None:
        async with self._operations:
            now = int(self.clock())
            for candidate in await self.store.cleanup_candidates(now):
                session = await self.store.closing(candidate.session_id)
                if session.status == "CLOSED":
                    continue
                try:
                    await asyncio.wait_for(self.gateway.delete_room(session.room_name), timeout=5)
                except Exception:
                    continue  # keep CLOSING and quota until the next bounded retry
                if int(self.clock()) >= session.expires_at:
                    await self.store.closed(session.session_id)

    async def ready(self) -> bool:
        try:
            return bool(await self.authority.ready() and await self.gateway.ready())
        except Exception:
            return False
