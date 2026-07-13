"""Tenant-scoped persistence for P2 spatial products."""

from __future__ import annotations

import json


async def _tenant(conn, tenant_id: str):
    await conn.execute("SELECT set_config('app.current_tenant_id',$1,true)", tenant_id)


async def save_product(
    pool,
    *,
    table: str,
    id_column: str,
    product_id: str,
    tenant_id: str,
    field_id: str,
    product_type: str,
    version: str,
    geometry_hash: str,
    payload: dict,
):
    allowed = {
        ("soil_bare_composites", "composite_id"),
        ("soil_terrain_products", "terrain_product_id"),
        ("soil_texture_products", "texture_product_id"),
        ("soil_salinity_products", "salinity_product_id"),
    }
    if (table, id_column) not in allowed:
        raise ValueError("unsupported_product_table")
    async with pool.acquire() as c:
        async with c.transaction():
            await _tenant(c, tenant_id)
            row = await c.fetchrow(
                f"""INSERT INTO {table}({id_column},tenant_id,field_id,product_type,version,geometry_hash,payload)
        VALUES($1,$2,$3,$4,$5,$6,$7::jsonb)
        ON CONFLICT(tenant_id,field_id,product_type,version,geometry_hash)
        DO UPDATE SET payload=EXCLUDED.payload, updated_at=now()
        RETURNING payload""",
                product_id,
                tenant_id,
                field_id,
                product_type,
                version,
                geometry_hash,
                json.dumps(payload),
            )
            return dict(row["payload"])


async def get_latest(pool, *, table: str, tenant_id: str, field_id: str):
    allowed = {
        "soil_bare_composites",
        "soil_terrain_products",
        "soil_texture_products",
        "soil_salinity_products",
    }
    if table not in allowed:
        raise ValueError("unsupported_product_table")
    async with pool.acquire() as c:
        async with c.transaction():
            await _tenant(c, tenant_id)
            row = await c.fetchrow(
                f"SELECT payload FROM {table} WHERE tenant_id=$1 AND field_id=$2 ORDER BY updated_at DESC, created_at DESC LIMIT 1",
                tenant_id,
                field_id,
            )
            return dict(row["payload"]) if row else None
