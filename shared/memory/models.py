"""
shared/memory/models.py — SAHOOL Farm Memory: Pydantic v2 data models.

Defines the core data structures for tenant-isolated farm knowledge storage.
All models are UTF-8 safe and support Arabic content.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

# Schema version — increment when breaking changes are made to stored structures.
SCHEMA_VERSION = "v2"


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
    timestamp: datetime = Field(default_factory=_now_utc)
    topic: str | None = None
    satisfaction_score: float | None = None

    model_config = {"json_encoders": {datetime: lambda v: v.isoformat()}}


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
    last_seen: datetime = Field(default_factory=_now_utc)

    model_config = {"json_encoders": {datetime: lambda v: v.isoformat()}}


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
    made_at: datetime = Field(default_factory=_now_utc)
    farmer_response: str | None = None
    outcome: str | None = None
    confidence: float = 1.0

    model_config = {"json_encoders": {datetime: lambda v: v.isoformat()}}


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
    timestamp: datetime = Field(default_factory=_now_utc)

    model_config = {"json_encoders": {datetime: lambda v: v.isoformat()}}
