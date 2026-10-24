"""Server-owned identities and durable session state; never persist bearer tokens."""

from __future__ import annotations

from dataclasses import dataclass


class SessionError(Exception):
    def __init__(self, status: int, code: str):
        super().__init__(code)
        self.status = status
        self.code = code


@dataclass(frozen=True)
class Principal:
    tenant_id: str
    user_id: str


@dataclass(frozen=True)
class Session:
    session_id: str
    room_name: str
    tenant_id: str
    user_id: str
    field_id: str
    created_at: int
    expires_at: int
    status: str

    def public(self) -> dict:
        return {
            "session_id": self.session_id,
            "field_id": self.field_id,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "status": self.status,
        }
