"""Durable SQLite leases for a single-node realtime proof of concept.

Every operation opens its own connection. ``BEGIN IMMEDIATE`` serializes quota
admission across threads/processes sharing this database file. This is not a
distributed store: replicas on separate disks cannot share a quota or lease.
Expired leases retain capacity until external room deletion is confirmed.
"""

from __future__ import annotations

import asyncio
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from .contracts import Session, SessionError

_COLUMNS = "session_id, room_name, tenant_id, user_id, field_id, created_at, expires_at, status"


class SessionStore:
    def __init__(self, path: str | Path, max_per_tenant: int = 2, max_per_actor: int = 1):
        if str(path) == ":memory:":
            raise ValueError("Session storage requires a durable database file")
        for limit in (max_per_tenant, max_per_actor):
            if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
                raise ValueError("Session quotas must be positive integers")
        self.path = Path(path)
        self.max_per_tenant = max_per_tenant
        self.max_per_actor = max_per_actor

    @contextmanager
    def _connection(self, *, write: bool = False):
        conn = None
        try:
            conn = sqlite3.connect(self.path, timeout=2.0)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA busy_timeout = 2000")
            conn.execute("PRAGMA synchronous = FULL")
            if write:
                conn.execute("BEGIN IMMEDIATE")
            yield conn
            if write:
                conn.commit()
        except (sqlite3.Error, OSError) as exc:
            if conn is not None:
                conn.rollback()
            raise SessionError(503, "session_store_unavailable") from exc
        finally:
            if conn is not None:
                conn.close()

    @staticmethod
    def _session(row: sqlite3.Row | None) -> Session | None:
        return Session(**dict(row)) if row is not None else None

    @staticmethod
    def _required(conn: sqlite3.Connection, session_id: str) -> Session:
        row = conn.execute(
            f"SELECT {_COLUMNS} FROM realtime_sessions WHERE session_id = ?", (session_id,)
        ).fetchone()
        if row is None:
            raise SessionError(404, "session_not_found")
        return Session(**dict(row))

    def _initialize(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        except OSError as exc:
            raise SessionError(503, "session_store_unavailable") from exc
        # Use SQLite's default rollback journal. There is no concurrent
        # journal_mode=WAL startup transition to race between workers.
        with self._connection(write=True) as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS realtime_sessions ("
                "session_id TEXT PRIMARY KEY, room_name TEXT NOT NULL UNIQUE, "
                "tenant_id TEXT NOT NULL, user_id TEXT NOT NULL, field_id TEXT NOT NULL, "
                "created_at INTEGER NOT NULL, expires_at INTEGER NOT NULL, "
                "status TEXT NOT NULL CHECK(status IN ('PENDING','ACTIVE','CLOSING','CLOSED')), "
                "CHECK(expires_at > created_at))"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS realtime_sessions_tenant_actor_status "
                "ON realtime_sessions (tenant_id, user_id, status)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS realtime_sessions_cleanup "
                "ON realtime_sessions (status, expires_at, created_at)"
            )

    async def initialize(self) -> None:
        await asyncio.to_thread(self._initialize)

    def _reserve(self, session: Session, now: int) -> None:
        if session.status != "PENDING" or session.expires_at <= now:
            raise SessionError(409, "invalid_session_state")
        with self._connection(write=True) as conn:
            existing = conn.execute(
                "SELECT 1 FROM realtime_sessions WHERE session_id = ? OR room_name = ?",
                (session.session_id, session.room_name),
            ).fetchone()
            if existing:
                raise SessionError(409, "session_already_exists")
            tenant_count, actor_count = conn.execute(
                "SELECT COUNT(*), COALESCE(SUM(user_id = ?), 0) FROM realtime_sessions "
                "WHERE tenant_id = ? AND status IN ('PENDING','ACTIVE','CLOSING')",
                (session.user_id, session.tenant_id),
            ).fetchone()
            if tenant_count >= self.max_per_tenant or actor_count >= self.max_per_actor:
                raise SessionError(429, "session_quota_exceeded")
            conn.execute(
                f"INSERT INTO realtime_sessions ({_COLUMNS}) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                tuple(getattr(session, key) for key in _COLUMNS.split(", ")),
            )

    async def reserve(self, session: Session, now: int) -> None:
        await asyncio.to_thread(self._reserve, session, now)

    def _activate(self, session_id: str, now: int) -> Session:
        with self._connection(write=True) as conn:
            changed = conn.execute(
                "UPDATE realtime_sessions SET status = 'ACTIVE' "
                "WHERE session_id = ? AND status = 'PENDING' AND expires_at > ?",
                (session_id, now),
            ).rowcount
            if changed != 1:
                self._required(conn, session_id)
                raise SessionError(409, "invalid_session_state")
            return self._required(conn, session_id)

    async def activate(self, session_id: str, now: int) -> Session:
        return await asyncio.to_thread(self._activate, session_id, now)

    def _get(self, session_id: str) -> Session | None:
        with self._connection() as conn:
            return self._session(
                conn.execute(
                    f"SELECT {_COLUMNS} FROM realtime_sessions WHERE session_id = ?",
                    (session_id,),
                ).fetchone()
            )

    async def get(self, session_id: str) -> Session | None:
        return await asyncio.to_thread(self._get, session_id)

    def _closing(self, session_id: str) -> Session:
        with self._connection(write=True) as conn:
            self._required(conn, session_id)
            conn.execute(
                "UPDATE realtime_sessions SET status = 'CLOSING' "
                "WHERE session_id = ? AND status IN ('PENDING','ACTIVE')",
                (session_id,),
            )
            return self._required(conn, session_id)

    async def closing(self, session_id: str) -> Session:
        return await asyncio.to_thread(self._closing, session_id)

    def _closed(self, session_id: str) -> Session:
        with self._connection(write=True) as conn:
            session = self._required(conn, session_id)
            if session.status not in {"CLOSING", "CLOSED"}:
                raise SessionError(409, "invalid_session_state")
            conn.execute(
                "UPDATE realtime_sessions SET status = 'CLOSED' "
                "WHERE session_id = ? AND status = 'CLOSING'",
                (session_id,),
            )
            return self._required(conn, session_id)

    async def closed(self, session_id: str) -> Session:
        """Confirm closure only after the caller has confirmed external room deletion."""
        return await asyncio.to_thread(self._closed, session_id)

    def _cleanup_candidates(self, now: int) -> list[Session]:
        with self._connection() as conn:
            rows = conn.execute(
                f"SELECT {_COLUMNS} FROM realtime_sessions WHERE status = 'CLOSING' "
                "OR (status = 'PENDING' AND created_at <= ?) "
                "OR (status = 'ACTIVE' AND expires_at <= ?) ORDER BY created_at, session_id",
                (now - 10, now),
            ).fetchall()
            return [Session(**dict(row)) for row in rows]

    async def cleanup_candidates(self, now: int) -> list[Session]:
        return await asyncio.to_thread(self._cleanup_candidates, now)
