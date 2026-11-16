"""W3-12: service tokens that only fail at request time are required in production and visible.

``TASK_SERVICE_CALLBACK_TOKEN`` (field-task verification callback into vegetation-analysis),
``SCOUT_MEDIA_SERVICE_TOKEN`` (scouting media) and ``EDGE_SYNC_TOKEN`` (edge sync) defaulted to
empty in compose; the services started and the endpoints answered 503 when first called. The
production compose preflight now refuses to start without them, and the two services' /readyz
report the booleans (never a value) without changing readiness.
"""

from __future__ import annotations

import ast
import os
import re
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = (
    "TASK_SERVICE_CALLBACK_TOKEN",
    "SCOUT_MEDIA_SERVICE_TOKEN",
    "EDGE_SYNC_TOKEN",
    # The plan row's "tasks" token: the gateway's field-task route credential.
    "FIELD_TASKS_SERVICE_TOKEN",
)


READYZ = {
    "services/vegetation-analysis-service/routers/health.py": ("TASK_SERVICE_CALLBACK_TOKEN",),
    "services/scout-ingest-service/main.py": (
        "SCOUT_MEDIA_SERVICE_TOKEN",
        "SCOUT_INGEST_READ_TOKEN",
    ),
}


def _service_tokens_expr(source: str) -> ast.expr:
    """The real ``"service_tokens"`` value inside the service's ``readyz`` function.

    Service-local on purpose: a shared/ module would make Railway rebuild every service that
    watches shared/ for a two-line readiness field.
    """
    tree = ast.parse((ROOT / source).read_text(encoding="utf-8"))
    fn = next(
        n
        for n in ast.walk(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == "readyz"
    )
    for node in ast.walk(fn):
        if isinstance(node, ast.Dict):
            for key, value in zip(node.keys, node.values, strict=True):
                if isinstance(key, ast.Constant) and key.value == "service_tokens":
                    return value
    raise AssertionError(f"{source}: readyz has no service_tokens field")


def _evaluate(source: str) -> dict:
    expr = ast.Expression(_service_tokens_expr(source))
    return eval(compile(expr, source, "eval"), {"os": os})  # noqa: S307 - repo source


def test_the_production_preflight_requires_each_token():
    prod = yaml.safe_load((ROOT / "docker-compose.production.yml").read_text(encoding="utf-8"))
    env = prod["services"]["production-preflight"]["environment"]
    for name in REQUIRED:
        assert re.fullmatch(rf"\$\{{{name}:\?[^}}]+\}}", env[name]), (name, env.get(name))


@pytest.mark.parametrize(("source", "names"), sorted(READYZ.items()))
def test_readyz_reports_booleans_and_never_a_value(monkeypatch, source, names):
    first, *rest = names
    monkeypatch.setenv(first, "s3cret-value")
    for name in rest:
        monkeypatch.setenv(name, "")
    result = _evaluate(source)
    assert result == {first: True, **{name: False for name in rest}}
    assert all(type(v) is bool for v in result.values())
    assert "s3cret-value" not in repr(result)
    monkeypatch.delenv(first)
    assert _evaluate(source)[first] is False


def test_the_readiness_field_does_not_touch_shared():
    assert not (ROOT / "shared/security/service_token_status.py").exists()
    for source in READYZ:
        assert "service_token_status" not in (ROOT / source).read_text(encoding="utf-8"), source


@pytest.mark.parametrize(("source", "names"), sorted(READYZ.items()))
def test_readyz_reports_the_tokens_its_endpoints_need(source, names):
    expr = _service_tokens_expr(source)
    named = {n.value for n in ast.walk(expr) if isinstance(n, ast.Constant)}
    assert set(names) == named, (source, named)


def test_edge_readiness_already_reports_its_sync_token():
    text = (ROOT / "services/edge-inference/main.py").read_text(encoding="utf-8")
    assert '"sync_token_configured": bool(os.getenv("EDGE_SYNC_TOKEN"))' in text


def test_the_field_tasks_token_is_the_one_the_gateway_injects_and_the_service_checks():
    conf = (ROOT / "nginx/nginx.v9.conf").read_text(encoding="utf-8")
    assert 'proxy_set_header X-Field-Tasks-Token "${FIELD_TASKS_SERVICE_TOKEN}";' in conf
    gateway = (ROOT / "services/field-management-service/fm_gateway.py").read_text(encoding="utf-8")
    assert 'os.getenv("FIELD_TASKS_SERVICE_TOKEN", "")' in gateway
