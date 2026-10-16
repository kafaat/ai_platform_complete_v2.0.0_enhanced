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


@pytest.mark.asyncio
async def test_irrigation_workflow_requires_both_scope_identifiers(monkeypatch):
    mod = _load_module()
    monkeypatch.setattr(mod, "sor_enabled", lambda: True)
    with pytest.raises(HTTPException) as exc:
        await mod.review_queue(
            x_tenant_id="00000000-0000-0000-0000-000000000002", limit=20, field_id="f"
        )
    assert exc.value.status_code == 422


@pytest.mark.asyncio
async def test_irrigation_workflow_passes_scope_to_authoritative_persistence(monkeypatch):
    mod = _load_module()
    monkeypatch.setattr(mod, "sor_enabled", lambda: True)
    seen = {}

    async def fake_list(**kwargs):
        seen.update(kwargs)
        return [{"decision_id": "approved", "review_state": "approved"}]

    monkeypatch.setattr(mod, "list_review_queue", fake_list)
    out = await mod.review_queue(
        x_tenant_id="00000000-0000-0000-0000-000000000002", limit=20, field_id="f", season_id="s"
    )
    assert seen == {
        "tenant_id": "00000000-0000-0000-0000-000000000002",
        "limit": 20,
        "field_id": "f",
        "season_id": "s",
    }
    assert out["items"][0]["review_state"] == "approved"


@pytest.mark.asyncio
async def test_workflow_rehydrates_only_saved_review_and_plan_results(monkeypatch):
    import json

    import persistence

    review = {
        "decision_id": "d",
        "previous_state": "pending_approval",
        "new_state": "approved",
        "review_id": "rev",
        "reviewed_by": "u",
        "reviewed_at": "2026-10-16T00:00:00+00:00",
        "candidate_lineage_id": "lin",
        "approved_decision_value_digest": "a" * 64,
    }
    plan = {
        "execution_plan_id": "plan",
        "decision_id": "d",
        "review_id": "rev",
        "candidate_lineage_id": "lin",
        "status": "planned",
        "created_by": "u",
        "created_at": "2026-10-16T00:01:00+00:00",
        "request_hash": "b" * 64,
        "decision_value_digest": "a" * 64,
    }
    seen = {}

    class Transaction:
        async def __aenter__(self):
            pass

        async def __aexit__(self, exc_type, exc, tb):
            pass

    class Conn:
        def transaction(self):
            return Transaction()

        async def execute(self, sql, *params):
            pass

        async def fetch(self, sql, *params):
            seen.update(sql=sql, params=params)
            return [
                {
                    "decision_id": "d",
                    "decision_value": json.dumps({"season_id": "s"}),
                    "saved_review": json.dumps(review),
                    "saved_plan": json.dumps(plan),
                },
                {
                    "decision_id": "pending",
                    "decision_value": {"season_id": "s"},
                    "saved_review": None,
                    "saved_plan": None,
                },
                {
                    "decision_id": "invalid-json",
                    "decision_value": "broken",
                    "saved_review": None,
                    "saved_plan": None,
                },
                {
                    "decision_id": "array",
                    "decision_value": "[]",
                    "saved_review": None,
                    "saved_plan": None,
                },
            ]

        async def close(self):
            seen["closed"] = True

    async def connect():
        return Conn()

    monkeypatch.setattr(persistence, "_connect", connect)
    rows = await persistence.list_review_queue(
        tenant_id="tenant", limit=20, field_id="f", season_id="s"
    )
    assert seen["params"] == ("tenant", 20, "f", "s")
    assert seen["closed"] is True
    assert rows[0]["review"]["authoritative"] is True
    assert rows[0]["review"]["review_id"] == "rev"
    assert rows[0]["review"]["approved_decision_value_digest"] == "a" * 64
    assert rows[0]["execution_plan"]["execution_plan_id"] == "plan"
    assert rows[0]["execution_plan"]["plan_state"] == "planned"
    assert rows[1]["review"] is rows[1]["execution_plan"] is None
    assert rows[0]["decision_value"] == {"season_id": "s"}
    assert len(rows) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("fetch_fails", [False, True])
async def test_queue_binds_tenant_in_transaction_before_read_and_releases(monkeypatch, fetch_fails):
    import persistence

    events = []

    class Transaction:
        async def __aenter__(self):
            events.append("begin")

        async def __aexit__(self, exc_type, exc, tb):
            events.append("rollback" if exc_type else "commit")

    class Connection:
        def transaction(self):
            return Transaction()

        async def execute(self, sql, *params):
            assert events == ["begin"]
            assert sql == "SELECT set_config('app.current_tenant', $1, true)"
            assert params == ("tenant",)
            events.append("bind")

        async def fetch(self, sql, *params):
            assert events == ["begin", "bind"]
            events.append("read")
            if fetch_fails:
                raise RuntimeError("read failed")
            return []

        async def close(self):
            events.append("close")

    async def connect():
        return Connection()

    monkeypatch.setattr(persistence, "_connect", connect)
    kwargs = {"field_id": "f", "season_id": "s"}
    if fetch_fails:
        with pytest.raises(RuntimeError, match="read failed"):
            await persistence.list_review_queue(tenant_id="tenant", **kwargs)
    else:
        assert await persistence.list_review_queue(tenant_id="tenant", **kwargs) == []
    assert events == ["begin", "bind", "read", "rollback" if fetch_fails else "commit", "close"]
