"""Regression witnesses for the 2026-09-15 readiness review (no live services)."""

from __future__ import annotations

import ast
import asyncio
import importlib.util
import logging
import sys
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from secrets import token_urlsafe
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import numpy as np
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.unit


def load_service(monkeypatch, folder, name="main"):
    directory = ROOT / "services" / folder
    monkeypatch.syspath_prepend(str(directory))
    spec = importlib.util.spec_from_file_location(
        f"readiness_{folder}_{name}", directory / f"{name}.py"
    )
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, module)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("body", [{}, {"ndvi": 0, "soil_ph": 7}])
def test_agriai_never_invents_measurements(monkeypatch, body):
    module = load_service(monkeypatch, "agriai-engine")
    monkeypatch.setattr(module, "AGENT_TOKEN", "unit-service-credential")
    monkeypatch.setattr(module, "STRICT_AGRONOMIC_CONTEXT", False)
    response = TestClient(module.app).post(
        "/v1/recommend", json=body, headers={"X-Agent-Token": "unit-service-credential"}
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["evidence_sufficient"] is False
    assert payload["confidence"] == 0
    assert payload["recommendation"] is None
    req = module.RecommendRequest(**body)
    bundle = module._build_bundle(req.evidence, ndvi=req.ndvi, soil_ph=req.soil_ph)
    assert bundle["items"] == []
    assert bundle["context"]["unverified_inputs"]["ndvi"] == body.get("ndvi")


@pytest.mark.parametrize(
    "confidence, observed_at, expected",
    [
        (None, "2026-09-15T00:00:00Z", 0),
        (0, "2026-09-15T00:00:00Z", 0),
        (0.8, "2026-09-15T00:00:00Z", 0.8),
        (0.8, None, 0),
        (0.8, "invalid", 0),
        (0.8, "2026-09-15", 0),
        (float("nan"), "2026-09-15T00:00:00Z", 0),
    ],
)
def test_evidence_confidence_requires_a_dated_observation(
    monkeypatch, confidence, observed_at, expected
):
    module = load_service(monkeypatch, "agriai-engine", "evidence_bundle")
    item = module.make_evidence_item(
        source="lab:sample-1",
        kind="soil_ph",
        value=7,
        strength="lab",
        observed_at=observed_at,
        confidence=confidence,
    )
    assert module.compose_confidence([item]) == expected


class TransactionConnection:
    """Models PostgreSQL's aborted-transaction state and savepoint rollback."""

    def __init__(self):
        self.aborted = False
        self.fail_next = True
        self.savepoints = 0

    @asynccontextmanager
    async def transaction(self):
        self.savepoints += 1
        try:
            yield
        except Exception:
            self.aborted = False
            raise

    async def fetch(self, *_args):
        if self.aborted:
            raise RuntimeError("current transaction is aborted")
        if self.fail_next:
            self.fail_next = False
            self.aborted = True
            raise RuntimeError("optional relation is unavailable")
        return []

    async def fetchrow(self, *args):
        await self.fetch(*args)
        return None


@pytest.mark.parametrize(
    "name",
    [
        "_optional_active_season",
        "_optional_events",
        "_optional_drawings",
        "_optional_alerts",
        "_optional_recommendations",
    ],
)
async def test_optional_read_failure_does_not_poison_following_reads(name):
    from api.routers import field_ai_context as context

    conn = TransactionConnection()
    args = (
        (conn, "field-1", "tenant-1", 20)
        if name == "_optional_events"
        else (conn, "field-1", "tenant-1")
    )
    _, warning = await getattr(context, name)(*args)
    assert warning
    assert conn.savepoints == 1
    assert not conn.aborted
    assert await conn.fetch("SELECT policy FROM tenant_ai_policies") == []


@pytest.mark.parametrize("age", [None, -2, 0, 30, 54, 90, 140])
async def test_weather_and_recommendations_share_crop_phase(age):
    from api.field_context import _field_season_context, _field_weather_context

    sowing = date.today() - timedelta(days=age) if age is not None else None
    season = {"crops": ["wheat"], "sowing_date": sowing}
    conn = SimpleNamespace(
        fetchrow=AsyncMock(
            side_effect=[
                {"lat": 15, "lon": 44, "crop": "wheat"},
                season,
                {"lat": 15, "lon": 44, "crop": "wheat"},
                season,
            ]
        )
    )
    weather = await _field_weather_context(conn, "field-1")
    recommendation = await _field_season_context(conn, "field-1")
    assert weather[3] == recommendation[3]
    if age is None or age < 0:
        assert weather[3] is None
    if age == 54:
        assert weather[3] == "mid"


@pytest.mark.parametrize("valid", [False, True])
def test_precomputed_raster_rejects_nodata_but_keeps_measured_zero(monkeypatch, tmp_path, valid):
    import rasterio
    from rasterio.transform import from_origin

    module = load_service(monkeypatch, "raster-service", "raster_pixel_processing")
    from raster_api_models import IndicatorKind, ProcessRequest, SourceFormat

    path = tmp_path / "input.tif"
    values = np.full((13, 23), 0 if valid else -9999, dtype="float32")
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=23,
        height=13,
        count=1,
        dtype="float32",
        crs="EPSG:32638",
        transform=from_origin(500000, 2800000, 10, 10),
        nodata=-9999,
    ) as dst:
        dst.write(values, 1)
    output = tmp_path / "output"
    output.mkdir()
    ctx = SimpleNamespace(
        _safe_raster_source=lambda value: value,
        HTTPException=HTTPException,
        UPLOAD_DIR=str(output),
        RASTER_NODATA=-9999,
        logger=logging.getLogger(__name__),
    )
    req = ProcessRequest(
        tenant_id="tenant-1",
        bands={},
        raster_url=str(path),
        indicator=IndicatorKind.ndvi,
        source_format=SourceFormat.custom,
        precomputed_index=True,
        raw_qa_required=False,
    )
    if not valid:
        with pytest.raises(HTTPException) as error:
            module.process_precomputed_pixels(ctx, req, "layer-1")
        assert error.value.status_code == 422
        assert error.value.detail["code"] == "raw_raster_no_valid_pixels"
        assert list(output.iterdir()) == []
    else:
        stats, *_ = module.process_precomputed_pixels(ctx, req, "layer-1")
        assert stats["mean"] == 0
        assert stats["valid_pixels"] == values.size
    lookup = load_service(monkeypatch, "raster-service", "layer_lookup")
    old = lookup.grid_from_cog(
        {"cog_url": str(path), "field_id": "f1"},
        "ndvi",
        "2026-09-15",
        2,
        SimpleNamespace(to_gdal_path=lambda value: value),
    )
    if valid:
        assert old["stats"]["mean"] == 0
    else:
        assert old is None


