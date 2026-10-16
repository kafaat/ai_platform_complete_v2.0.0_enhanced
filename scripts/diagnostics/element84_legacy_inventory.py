#!/usr/bin/env python3
"""Bounded, tenant-scoped, read-only legacy imagery inventory.

Run only against an explicitly authorized database with a SELECT-only role using
SAHOOL_INVENTORY_DATABASE_URL. No migration, processing, provider request, deletion
or correction is performed. Unknown provenance remains unknown; an empty snapshot
is not proof that historical HTTP failures were durably recorded.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

# Schema sources: migrations/v14, v114, v116, v143, v144, v154. Projection
# intentionally excludes COG URLs, geometry, complete request/result/error payloads.
QUERIES = {
    "raster_assets": """
        SELECT id::text AS id, tenant_id::text AS tenant_id, field_id, scene_id,
               index_name, provenance->>'provider' AS provider, geometry_revision,
               provenance->>'processing_version' AS processing_version,
               algorithm_version, product_identity_key,
               acquisition_date::text AS product_date, processing_job_id AS job_id
        FROM raster_assets WHERE tenant_id = $1::uuid ORDER BY id LIMIT $2
    """,
    "raster_registry": """
        SELECT id::text AS id, tenant_id::text AS tenant_id, field_id, scene_id,
               index_type AS index_name, metadata->>'provider' AS provider,
               metadata->>'geometry_revision' AS geometry_revision,
               metadata->>'processing_version' AS processing_version,
               product_date::text AS product_date
        FROM raster_registry WHERE tenant_id = $1::uuid ORDER BY id LIMIT $2
    """,
    "backfill_run_items": """
        SELECT i.id::text AS id, i.tenant_id::text AS tenant_id, i.field_id, i.scene_id,
               i.index_name, i.provider, r.geometry_revision,
               NULL::text AS processing_version, i.status, i.job_id,
               i.run_id::text AS run_id, i.error AS error_evidence
        FROM backfill_run_items i
        LEFT JOIN backfill_runs r ON r.id = i.run_id AND r.tenant_id = i.tenant_id
        WHERE i.tenant_id = $1::uuid ORDER BY i.id LIMIT $2
    """,
    "backfill_runs_failed": """
        SELECT id::text AS id, tenant_id::text AS tenant_id, field_id,
               geometry_revision, status, error AS error_evidence
        FROM backfill_runs WHERE tenant_id = $1::uuid
          AND status IN ('failed', 'completed_with_errors') ORDER BY id LIMIT $2
    """,
    "raster_batch_jobs_failed": """
        SELECT job_id AS id, tenant_id::text AS tenant_id, field_id, status,
               request_payload->>'scene_id' AS scene_id,
               request_payload->>'provider' AS provider,
               request_payload->>'geometry_revision' AS geometry_revision,
               request_payload->>'processing_version' AS processing_version,
               error_code AS error_evidence
        FROM raster_batch_jobs WHERE tenant_id = $1::uuid AND status = 'failed'
        ORDER BY job_id LIMIT $2
    """,
    "distributed_raster_jobs_failed": """
        SELECT id::text AS id, tenant_id::text AS tenant_id, status,
               input->>'field_id' AS field_id, input->>'scene_id' AS scene_id,
               input->>'provider' AS provider,
               input->>'geometry_revision' AS geometry_revision,
               input->>'processing_version' AS processing_version,
               error AS error_evidence
        FROM distributed_raster_jobs WHERE tenant_id = $1::uuid AND status = 'failed'
        ORDER BY id LIMIT $2
    """,
}


TABLES = (
    "raster_assets",
    "raster_registry",
    "backfill_run_items",
    "backfill_runs",
    "raster_batch_jobs",
    "distributed_raster_jobs",
)
POLICY_QUERY = """
    SELECT jsonb_agg(jsonb_build_object(
        'table', c.relname, 'enabled', c.relrowsecurity, 'forced', c.relforcerowsecurity,
        'qual', pg_get_expr(p.polqual, p.polrelid)))
    FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
    LEFT JOIN pg_policy p ON p.polrelid = c.oid AND p.polcmd IN ('r', '*')
    WHERE n.nspname = 'public' AND c.relname = ANY($1::text[])
