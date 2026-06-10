"""
shared/memory/farm_memory.py — SAHOOL Farm Memory: core storage engine.

Provides a tenant-isolated, versioned farm knowledge store with:
- Local file/in-memory backend (always available).
- Qdrant backend (lazy import; falls back to local if not installed).
- Keyword-based search using token-set Jaccard similarity (no ML deps).
- Full CRUD for conversations, preferences, usage patterns, recommendations.

Real deployment: swap the scoring function for fastembed + qdrant vectors.
"""

from __future__ import annotations

import copy
import json
import logging
import os
import re
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from typing import Any

from .models import SCHEMA_VERSION, ConversationTurn, MemoryItem, Recommendation, UsagePattern

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tenant-ID validation (mirrors shared/helpers.py pattern)
# ---------------------------------------------------------------------------
_TENANT_RE = re.compile(r"^[a-zA-Z0-9_\-]{1,128}$")


def _validate_farm_id(farm_id: str) -> str:
    """Validate farm_id to prevent namespace traversal attacks."""
    if not farm_id or not _TENANT_RE.match(farm_id):
        raise ValueError(f"Invalid farm_id: {farm_id!r} — only [a-zA-Z0-9_-] up to 128 chars")
    return farm_id


# ---------------------------------------------------------------------------
# Deterministic text scoring: token-set Jaccard similarity
# ---------------------------------------------------------------------------
_TOKEN_RE = re.compile(r"[^\w؀-ۿ]+")  # ASCII words + Arabic Unicode block


def _tokenize(text: str) -> set[str]:
    """Tokenize text into a lowercase token set. Arabic-aware."""
    return {t.lower() for t in _TOKEN_RE.split(text) if t}


def _jaccard_score(query_tokens: set[str], text: str) -> float:
    """Compute token-set Jaccard similarity between query and text.

    Returns 0.0–1.0. This is a deterministic, dependency-free similarity
    measure. In production, replace with fastembed + cosine on real vectors.
    """
    if not query_tokens:
        return 0.0
    doc_tokens = _tokenize(text)
    if not doc_tokens:
        return 0.0
    intersection = query_tokens & doc_tokens
    union = query_tokens | doc_tokens
    return len(intersection) / len(union) if union else 0.0


def _item_text(kind: str, payload: dict[str, Any]) -> str:
    """Extract searchable text from an item payload."""
    parts: list[str] = []
    if kind == "conversation":
        parts.append(payload.get("user_query", ""))
        parts.append(payload.get("ai_response", ""))
        if payload.get("topic"):
            parts.append(payload["topic"])
    elif kind == "pattern":
        parts.append(payload.get("description", ""))
        parts.append(payload.get("cadence", "") or "")
        parts.append(payload.get("schedule", "") or "")
    elif kind == "recommendation":
        parts.append(payload.get("text", ""))
        parts.append(payload.get("farmer_response", "") or "")
        parts.append(payload.get("outcome", "") or "")
    return " ".join(parts)


# ---------------------------------------------------------------------------
# Local in-memory/file store
# ---------------------------------------------------------------------------


