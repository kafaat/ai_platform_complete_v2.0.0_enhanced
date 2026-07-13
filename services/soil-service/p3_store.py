"""Tenant-scoped persistence for P3 products."""

from __future__ import annotations

import json

_ALLOWED = {
    ("soil_visual_observations", "visual_observation_id"),
    ("soil_analog_products", "analog_product_id"),
    ("soil_drainage_assessments", "drainage_assessment_id"),
    ("soil_reclamation_assessments", "reclamation_assessment_id"),
    ("soil_reclamation_economics", "economics_product_id"),
}


async def _tenant(conn, tenant_id):
    await conn.execute("SELECT set_config('app.current_tenant_id',$1,true)", tenant_id)


async def save(
    pool,
    *,
    table,
    id_column,
    product_id,
    tenant_id,
    field_id,
    product_type,
    version,
    identity_hash,
    payload,
):
    if (table, id_column) not in _ALLOWED:
        raise ValueError("unsupported_p3_table")
    async with pool.acquire() as c:
        async with c.transaction():
            await _tenant(c, tenant_id)
            row = await c.fetchrow(
                f"""INSERT INTO {table}({id_column},tenant_id,field_id,product_type,version,identity_hash,payload)
        VALUES($1,$2,$3,$4,$5,$6,$7::jsonb)
        ON CONFLICT(tenant_id,field_id,product_type,version,identity_hash)
        DO UPDATE SET payload=EXCLUDED.payload,updated_at=now() RETURNING payload""",
                product_id,
                tenant_id,
                field_id,
                product_type,
                version,
                identity_hash,
                json.dumps(payload),
            )
            return dict(row["payload"])


async def latest(pool, *, table, tenant_id, field_id):
    if table not in {x[0] for x in _ALLOWED}:
        raise ValueError("unsupported_p3_table")
    async with pool.acquire() as c:
        async with c.transaction():
            await _tenant(c, tenant_id)
            row = await c.fetchrow(
                f"SELECT payload FROM {table} WHERE tenant_id=$1 AND field_id=$2 ORDER BY updated_at DESC,created_at DESC LIMIT 1",
                tenant_id,
                field_id,
            )
            return dict(row["payload"]) if row else None
