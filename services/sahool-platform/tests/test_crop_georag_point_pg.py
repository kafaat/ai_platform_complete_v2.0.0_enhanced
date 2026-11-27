"""Exercise both crop-decision previews through ASGI and native PostGIS.

The auth dependency supplies the test principal. Weather and retrieval have fixture
responses. PostgreSQL evaluates the actual point lookup on polygons for two tenants.
"""

from __future__ import annotations

import json
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import asyncpg
import httpx
import pytest
from api import main
from api.routers import crop_twin
from core.canonical_schemas import UserRole, UserSchema
from fastapi import FastAPI

pytestmark = pytest.mark.integration

TENANT = "00000000-0000-0000-0000-000000000011"
NEIGHBOR = "00000000-0000-0000-0000-000000000022"


async def test_preview_resolves_point_under_authenticated_tenant(monkeypatch):
    dsn = os.environ.get("TEST_DATABASE_URL")
    if not dsn:
        pytest.skip("requires PostgreSQL with PostGIS")
    pool = await asyncpg.create_pool(dsn, min_size=1, max_size=1)
    seen = []

    class Retrieval(BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            field = body["field_id"]
            seen.append(
                (self.path, self.headers["X-Tenant-Id"], field, self.headers["X-Agent-Token"])
            )
            result = json.dumps(
                {
                    "annotations": [
                        {
                            "chunk_id": field,
                            "tenant_id": TENANT,
                            "verified": False,
                            "decision_authority": "none",
                            "source_uri": "urn:test:field",
                            "source_revision": "1",
                            "content_digest": "fixture",
                            "spatial_scope": {"field_id": field},
                        }
                    ]
                }
            ).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(result)))
            self.end_headers()
            self.wfile.write(result)

        def log_message(self, *_):
            pass

    async def daily_gdd(**_):
        return {"daily_gdd": [12], "accumulated_gdd": 12}

    server = HTTPServer(("127.0.0.1", 0), Retrieval)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                "CREATE TEMP TABLE fields (field_id text, tenant_id uuid, geom geometry)"
            )
            await conn.executemany(
                """INSERT INTO fields VALUES ($1, $2::uuid,
                    ST_MakeEnvelope($3, 10, $4, 11, 4326))""",
                [
                    ("pivot-a", TENANT, 40, 41),
                    ("pivot-b", TENANT, 41, 42),
                    ("other-tenant", NEIGHBOR, 40, 41),
                    ("only-other", NEIGHBOR, 45, 46),
                ],
            )

        user = UserSchema(user_id="tester", tenant_id=TENANT, role=UserRole.OWNER, name_ar="اختبار")
        app = FastAPI()
        app.include_router(crop_twin.router)
        app.dependency_overrides[main.get_current_user] = lambda: user
        monkeypatch.setattr(main, "get_pool", lambda: pool)
        monkeypatch.setattr(crop_twin, "get_gdd_product", daily_gdd)
        monkeypatch.setenv("RAG_RETRIEVAL_URL", f"http://127.0.0.1:{server.server_port}")
        monkeypatch.setenv("SAHOOL_AGENT_TOKEN", "fixture-only")
        route = "/api/v1/crop-twin/decision"
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://preview"
        ) as client:

            async def preview(lon, *, suffix="", **kw):
                return await client.post(
                    route + suffix,
                    json={
                        "georag": {"longitude": lon, "latitude": 10.5, "query": "salinity"},
                        "crop": "wheat",
                        "forecast": [{"t_min_c": 10, "t_max_c": 25, "et0_mm": 4}],
                        **kw,
                    },
                )

            for lon, field, suffix in [(40.5, "pivot-a", ""), (41.5, "pivot-b", "/profit-aware")]:
                response = await preview(lon, suffix=suffix)
                assert response.status_code == 200, response.text
                decision = response.json()
                assert decision["field_id"] == decision["decision_scope"]["field_id"] == field
                assert decision["georag_evidence"]["annotations"][0]["chunk_id"] == field
                assert decision["decision_scope"]["georag_grounded"] is True
                assert decision["persisted"] is False

            assert (await preview(41)).status_code == 409  # shared edge
            assert (await preview(45.5)).status_code == 404  # only another tenant
            assert (await preview(50)).status_code == 404
            assert (await preview(40.5, field_id="pivot-b")).status_code == 422
            assert (await preview(181)).status_code == 422
            assert seen == [
                ("/v1/search", TENANT, field, "fixture-only") for field in ("pivot-a", "pivot-b")
            ]

            monkeypatch.delenv("SAHOOL_AGENT_TOKEN")
            response = await preview(40.5)
            assert response.status_code == 200
            assert response.json()["decision_scope"]["georag_grounded"] is False
            assert len(seen) == 2
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
        await pool.close()