def test_old_empty_grid_is_missing_not_zero(monkeypatch):
    module = load_service(monkeypatch, "raster-service", "indicator_grid")
    result = module.grid_from_array(np.full((4, 4), np.nan), "ndvi", 2)
    assert result["stats"] == {"min": None, "max": None, "mean": None}
    assert result["zones"] == []
    assert module.grid_from_array(np.zeros((4, 4)), "ndvi", 2)["stats"]["mean"] == 0


def test_unavailable_fields_and_rrf_scores_do_not_gain_confidence():
    from services.ai_agronomist import ai_evidence_runtime as runtime

    assert (
        runtime._confidence_from_payloads(
            {"annotations": [{"score": 99, "text": "reference"}]},
            {"edges": [{"edge_id": "e1"}]},
            {"validity": "insufficient", "remote_sensing": {"available": False}},
        )
        == 0
    )
    state = {
        "schema_version": "canonical_field_state.v1",
        "weather": {"quality_status": "validated", "confidence": 0.8},
    }
    assert runtime._confidence_from_payloads({}, {}, state) == 0.8
    state["weather"]["limitations"] = ["stale"]
    assert runtime._confidence_from_payloads({}, {}, state) == 0


async def test_canonical_context_is_requested_and_identity_bound(monkeypatch):
    from services.ai_agronomist import ai_evidence_runtime as runtime

    monkeypatch.setattr(runtime, "AGENT_TOKEN", "unit-credential")
    payload = {
        "state": {"validity": "legacy"},
        "canonical_field_state": {"schema_version": "canonical_field_state.v1", "field_id": "f1"},
        "ai_context_pack": {"field_id": "f1", "tenant_id": "t1", "policy_envelope": {}},
    }
    client = SimpleNamespace(get=AsyncMock(return_value=httpx.Response(200, json=payload)))
    result = await runtime._fetch_canonical_field_state(client, tenant_id="t1", field_id="f1")
    assert client.get.call_args.kwargs["params"] == {
        "tenant_id": "t1",
        "canonical": "true",
        "ai_context": "true",
    }
    assert result["schema_version"] == "canonical_field_state.v1"
    assert "validity" not in result
    payload["ai_context_pack"]["tenant_id"] = "t2"
    client.get.return_value = httpx.Response(200, json=payload)
    assert (await runtime._fetch_canonical_field_state(client, tenant_id="t1", field_id="f1"))[
        "status"
    ] == "unavailable"


