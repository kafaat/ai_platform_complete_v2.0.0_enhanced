"""Execute production entrypoint contracts without optional inference dependencies."""

from __future__ import annotations

import ast
import asyncio
import inspect
import os
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Annotated

import pytest
from fastapi import FastAPI, File, Form, Header, Response, UploadFile
from fastapi.testclient import TestClient
from pydantic import TypeAdapter, ValidationError

pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[1]


def _function(relative_path, name, namespace, *, keep_decorator=False):
    path = ROOT / relative_path
    tree = ast.parse(path.read_text(encoding="utf-8"))
    node = next(n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == name)
    if not keep_decorator:
        node.decorator_list = []
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), "exec"), namespace)
    return namespace[name]


def _module_constants(relative_path, namespace):
    """Execute the literal top-level UPPER_CASE assignments (shared input limits)."""
    tree = ast.parse((ROOT / relative_path).read_text(encoding="utf-8"))
    nodes = [
        n
        for n in tree.body
        if isinstance(n, ast.Assign)
        and all(isinstance(t, ast.Name) and t.id.isupper() for t in n.targets)
        and isinstance(n.value, (ast.Constant, ast.Dict))
    ]
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(relative_path), "exec"), namespace)
    return namespace


@pytest.mark.parametrize(
    "handler,field,value",
    [
        ("detect_pest", "confidence_threshold", "2"),
        ("detect_pest", "confidence_threshold", "0"),
        ("detect_pest", "confidence_threshold", "nan"),
        ("detect_pest", "field_id", "x" * 51),
        ("detect_pest", "crop", "unsupported"),
        ("estimate_yield", "image_count", "0"),
        ("estimate_yield", "image_count", "21"),
        ("estimate_yield", "field_id", "x" * 51),
        ("estimate_yield", "growth_stage", "unsupported"),
    ],
)
def test_invalid_forms_rejected_by_request_field_validation(handler, field, value):
    namespace = {"File": File, "Form": Form, "Header": Header, "UploadFile": UploadFile}
    _module_constants("services/edge-inference/main.py", namespace)
    function = _function("services/edge-inference/main.py", handler, namespace)
    parameter = inspect.signature(function).parameters[field]
    annotation = inspect.get_annotations(function, eval_str=True)[field]
    adapter = TypeAdapter(Annotated[annotation, parameter.default])
    with pytest.raises(ValidationError):
        adapter.validate_python(value)


@pytest.mark.parametrize("ending", ["normal", "exception", "cancelled"])
def test_edge_lifespan_awaits_worker_cleanup(ending):
    async def run():
        stopped = asyncio.Event()

        async def worker():
            try:
                await asyncio.Event().wait()
            finally:
                stopped.set()

        namespace = {
            "asynccontextmanager": asynccontextmanager,
            "FastAPI": FastAPI,
            "asyncio": asyncio,
            "OFFLINE_MODE": False,
            "_periodic_sync": worker,
        }
        lifespan = _function(
            "services/edge-inference/main.py", "lifespan", namespace, keep_decorator=True
        )
        app = FastAPI()
        try:
            try:
                async with lifespan(app):
                    await asyncio.sleep(0)
                    if ending == "exception":
                        raise RuntimeError("synthetic lifespan body failure")
                    if ending == "cancelled":
                        raise asyncio.CancelledError
            except (RuntimeError, asyncio.CancelledError):
                pass
            assert app.state.sync_task.done()
            assert stopped.is_set()
        finally:
            app.state.sync_task.cancel()
            await asyncio.gather(app.state.sync_task, return_exceptions=True)

    asyncio.run(run())


@pytest.mark.parametrize(
    "production,scientific_ready,status",
    [(True, False, 503), (True, True, 200), (False, False, 200)],
)
def test_agriai_readiness_http_status(monkeypatch, production, scientific_ready, status):
    monkeypatch.setenv("AGRIAI_PRODUCTION_MODE", "1" if production else "0")
    app = FastAPI()
    namespace = {
        "app": app,
        "Response": Response,
        "os": os,
        "wa": SimpleNamespace(
            scientific_path_status=lambda: {"scientific_ready": scientific_ready}
        ),
    }
    _function("services/agriai-engine/main.py", "readyz", namespace, keep_decorator=True)
    response = TestClient(app).get("/readyz")
    assert response.status_code == status
    assert response.json()["ready"] is (status == 200)
