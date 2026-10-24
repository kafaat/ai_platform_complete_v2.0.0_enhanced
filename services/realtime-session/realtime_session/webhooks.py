"""Verified LiveKit receipts are hints, never session/lease authority.

Only event identity, classification and a payload digest reach the local database.
The raw request and any embedded participant metadata are discarded after signature
verification. Reconciliation and expiration remain owned by the session engine.
"""

from __future__ import annotations

import asyncio
import hashlib
import sqlite3

from fastapi import FastAPI, Request

from .contracts import SessionError

MAX_BODY = 4096


class WebhookReceiptStore:
    def __init__(self, path: str):
        self.path = path

    async def initialize(self) -> None:
        await asyncio.to_thread(self._initialize)

    def _connect(self):
        return sqlite3.connect(self.path, timeout=3)

    def _initialize(self) -> None:
        with self._connect() as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS realtime_hook_receipts ("
                "event_id TEXT PRIMARY KEY, event_type TEXT NOT NULL, "
                "room_name TEXT NOT NULL, created_at INTEGER NOT NULL, "
                "payload_digest TEXT NOT NULL)"
            )

    async def record(
        self, event_id: str, event_type: str, room_name: str, created_at: int, payload_digest: str
    ) -> bool:
        return await asyncio.to_thread(
            self._record, event_id, event_type, room_name, created_at, payload_digest
        )

    def _record(self, event_id, event_type, room_name, created_at, payload_digest) -> bool:
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            old = db.execute(
                "SELECT payload_digest FROM realtime_hook_receipts WHERE event_id=?",
                (event_id,),
            ).fetchone()
            if old:
                if old[0] != payload_digest:
                    raise SessionError(409, "webhook_event_conflict")
                return False
            db.execute(
                "INSERT INTO realtime_hook_receipts VALUES (?,?,?,?,?)",
                (event_id, event_type, room_name, created_at, payload_digest),
            )
            return True


def register_webhook_route(app: FastAPI) -> None:
    @app.post("/api/v1/realtime/hooks/livekit")
    async def livekit_webhook(request: Request):
        receiver = getattr(request.app.state, "webhook_receiver", None)
        store = getattr(request.app.state, "webhook_receipts", None)
        if receiver is None or store is None:
            raise SessionError(503, "webhook_disabled")
        authorization = request.headers.get("authorization", "")
        if not authorization or len(authorization) > 8192:
            raise SessionError(401, "webhook_authentication_required")
        body = bytearray()
        try:
            async with asyncio.timeout(5):
                async for chunk in request.stream():
                    if len(body) + len(chunk) > MAX_BODY:
                        raise SessionError(413, "webhook_body_too_large")
                    body.extend(chunk)
        except TimeoutError:
            raise SessionError(408, "webhook_body_timeout") from None
        try:
            # SDK verifies the signed JWT and SHA-256 of these exact UTF-8 bytes.
            event = receiver.receive(bytes(body).decode("utf-8"), authorization)
        except Exception:
            raise SessionError(401, "webhook_verification_failed") from None
        if (
            not event.id
            or len(event.id) > 128
            or not event.event
            or len(event.event) > 128
            or len(event.room.name) > 256
            or event.created_at < 0
        ):
            raise SessionError(422, "invalid_webhook_event")
        fresh = await store.record(
            event.id,
            event.event,
            event.room.name,
            event.created_at,
            hashlib.sha256(body).hexdigest(),
        )
        # Unknown rooms and out-of-order events are deliberately acknowledged.
        # No webhook event can release quota, create leases or close a session.
        return {"accepted": True, "duplicate": not fresh}
