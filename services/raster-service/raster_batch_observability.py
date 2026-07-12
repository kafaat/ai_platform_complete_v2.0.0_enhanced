"""Process-local counters for raster batch idempotency and I/O strategy honesty."""

from collections import Counter
from threading import Lock

_LOCK = Lock()
COUNTERS = Counter()


def inc(name: str, amount: int = 1) -> None:
    with _LOCK:
        COUNTERS[name] += int(amount)


def snapshot() -> dict[str, int]:
    with _LOCK:
        return dict(COUNTERS)


def reset() -> None:
    with _LOCK:
        COUNTERS.clear()