@pytest.mark.parametrize(
    "tenant, token, expected",
    [
        ("t1", None, 403),
        ("t1", "wrong", 403),
        ("t1", "unit-credential", 200),
        ("__global__", "unit-credential", 403),
        ("__seed_quarantine__", "unit-credential", 403),
    ],
)
def test_rag_search_authenticates_before_reading(monkeypatch, tenant, token, expected):
    module = load_service(monkeypatch, "rag-retrieval")
    monkeypatch.setenv("SAHOOL_AGENT_TOKEN", "unit-credential")
    reads = []
    monkeypatch.setattr(module, "_ensure_sparse_index", lambda: reads.append(True))
    monkeypatch.setattr(module._retriever, "retrieve", lambda *a, **kw: [])
    headers = {"X-Tenant-Id": tenant}
    if token:
        headers["X-Agent-Token"] = token
    response = TestClient(module.app).post(
        "/v1/search", json={"tenant_id": tenant, "query": "wheat"}, headers=headers
    )
    assert response.status_code == expected
    assert bool(reads) is (expected == 200)


def test_public_rag_uses_verified_jwt_tenant(monkeypatch):
    module = load_service(monkeypatch, "rag-retrieval")
    monkeypatch.setattr(module, "_verify_search_user", lambda _token: "t1")
    monkeypatch.setattr(module, "_ensure_sparse_index", lambda: {})
    monkeypatch.setattr(module._retriever, "retrieve", lambda *a, **kw: [])
    client = TestClient(module.app)
    assert (
        client.post(
            "/v1/search",
            json={"tenant_id": "t1", "query": "q"},
            headers={"Authorization": "Bearer unit-jwt"},
        ).status_code
        == 200
    )
    assert (
        client.post(
            "/v1/search",
            json={"tenant_id": "t2", "query": "q"},
            headers={"Authorization": "Bearer unit-jwt", "X-Tenant-Id": "t2"},
        ).status_code
        == 403
    )


@pytest.mark.parametrize(
    "case, expected",
    [
        ("valid", 200),
        ("expired", 403),
        ("signature", 403),
        ("issuer", 403),
        ("audience", 403),
        ("tenant", 403),
        ("unconfigured", 503),
    ],
)
def test_public_rag_verifies_signed_access_tokens_before_retrieval(monkeypatch, case, expected):
    from jose import jwt

    module = load_service(monkeypatch, "rag-retrieval")
    secret = token_urlsafe(48)
    monkeypatch.setenv("SAHOOL_ENV", "development")
    monkeypatch.setenv("JWT_PUBLIC_KEY", "")
    monkeypatch.setenv("JWT_SECRET", "" if case == "unconfigured" else secret)
    claims = {
        "sub": "user-1",
        "tenant_id": "t1",
        "iss": "sahool-auth",
        "aud": "sahool",
        "exp": datetime.now(UTC) + timedelta(minutes=-1 if case == "expired" else 5),
    }
    if case == "issuer":
        claims["iss"] = "untrusted"
    if case == "audience":
        claims["aud"] = "another-service"
    token = jwt.encode(claims, secret + "bad" if case == "signature" else secret, algorithm="HS256")
    reads = []
    monkeypatch.setattr(module, "_ensure_sparse_index", lambda: reads.append(True))
    monkeypatch.setattr(module._retriever, "retrieve", lambda *a, **kw: [])
    response = TestClient(module.app).post(
        "/v1/search",
        json={"tenant_id": "t2" if case == "tenant" else "t1", "query": "q"},
        headers={"Authorization": "Bearer " + token},
    )
    assert response.status_code == expected, response.text
    assert bool(reads) is (expected == 200)


def test_public_rag_production_uses_rsa_verification_key(monkeypatch):
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from jose import jwt

    module = load_service(monkeypatch, "rag-retrieval")
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private = key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    )
    public = key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    monkeypatch.setenv("SAHOOL_ENV", "production")
    monkeypatch.setenv("JWT_PUBLIC_KEY", public.decode())
    monkeypatch.setenv("SAHOOL_ALLOW_HS256_IN_PROD", "false")
    token = jwt.encode(
        {
            "sub": "u1",
            "tenant_id": "t1",
            "iss": "sahool-auth",
            "aud": "sahool",
            "exp": datetime.now(UTC) + timedelta(minutes=5),
        },
        private,
        algorithm="RS256",
    )
    assert module._verify_search_user("Bearer " + token) == "t1"


