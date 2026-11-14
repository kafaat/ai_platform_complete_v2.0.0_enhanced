"""Tenant-scoped persistence for P2 spatial products."""

from __future__ import annotations

import json

from jsonb_values import decode_jsonb_object

_PRODUCT_IDS = {
    "soil_bare_composites": "composite_id",
    "soil_terrain_products": "terrain_product_id",
    "soil_texture_products": "texture_product_id",
    "soil_salinity_products": "salinity_product_id",
}


# Server-owned revisions distinguish evidence semantics from a caller's model label.
_PROCESSING_REVISIONS = {
    "soil_bare_composites": "bare-scene-support-v2",
    "soil_terrain_products": "terrain-local-derivatives-v2",
    "soil_texture_products": "texture-fractions-v2",
    "soil_salinity_products": "salinity-screening-v2",
}


class ProductRequiresRecomputation(Exception):
    """The latest stored result predates the supported scientific method."""


async def _tenant(conn, tenant_id: str):
    # v162 defines the policies for these four product tables using this key.
    await conn.execute("SELECT set_config('app.current_tenant_id',$1,true)", tenant_id)


def _product(row):
    payload = decode_jsonb_object(row["payload"])
    # Older upserts could leave a newly generated ID in the JSON and keep the
    # original primary key. Return the stored identity on both reads and writes.
    return {**payload, "product_id": row["stored_id"]}


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
    if table not in _PRODUCT_IDS or _PRODUCT_IDS[table] != id_column:
        raise ValueError("unsupported_product_table")
    revision = _PROCESSING_REVISIONS[table]
    payload = {
        **payload,
        "provenance": {**payload.get("provenance", {}), "processing_revision": revision},
    }
    # A fresh computation must not overwrite a pre-revision raw product.
    storage_version = f"{revision}:{version}"
    async with pool.acquire() as c:
        async with c.transaction():
            await _tenant(c, tenant_id)
            # Replaying unchanged scientific content preserves generation time.
            # A new observation for the same version and geometry updates the
            # current product in place while retaining its database identity.
            row = await c.fetchrow(
                f"""
                INSERT INTO {table} AS stored
                    ({id_column},tenant_id,field_id,product_type,version,geometry_hash,payload)
                VALUES($1,$2,$3,$4,$5,$6,$7::jsonb)
                ON CONFLICT(tenant_id,field_id,product_type,version,geometry_hash)
                DO UPDATE SET payload = jsonb_set(
                    CASE WHEN (stored.payload - 'product_id' - 'generated_at') =
                              (EXCLUDED.payload - 'product_id' - 'generated_at')
                         THEN stored.payload ELSE EXCLUDED.payload END,
                    '{{product_id}}', to_jsonb(stored.{id_column})),
                    updated_at = CASE WHEN (stored.payload - 'product_id' - 'generated_at') =
                                           (EXCLUDED.payload - 'product_id' - 'generated_at')
                                      THEN stored.updated_at ELSE now() END
                RETURNING {id_column} AS stored_id, payload
                """,
                product_id,
                tenant_id,
                field_id,
                product_type,
                storage_version,
                geometry_hash,
                json.dumps(payload, allow_nan=False),
            )
            return _product(row)


async def get_latest(pool, *, table: str, tenant_id: str, field_id: str):
    if table not in _PRODUCT_IDS:
        raise ValueError("unsupported_product_table")
    async with pool.acquire() as c:
        async with c.transaction():
            await _tenant(c, tenant_id)
            row = await c.fetchrow(
                f"""SELECT {_PRODUCT_IDS[table]} AS stored_id, version, payload FROM {table}
                    WHERE tenant_id=$1 AND field_id=$2
                    ORDER BY updated_at DESC, created_at DESC, {_PRODUCT_IDS[table]} DESC LIMIT 1""",
                tenant_id,
                field_id,
            )
            if not row:
                return None
            data = _product(row)
            revision = _PROCESSING_REVISIONS[table]
            if (
                not row["version"].startswith(revision + ":")
                or data.get("provenance", {}).get("processing_revision") != revision
            ):
                raise ProductRequiresRecomputation(revision)
            return data