"""


def validate_policies(value) -> None:
    """Unsupported RLS context is an error, never a misleading empty snapshot."""
    policies = json.loads(value) if isinstance(value, str) else value
    if not isinstance(policies, list) or {p.get("table") for p in policies} != set(TABLES):
        raise InventoryRefused("missing inventory table or policy metadata")
    for policy in policies:
        contexts = set(re.findall(r"current_setting\('([^']+)'", policy.get("qual") or ""))
        if not (policy.get("enabled") and policy.get("forced")):
            raise InventoryRefused("inventory table must enforce row-level security")
        if contexts != {"app.current_tenant"}:
            raise InventoryRefused("unsupported tenant RLS policy context")


class InventoryRefused(ValueError):
    """The inventory cannot be safely or completely evaluated."""


def classify_row(row: dict) -> dict:
    """Keep unknown providers in scope and avoid guessing lost HTTP status codes."""
    item = dict(row)
    provider = str(item.get("provider") or "").strip().lower()
    unknown = provider in ("", "unknown")
    item["provider_attribution"] = "unknown" if unknown else "explicit"
    item["element84_candidate"] = unknown or provider in ("element84", "landsat-element84")
    error = str(item.pop("error_evidence", None) or "")
    item["http_422_evidence"] = (
        "explicit_http_status"
        if re.search(r"\b(?:HTTP(?:/[0-9.]+)?\s+|status(?:_code)?[\s:=]+)422\b", error, re.I)
        else "unavailable"
    )
    return item


def validate_scope(tenant_id: str, limit: int) -> str:
    try:
        tenant = str(UUID(str(tenant_id)))
    except (ValueError, TypeError, AttributeError) as exc:
        raise InventoryRefused("one explicit UUID tenant is required") from exc
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100000:
        raise InventoryRefused("limit must be an integer from 1 to 100000")
    return tenant


async def collect_inventory(conn, tenant_id: str, *, limit: int = 10000) -> dict:
    """Collect one repeatable snapshot; refuse invalid scope or any leaked row.

    SQL errors propagate: a missing table/column/permission is not an empty table.
    Every source is bounded independently; truncated reports are visibly incomplete.
    """
    tenant = validate_scope(tenant_id, limit)
    sources = {}
    async with conn.transaction(readonly=True, isolation="repeatable_read"):
        await conn.execute("SET LOCAL statement_timeout = '30s'")
        await conn.execute("SET LOCAL row_security = on")
        await conn.execute("SET LOCAL search_path = pg_catalog, public")
        privileged = await conn.fetchval(
            "SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname = current_user"
        )
        if privileged is not False:
            raise InventoryRefused("privileged or unverified database role refused")
        validate_policies(await conn.fetchval(POLICY_QUERY, list(TABLES)))
        await conn.execute("SELECT set_config('app.current_tenant', $1, true)", tenant)
        for name, sql in QUERIES.items():
            rows = await conn.fetch(sql, tenant, limit + 1)
            if any(str(row["tenant_id"]) != tenant for row in rows):
                raise InventoryRefused("cross-tenant result refused")
            sources[name] = {
                "truncated": len(rows) > limit,
                "row_count_lower_bound": len(rows),
                "rows": [classify_row(dict(row)) for row in rows[:limit]],
            }
    return {
        "schema": "sahool.element84-legacy-inventory.v1",
        "observed_at": datetime.now(UTC).isoformat(),
        "tenant_id": tenant,
        "snapshot_complete": not any(source["truncated"] for source in sources.values()),
        "production_acceptance": False,
        "sources": sources,
        "limitations": [
            "Rows are separate source records, not a deduplicated damaged-product count.",
            "Snapshot covers rows visible to this SELECT role, not proof of unrestricted tenant completeness.",
            "Unknown provider rows remain candidates; absence is not proof of no Element84 use.",
            "algorithm_version is not relabelled as processing_version; absent values stay null.",
            "HTTP 422 errors never durably stored cannot be recovered by this snapshot.",
            "Explicit HTTP status text is evidence only, not proof that radiometry caused failure.",
            "Read-only inventory does not validate or repair historical product values.",
        ],
    }


async def _run(args) -> int:
    validate_scope(args.tenant_id, args.limit)
    import asyncpg

    dsn = os.environ.get("SAHOOL_INVENTORY_DATABASE_URL")
    if not dsn:
        raise InventoryRefused("SAHOOL_INVENTORY_DATABASE_URL is required")
    conn = await asyncpg.connect(dsn, statement_cache_size=0, timeout=10)
    try:
        report = await collect_inventory(conn, args.tenant_id, limit=args.limit)
    finally:
        await conn.close()
    # Exclusive creation avoids silently replacing a prior evidence receipt.
    with args.output.open(
        "x", encoding="utf-8", opener=lambda path, flags: os.open(path, flags, 0o600)
    ) as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    return 0 if report["snapshot_complete"] else 3


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tenant-id", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--limit", type=int, default=10000)
    args = parser.parse_args()
    try:
        return asyncio.run(_run(args))
    except Exception as exc:  # noqa: BLE001 — driver errors may include DSNs or server details
        print(f"Inventory failed ({type(exc).__name__}); no acceptance claim.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