async def test_ollama_accepts_latest_tag_without_pulling():
    # Load the real initialization functions without LangChain's unrelated runtime.
    source = ROOT / "services/local-ai-rag/main.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    functions = [
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name in {"_model_name", "wait_for_ollama"}
    ]
    client = AsyncMock()
    client.get.return_value = httpx.Response(
        200, json={"models": [{"name": "llama3.2:3b"}, {"name": "nomic-embed-text:latest"}]}
    )
    factory = SimpleNamespace(AsyncClient=lambda **_: client)
    client.__aenter__.return_value = client
    namespace = {
        "asyncio": asyncio,
        "httpx": factory,
        "logger": logging.getLogger(__name__),
        "OLLAMA_BASE_URL": "http://ollama",
        "LLM_MODEL": "llama3.2:3b",
        "EMBED_MODEL": "nomic-embed-text",
    }
    exec(compile(ast.Module(body=functions, type_ignores=[]), str(source), "exec"), namespace)
    assert await namespace["wait_for_ollama"](timeout=0.5)
    client.post.assert_not_called()
    assert namespace["_model_name"]("registry:5000/team/model") == "registry:5000/team/model:latest"


@pytest.mark.parametrize("has_reference", [True, False])
async def test_model_prose_cannot_be_published_merely_because_rag_found_text(
    monkeypatch, has_reference
):
    from services.ai_agronomist import ai_evidence_runtime as runtime
    from services.ai_agronomist.main import AdvisorQuery

    original = httpx.AsyncClient
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            json={
                "annotations": [{"chunk_id": "unrelated", "text": "مرجع عام عن القمح"}]
                if has_reference
                else [],
                "edges": [],
            },
        )
    )
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: original(transport=transport, **kw))
    monkeypatch.setattr(runtime, "_generation_allowed", lambda tenant: True)
    monkeypatch.setattr(runtime.ai_generation, "resolve_generation", lambda model: None)
    monkeypatch.setattr(
        runtime.policy_envelope, "gate_generation", lambda *a, **kw: {"decision": "allowed"}
    )
    invented = "أضف 50 كغ من السماد الآن"
    generation = SimpleNamespace(
        text=invented,
        model="unit",
        provider="local",
        tool_calls=[{"tool": "get_field_state", "status": "unavailable"}],
        pending_approvals=[{"approval_id": "unit-approval", "status": "pending"}],
        tool_calls_truncated=False,
        tool_rounds=0,
    )
    monkeypatch.setattr(runtime.ai_generation, "generate", AsyncMock(return_value=generation))
    monkeypatch.setattr(
        runtime, "_record_ai_advice_event", AsyncMock(return_value={"status": "recorded"})
    )
    result = await runtime.build_evidence_response(
        AdvisorQuery(question="ماذا أفعل؟"),
        endpoint_mode="chat",
        x_tenant_id="t1",
        save_agent_tool_audit=lambda value: None,
        save_pending_approval=lambda value: None,
    )
    assert invented not in result["answer_ar"]
    assert result["generation_status"] == (
        "suppressed_unvalidated_output" if has_reference else "suppressed_ungrounded"
    )
    assert result["mode"] == "evidence_only"
    assert result["tool_calls"] == generation.tool_calls
    assert result["pending_approvals"] == generation.pending_approvals
    if has_reference:
        assert result["guardrail_result"]["status"] == "blocked"
        assert result["guardrail_result"]["decision_validation"] == "not_executed"
    else:
        assert "لم تتوفر أدلة كافية" in result["answer_ar"]


async def test_imagery_registration_uses_callers_transaction_and_failure_propagates():
    from api.imagery_automation import ImageryAutomation

    automation = ImageryAutomation()
    conn = SimpleNamespace(execute=AsyncMock())
    await automation.register_on_connection(
        conn, field_id="f1", tenant_id="t1", bbox=[44, 15, 45, 16]
    )
    args = conn.execute.call_args.args
    assert "ON CONFLICT (field_id) DO NOTHING" in args[0]
    assert args[1:] == ("f1", "t1", 44, 15, 45, 16)
    conn.execute.side_effect = RuntimeError("database unavailable")
    with pytest.raises(RuntimeError, match="database unavailable"):
        await automation.register_on_connection(
            conn, field_id="f1", tenant_id="t1", bbox=[44, 15, 45, 16]
        )


async def test_scan_recovers_registration_when_background_kick_was_lost(monkeypatch):
    from api.imagery_automation import ImageryAutomation

    automation = ImageryAutomation()
    row = {
        "field_id": "f1",
        "tenant_id": "t1",
        "bbox_west": 44,
        "bbox_south": 15,
        "bbox_east": 45,
        "bbox_north": 16,
        "last_image_id": None,
        "last_image_date": None,
        "last_indicator_job": None,
        "new_images_found": 0,
        "check_errors": 0,
    }

    @asynccontextmanager
    async def acquire():
        yield SimpleNamespace(fetch=AsyncMock(return_value=[row]))

    automation.set_pool(SimpleNamespace(acquire=acquire))
    scan = AsyncMock(return_value=(False, None))
    monkeypatch.setattr(automation, "_scan_one", scan)
    result = await automation.scan_all()
    assert result["scanned"] == 1
    assert automation._fields["f1"].tenant_id == "t1"
    assert scan.await_count == 1
