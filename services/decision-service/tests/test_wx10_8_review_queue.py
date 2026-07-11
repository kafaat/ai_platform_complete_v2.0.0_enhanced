from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest
from fastapi import HTTPException

# decision-service main.py lives one level up from this tests/ dir. This runs in the
# Decision Service Tests CI job (which installs fastapi + pytest-asyncio); it monkeypatches
# sor_enabled/list_review_queue so it needs no database.
MODULE_PATH = Path(__file__).resolve().parents[1] / "main.py"


def _load_module():
    service_dir = str(MODULE_PATH.parent)
    if service_dir not in sys.path:
        sys.path.insert(0, service_dir)
    spec = importlib.util.spec_from_file_location("decision_service_main_wx108", MODULE_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.asyncio
async def test_review_queue_is_authoritative_and_tenant_scoped(monkeypatch):
    mod = _load_module()
    seen = {}

    monkeypatch.setattr(mod, "sor_enabled", lambda: True)

    async def fake_list(*, tenant_id: str, limit: int):
        seen.update(tenant_id=tenant_id, limit=limit)
        return [{"decision_id": "dec_1", "review_state": "pending_approval"}]

    monkeypatch.setattr(mod, "list_review_queue", fake_list)
    out = await mod.review_queue(x_tenant_id="00000000-0000-0000-0000-000000000002", limit=20)
    assert out == {
        "authoritative": True,
        "persisted": True,
        "items": [{"decision_id": "dec_1", "review_state": "pending_approval"}],
        "count": 1,
    }
    assert seen == {
        "tenant_id": "00000000-0000-0000-0000-000000000002",
        "limit": 20,
    }


@pytest.mark.asyncio
async def test_review_queue_fails_closed_in_mirror_mode(monkeypatch):
    mod = _load_module()
    monkeypatch.setattr(mod, "sor_enabled", lambda: False)
    with pytest.raises(HTTPException) as exc:
        await mod.review_queue(x_tenant_id="00000000-0000-0000-0000-000000000002", limit=20)
    assert exc.value.status_code == 503
