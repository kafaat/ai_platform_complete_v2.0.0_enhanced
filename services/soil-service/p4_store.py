from __future__ import annotations

import json


async def save(
    pool,
    *,
    table: str,
    id_column: str,
    record_id: str,
    tenant_id: str,
    field_id: str,
    payload: dict,
    extra: dict | None = None,
):
    extra = extra or {}
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute("SELECT set_config('app.current_tenant',$1,true)", tenant_id)
            cols = [id_column, "tenant_id", "field_id"] + list(extra) + ["payload"]
            vals = (
                [record_id, tenant_id, field_id]
                + list(extra.values())
                + [json.dumps(payload, default=str)]
            )
            ph = ",".join(f"${i}" for i in range(1, len(vals) + 1))
            sql = f"INSERT INTO {table} ({','.join(cols)}) VALUES ({ph}) ON CONFLICT ({id_column}) DO UPDATE SET payload=EXCLUDED.payload RETURNING payload"
            row = await conn.fetchrow(sql, *vals)
            return json.loads(row["payload"]) if isinstance(row["payload"], str) else row["payload"]


async def get(pool, *, table: str, id_column: str, record_id: str, tenant_id: str):
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute("SELECT set_config('app.current_tenant',$1,true)", tenant_id)
            row = await conn.fetchrow(
                f"SELECT payload FROM {table} WHERE {id_column}=$1", record_id
            )
            if not row:
                return None
            return json.loads(row["payload"]) if isinstance(row["payload"], str) else row["payload"]


async def list_field(pool, *, table: str, tenant_id: str, field_id: str, limit: int = 100):
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute("SELECT set_config('app.current_tenant',$1,true)", tenant_id)
            rows = await conn.fetch(
                f"SELECT payload FROM {table} WHERE field_id=$1 ORDER BY created_at DESC LIMIT $2",
                field_id,
                limit,
            )
            return [
                json.loads(r["payload"]) if isinstance(r["payload"], str) else r["payload"]
                for r in rows
            ]
