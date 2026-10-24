"""Live authorization lease, with no persisted or printable participant bearer."""

from __future__ import annotations

import asyncio
import json
import math
import re
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

from .config import origin


class LeaseRejected(Exception):
    """Stable error without metadata, request bodies or credentials."""


def parse_job(metadata: str) -> tuple[str, str]:
    try:
        if len(metadata) > 2048:
            raise ValueError
        value = json.loads(metadata)
        if not isinstance(value, dict) or set(value) != {"session_id", "nonce"}:
            raise ValueError
        session_id, nonce = value["session_id"], value["nonce"]
        if not isinstance(session_id, str) or not re.fullmatch(r"[a-f0-9-]{32,36}", session_id):
            raise ValueError
        if not isinstance(nonce, str) or not re.fullmatch(r"[a-f0-9]{32}", nonce):
            raise ValueError
        return session_id, nonce
    except (ValueError, TypeError, KeyError) as exc:
        raise LeaseRejected("invalid_job_assignment") from exc


def local_policy(value: Any, tenant_id: str) -> bool:
    return (
        isinstance(value, dict)
        and value.get("contract") == "sahool.ai_policy_envelope"
        and type(value.get("contract_version")) is int
        and value["contract_version"] == 2
        and value.get("version") == "v52"
        and value.get("tenant_id") == tenant_id
        and value.get("policy_mode") == "local_only"
        and value.get("external_llm_allowed") is False
        and value.get("external_tts_allowed") is False
        and isinstance(value.get("allowed_tools"), list)
    )


@dataclass(frozen=True)
class VoiceContext:
    session_id: str
    room_name: str
    participant_identity: str
    tenant_id: str
    user_id: str
    field_id: str
    expires_at: float
    bearer: str = field(repr=False)
    policy_envelope: dict = field(repr=False)

    @property
    def identity(self) -> tuple:
        return (
            self.session_id,
            self.room_name,
            self.participant_identity,
            self.tenant_id,
            self.user_id,
            self.field_id,
            self.expires_at,
        )

    def provider_context(self) -> dict:
        return {
            "session_id": self.session_id,
            "room_name": self.room_name,
            "participant_identity": self.participant_identity,
            "tenant_id": self.tenant_id,
            "user_id": self.user_id,
            "field_id": self.field_id,
            "expires_at": self.expires_at,
            "bearer": self.bearer,
            "policy_envelope": self.policy_envelope,
        }


def validate_context(value: Any, session_id: str, *, now: float | None = None) -> VoiceContext:
    now = time.time() if now is None else now
    if not isinstance(value, dict):
        raise LeaseRejected("invalid_context")
    try:
        for key in (
            "session_id",
            "room_name",
            "participant_identity",
            "tenant_id",
            "user_id",
            "field_id",
            "bearer",
        ):
            item = value[key]
            if (
                not isinstance(item, str)
                or not item
                or len(item) > 16384
                or "\r" in item
                or "\n" in item
            ):
                raise ValueError
        expiry = value["expires_at"]
        if (
            type(expiry) not in (int, float)
            or not math.isfinite(expiry)
            or not now < expiry <= now + 3600
        ):
            raise ValueError
        if (
            value["session_id"] != session_id
            or value["participant_identity"] != "participant-" + session_id
        ):
            raise ValueError
        if not local_policy(value.get("policy_envelope"), value["tenant_id"]):
            raise ValueError
        return VoiceContext(**{k: value[k] for k in VoiceContext.__dataclass_fields__})
    except (ValueError, KeyError, TypeError) as exc:
        raise LeaseRejected("invalid_context") from exc


class BrokerLease:
    def __init__(
        self,
        broker_origin: str,
        secret: str,
        session_id: str,
        nonce: str,
        *,
        client: httpx.AsyncClient | None = None,
    ):
        self._origin = origin(broker_origin)
        self._secret = secret
        self._session_id = session_id
        self._nonce = nonce
        self._client = client or httpx.AsyncClient(
            timeout=5, follow_redirects=False, trust_env=False
        )
        self._owns_client = client is None
        self._identity: tuple | None = None

    async def fetch(self) -> VoiceContext:
        try:
            # httpx's timeout is per-I/O; this outer deadline caps the entire request.
            async with asyncio.timeout(5):
                async with self._client.stream(
                    "GET",
                    self._origin + "/api/v1/realtime/internal/jobs/" + self._session_id,
                    headers={
                        "X-Realtime-Worker-Token": self._secret,
                        "X-Realtime-Job-Nonce": self._nonce,
                    },
                ) as response:
                    if response.status_code != 200:
                        raise LeaseRejected("lease_rejected")
                    data = bytearray()
                    async for chunk in response.aiter_bytes():
                        data.extend(chunk)
                        if len(data) > 32768:
                            raise LeaseRejected("context_too_large")
                    context = validate_context(json.loads(data), self._session_id)
            if self._identity is not None and self._identity != context.identity:
                raise LeaseRejected("assignment_changed")
            self._identity = context.identity
            return context
        except (httpx.HTTPError, TimeoutError, ValueError) as exc:
            raise LeaseRejected("context_unavailable") from exc

    async def close(self) -> None:
        self._secret = ""
        self._nonce = ""
        if self._owns_client:
            await self._client.aclose()
