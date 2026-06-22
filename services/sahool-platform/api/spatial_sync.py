"""Spatial synchronization helpers for geometry history and raster invalidation."""

from __future__ import annotations

import json
from typing import Any


async def save_field_geometry_revision(
    conn,
    *,
    tenant_id: str,
    field_id: str,
    geometry: dict[str, Any],
    changed_by: str | None,
    reason: str,
    source: str,
    metadata: dict[str, Any] | None = None,
) -> int | None:
    """Append a field geometry revision. Safe no-op if migration was not applied yet."""
    try:
        rev = await conn.fetchval(
            """
            INSERT INTO field_geometry_history
                (tenant_id, field_id, geometry, changed_by, reason, source, metadata)
            VALUES ($1::uuid, $2, $3::jsonb, $4, $5, $6, $7::jsonb)
            RETURNING revision
            """,
            tenant_id,
            field_id,
            json.dumps(geometry),
            changed_by,
            reason,
            source,
            json.dumps(metadata or {}),
        )
        return int(rev) if rev is not None else None
    except Exception:  # noqa: BLE001 — أفضل-جهد: سجلّ المراجعة لا يجب أن يكسر حفظ الحقل (جدول v96 قد لا يكون مُطبَّقاً بعد)
        return None


async def mark_raster_cache_stale(
    conn, *, tenant_id: str, field_id: str, reason: str, metadata: dict[str, Any] | None = None
) -> None:
    """Mark raster/indicator products stale after geometry changes.

    This records the invalidation in a small durable table. Existing raster workers can
    poll it; events emitted by the caller remain the live notification path.
    """
    try:
        await conn.execute(
            """
            INSERT INTO raster_cache_invalidations (tenant_id, field_id, reason, metadata)
            VALUES ($1::uuid, $2, $3, $4::jsonb)
            """,
            tenant_id,
            field_id,
            reason,
            json.dumps(metadata or {}),
        )
    except Exception:  # noqa: BLE001 — أفضل-جهد: إبطال الكاش لا يجب أن يكسر حفظ الحقل (جدول v96 قد لا يكون مُطبَّقاً بعد)
        return
