"""In-memory Redis double with WATCH/MULTI/EXEC semantics, for the agent approval store tests.

``fakeredis`` is not installed in the test environment, so this double implements only what
``services/ai_agronomist/agent_stores.py`` calls, with Redis's own semantics for each:

- ``SET`` honours ``NX``/``XX``/``EX``/``KEEPTTL``; a ``SET`` without ``EX`` or ``KEEPTTL`` drops
  the key's TTL, as Redis does. TTLs are counters (no wall clock): ``tick`` ages every key.
- ``pipeline()`` gives a redis-py style pipeline: after ``watch`` commands run immediately;
  after ``multi`` they are queued; ``execute`` raises ``WatchError`` (redis-py's own class) and
  applies nothing if any watched key was written since ``watch``. Leaving the ``with`` block while
  still watching sends ``UNWATCH``, like ``redis.client.Pipeline.reset``.
- Every command that reaches the "server" is recorded in ``commands`` (lower case), so a test can
  compare what really ran with the compose ACL.
- ``on_watched_get`` (optional) runs once right after the first immediate ``GET`` under ``WATCH``:
  a deterministic way to land a competing write between a transaction's read and its ``EXEC``.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


def _watch_error() -> type[BaseException]:
    from services.ai_agronomist import agent_stores

    return agent_stores._watch_error_types()[0]


def _b(value: Any) -> bytes:
    return value if isinstance(value, bytes) else str(value).encode("utf-8")


class RedisTxnDouble:
    def __init__(self) -> None:
        self.kv: dict[str, bytes] = {}
        self.ttls: dict[str, int] = {}
        self.sets: dict[str, set[bytes]] = {}
        self.lists: dict[str, list[bytes]] = {}
        self.versions: dict[str, int] = {}
        self.commands: list[str] = []
        self.on_watched_get: Callable[[], None] | None = None

    # ── helpers ────────────────────────────────────────────────────────────
    def _touch(self, key: str) -> None:
        self.versions[key] = self.versions.get(key, 0) + 1

    def tick(self, seconds: int) -> None:
        for key in list(self.ttls):
            self.ttls[key] -= seconds
            if self.ttls[key] <= 0:
                self.kv.pop(key, None)
                self.ttls.pop(key, None)
                self._touch(key)

    # ── commands ───────────────────────────────────────────────────────────
    def ping(self) -> bool:
        self.commands.append("ping")
        return True

    def get(self, key: str) -> bytes | None:
        self.commands.append("get")
        return self.kv.get(key)

    def ttl(self, key: str) -> int:  # test inspection only; not a store command
        if key not in self.kv:
            return -2
        return self.ttls.get(key, -1)

    def set(
        self,
        key: str,
        value: Any,
        ex: int | None = None,
        nx: bool = False,
        xx: bool = False,
        keepttl: bool = False,
    ) -> bool | None:
        self.commands.append("set")
        exists = key in self.kv
        if (nx and exists) or (xx and not exists):
            return None
        self.kv[key] = _b(value)
        if ex is not None:
            self.ttls[key] = int(ex)
        elif not keepttl:
            self.ttls.pop(key, None)
        self._touch(key)
        return True

    def sadd(self, key: str, member: Any) -> int:
        self.commands.append("sadd")
        s = self.sets.setdefault(key, set())
        before = len(s)
        s.add(_b(member))
        self._touch(key)
        return len(s) - before

    def srem(self, key: str, member: Any) -> int:
        self.commands.append("srem")
        s = self.sets.get(key, set())
        had = _b(member) in s
        s.discard(_b(member))
        self._touch(key)
        return int(had)

    def smembers(self, key: str) -> set[bytes]:
        self.commands.append("smembers")
        return set(self.sets.get(key, set()))

    def rpush(self, key: str, value: Any) -> int:
        self.commands.append("rpush")
        self.lists.setdefault(key, []).append(_b(value))
        self._touch(key)
        return len(self.lists[key])

    def ltrim(self, key: str, start: int, end: int) -> bool:
        self.commands.append("ltrim")
        items = self.lists.get(key, [])
        n = len(items)
        lo = max(start + n if start < 0 else start, 0)
        hi = end + n if end < 0 else end
        self.lists[key] = items[lo : hi + 1]
        self._touch(key)
        return True

    def lrange(self, key: str, start: int, end: int) -> list[bytes]:
        self.commands.append("lrange")
        items = self.lists.get(key, [])
        n = len(items)
        lo = max(start + n if start < 0 else start, 0)
        hi = end + n if end < 0 else end
        return items[lo : hi + 1]

    def pipeline(self, transaction: bool = True) -> _Pipeline:
        assert transaction, "the store only uses transactional pipelines"
        return _Pipeline(self)


class _Pipeline:
    def __init__(self, server: RedisTxnDouble) -> None:
        self._s = server
        self._watched: dict[str, int] = {}
        self._queue: list[tuple[str, tuple, dict]] = []
        self._in_multi = False
        self._hook_fired = False

    def __enter__(self) -> _Pipeline:
        return self

    def __exit__(self, *exc: object) -> None:
        self.reset()

    def reset(self) -> None:
        if self._watched:
            self._s.commands.append("unwatch")
        self._watched = {}
        self._queue = []
        self._in_multi = False

    def watch(self, *keys: str) -> None:
        assert not self._in_multi, "WATCH inside MULTI is an error in Redis"
        self._s.commands.append("watch")
        for key in keys:
            self._watched[key] = self._s.versions.get(key, 0)

    def unwatch(self) -> None:
        self._s.commands.append("unwatch")
        self._watched = {}

    def multi(self) -> None:
        assert not self._in_multi, "nested MULTI"
        self._in_multi = True

    def _call(self, name: str, *args: Any, **kwargs: Any) -> Any:
        if self._in_multi:
            self._queue.append((name, args, kwargs))
            return self
        result = getattr(self._s, name)(*args, **kwargs)
        if name == "get" and self._watched and not self._hook_fired:
            self._hook_fired = True
            if self._s.on_watched_get is not None:
                hook, self._s.on_watched_get = self._s.on_watched_get, None
                hook()
        return result

    def get(self, *a: Any, **k: Any) -> Any:
        return self._call("get", *a, **k)

    def set(self, *a: Any, **k: Any) -> Any:
        return self._call("set", *a, **k)

    def sadd(self, *a: Any, **k: Any) -> Any:
        return self._call("sadd", *a, **k)

    def srem(self, *a: Any, **k: Any) -> Any:
        return self._call("srem", *a, **k)

    def execute(self) -> list[Any]:
        assert self._in_multi, "EXEC without MULTI"
        self._s.commands.append("multi")
        self._s.commands.append("exec")
        changed = any(self._s.versions.get(k, 0) != v for k, v in self._watched.items())
        queue, self._queue, self._in_multi = self._queue, [], False
        self._watched = {}  # EXEC clears WATCH whether it ran or aborted
        if changed:
            raise _watch_error()("Watched variable changed.")
        return [getattr(self._s, name)(*a, **k) for name, a, k in queue]
