"""Small resumable stream checkpoint primitive.

Used by long-running Daily Brief / Prescription generation to avoid losing all
progress when weak farm connectivity drops. The store is deliberately pluggable;
production should back it by Redis, tests can use the in-memory store below.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from time import time


@dataclass
class StreamCheckpoint:
    stream_id: str
    chunks: list[str] = field(default_factory=list)
    updated_at: float = field(default_factory=time)

    @property
    def offset(self) -> int:
        return len(self.chunks)


class InMemoryStreamStore:
    def __init__(self) -> None:
        self._data: dict[str, StreamCheckpoint] = {}

    def append(self, stream_id: str, chunk: str) -> StreamCheckpoint:
        cp = self._data.setdefault(stream_id, StreamCheckpoint(stream_id=stream_id))
        cp.chunks.append(chunk)
        cp.updated_at = time()
        return cp

    def resume(self, stream_id: str, after_offset: int = 0) -> list[str]:
        cp = self._data.get(stream_id)
        if not cp:
            return []
        return cp.chunks[max(0, after_offset) :]

    def checkpoint(self, stream_id: str) -> StreamCheckpoint | None:
        return self._data.get(stream_id)
