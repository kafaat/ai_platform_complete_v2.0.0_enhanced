"""Append-only event chains shared by the scout photo ledgers (owner phases 8-11, v266-v272).

Every ledger is a linear chain: one root per subject (a unique partial index), one successor per
event (``UNIQUE (previous_event_id)``), and a client-generated ``event_id`` that makes a retry
idempotent. This module holds the one append protocol they all follow, so the race that the owner
delivery had in each copy is fixed once: an identical concurrent request reads the first request's
event as the new head (or loses the ``ON CONFLICT DO NOTHING``); it is acknowledged as a replay
when every immutable field agrees, never answered 409.

Pure apart from the callables it is given; the callables run on the caller's tenant connection.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from fastapi import HTTPException

HISTORY_LIMIT = 200


@dataclass(frozen=True)
class ChainCodes:
    """The refusal codes of one ledger (stable API strings)."""

    reused: str  # the event id names another payload (409)
    predecessor: str  # previous_event_id is not the current head (409)
    concurrent: str  # a different event won the same slot (409)
    unverified: str  # the insert reported success but the head is another event (503)
    ambiguous: str  # more than one head (schema drift) (503)


def text_or_none(value: Any) -> str | None:
    return str(value) if value is not None else None


def same_previous(stored: Any, requested: UUID | None) -> bool:
    return text_or_none(stored) == text_or_none(requested)


def single_head(rows: list, codes: ChainCodes):
    """The head of a chain read with ``LIMIT 2``: never an arbitrary winner of two."""
    if len(rows) > 1:
        raise HTTPException(503, codes.ambiguous)
    return rows[0] if rows else None


async def append_event(
    *,
    event_id: UUID,
    previous_event_id: UUID | None,
    load_existing: Callable[[], Awaitable[Any]],
    matches: Callable[[Any], bool],
    read_head: Callable[[], Awaitable[Any]],
    insert: Callable[[], Awaitable[Any]],
    codes: ChainCodes,
    head_required: bool = False,
    head_allows: Callable[[Any], None] | None = None,
    explain_refusal: Callable[[], Awaitable[None]] | None = None,
) -> tuple[bool, Any]:
    """Append one event; ``(idempotent, head)``.

    ``head_required``: the event revises an existing chain (a revocation needs a head).
    ``head_allows(head)``: raises when the head's state forbids this event (a transition rule).
    ``explain_refusal()``: when the insert wrote nothing and no identical event exists, raises the
    specific 4xx (e.g. no accepted sample) before the generic concurrent-conflict 409.
    """

    async def replay():
        stored = await load_existing()
        if stored is None:
            return None
        if not matches(stored):
            raise HTTPException(409, codes.reused)
        return True, await read_head()

    if (receipt := await replay()) is not None:
        return receipt
    head = await read_head()
    expected = text_or_none(head["event_id"]) if head is not None else None
    if expected != text_or_none(previous_event_id) or (head_required and head is None):
        if (receipt := await replay()) is not None:
            return receipt
        raise HTTPException(409, codes.predecessor)
    if head_allows is not None:
        head_allows(head)
    if await insert() is None:
        if (receipt := await replay()) is not None:
            return receipt
        if explain_refusal is not None:
            await explain_refusal()
        raise HTTPException(409, codes.concurrent)
    new_head = await read_head()
    if new_head is None or text_or_none(new_head["event_id"]) != str(event_id):
        raise HTTPException(503, codes.unverified)
    return False, new_head


def history_rows(rows: list, limit_code: str) -> list[dict]:
    """A complete history or a 503 (never a partial audit trail); JSON-safe values."""
    if len(rows) > HISTORY_LIMIT:
        raise HTTPException(503, limit_code)
    out = []
    for row in rows:
        item = {}
        for key, value in dict(row).items():
            if isinstance(value, UUID):
                value = str(value)
            elif hasattr(value, "isoformat"):
                value = value.isoformat()
            item[key] = value
        out.append(item)
    return out


def positive_user_id(actor: str, code: str) -> int:
    """The trusted X-User-Id as users.id (a canonical positive integer), else 403."""
    try:
        number = int(actor)
    except (TypeError, ValueError):
        raise HTTPException(403, code) from None
    if number <= 0 or str(number) != actor:
        raise HTTPException(403, code)
    return number


def guard_refusal(exc: BaseException) -> bool:
    """A scout ledger SQL guard refused the actor (SQLSTATE 42501 raised by our triggers).

    Our guards RAISE a bare ``scout_…`` code. A missing table privilege is also 42501 but reads
    "permission denied for table …"; that stays a 503.
    """
    return getattr(exc, "sqlstate", None) == "42501" and str(exc).startswith("scout_")
