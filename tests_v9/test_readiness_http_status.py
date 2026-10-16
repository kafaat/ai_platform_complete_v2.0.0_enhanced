"""READYZ-RETURNS-200-WHEN-IT-REPORTS-NOT-READY-01: HTTP probe contracts.

Mount the unchanged production handler AST on FastAPI with dependency probes
injected. This exercises routing, response status and serialization without
starting DB/Redis connections or conflating Claude's startup/auth retry work.
These are route-level unit witnesses, not deployment or lifespan evidence.
"""

from __future__ import annotations

import ast
import logging
import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
from fastapi import APIRouter, FastAPI, Response
from fastapi.testclient import TestClient

pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[1]


def _client(relative_path: str, dependencies: dict[str, Any]) -> TestClient:
    path = ROOT / relative_path
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    handler = next(
        node
        for node in tree.body
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "readyz"
    )
    app = FastAPI()
    router = APIRouter()
    namespace = {
        "app": app,
        "router": router,
        "Response": Response,
        "Any": Any,
        "os": os,
        **dependencies,
    }
    # Keep the actual route decorator and function body: assertions use real
    # ASGI responses, never the handler's spelling or a copied implementation.
    exec(compile(ast.Module(body=[handler], type_ignores=[]), str(path), "exec"), namespace)
    app.include_router(router)
    return TestClient(app)


def _decision_client(*, sor=True, misconfigured=False, auth_missing=False, db=None):
    probe = AsyncMock(return_value=db or {"db_reachable": True, "migrations_current": True})
    return (
        _client(
            "services/decision-service/main.py",
            {
                "_db_readiness": probe,
                "sor_enabled": lambda: sor,
                "sor_requested_without_db": lambda: misconfigured,
                "auth_token_missing_in_sor": lambda: auth_missing,
                "strict_worker_tenants_enabled": lambda: True,
                "LOOP_TABLES": ["decision_record"],
            },
        ),
        probe,
    )


@pytest.mark.parametrize(
    "options",
    [
        {"misconfigured": True, "sor": False},
        {"auth_missing": True},
        {"db": {"db_reachable": False, "migrations_current": True}},
        {"db": {"db_reachable": True, "migrations_current": False}},
    ],
    ids=["missing-database-config", "missing-auth", "database-down", "migrations-stale"],
)
def test_decision_rejects_unready_http_probe(options):
    client, probe = _decision_client(**options)
    response = client.get("/readyz")
    assert response.status_code == 503
    assert response.json()["ready"] is False
    assert response.json()["status"] == "degraded"
    probe.assert_awaited_once()


def test_decision_readiness_recovers_without_restarting_handler():
    client, probe = _decision_client()
    probe.side_effect = [
        {"db_reachable": True, "migrations_current": True},
        {"db_reachable": False, "migrations_current": False},
        {"db_reachable": True, "migrations_current": True},
    ]
    responses = [client.get("/readyz") for _ in range(3)]
    assert [r.status_code for r in responses] == [200, 503, 200]
    assert [r.json()["ready"] for r in responses] == [True, False, True]
    assert probe.await_count == 3


def test_decision_explicit_mirror_does_not_require_database():
    client, _ = _decision_client(sor=False, db={"db_reachable": None, "migrations_current": None})
    response = client.get("/readyz")
    assert response.status_code == 200
    assert response.json()["ready"] is True
    assert response.json()["mode"] == "interim-mirror"


def _tts_client(redis):
    state = SimpleNamespace(
        _redis=redis, logger=logging.getLogger(__name__), VOICES={"voice": object()}
    )
    return _client("services/tts-service/routers/health.py", {"main": state}), state


def test_tts_absent_redis_is_unready_then_new_connection_can_recover():
    client, state = _tts_client(None)
    unavailable = client.get("/readyz")
    state._redis = SimpleNamespace(ping=AsyncMock(return_value=True))
    recovered = client.get("/readyz")
    assert unavailable.status_code == 503
    assert unavailable.json()["ready"] is False
    assert unavailable.json()["status"] == "degraded"
    assert recovered.status_code == 200
    assert recovered.json()["ready"] is True
    assert recovered.json()["redis"] is True
    assert recovered.json()["voices_available"] == 1


def test_tts_connection_loss_and_recovery_are_reflected_in_http_status():
    redis = SimpleNamespace(ping=AsyncMock(side_effect=[True, ConnectionError("offline"), True]))
    client, _ = _tts_client(redis)
    responses = [client.get("/readyz") for _ in range(3)]
    assert [r.status_code for r in responses] == [200, 503, 200]
    assert [r.json()["redis"] for r in responses] == [True, False, True]
    assert redis.ping.await_count == 3


def test_tts_negative_ping_is_not_healthy():
    client, _ = _tts_client(SimpleNamespace(ping=AsyncMock(return_value=False)))
    response = client.get("/readyz")
    assert response.status_code == 503
    assert response.json()["redis"] is False
