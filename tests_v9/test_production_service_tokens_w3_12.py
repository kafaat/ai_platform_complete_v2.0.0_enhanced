"""W3-12: service tokens that only fail at request time are required in production and visible.

``TASK_SERVICE_CALLBACK_TOKEN`` (field-task verification callback into vegetation-analysis),
``SCOUT_MEDIA_SERVICE_TOKEN`` (scouting media) and ``EDGE_SYNC_TOKEN`` (edge sync) defaulted to
empty in compose; the services started and the endpoints answered 503 when first called. The
production compose preflight now refuses to start without them, and the two services' /readyz
report the booleans (never a value) without changing readiness.
"""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = ("TASK_SERVICE_CALLBACK_TOKEN", "SCOUT_MEDIA_SERVICE_TOKEN", "EDGE_SYNC_TOKEN")


def _helper():
    path = ROOT / "shared/security/service_token_status.py"
    spec = importlib.util.spec_from_file_location("_w312_service_token_status", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module.service_token_status


def test_the_production_preflight_requires_each_token():
    prod = yaml.safe_load((ROOT / "docker-compose.production.yml").read_text(encoding="utf-8"))
    env = prod["services"]["production-preflight"]["environment"]
    for name in REQUIRED:
        assert re.fullmatch(rf"\$\{{{name}:\?[^}}]+\}}", env[name]), (name, env.get(name))


def test_status_reports_booleans_and_never_a_value(monkeypatch):
    status = _helper()
    monkeypatch.setenv("TASK_SERVICE_CALLBACK_TOKEN", "s3cret-value")
    monkeypatch.setenv("SCOUT_MEDIA_SERVICE_TOKEN", "")
    monkeypatch.delenv("EDGE_SYNC_TOKEN", raising=False)
    result = status(REQUIRED)
    assert result == {
        "TASK_SERVICE_CALLBACK_TOKEN": True,
        "SCOUT_MEDIA_SERVICE_TOKEN": False,
        "EDGE_SYNC_TOKEN": False,
    }
    assert "s3cret-value" not in repr(result)


@pytest.mark.parametrize(
    ("source", "names"),
    [
        (
            "services/vegetation-analysis-service/routers/health.py",
            ("TASK_SERVICE_CALLBACK_TOKEN",),
        ),
        (
            "services/scout-ingest-service/main.py",
            ("SCOUT_MEDIA_SERVICE_TOKEN", "SCOUT_INGEST_READ_TOKEN"),
        ),
    ],
)
def test_readyz_reports_the_tokens_its_endpoints_need(source, names):
    text = (ROOT / source).read_text(encoding="utf-8")
    readyz = text[text.index('"/readyz")') :]
    readyz = readyz[: readyz.index("\n\n\n")] if "\n\n\n" in readyz else readyz
    assert '"service_tokens": service_token_status(' in readyz
    for name in names:
        assert f'"{name}"' in readyz


def test_edge_readiness_already_reports_its_sync_token():
    text = (ROOT / "services/edge-inference/main.py").read_text(encoding="utf-8")
    assert '"sync_token_configured": bool(os.getenv("EDGE_SYNC_TOKEN"))' in text
