"""Redis-ready resumable SSE checkpoints for long agricultural jobs.

The class accepts any Redis-like object with get/set methods. Tests use the
in-memory adapter; production can pass redis.Redis without changing callers.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from time import time
from typing import Protocol


class RedisLike(Protocol):
    def get(self, key: str) -> str | bytes | None: ...
    def set(self, key: str, value: str, ex: int | None = None) -> object: ...


class MemoryRedis:
    def __init__(self) -> None:
        self.data: dict[str, str] = {}

    def get(self, key: str) -> str | None:
        return self.data.get(key)

    def set(self, key: str, value: str, ex: int | None = None) -> bool:
        self.data[key] = value
        return True


@dataclass(frozen=True)
class StreamEvent:
    stream_id: str
    offset: int
    event: str
    data: str
    updated_at: float


class RedisResumableStream:
    def __init__(
        self, redis: RedisLike, prefix: str = "sahool:stream", ttl_seconds: int = 3600
    ) -> None:
        self.redis = redis
        self.prefix = prefix
        self.ttl_seconds = ttl_seconds

    def _key(self, stream_id: str) -> str:
        return f"{self.prefix}:{stream_id}"

    def _load(self, stream_id: str) -> list[dict]:
        raw = self.redis.get(self._key(stream_id))
        if raw is None:
            return []
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        return list(json.loads(raw))

    def _save(self, stream_id: str, rows: list[dict]) -> None:
        self.redis.set(
            self._key(stream_id), json.dumps(rows, ensure_ascii=False), ex=self.ttl_seconds
        )

    def append(self, stream_id: str, data: str, event: str = "message") -> StreamEvent:
        rows = self._load(stream_id)
        next_offset = len(rows)
        row = {
            "stream_id": stream_id,
            "offset": next_offset,
            "event": event,
            "data": data,
            "updated_at": time(),
        }
        rows.append(row)
        self._save(stream_id, rows)
        return StreamEvent(**row)

    def resume(self, stream_id: str, after_offset: int = -1) -> list[StreamEvent]:
        return [
            StreamEvent(**row) for row in self._load(stream_id) if int(row["offset"]) > after_offset
        ]

    def sse_lines(self, stream_id: str, after_offset: int = -1) -> list[str]:
        lines: list[str] = []
        for event in self.resume(stream_id, after_offset):
            lines.append(f"id: {event.offset}\nevent: {event.event}\ndata: {event.data}\n")
        return lines