class _LocalStore:
    """Thread-safe in-memory store with optional JSON file persistence.

    Data is organised per-farm under ``<store_dir>/<farm_id>/memory.json``.
    All mutations are written-through to disk when ``store_dir`` is given.
    """

    _EMPTY: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "conversations": [],
        "preferences": {},
        "patterns": [],
        "recommendations": [],
    }

    def __init__(self, farm_id: str, store_dir: Path | None) -> None:
        self._farm_id = farm_id
        self._store_dir = store_dir
        self._lock = Lock()
        self._data: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "conversations": [],
            "preferences": {},
            "patterns": [],
            "recommendations": [],
        }
        if store_dir is not None:
            self._path = store_dir / farm_id / "memory.json"
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._load()
        else:
            self._path = None

    def _load(self) -> None:
        if self._path and self._path.exists():
            try:
                raw = self._path.read_text(encoding="utf-8")
                loaded = json.loads(raw)
                # Merge so missing keys get their real defaults (deep-copied).
                # NOTE: type(v)() would set schema_version to '' (type('v2')()),
                # silently erasing the version on older/partial files.
                for k, v in self._EMPTY.items():
                    if k not in loaded:
                        loaded[k] = copy.deepcopy(v)
                self._data = loaded
                logger.debug("farm_memory: loaded %s", self._path)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "farm_memory: could not load %s — starting fresh: %s", self._path, exc
                )

    def _save(self) -> None:
        if self._path is None:
            return
        try:
            tmp = self._path.with_suffix(".tmp")
            tmp.write_text(
                json.dumps(self._data, ensure_ascii=False, default=str, indent=2),
                encoding="utf-8",
            )
            tmp.replace(self._path)
        except Exception as exc:  # noqa: BLE001
            logger.error("farm_memory: failed to persist %s: %s", self._path, exc)

    # ── mutations ──────────────────────────────────────────────

    def add_conversation(self, turn: ConversationTurn) -> None:
        with self._lock:
            self._data["conversations"].append(turn.model_dump(mode="json"))
            self._save()
        logger.info(
            "farm_memory[%s]: added conversation %s (topic=%s)", self._farm_id, turn.id, turn.topic
        )

    def add_preference(self, key: str, value: Any) -> None:
        with self._lock:
            self._data["preferences"][key] = value
            self._save()
        logger.info("farm_memory[%s]: set preference %s", self._farm_id, key)

    def get_preferences(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._data["preferences"])

    def add_pattern(self, pattern: UsagePattern) -> None:
        with self._lock:
            self._data["patterns"].append(pattern.model_dump(mode="json"))
            self._save()
        logger.info("farm_memory[%s]: added pattern %s", self._farm_id, pattern.id)

    def add_recommendation(self, rec: Recommendation) -> None:
        with self._lock:
            self._data["recommendations"].append(rec.model_dump(mode="json"))
            self._save()
        logger.info(
            "farm_memory[%s]: added recommendation %s (conf=%.2f)",
            self._farm_id,
            rec.id,
            rec.confidence,
        )

    # ── queries ────────────────────────────────────────────────

    def all_items(self) -> list[MemoryItem]:
        """Return every stored item as MemoryItem (score=0)."""
        items: list[MemoryItem] = []
        with self._lock:
            for conv in self._data["conversations"]:
                items.append(
                    MemoryItem(
                        id=conv["id"],
                        kind="conversation",
                        payload=conv,
                        score=0.0,
                        timestamp=_parse_ts(conv.get("timestamp")),
                    )
                )
            for pat in self._data["patterns"]:
                items.append(
                    MemoryItem(
                        id=pat["id"],
                        kind="pattern",
                        payload=pat,
                        score=0.0,
                        timestamp=_parse_ts(pat.get("last_seen")),
                    )
                )
            for rec in self._data["recommendations"]:
                items.append(
                    MemoryItem(
                        id=rec["id"],
                        kind="recommendation",
                        payload=rec,
                        score=0.0,
                        timestamp=_parse_ts(rec.get("made_at")),
                    )
                )
        return items

    def search(self, query: str, k: int, kind: str | None) -> list[MemoryItem]:
        """Keyword search over stored items using Jaccard similarity."""
        query_tokens = _tokenize(query)
        results: list[tuple[float, MemoryItem]] = []

        with self._lock:
            data_snapshot = {
                "conversations": list(self._data["conversations"]),
                "patterns": list(self._data["patterns"]),
                "recommendations": list(self._data["recommendations"]),
            }

        # Conversations
        if kind is None or kind == "conversation":
            for conv in data_snapshot["conversations"]:
                text = _item_text("conversation", conv)
                score = _jaccard_score(query_tokens, text)
                if score > 0:
                    results.append(
                        (
                            score,
                            MemoryItem(
                                id=conv["id"],
                                kind="conversation",
                                payload=conv,
                                score=score,
                                timestamp=_parse_ts(conv.get("timestamp")),
                            ),
                        )
                    )

        # Patterns
        if kind is None or kind == "pattern":
            for pat in data_snapshot["patterns"]:
                text = _item_text("pattern", pat)
                score = _jaccard_score(query_tokens, text)
                if score > 0:
                    results.append(
                        (
                            score,
                            MemoryItem(
                                id=pat["id"],
                                kind="pattern",
                                payload=pat,
                                score=score,
                                timestamp=_parse_ts(pat.get("last_seen")),
                            ),
                        )
                    )

        # Recommendations
        if kind is None or kind == "recommendation":
            for rec in data_snapshot["recommendations"]:
                text = _item_text("recommendation", rec)
                score = _jaccard_score(query_tokens, text)
                if score > 0:
                    results.append(
                        (
                            score,
                            MemoryItem(
                                id=rec["id"],
                                kind="recommendation",
                                payload=rec,
                                score=score,
                                timestamp=_parse_ts(rec.get("made_at")),
                            ),
                        )
                    )

        # Sort by score desc, then by timestamp desc for ties
        results.sort(key=lambda t: (t[0], t[1].timestamp.timestamp()), reverse=True)
        logger.info(
            "farm_memory[%s]: search '%s' → %d candidates, returning top %d",
            self._farm_id,
            query[:40],
            len(results),
            k,
        )
        return [item for _, item in results[:k]]

    def raw_data(self) -> dict[str, Any]:
        with self._lock:
            return json.loads(json.dumps(self._data, ensure_ascii=False, default=str))

    def clear(self) -> None:
        with self._lock:
            self._data = {
                "schema_version": SCHEMA_VERSION,
                "conversations": [],
                "preferences": {},
                "patterns": [],
                "recommendations": [],
            }
            self._save()
        logger.info("farm_memory[%s]: cleared all data", self._farm_id)


