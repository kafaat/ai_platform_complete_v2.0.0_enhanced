"""Transient voice credentials with current Platform authorization on every read.

Only opaque session IDs are durable. Restart never recovers a bearer or a job
nonce; startup moves former voice sessions to cleanup before admitting work.
"""

from __future__ import annotations

import asyncio
import hmac
import secrets
import time
from dataclasses import dataclass, field

from .contracts import Principal, Session, SessionError


@dataclass(frozen=True)
class _Credential:
    bearer: str = field(repr=False)
    nonce: str = field(repr=False)
    expires_at: int


class VoiceJobBroker:
    def __init__(self, authority, store, worker_secret: str, clock=time.time):
        if (
            not isinstance(worker_secret, str)
            or not 32 <= len(worker_secret) <= 256
            or not worker_secret.isascii()
            or any(ord(c) < 33 or ord(c) == 127 for c in worker_secret)
        ):
            raise ValueError("a dedicated ASCII worker credential is required")
        self.authority = authority
        self.store = store
        self.clock = clock
        self._worker_secret = worker_secret
        self._credentials: dict[str, _Credential] = {}
        self._expiry: dict[str, asyncio.TimerHandle] = {}

    def issue(self, session: Session, bearer: str, now: int) -> str:
        if session.status != "ACTIVE" or now >= session.expires_at:
            raise SessionError(409, "voice_job_unavailable")
        self.revoke(session.session_id)
        nonce = secrets.token_hex(16)
        self._credentials[session.session_id] = _Credential(bearer, nonce, session.expires_at)
        self._expiry[session.session_id] = asyncio.get_running_loop().call_later(
            max(0, session.expires_at - now), self.revoke, session.session_id
        )
        return nonce

    async def prepare(self, session: Session, bearer: str, now: int) -> str:
        nonce = self.issue(session, bearer, now)
        await self._validated_context(session.session_id, nonce)
        return nonce

    def revoke(self, session_id: str) -> None:
        self._credentials.pop(session_id, None)
        timer = self._expiry.pop(session_id, None)
        if timer is not None:
            timer.cancel()

    def close(self) -> None:
        for session_id in list(self._credentials):
            self.revoke(session_id)

    def _credential(self, session_id: str, nonce: str) -> _Credential:
        entry = self._credentials.get(session_id)
        if entry is not None and int(self.clock()) >= entry.expires_at:
            self.revoke(session_id)
            entry = None
        if (
            entry is None
            or not isinstance(nonce, str)
            or len(nonce) != 32
            or not nonce.isascii()
            or not hmac.compare_digest(entry.nonce, nonce)
        ):
            raise SessionError(404, "voice_job_unavailable")
        return entry

    async def context(self, session_id: str, worker_secret: str, nonce: str) -> dict:
        if (
            not isinstance(worker_secret, str)
            or not 32 <= len(worker_secret) <= 256
            or not worker_secret.isascii()
            or not hmac.compare_digest(self._worker_secret, worker_secret)
        ):
            raise SessionError(401, "worker_authentication_required")
        return await self._validated_context(session_id, nonce)

    async def _validated_context(self, session_id: str, nonce: str) -> dict:
        entry = self._credential(session_id, nonce)
        try:
            session = await self.store.get(session_id)
            self._active(session, entry)
            principal, envelope = await self.authority.verified_identity(entry.bearer)
            if principal != Principal(session.tenant_id, session.user_id):
                raise SessionError(403, "voice_identity_changed")
            if (
                not isinstance(envelope, dict)
                or envelope.get("contract") != "sahool.ai_policy_envelope"
                or type(envelope.get("contract_version")) is not int
                or envelope.get("contract_version") != 2
                or envelope.get("version") != "v52"
                or envelope.get("tenant_id") != session.tenant_id
                or not isinstance(envelope.get("allowed_tools"), list)
                or envelope.get("policy_mode") != "local_only"
                or envelope.get("external_llm_allowed") is not False
                or envelope.get("external_tts_allowed") is not False
            ):
                raise SessionError(403, "voice_local_policy_required")
            await self.authority.authorize_field(entry.bearer, principal, session.field_id)
            # A close, expiry or policy failure can have happened during either
            # upstream request. Never return a previously checked stale context.
            if self._credential(session_id, nonce) is not entry:
                raise SessionError(404, "voice_job_unavailable")
            session = await self.store.get(session_id)
            self._active(session, entry)
            return {
                "session_id": session.session_id,
                "room_name": session.room_name,
                "participant_identity": "participant-" + session.session_id,
                "tenant_id": session.tenant_id,
                "user_id": session.user_id,
                "field_id": session.field_id,
                "bearer": entry.bearer,
                "expires_at": session.expires_at,
                "policy_envelope": envelope,
            }
        except (asyncio.CancelledError, Exception):
            self.revoke(session_id)
            raise

    def _active(self, session: Session | None, entry: _Credential) -> None:
        if (
            session is None
            or session.status != "ACTIVE"
            or session.expires_at != entry.expires_at
            or int(self.clock()) >= session.expires_at
        ):
            raise SessionError(404, "voice_job_unavailable")
