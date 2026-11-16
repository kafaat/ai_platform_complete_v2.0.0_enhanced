"""Tenant-scoped persistence for governed P1 products."""

from __future__ import annotations

import json

from jsonb_values import decode_jsonb_object


async def _tenant(conn, tenant_id):
    await conn.execute("SELECT set_config('app.current_tenant_id',$1,true)", tenant_id)


async def save_spatial(pool, p):
    async with pool.acquire() as c:
        async with c.transaction():
            await _tenant(c, p.tenant_id)
            row = await c.fetchrow(
                """INSERT INTO soil_spatial_products(product_id,tenant_id,field_id,product_type,dataset_version,geometry_hash,payload)
       VALUES($1,$2,$3,'soilgrids_polygon',$4,$5,$6::jsonb) ON CONFLICT(tenant_id,field_id,product_type,dataset_version,geometry_hash) DO UPDATE SET payload=EXCLUDED.payload RETURNING product_id""",
                p.product_id,
                p.tenant_id,
                p.field_id,
                p.dataset_version,
                p.geometry_hash,
                json.dumps(p.model_dump(mode="json")),
            )
            return row["product_id"]


async def save_sampling(pool, p):
    async with pool.acquire() as c:
        async with c.transaction():
            await _tenant(c, p.tenant_id)
            await c.execute(
                "INSERT INTO soil_sampling_plans(plan_id,tenant_id,field_id,status,mode,payload) VALUES($1,$2,$3,$4,$5,$6::jsonb)",
                p.plan_id,
                p.tenant_id,
                p.field_id,
                p.status,
                p.mode,
                json.dumps(p.model_dump(mode="json")),
            )


async def approve_sampling(pool, tenant_id, plan_id, actor):
    async with pool.acquire() as c:
        async with c.transaction():
            await _tenant(c, tenant_id)
            row = await c.fetchrow(
                "UPDATE soil_sampling_plans SET status='approved',approved_by=$3,approved_at=now(),payload=jsonb_set(payload,'{status}','\"approved\"') WHERE tenant_id=$1 AND plan_id=$2 AND status='draft' RETURNING payload",
                tenant_id,
                plan_id,
                actor,
            )
            return decode_jsonb_object(row["payload"]) if row else None


async def save_hydraulic(pool, p):
    async with pool.acquire() as c:
        async with c.transaction():
            await _tenant(c, p.tenant_id)
            row = await c.fetchrow(
                """INSERT INTO soil_hydraulic_profiles(hydraulic_profile_id,tenant_id,field_id,source_soil_profile_hash,payload)
       VALUES($1,$2,$3,$4,$5::jsonb) ON CONFLICT(tenant_id,field_id,source_soil_profile_hash) DO UPDATE SET payload=EXCLUDED.payload RETURNING payload""",
                p.profile_id,
                p.tenant_id,
                p.field_id,
                p.source_soil_profile_hash,
                json.dumps(p.model_dump(mode="json")),
            )
            return decode_jsonb_object(row["payload"])


async def project_hydraulic_in_transaction(conn, p) -> bool:
    """W1-04: the projection written beside a new soil snapshot, in the caller's transaction.

    One profile per ``(tenant, field, source_soil_profile_hash)``: a rebuild that lands on a
    hash already projected keeps the stored profile (and its id) instead of churning it, so the
    projection runs only when ``profile_hash`` changes. Returns whether a row was written.
    """
    await _tenant(conn, p.tenant_id)
    written = await conn.fetchval(
        """INSERT INTO soil_hydraulic_profiles(hydraulic_profile_id,tenant_id,field_id,source_soil_profile_hash,payload)
       VALUES($1,$2,$3,$4,$5::jsonb) ON CONFLICT(tenant_id,field_id,source_soil_profile_hash) DO NOTHING RETURNING hydraulic_profile_id""",
        p.profile_id,
        p.tenant_id,
        p.field_id,
        p.source_soil_profile_hash,
        json.dumps(p.model_dump(mode="json")),
    )
    return written is not None


async def get_current_hydraulic(pool, tenant_id, field_id):
    """The hydraulic profile built from the field's *current* soil snapshot, or ``None``.

    Joined on ``source_soil_profile_hash`` = the current snapshot's ``profile_hash``. A profile
    projected from an older snapshot is never served as current (it would describe soil the
    canonical profile no longer reports); absence reads as unavailable, never synthesized.
    """
    async with pool.acquire() as c:
        async with c.transaction():
            await _tenant(c, tenant_id)
            # soil_profile_current / soil_profile_snapshots are isolated on app.current_tenant.
            await c.execute("SELECT set_config('app.current_tenant',$1,true)", tenant_id)
            row = await c.fetchrow(
                """SELECT h.payload
       FROM soil_profile_current cur
       JOIN soil_profile_snapshots s
         ON s.tenant_id=cur.tenant_id AND s.profile_id=cur.current_profile_id
       JOIN soil_hydraulic_profiles h
         ON h.tenant_id=$1 AND h.field_id=cur.field_id AND h.source_soil_profile_hash=s.profile_hash
       WHERE cur.tenant_id=$1::uuid AND cur.field_id=$2""",
                tenant_id,
                field_id,
            )
            return decode_jsonb_object(row["payload"]) if row else None


async def save_water(pool, s, p):
    async with pool.acquire() as c:
        async with c.transaction():
            await _tenant(c, s.tenant_id)
            await c.execute(
                "INSERT INTO irrigation_water_samples(sample_id,tenant_id,field_id,source_id,sampled_at,approved,payload) VALUES($1,$2,$3,$4,$5,$6,$7::jsonb) ON CONFLICT(sample_id) DO NOTHING",
                s.sample_id,
                s.tenant_id,
                s.field_id,
                s.source_id,
                s.sampled_at,
                s.approved,
                json.dumps(s.model_dump(mode="json")),
            )
            row = await c.fetchrow(
                """INSERT INTO irrigation_water_profiles(water_profile_id,tenant_id,field_id,source_id,sample_id,payload,effective_at)
       VALUES($1,$2,$3,$4,$5,$6::jsonb,$7) ON CONFLICT(tenant_id,sample_id) DO UPDATE SET payload=EXCLUDED.payload RETURNING payload""",
                p.profile_id,
                p.tenant_id,
                p.field_id,
                p.source_id,
                p.sample_id,
                json.dumps(p.model_dump(mode="json")),
                p.effective_at,
            )
            return decode_jsonb_object(row["payload"])


async def get_latest(pool, tenant_id, table, field, field_id):
    allowed = {
        ("soil_spatial_products", "field_id"): "payload",
        ("soil_sampling_plans", "field_id"): "payload",
        ("soil_hydraulic_profiles", "field_id"): "payload",
        ("irrigation_water_profiles", "source_id"): "payload",
    }
    column = allowed.get((table, field))
    if not column:
        raise ValueError("unsupported_lookup")
    async with pool.acquire() as c:
        async with c.transaction():
            await _tenant(c, tenant_id)
            row = await c.fetchrow(
                f"SELECT {column} FROM {table} WHERE tenant_id=$1 AND {field}=$2 ORDER BY created_at DESC LIMIT 1",
                tenant_id,
                field_id,
            )
            return decode_jsonb_object(row[column]) if row else None
