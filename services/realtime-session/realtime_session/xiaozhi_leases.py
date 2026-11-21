"""Explicit, short-lived device consent with canonical identity revalidation.

Device-Id and Client-Id bind the enrollment; they are not authentication by
themselves. Only the random one-connection lease token admits device media.
Tokens and user credentials are ephemeral and are never persisted or logged.
"""

from __future__ import annotations

import asyncio
import hashlib
import re
import secrets
import time
import uuid
from dataclasses import dataclass, field

from realtime_agent.context import VoiceContext, local_policy

from .contracts import Principal, SessionError


@dataclass
class DeviceLease:
    session_id: str
    device_id: str
    client_id: str
    principal: Principal
    field_id: str
    expires_at: float
    bearer: str = field(repr=False)
    token_digest: str = field(repr=False)
    claimed: bool = False
    stop: asyncio.Event = field(default_factory=asyncio.Event, repr=False)


class DeviceLeases:
    def __init__(self, authority, *, clock=time.time, ttl: int = 300):
        if not 30 <= ttl <= 300:
            raise ValueError("invalid_device_lease_ttl")
        self.authority, self.clock, self.ttl = authority, clock, ttl
        self._leases: dict[str, DeviceLease] = {}
        self._tokens: dict[str, str] = {}
        self._timers: dict[str, asyncio.TimerHandle] = {}
        self._admission = asyncio.Lock()

    async def create(self, bearer, field_id, device_id, client_id, consent, voice_consent) -> dict:
        if consent is not True or voice_consent is not True:
            raise SessionError(403, "device_voice_consent_required")
        if not isinstance(device_id, str) or not re.fullmatch(
            r"(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}", device_id
        ):
            raise SessionError(422, "device_id_invalid")
        try:
            if not isinstance(client_id, str) or str(uuid.UUID(client_id)) != client_id.lower():
                raise ValueError
        except (ValueError, TypeError, AttributeError):
            raise SessionError(422, "client_id_invalid") from None
        async with self._admission:
            principal, policy = await self.authority.verified_identity(bearer)
            if not local_policy(policy, principal.tenant_id):
                raise SessionError(403, "voice_local_policy_required")
            await self.authority.authorize_field(bearer, principal, field_id)
            for item in list(self._leases.values()):
                if self.clock() >= item.expires_at:
                    self.revoke(item.session_id)
            active = list(self._leases.values())
            if any(item.principal == principal for item in active) or any(
                item.device_id == device_id.lower() for item in active
            ):
                raise SessionError(409, "device_lease_already_active")
            if (
                len(active) >= 16
                or sum(item.principal.tenant_id == principal.tenant_id for item in active) >= 4
            ):
                raise SessionError(429, "device_capacity_exhausted")
            token = secrets.token_urlsafe(32)
            digest = hashlib.sha256(token.encode("ascii")).hexdigest()
            session_id = uuid.uuid4().hex
            lease = DeviceLease(
                session_id,
                device_id.lower(),
                client_id.lower(),
                principal,
                field_id,
                self.clock() + self.ttl,
                bearer,
                digest,
            )
            self._leases[session_id] = lease
            self._tokens[digest] = session_id
            self._timers[session_id] = asyncio.get_running_loop().call_later(
                self.ttl, self.revoke, session_id
            )
            return {
                "session_id": session_id,
                "token": token,
                "expires_at": lease.expires_at,
                "device_id": lease.device_id,
                "client_id": lease.client_id,
                "voice_read_only": True,
                "reconnect_requires_new_lease": True,
            }

    def _live(self, lease: DeviceLease) -> None:
        if (
            self._leases.get(lease.session_id) is not lease
            or lease.stop.is_set()
            or self.clock() >= lease.expires_at
        ):
            self.revoke(lease.session_id)
            raise SessionError(401, "device_lease_unavailable")

    async def claim(self, token: str, device_id: str, client_id: str) -> DeviceLease:
        if not isinstance(token, str) or not re.fullmatch(r"[A-Za-z0-9_-]{43}", token):
            raise SessionError(401, "device_authentication_required")
        digest = hashlib.sha256(token.encode("ascii")).hexdigest()
        lease = self._leases.get(self._tokens.get(digest, ""))
        if lease is None:
            raise SessionError(401, "device_authentication_required")
        self._live(lease)
        if lease.claimed or (device_id.lower(), client_id.lower()) != (
            lease.device_id,
            lease.client_id,
        ):
            raise SessionError(403, "device_binding_rejected")
        # No await between checking and consuming; one process / one connection.
        lease.claimed = True
        try:
            await self.fetch(lease)
        except (asyncio.CancelledError, Exception):
            self.revoke(lease.session_id)
            raise
        return lease

    async def fetch(self, lease: DeviceLease) -> VoiceContext:
        self._live(lease)
        try:
            principal, policy = await self.authority.verified_identity(lease.bearer)
            if principal != lease.principal or not local_policy(policy, principal.tenant_id):
                raise SessionError(403, "device_authorization_changed")
            await self.authority.authorize_field(lease.bearer, principal, lease.field_id)
            self._live(lease)
            return VoiceContext(
                session_id=lease.session_id,
                room_name="xiaozhi-" + lease.session_id,
                participant_identity="participant-" + lease.session_id,
                tenant_id=principal.tenant_id,
                user_id=principal.user_id,
                field_id=lease.field_id,
                expires_at=lease.expires_at,
                bearer=lease.bearer,
                policy_envelope=policy,
            )
        except asyncio.CancelledError:
            # An interrupted speech turn may cancel its boundary check. The
            # independent lease guard still enforces revocation and expiry.
            raise
        except Exception:
            self.revoke(lease.session_id)
            raise

    async def close_owned(self, bearer: str, session_id: str) -> dict:
        principal = await self.authority.identity(bearer)
        lease = self._leases.get(session_id)
        if lease is None or lease.principal != principal:
            raise SessionError(404, "device_lease_not_found")
        self.revoke(session_id)
        return {"session_id": session_id, "status": "CLOSED"}

    def revoke(self, session_id: str) -> None:
        lease = self._leases.pop(session_id, None)
        if lease is not None:
            self._tokens.pop(lease.token_digest, None)
            lease.stop.set()
            lease.bearer = ""
        timer = self._timers.pop(session_id, None)
        if timer is not None:
            timer.cancel()

    def close(self):
        for session_id in list(self._leases):
            self.revoke(session_id)
