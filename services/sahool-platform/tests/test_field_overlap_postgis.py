"""Exercise the actual field overlap guard against an installed PostGIS extension."""

import json
import os

import asyncpg
import pytest
from fastapi import HTTPException

DATABASE_URL = os.environ.get("SAHOOL_FIELD_POSTGIS_TEST_URL")
pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(not DATABASE_URL, reason="PostGIS DSN required"),
]


async def test_update_excludes_self_and_other_tenant_only():
    # Import the application before its routers, as production does.
    from api import main  # noqa: F401
    from api.routers.fields import _reject_field_overlap

    tenant = "11111111-1111-4111-8111-111111111111"
    foreign = "22222222-2222-4222-8222-222222222222"
    box = {
        "type": "Polygon",
        "coordinates": [[[44, 16], [44.01, 16], [44.01, 16.01], [44, 16.01], [44, 16]]],
    }
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        async with conn.transaction():
            await conn.execute(
                "CREATE TEMP TABLE fields (field_id text, name text, tenant_id uuid, geom geometry(Polygon,4326)) ON COMMIT DROP"
            )
            insert = "INSERT INTO fields VALUES ($1, $1, $2::uuid, ST_GeomFromGeoJSON($3))"
            await conn.execute(insert, "current", tenant, json.dumps(box))
            await conn.execute(insert, "other-tenant", foreign, json.dumps(box))
            await _reject_field_overlap(conn, tenant, box, "current")
            await conn.execute(insert, "neighbor", tenant, json.dumps(box))
            with pytest.raises(HTTPException) as exc:
                await _reject_field_overlap(conn, tenant, box, "current")
            assert exc.value.status_code == 409
            overlaps = exc.value.detail["overlaps"]
            assert [row["field_id"] for row in overlaps] == ["neighbor"]
            assert overlaps[0]["overlap_m2"] > 1_000_000
    finally:
        await conn.close()