def _parse_ts(ts_val: Any) -> datetime:
    """Parse a timestamp value into a timezone-aware datetime (UTC)."""
    if isinstance(ts_val, datetime):
        return ts_val if ts_val.tzinfo else ts_val.replace(tzinfo=UTC)
    if isinstance(ts_val, str):
        try:
            dt = datetime.fromisoformat(ts_val.replace("Z", "+00:00"))
            return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
        except ValueError:
            pass
    return datetime.now(UTC)


# ---------------------------------------------------------------------------
# Public FarmMemory class
# ---------------------------------------------------------------------------


class FarmMemory:
    """Tenant-isolated, versioned farm knowledge store.

    Parameters
    ----------
    farm_id:
        Unique identifier for this farm/tenant. Validated to prevent
        namespace traversal. Farm A can never see Farm B's data.
    backend:
        "local" (default) — file-backed JSON store.
        "qdrant" — attempts lazy import of ``qdrant_client``; if not installed,
        falls back to "local" with a warning.
    store_dir:
        Root directory for local storage. Defaults to
        ``$SAHOOL_MEMORY_DIR`` env var, or a ``sahool_memory`` sub-dir
        inside the system temp directory.

    Usage
    -----
    >>> mem = FarmMemory("farm-001")
    >>> mem.add_preference("crop", "wheat")
    >>> mem.get_preferences()
    {'crop': 'wheat'}
    """

    def __init__(
        self,
        farm_id: str,
        backend: str = "local",
        store_dir: str | None = None,
    ) -> None:
        self._farm_id = _validate_farm_id(farm_id)
        self._backend = backend

        # Resolve storage directory
        if store_dir is not None:
            resolved_dir: Path | None = Path(store_dir)
        else:
            env_dir = os.environ.get("SAHOOL_MEMORY_DIR")
            if env_dir:
                resolved_dir = Path(env_dir)
            else:
                resolved_dir = Path(tempfile.gettempdir()) / "sahool_memory"

        if backend == "qdrant":
            try:
                import qdrant_client  # noqa: F401

                logger.info("farm_memory[%s]: using qdrant backend", farm_id)
                # Future: initialise QdrantClient here, one collection per farm_id.
                # For now, fall through to local store.
                logger.warning(
                    "farm_memory[%s]: qdrant backend not fully implemented — "
                    "falling back to local store",
                    farm_id,
                )
                self._store = _LocalStore(self._farm_id, resolved_dir)
            except ImportError:
                logger.warning(
                    "farm_memory[%s]: qdrant_client غير مثبّت — "
                    "الرجوع التلقائي إلى المخزن المحلي. "
                    "لتفعيل qdrant: pip install qdrant-client",
                    farm_id,
                )
                self._store = _LocalStore(self._farm_id, resolved_dir)
        else:
            self._store = _LocalStore(self._farm_id, resolved_dir)

        logger.info(
            "FarmMemory initialised: farm_id=%s backend=%s store_dir=%s",
            self._farm_id,
            self._backend,
            resolved_dir,
        )

    # ── write operations ───────────────────────────────────────

    def add_conversation(self, turn: ConversationTurn) -> None:
        """Store a conversation turn. Enforces tenant isolation: turn.farm_id must match."""
        if turn.farm_id != self._farm_id:
            raise ValueError(
                f"Tenant isolation violation: turn.farm_id={turn.farm_id!r} "
                f"!= FarmMemory.farm_id={self._farm_id!r}"
            )
        self._store.add_conversation(turn)

    def add_preference(self, key: str, value: Any) -> None:
        """Store or update a farm preference (key-value)."""
        self._store.add_preference(key, value)

    def get_preferences(self) -> dict[str, Any]:
        """Return all preferences for this farm as a dict."""
        return self._store.get_preferences()

    def add_pattern(self, pattern: UsagePattern) -> None:
        """Store a usage pattern. Enforces tenant isolation."""
        if pattern.farm_id != self._farm_id:
            raise ValueError(
                f"Tenant isolation violation: pattern.farm_id={pattern.farm_id!r} "
                f"!= FarmMemory.farm_id={self._farm_id!r}"
            )
        self._store.add_pattern(pattern)

    def add_recommendation(self, rec: Recommendation) -> None:
        """Store an AI recommendation. Enforces tenant isolation."""
        if rec.farm_id != self._farm_id:
            raise ValueError(
                f"Tenant isolation violation: rec.farm_id={rec.farm_id!r} "
                f"!= FarmMemory.farm_id={self._farm_id!r}"
            )
        self._store.add_recommendation(rec)

    # ── read operations ────────────────────────────────────────

    def search(
        self,
        query: str,
        k: int = 5,
        kind: str | None = None,
    ) -> list[MemoryItem]:
        """Search memory using token-set Jaccard similarity.

        Parameters
        ----------
        query:
            Free-text search query (Arabic and English supported).
        k:
            Maximum number of results to return.
        kind:
            Filter by item type: "conversation" | "pattern" | "recommendation".
            Pass None to search all kinds.

        Returns
        -------
        list[MemoryItem]
            Up to ``k`` items sorted by relevance score descending.
            All items belong ONLY to this farm (tenant isolation enforced).

        Notes
        -----
        Scoring is token-set Jaccard similarity — deterministic, no ML deps.
        In production, replace ``_jaccard_score`` with a cosine similarity
        over fastembed vectors stored in qdrant.
        """
        return self._store.search(query, k=k, kind=kind)

    def all_items(self) -> list[MemoryItem]:
        """Return every stored item as MemoryItem objects (score=0)."""
        return self._store.all_items()

    def clear(self) -> None:
        """Delete all stored data for this farm. Irreversible."""
        self._store.clear()

    def raw_data(self) -> dict[str, Any]:
        """Return raw internal data dict (for export engine). Do not mutate."""
        return self._store.raw_data()

    @property
    def farm_id(self) -> str:
        """Read-only farm identifier."""
        return self._farm_id

    def _replace_data(self, data: dict[str, Any]) -> None:
        """Replace internal data (used by import engine). Internal use only."""
        with self._store._lock:
            self._store._data = data
            self._store._save()
        logger.info("farm_memory[%s]: data replaced by import engine", self._farm_id)
