"""Isolated cross-service proof. Requires QDRANT_BIN v1.17.1 and a disposable PostGIS DSN."""

import json
import os
import secrets
import socket
import subprocess
import sys
import threading
import time
from contextlib import ExitStack
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import httpx
import pytest


def port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def launch(stack, args, cwd, env, log, url):
    output = stack.enter_context(log.open("w"))
    proc = subprocess.Popen(
        args, cwd=cwd, env=env, stdout=output, stderr=subprocess.STDOUT
    )

    def stop():
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=8)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()

    stack.callback(stop)
    for _ in range(120):
        if proc.poll() is not None:
            raise RuntimeError(log.read_text()[-1800:])
        try:
            if httpx.get(url, timeout=1, trust_env=False).is_success:
                return
        except httpx.TransportError:
            pass
        time.sleep(0.15)
    raise RuntimeError("service did not start: " + str(log))


@pytest.mark.asyncio
async def test_crop_preview_with_postgis_rag_and_qdrant(monkeypatch, tmp_path):
    root = Path(os.environ["SAHOOL_REPO"]).resolve()
    qdrant = os.environ["QDRANT_BIN"]
    assert (
        subprocess.check_output([qdrant, "--version"], text=True).strip()
        == "qdrant 1.17.1"
    )
    platform = root / "services" / "sahool-platform"
    sys.path[:0] = [str(platform), str(root)]
    from api import main
    from api.routers import crop_twin
    from core.canonical_schemas import UserRole, UserSchema
    from core.rag.production_qdrant import HashEmbeddingProvider
    from fastapi import FastAPI

    tenant = "00000000-0000-0000-0000-000000000011"
    neighbor = "00000000-0000-0000-0000-000000000022"
    token = secrets.token_urlsafe(32)
    embedding = HashEmbeddingProvider(dimensions=64)

    class OfflineEmbedding(BaseHTTPRequestHandler):
        def do_POST(self):
            assert self.path == "/api/embeddings"
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            out = json.dumps({"embedding": embedding.embed(body["prompt"])}).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(out)))
            self.end_headers()
            self.wfile.write(out)

        def log_message(self, *_):
            pass

    with ExitStack() as stack:
        fixture = ThreadingHTTPServer(("127.0.0.1", 0), OfflineEmbedding)
        thread = threading.Thread(target=fixture.serve_forever, daemon=True)
        thread.start()
        stack.callback(thread.join)
        stack.callback(fixture.server_close)
        stack.callback(fixture.shutdown)
        qp, grpc, rp = port(), port(), port()
        assert len({qp, grpc, rp}) == 3
        qurl, rurl = f"http://127.0.0.1:{qp}", f"http://127.0.0.1:{rp}"
        env = {
            **os.environ,
            "QDRANT__SERVICE__HOST": "127.0.0.1",
            "QDRANT__SERVICE__HTTP_PORT": str(qp),
            "QDRANT__SERVICE__GRPC_PORT": str(grpc),
            "QDRANT__SERVICE__MAX_WORKERS": "1",
            "QDRANT__STORAGE__PERFORMANCE__MAX_SEARCH_THREADS": "1",
            "QDRANT__TELEMETRY_DISABLED": "true",
            "RAYON_NUM_THREADS": "2",
        }
        launch(
            stack,
            [qdrant, "--disable-telemetry"],
            tmp_path,
            env,
            tmp_path / "qdrant.log",
            qurl + "/healthz",
        )
        rag = root / "services" / "rag-retrieval"
        env.update(
            {
                "PYTHONPATH": os.pathsep.join(map(str, [rag, platform, root])),
                "SAHOOL_AGENT_TOKEN": token,
                "QDRANT_URL": qurl,
                "QDRANT_COLLECTION": "spatial_test",
                "OLLAMA_BASE_URL": f"http://127.0.0.1:{fixture.server_port}",
            }
        )
        launch(
            stack,
            [
                sys.executable,
                "-m",
                "uvicorn",
                "main:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(rp),
            ],
            rag,
            env,
            tmp_path / "retrieval.log",
            rurl + "/openapi.json",
        )
        async with httpx.AsyncClient(trust_env=False, timeout=25) as client:
            for owner, field_id, label in [
                (tenant, "pivot-a", "a"),
                (tenant, "pivot-a", "flat-zone"),
                (tenant, "pivot-a", "nested-zone"),
                (tenant, "pivot-b", "b"),
                (neighbor, "pivot-a", "foreign"),
            ]:
                response = await client.post(
                    rurl + "/v1/ingest",
                    headers={"X-Tenant-Id": owner, "X-Agent-Token": token},
                    json={
                        "chunks": [
                            {
                                "tenant_id": owner,
                                "chunk_id": label,
                                "document_id": label,
                                "chunk_index": 0,
                                "total_chunks": 1,
                                "text": "salinity observation in " + field_id,
                                "source_type": "internal_document",
                                "metadata": {
                                    "field_id": field_id,
                                    "source_uri": "urn:fixture:" + label,
                                    **({"zone_id": "z1"} if label == "flat-zone" else {}),
                                    **(
                                        {"spatial_scope": {"field_id": field_id, "zone_id": "z1"}}
                                        if label == "nested-zone" else {}
                                    ),
                                    "source_revision": "r1",
                                },
                            }
                        ]
                    },
                )
                assert response.is_success, response.text
            data = await client.get(qurl + "/collections/spatial_test")
            assert data.json()["result"]["points_count"] == 5
        monkeypatch.setenv("RAG_RETRIEVAL_URL", rurl)
        monkeypatch.setenv("SAHOOL_AGENT_TOKEN", token)
        for key in ["DATABASE_URL", "JOBS_DATABASE_URL"]:
            monkeypatch.setenv(key, os.environ["TEST_DATABASE_URL"])
        for key in ["DB_POOL_MIN", "DB_POOL_MAX"]:
            monkeypatch.setenv(key, "1")
        await main._init_db_pool()
        try:
            async with main.get_pool().acquire() as conn:
                await conn.execute(
                    "CREATE TEMP TABLE fields(field_id text, tenant_id uuid, geom geometry)"
                )
                await conn.executemany(
                    "INSERT INTO fields VALUES ($1,$2::uuid,ST_MakeEnvelope($3,10,$4,11,4326))",
                    [
                        ("pivot-a", tenant, 40, 41),
                        ("pivot-b", tenant, 41, 42),
                        ("pivot-a", neighbor, 40, 41),
                        ("private", neighbor, 45, 46),
                    ],
                )

                await conn.executemany(
                    "INSERT INTO fields VALUES ($1,$2::uuid,ST_GeomFromText($3,4326))",
                    [
                        (
                            "overlap",
                            tenant,
                            "POLYGON((40 10.6,40.3 10.6,40.3 10.8,40 10.8,40 10.6))",
                        ),
                        (
                            "islands",
                            tenant,
                            "MULTIPOLYGON(((49 10,50 10,50 11,49 11,49 10)),((51 10,52 10,52 11,51 11,51 10)))",
                        ),
                        (
                            "outer",
                            tenant,
                            "POLYGON((54 10,56 10,56 12,54 12,54 10),(54.5 10.5,54.5 11.5,55.5 11.5,55.5 10.5,54.5 10.5))",
                        ),
                    ],
                )

            async def weather(**_):
                return {"daily_gdd": [12], "accumulated_gdd": 12}

            monkeypatch.setattr(crop_twin, "get_gdd_product", weather)
            user = UserSchema(
                user_id="review",
                tenant_id=tenant,
                role=UserRole.OWNER,
                name_ar="اختبار",
            )
            app = FastAPI()
            app.include_router(crop_twin.router)
            app.dependency_overrides[main.get_current_user] = lambda: user
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://preview"
            ) as client:
                for lon, lat, suffix, code, field, chunk in [
                    (40.5, 10.5, "", 200, "pivot-a", "a"),
                    (41.5, 10.5, "/profit-aware", 200, "pivot-b", "b"),
                    (41, 10.5, "", 409, None, None),
                    (45.5, 10.5, "", 404, None, None),
                    (40.1, 10.7, "", 409, None, None),
                    (49.5, 10.5, "", 200, "islands", None),
                    (51.5, 10.5, "", 200, "islands", None),
                    (50.5, 10.5, "", 404, None, None),
                    (54.25, 11, "", 200, "outer", None),
                    (55, 11, "", 404, None, None),
                ]:
                    response = await client.post(
                        "/api/v1/crop-twin/decision" + suffix,
                        json={
                            "georag": {
                                "longitude": lon,
                                "latitude": lat,
                                "query": "salinity",
                            },
                            "crop": "wheat",
                            "forecast": [{"t_min_c": 10, "t_max_c": 25, "et0_mm": 4}],
                        },
                    )
                    assert response.status_code == code, response.text
                    if field:
                        decision = response.json()
                        assert (
                            decision["field_id"]
                            == decision["decision_scope"]["field_id"]
                            == field
                        )
                        assert decision["decision_scope"]["georag_grounded"] is (
                            chunk is not None
                        )
                        if field == "pivot-a":
                            evidence = decision["georag_evidence"]
                            rejected_zones = {
                                r["chunk_id"] for r in evidence["rejected"]
                                if r["reason"] == "zone_scope_mismatch"
                            }
                            assert rejected_zones == {"flat-zone", "nested-zone"}, (
                                f"zone rejections={sorted(rejected_zones)}; "
                                f"admitted={[a['chunk_id'] for a in evidence['annotations']]}"
                            )
                        assert [
                            a["chunk_id"]
                            for a in decision["georag_evidence"]["annotations"]
                        ] == ([chunk] if chunk else [])
                        assert decision["persisted"] is False
            print(
                "Native Qdrant 1.17.1: 5 documents, flat and nested zone restrictions, 2 tenants, 10 spatial previews; correct field documents, empty corpus by field, adjacent and overlapping polygons, MultiPolygon parts and gap, polygon shell and hole. Deterministic embeddings and weather."
            )
        finally:
            await main._close_db_pool()
