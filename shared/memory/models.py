"""
shared/memory/models.py — SAHOOL Farm Memory: Pydantic v2 data models.

Defines the core data structures for tenant-isolated farm knowledge storage.
All models are UTF-8 safe and support Arabic content.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any
from uuid import uuid4

from pydantic import BaseModel, Field, PlainSerializer

# Schema version — increment when breaking changes are made to stored structures.
SCHEMA_VERSION = "v2"

# `json_encoders` is deprecated since Pydantic 2.0 (PydanticDeprecatedSince20, raised at
# class creation). Its documented replacement is a serializer — but the swap is only safe
# because it was measured: **dropping the encoder is not a no-op.** Pydantic v2's built-in
# datetime serialization emits RFC 3339 with a `Z` suffix, while `.isoformat()` emits
# `+00:00`, and `farm_memory.py` persists these models with `model_dump(mode="json")`.
# So a plain removal would silently rewrite the on-disk format of every farm memory store
# and leave existing files mixed-format.
#
# `PlainSerializer` was measured byte-identical to the encoder it replaces, for both
# `model_dump(mode="json")` and `model_dump_json()`, while `mode="python"` still yields a
# `datetime`. `when_used="json"` is what keeps that last property true.
UtcDatetime = Annotated[
    datetime,
    PlainSerializer(lambda value: value.isoformat(), return_type=str, when_used="json"),
]


def _now_utc() -> datetime:
    """Return current UTC datetime (used as Pydantic default factory)."""
    return datetime.now(UTC)


def _new_id() -> str:
    """Generate a new UUID4 string ID."""
    return str(uuid4())


class ConversationTurn(BaseModel):
    """A single conversation turn between a farmer and the AI assistant.

    Attributes:
        id: Unique identifier for this turn.
        farm_id: Tenant identifier — links turn to a specific farm.
        user_query: The farmer's question or message.
        ai_response: The AI assistant's reply.
        timestamp: When the turn occurred (UTC).
        topic: Optional topic tag (e.g. "irrigation", "pest").
        satisfaction_score: Optional farmer satisfaction rating 0.0–1.0.
    """

    id: str = Field(default_factory=_new_id)
    farm_id: str
    user_query: str
    ai_response: str
    timestamp: UtcDatetime = Field(default_factory=_now_utc)
    topic: str | None = None
    satisfaction_score: float | None = None


class UsagePattern(BaseModel):
    """A recurring behavior or usage pattern observed for a farm.

    Examples: farmer checks weather every morning, asks about irrigation weekly.

    Attributes:
        id: Unique identifier.
        farm_id: Tenant identifier.
        description: Human-readable description of the pattern (Arabic OK).
        cadence: How often this pattern occurs (e.g. "daily", "every Monday").
        schedule: Optional cron-like or free-form schedule string.
        last_seen: When this pattern was last observed (UTC).
    """

    id: str = Field(default_factory=_new_id)
    farm_id: str
    description: str
    cadence: str | None = None
    schedule: str | None = None
    last_seen: UtcDatetime = Field(default_factory=_now_utc)


class Recommendation(BaseModel):
    """An AI-generated recommendation made to a farmer.

    Attributes:
        id: Unique identifier.
        farm_id: Tenant identifier.
        text: The recommendation text (Arabic OK).
        made_at: When this recommendation was generated (UTC).
        farmer_response: Optional farmer feedback on this recommendation.
        outcome: Optional outcome observed after following the recommendation.
        confidence: Model confidence 0.0–1.0 when generating this recommendation.
    """

    id: str = Field(default_factory=_new_id)
    farm_id: str
    text: str
    made_at: UtcDatetime = Field(default_factory=_now_utc)
    farmer_response: str | None = None
    outcome: str | None = None
    confidence: float = 1.0


class MemoryItem(BaseModel):
    """Generic wrapper for a search result from the memory store.

    Used to present heterogeneous memory items (conversations, patterns,
    recommendations) in a unified format.

    Attributes:
        id: Original item ID.
        kind: Item type: "conversation" | "pattern" | "recommendation" | "preference".
        payload: Full item data as a dict.
        score: Similarity/relevance score from the search (0.0–1.0).
        timestamp: Item timestamp for recency ranking.
    """

    id: str
    kind: str
    payload: dict[str, Any]
    score: float = 0.0
    timestamp: UtcDatetime = Field(default_factory=_now_utc)
