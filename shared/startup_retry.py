"""Bounded retry for a service's first database connection at startup.

RESTART-POLICY-BYPASSES-DEPENDS-ON-HEALTH-01: compose evaluates
``depends_on: condition: service_healthy`` only on ``docker compose up``. A
container that the ``restart:`` policy brings back after a daemon/host restart
does not wait for Postgres, so a service whose first ``create_pool``/``connect``
fails fast dies (or, worse, swallows the refusal and runs DB-less forever)
while Postgres is still starting. The remedy is in each service: retry the
first connection with exponential backoff, a backoff cap and a deadline.

What is retried — and only that: failures that say "the server is not there
*yet*" (refused/reset sockets, DNS not yet resolvable, timeouts, SQLSTATE class
08 connection exceptions, 57P01-57P03 shutdown/startup, 53300 too many
connections). Anything else — a wrong password, a missing database, a bad DSN —
is a configuration error and propagates on the first attempt, so a broken
deployment still fails at once instead of hiding behind 90 seconds of retries.

Logs carry the exception *class name* only: driver messages can echo the DSN,
user or host, and this module never formats them. After the deadline it raises
:class:`StartupConnectDeadlineExceeded` (a ``RuntimeError``, chained from the
last failure) so a caller that deliberately treats ``RuntimeError`` as a
startup refusal does not mistake an unreachable database for "run DB-less".

Stdlib only: images that copy just ``shared/__init__.py`` and this file (the
weather-signal-engine) must be able to import it.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from collections.abc import Awaitable, Callable
from typing import TypeVar

T = TypeVar("T")

DEADLINE_ENV = "SAHOOL_STARTUP_CONNECT_DEADLINE_SECONDS"
INITIAL_BACKOFF_ENV = "SAHOOL_STARTUP_CONNECT_INITIAL_BACKOFF_SECONDS"
MAX_BACKOFF_ENV = "SAHOOL_STARTUP_CONNECT_MAX_BACKOFF_SECONDS"

DEFAULT_DEADLINE_SECONDS = 90.0
DEFAULT_INITIAL_BACKOFF_SECONDS = 0.5
DEFAULT_MAX_BACKOFF_SECONDS = 10.0

# SQLSTATEs outside class 08 that still mean "not reachable yet".
_TRANSIENT_SQLSTATES = frozenset({"57P01", "57P02", "57P03", "53300"})

logger = logging.getLogger("sahool.startup_retry")


class StartupConnectDeadlineExceeded(RuntimeError):
    """The database stayed unreachable for the whole startup deadline."""


def is_transient_connect_error(exc: BaseException) -> bool:
    """True when ``exc`` means the server is not reachable *yet*."""
    if isinstance(exc, (OSError, asyncio.TimeoutError, TimeoutError)):
        return True
    sqlstate = getattr(exc, "sqlstate", None)
    if isinstance(sqlstate, str):
        return sqlstate.startswith("08") or sqlstate in _TRANSIENT_SQLSTATES
    return False


def _env_seconds(name: str, default: float) -> float:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError:
        logger.warning("%s is not a number; using %.1fs", name, default)
        return default
    return value if value >= 0 else default


async def retry_startup_connect(
    connect: Callable[..., Awaitable[T]],
    /,
    *args: object,
    startup_what: str = "database",
    startup_deadline: float | None = None,
    startup_initial_backoff: float | None = None,
    startup_max_backoff: float | None = None,
    startup_sleep: Callable[[float], Awaitable[object]] = asyncio.sleep,
    startup_clock: Callable[[], float] = time.monotonic,
    **kwargs: object,
) -> T:
    """Return ``await connect(*args, **kwargs)``, retrying transient failures.

    The ``startup_*`` keywords configure the retry; every other argument is passed
    to ``connect`` unchanged (so ``retry_startup_connect(asyncpg.create_pool, dsn,
    min_size=1)`` reads like the call it wraps). Defaults come from the
    ``SAHOOL_STARTUP_CONNECT_*_SECONDS`` environment; a deadline of 0 means one
    attempt. Non-transient failures propagate on the attempt that raised them.
    """
    deadline = (
        _env_seconds(DEADLINE_ENV, DEFAULT_DEADLINE_SECONDS)
        if startup_deadline is None
        else startup_deadline
    )
    backoff = (
        _env_seconds(INITIAL_BACKOFF_ENV, DEFAULT_INITIAL_BACKOFF_SECONDS)
        if startup_initial_backoff is None
        else startup_initial_backoff
    )
    cap = (
        _env_seconds(MAX_BACKOFF_ENV, DEFAULT_MAX_BACKOFF_SECONDS)
        if startup_max_backoff is None
        else startup_max_backoff
    )
    started = startup_clock()
    attempt = 0
    while True:
        attempt += 1
        try:
            result = await connect(*args, **kwargs)
        except Exception as exc:
            if not is_transient_connect_error(exc):
                raise
            elapsed = startup_clock() - started
            remaining = deadline - elapsed
            if remaining <= 0:
                logger.error(
                    "%s unreachable after %d attempt(s) in %.1fs (last: %s); giving up",
                    startup_what,
                    attempt,
                    elapsed,
                    type(exc).__name__,
                )
                raise StartupConnectDeadlineExceeded(
                    f"{startup_what} unreachable after {attempt} attempt(s) in "
                    f"{elapsed:.1f}s (last: {type(exc).__name__})"
                ) from exc
            delay = max(0.0, min(backoff, cap, remaining))
            logger.warning(
                "%s not reachable yet (attempt %d: %s); retrying in %.2fs",
                startup_what,
                attempt,
                type(exc).__name__,
                delay,
            )
            await startup_sleep(delay)
            backoff = min(backoff * 2 if backoff > 0 else cap, cap)
            continue
        if attempt > 1:
            logger.info("%s reachable after %d attempt(s)", startup_what, attempt)
        return result
