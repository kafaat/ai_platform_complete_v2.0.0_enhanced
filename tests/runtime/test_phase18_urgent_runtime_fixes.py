from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
import yaml
from fastapi import HTTPException

from api import phase_runtime_store as store

ROOT = Path(__file__).resolve().parents[2]


class FakeRequest:
    def __init__(self, *, headers: dict[str, str] | None = None, required: bool = False, pool=None):
        self.headers = headers or {}
        self.app = SimpleNamespace(state=SimpleNamespace(phase_runtime_persistence_required=required, db_pool=pool))


def test_phase_runtime_persistence_required_fails_closed_without_pool() -> None:
    request = FakeRequest(required=True)
    with pytest.raises(HTTPException) as exc:
        store._missing_runtime_dependency(request, "db_pool_missing")
    assert exc.value.status_code == 503
    assert exc.value.detail["error"] == "phase_runtime_persistence_required"


def test_phase_runtime_persistence_required_fails_closed_without_tenant() -> None:
    request = FakeRequest(required=True)
    with pytest.raises(HTTPException) as exc:
        store._tenant_required(request, None)
    assert exc.value.status_code == 400
    assert exc.value.detail["error"] == "phase_runtime_tenant_required"


def test_phase_runtime_tenant_header_is_supported() -> None:
    tenant = str(uuid4())
    request = FakeRequest(headers={"X-Tenant-Id": tenant})
    assert store.tenant_id_from_request(request) == tenant


def test_phase_runtime_worker_assets_and_compose_services_exist() -> None:
    assert (ROOT / "services/sahool-platform/api/phase_runtime_workers.py").exists()
    compose = yaml.safe_load((ROOT / "docker-compose.v9.yml").read_text(encoding="utf-8"))
    services = compose.get("services", {})
    required = {
        "sahool-phase-runtime-outbox-worker": "outbox",
        "sahool-plugin-runtime-worker": "plugin",
        "sahool-model-registry-worker": "model",
        "sahool-actuator-dispatch-worker": "actuator",
    }
    for service, kind in required.items():
        assert service in services
        assert services[service]["command"][-1] == kind
        assert "JOBS_DATABASE_URL" in services[service]["environment"]


def test_v113_worker_policy_migration_registered_and_manifest_md_mirrors_txt() -> None:
    manifest_txt = (ROOT / "migrations/MANIFEST.txt").read_text(encoding="utf-8")
    manifest_md = (ROOT / "migrations/MANIFEST.md").read_text(encoding="utf-8")
    assert "v113_phase_runtime_workers_jobs.sql" in manifest_txt
    assert "v113_phase_runtime_workers_jobs.sql" in manifest_md
    assert "Source of truth: `migrations/MANIFEST.txt`" in manifest_md  # الصياغة الفعليّة (كانت "Canonical source" بائتة)
    sql = (ROOT / "migrations/v113_phase_runtime_workers_jobs.sql").read_text(encoding="utf-8")
    assert "TO sahool_jobs" in sql
    assert "BYPASSRLS" not in sql.upper()
