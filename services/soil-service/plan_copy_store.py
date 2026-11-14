"""Tenant-scoped persistence for soil-sampling plan copies (v273, owner soil-service).

Every statement runs inside a transaction that first sets ``app.current_tenant`` (the table's
FORCE RLS policy reads it), and also filters by tenant explicitly. Copies are insert-only: a
plan id that is already stored with another digest is reported as a conflict, never replaced.
"""

from __future__ import annotations

import json
from typing import Any

from jsonb_values import decode_jsonb

_SET_TENANT = "SELECT set_config('app.current_tenant', $1, true)"


async def save_plan_copies(
    pool, *, tenant_id: str, copies: list[dict[str, Any]], source: str
) -> dict[str, int]:
    """Insert each normalized copy once. Returns ``stored``/``unchanged``/``conflicting`` counts."""
    counts = {"stored": 0, "unchanged": 0, "conflicting": 0}
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(_SET_TENANT, tenant_id)
            for copy in copies:
                status = await conn.execute(
                    """INSERT INTO soil_sampling_plan_copies
                       (tenant_id, plan_id, field_id, plan, sample_points, plan_digest, source)
                       VALUES ($1::uuid, $2, $3, $4::jsonb, $5::jsonb, $6, $7)
                       ON CONFLICT (tenant_id, plan_id) DO NOTHING""",
                    tenant_id,
                    copy["plan_id"],
                    copy["field_id"],
                    json.dumps(copy["plan"]),
                    json.dumps(copy["sample_points"]),
                    copy["plan_digest"],
                    source,
                )
                if str(status).endswith(" 1"):
                    counts["stored"] += 1
                    continue
                existing = await conn.fetchrow(
                    """SELECT field_id, plan_digest FROM soil_sampling_plan_copies
                       WHERE tenant_id=$1::uuid AND plan_id=$2""",
                    tenant_id,
                    copy["plan_id"],
                )
                same = (
                    existing is not None
                    and existing["field_id"] == copy["field_id"]
                    and existing["plan_digest"] == copy["plan_digest"]
                )
                counts["unchanged" if same else "conflicting"] += 1
    return counts


async def get_plan_copy(
    pool, *, tenant_id: str, field_id: str, plan_id: str
) -> dict[str, Any] | None:
    """The stored copy of ``plan_id`` for this tenant and field, or ``None``."""
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(_SET_TENANT, tenant_id)
            row = await conn.fetchrow(
                """SELECT plan_id, field_id, plan_digest, sample_points
                   FROM soil_sampling_plan_copies
                   WHERE tenant_id=$1::uuid AND field_id=$2 AND plan_id=$3""",
                tenant_id,
                field_id,
                plan_id,
            )
    if row is None:
        return None
    return {
        "plan_id": row["plan_id"],
        "field_id": row["field_id"],
        "plan_digest": row["plan_digest"],
        "sample_points": decode_jsonb(row["sample_points"]),
    }
