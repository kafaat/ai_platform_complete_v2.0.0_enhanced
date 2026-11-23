"""Recommendation → work order → field task → outcome, over HTTP against a live Postgres (G3).

F-D06: POST /api/v1/work-orders/from-recommendation writes a `work_orders` row (status planned,
field ownership checked) and answers its id, but no `field_tasks` row follows: the work order
never reaches the task list the field crew works from. The fix is an explicit, tenant-scoped,
idempotent step behind WORK_ORDER_FIELD_TASK_LINK_ENABLED (off by default): with the flag off a
request for the task writes nothing and says so; with it on, one task per work order, linked from
the work order (payload.field_task_id) next to its recommendation_id and decision_id.

F-D09: PATCH /api/v1/tasks/{id} with status=completed closes the task and nothing records what
happened in the field, attributed to the recommendation or decision. An administrative close is
not agronomic verification: an outcome is recorded only from an explicit result with its
evidence reference, on the work order the task came from, and the close answer says whether an
outcome was recorded. The work order is never moved to `verified` by a close.

The platform app runs in-process over ASGI, against a migrated Postgres through a NOBYPASSRLS
role (RLS applies). Only the users rows are seeded by the schema owner.
"""

from __future__ import annotations

import asyncio
import importlib
import json
import os
import sys
import uuid
from pathlib import Path

import pytest

pytestmark = [pytest.mark.integration]

# Switch read before any import (test_certification_switch_precedes_importorskip): on the
# certifying CI step a missing dependency or an unusable database fails the run, not a skip.
_CERTIFICATION_REQUIRED = os.getenv("WORK_ORDER_FIELD_TASK_LINK_CERTIFICATION_REQUIRED") == "1"


def _require(module: str):
    """Import ``module``; under the certification switch a missing one fails the run."""
    if _CERTIFICATION_REQUIRED:
        return importlib.import_module(module)
    return pytest.importorskip(module)


asyncpg = _require("asyncpg")
httpx = _require("httpx")
_require("fastapi")

ROOT = Path(__file__).resolve().parents[1]
PLATFORM = ROOT / "services" / "sahool-platform"
# The module connects as the schema owner and creates its own throwaway NOBYPASSRLS role for the
# request path. On its certifying CI step the owner comes from TEST_DATABASE_ADMIN_URL, so the
# step's TEST_DATABASE_URL never names a privileged role.
DSN = os.getenv("TEST_DATABASE_ADMIN_URL") or os.getenv(
    "TEST_DATABASE_URL", "postgresql://sahool_test:test_password@127.0.0.1:5433/sahool_test"
)
RING = [[44.200, 15.300], [44.204, 15.300], [44.204, 15.304], [44.200, 15.304], [44.200, 15.300]]
FLAG = "WORK_ORDER_FIELD_TASK_LINK_ENABLED"


async def _probe() -> str:
    try:
        conn = await asyncpg.connect(DSN, timeout=5)
    except Exception as exc:  # noqa: BLE001 - any failure means "no database here"
        return f"{type(exc).__name__}: {exc}"
    try:
        for table in ("work_orders", "field_tasks", "fields", "farms", "users"):
            if await conn.fetchval("SELECT to_regclass($1)", f"public.{table}") is None:
                return f"schema not migrated ({table} missing)"
    finally:
        await conn.close()
    return ""


_WHY = asyncio.run(_probe())
if _WHY and _CERTIFICATION_REQUIRED:
    raise RuntimeError(
        f"WORK_ORDER_FIELD_TASK_LINK_CERTIFICATION_REQUIRED=1 but the live database is unusable: {_WHY}"
    )
pytestmark.append(pytest.mark.skipif(bool(_WHY), reason=f"declared skip (not a pass): {_WHY}"))


def _platform():
    if str(PLATFORM) not in sys.path:
        sys.path.insert(0, str(PLATFORM))
    import api.main as main
    from api.routers import fields as fields_router

    return main, fields_router


class _World:
    """Two tenants, each with a manager and a field; the app wired to a NOBYPASSRLS pool."""

    def __init__(self, main, owner, pool, role, client):
        self.main, self.owner, self.pool, self.role, self.client = main, owner, pool, role, client
        self.tenants: dict[str, str] = {}
        self.fields: dict[str, str] = {}
        self.users: dict[str, int] = {}
        self.acting: dict = {"user": None}

    def act_as(self, tenant_key: str, user_role=None):
        from core.canonical_schemas import UserRole, UserSchema

        self.acting["user"] = UserSchema(
            user_id=str(self.users.get(tenant_key, 0)),
            tenant_id=self.tenants[tenant_key],
            role=user_role or UserRole.MANAGER,
            name_ar="u",
        )
        return self.acting["user"]

    async def tasks_of(self, tenant_key: str) -> list:
        return await self.owner.fetch(
            "SELECT task_id::text AS task_id, field_id, task_type, status FROM field_tasks"
            " WHERE tenant_id = $1::uuid",
            self.tenants[tenant_key],
        )

    async def work_order(self, work_order_id: str):
        row = await self.owner.fetchrow(
            "SELECT status, recommendation_id, payload::text AS payload FROM work_orders"
            " WHERE work_order_id::text = $1",
            work_order_id,
        )
        return None if row is None else {**dict(row), "payload": json.loads(row["payload"])}

    async def create_work_order(self, tenant_key: str, **extra) -> httpx.Response:
        self.act_as(tenant_key)
        body = {
            "field_id": self.fields[tenant_key],
            "recommendation": {
                "id": f"rec-{uuid.uuid4().hex[:8]}",
                "decision_id": f"dec_{uuid.uuid4().hex[:12]}",
                "action": "irrigation",
            },
        }
        headers = extra.pop("headers", None)
        body.update(extra)
        return await self.client.post(
            "/api/v1/work-orders/from-recommendation", json=body, headers=headers
        )


async def _with_world(monkeypatch, scenario):
    main, fields_router = _platform()
    from core.canonical_schemas import UserRole

    owner = await asyncpg.connect(DSN)
    role = None
    if await owner.fetchval(
        "SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname = current_user"
    ):
        role = f"g3_rls_{uuid.uuid4().hex[:10]}"
        await owner.execute(
            f'CREATE ROLE "{role}" NOLOGIN NOSUPERUSER NOBYPASSRLS;'
            f'GRANT USAGE ON SCHEMA public TO "{role}";'
            f'GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO "{role}";'
            f'GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO "{role}";'
            f'GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO "{role}";'
        )

    async def setup(conn):
        if role:
            await conn.execute(f'SET ROLE "{role}"')

    pool = await asyncpg.create_pool(DSN, min_size=1, max_size=4, setup=setup)
    monkeypatch.setattr(main, "_DB_POOL", pool)
    # The per-client minute window is shared by every test in the process; this journey
    # must not spend it for the live tests that follow (as test_farm_access_scope_live_pg).
    monkeypatch.setattr(main, "_RATE_LIMIT_PER_MIN", 0, raising=False)

    async def no_imagery(**_kwargs):
        return None

    monkeypatch.setattr(fields_router, "_kick_imagery_processing", no_imagery)
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=main.app, raise_app_exceptions=False),
            base_url="http://platform",
            timeout=60,
        ) as client:
            world = _World(main, owner, pool, role, client)
            main.app.dependency_overrides[main.get_current_user] = lambda: world.acting["user"]
            for key in ("a", "b"):
                world.tenants[key] = str(uuid.uuid4())
                world.users[key] = await owner.fetchval(
                    "INSERT INTO users (email, password_hash, full_name, role, tenant_id, active)"
                    " VALUES ($1, 'x', 'manager', 'manager', $2::uuid, true) RETURNING id",
                    f"g3.{uuid.uuid4().hex[:8]}@example.org",
                    world.tenants[key],
                )
                world.act_as(key, UserRole.OWNER)
                farm = await client.post("/api/v1/farms", json={"name": "مزرعة"})
                assert farm.status_code == 201, farm.text
                world.act_as(key)
                field = await client.post(
                    "/api/v1/fields",
                    json={
                        "name": "حقل",
                        "crop": "wheat",
                        "farm_id": farm.json().get("farm_id"),
                        "geometry": {"type": "Polygon", "coordinates": [RING]},
                    },
                )
                assert field.status_code == 201, field.text
                world.fields[key] = field.json()["field_id"]
            return await scenario(world)
    finally:
        main.app.dependency_overrides.pop(main.get_current_user, None)
        await pool.close()
        try:
            for tenant in world.tenants.values() if "world" in locals() else ():
                for table in ("field_tasks", "work_orders", "fields", "farms", "users"):
                    await owner.execute(f"DELETE FROM {table} WHERE tenant_id = $1::uuid", tenant)
        finally:
            if role:
                await owner.execute(f'DROP OWNED BY "{role}"; DROP ROLE "{role}"')
            await owner.close()


def _run(monkeypatch, scenario):
    return asyncio.run(_with_world(monkeypatch, scenario))


# ── F-D06 ────────────────────────────────────────────────────────────────────────────


def test_flag_on_turns_the_work_order_into_one_linked_field_task(monkeypatch):
    monkeypatch.setenv(FLAG, "1")

    async def scenario(w: _World):
        resp = await w.create_work_order("a", create_field_task=True)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["persisted"] is True and body["work_order_id"], body
        assert body["field_task"]["created"] is True, body
        task_id = body["field_task"]["task_id"]
        tasks = await w.tasks_of("a")
        assert [(t["task_id"], t["field_id"], t["task_type"], t["status"]) for t in tasks] == [
            (task_id, w.fields["a"], "irrigation", "pending")
        ]
        wo = await w.work_order(body["work_order_id"])
        rec = body["work_order"]
        # The identifier chain: recommendation → decision → work order → task.
        assert wo["status"] == "planned"
        assert wo["recommendation_id"] == rec["recommendation_id"]
        assert wo["payload"]["decision_id"] == rec["payload"]["decision_id"]
        assert wo["payload"]["field_task_id"] == task_id
        assert body["chain"] == {
            "recommendation_id": rec["recommendation_id"],
            "decision_id": rec["payload"]["decision_id"],
            "work_order_id": body["work_order_id"],
            "task_id": task_id,
        }

    _run(monkeypatch, scenario)


def test_flag_off_writes_no_task_and_says_so(monkeypatch):
    monkeypatch.delenv(FLAG, raising=False)

    async def scenario(w: _World):
        resp = await w.create_work_order("a", create_field_task=True)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["persisted"] is True, body
        assert body["field_task"] == {
            "requested": True,
            "created": False,
            "replayed": False,
            "task_id": None,
            "reason": "disabled",
        }
        assert await w.tasks_of("a") == []
        wo = await w.work_order(body["work_order_id"])
        assert "field_task_id" not in wo["payload"]

    _run(monkeypatch, scenario)


def test_the_task_step_is_idempotent_per_work_order(monkeypatch):
    monkeypatch.setenv(FLAG, "1")

    async def scenario(w: _World):
        key = str(uuid.uuid4())
        first = await w.create_work_order(
            "a", create_field_task=True, headers={"Idempotency-Key": key}
        )
        assert first.status_code == 200, first.text
        # Same Idempotency-Key ⇒ the same work order; the task step replays its link.
        body = first.json()
        again = await w.client.post(
            "/api/v1/work-orders/from-recommendation",
            json={
                "field_id": w.fields["a"],
                "recommendation": {
                    "id": body["work_order"]["recommendation_id"],
                    "decision_id": body["work_order"]["payload"]["decision_id"],
                    "action": "irrigation",
                },
                "create_field_task": True,
            },
            headers={"Idempotency-Key": key},
        )
        assert again.status_code == 200, again.text
        second = again.json()
        assert second["work_order_id"] == body["work_order_id"]
        assert second["field_task"]["task_id"] == body["field_task"]["task_id"]
        assert second["field_task"]["created"] is False
        assert second["field_task"]["replayed"] is True
        # And the step called directly, twice, concurrently, still writes one task.
        from api.routers.tasks import create_field_task_from_work_order

        user = w.act_as("a")
        results = await asyncio.gather(
            create_field_task_from_work_order(user, body["work_order_id"]),
            create_field_task_from_work_order(user, body["work_order_id"]),
        )
        assert {r["task_id"] for r in results} == {body["field_task"]["task_id"]}
        assert len(await w.tasks_of("a")) == 1

    _run(monkeypatch, scenario)


def test_another_tenant_cannot_create_a_task_from_the_work_order(monkeypatch):
    monkeypatch.setenv(FLAG, "1")

    async def scenario(w: _World):
        resp = await w.create_work_order("a")  # no task requested
        assert resp.status_code == 200, resp.text
        assert resp.json()["field_task"]["reason"] == "not_requested"
        wo_id = resp.json()["work_order_id"]
        from api.routers.tasks import create_field_task_from_work_order
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as refused:
            await create_field_task_from_work_order(w.act_as("b"), wo_id)
        assert refused.value.status_code == 404
        # Tenant B naming tenant A's field is refused before anything is written.
        w.act_as("b")
        cross = await w.client.post(
            "/api/v1/work-orders/from-recommendation",
            json={
                "field_id": w.fields["a"],
                "recommendation": {"id": "rec-x", "action": "irrigation"},
                "create_field_task": True,
            },
        )
        assert cross.status_code == 404, cross.text
        assert await w.tasks_of("a") == [] and await w.tasks_of("b") == []
        assert "field_task_id" not in (await w.work_order(wo_id))["payload"]

    _run(monkeypatch, scenario)


# ── F-D09 ────────────────────────────────────────────────────────────────────────────


async def _linked_task(w: _World) -> tuple[str, str]:
    """A work order from the real route, and a task linked to it as F-D06 links one.

    The link is seeded by the schema owner (field_tasks row + work_orders.payload.field_task_id)
    so that these close tests measure the close path alone, not the creation step.
    """
    resp = await w.create_work_order("a")
    assert resp.status_code == 200, resp.text
    wo_id = resp.json()["work_order_id"]
    assert wo_id, resp.text
    task_id = await w.owner.fetchval(
        "INSERT INTO field_tasks (tenant_id, field_id, task_type) VALUES ($1::uuid, $2,"
        " 'irrigation') RETURNING task_id::text",
        w.tenants["a"],
        w.fields["a"],
    )
    await w.owner.execute(
        "UPDATE work_orders SET payload = payload || jsonb_build_object('field_task_id', $2::text)"
        " WHERE work_order_id::text = $1",
        wo_id,
        task_id,
    )
    w.act_as("a")
    return wo_id, task_id


def test_an_administrative_close_records_no_outcome_and_says_so(monkeypatch):
    monkeypatch.setenv(FLAG, "1")

    async def scenario(w: _World):
        wo_id, task_id = await _linked_task(w)
        closed = await w.client.patch(f"/api/v1/tasks/{task_id}", json={"status": "completed"})
        assert closed.status_code == 200, closed.text
        assert closed.json()["status"] == "completed"
        assert closed.json()["outcome_recorded"] is False
        assert closed.json()["outcome_reason"] == "no_result_supplied"
        wo = await w.work_order(wo_id)
        assert "outcome" not in wo["payload"]
        assert wo["status"] == "planned"  # a close never verifies the work order

    _run(monkeypatch, scenario)


def test_a_close_with_result_and_evidence_records_an_attributed_outcome(monkeypatch):
    monkeypatch.setenv(FLAG, "1")

    async def scenario(w: _World):
        wo_id, task_id = await _linked_task(w)
        body = {
            "status": "completed",
            "outcome_result": "achieved",
            "outcome_evidence_ref": "photo:ev-123",
        }
        closed = await w.client.patch(f"/api/v1/tasks/{task_id}", json=body)
        assert closed.status_code == 200, closed.text
        assert closed.json()["outcome_recorded"] is True, closed.json()
        assert closed.json()["outcome_reason"] == "recorded"
        wo = await w.work_order(wo_id)
        outcome = wo["payload"]["outcome"]
        assert outcome["result"] == "achieved"
        assert outcome["evidence_ref"] == "photo:ev-123"
        assert outcome["task_id"] == task_id
        assert outcome["recommendation_id"] == wo["recommendation_id"]
        assert outcome["decision_id"] == wo["payload"]["decision_id"]
        assert outcome["verified"] is False
        assert wo["status"] == "planned"  # recorded, not verified on anyone's behalf
        # Repeating the same close is a replay: same outcome, nothing rewritten.
        again = await w.client.patch(f"/api/v1/tasks/{task_id}", json=body)
        assert again.status_code == 200, again.text
        assert again.json()["outcome_recorded"] is True
        assert again.json()["outcome_reason"] == "already_recorded"
        assert (await w.work_order(wo_id))["payload"]["outcome"] == outcome
        # A different result for an outcome already recorded is a conflict, not an overwrite.
        other = await w.client.patch(
            f"/api/v1/tasks/{task_id}", json={**body, "outcome_result": "not_achieved"}
        )
        assert other.status_code == 409, other.text
        assert (await w.work_order(wo_id))["payload"]["outcome"] == outcome

    _run(monkeypatch, scenario)


def test_a_result_without_evidence_is_refused(monkeypatch):
    monkeypatch.setenv(FLAG, "1")

    async def scenario(w: _World):
        wo_id, task_id = await _linked_task(w)
        refused = await w.client.patch(
            f"/api/v1/tasks/{task_id}", json={"status": "completed", "outcome_result": "achieved"}
        )
        assert refused.status_code == 422, refused.text
        assert "outcome" not in (await w.work_order(wo_id))["payload"]
        assert [t["status"] for t in await w.tasks_of("a")] == ["pending"]

    _run(monkeypatch, scenario)


def test_flag_off_records_no_outcome_even_with_evidence(monkeypatch):
    monkeypatch.setenv(FLAG, "1")

    async def scenario(w: _World):
        wo_id, task_id = await _linked_task(w)
        monkeypatch.delenv(FLAG)
        closed = await w.client.patch(
            f"/api/v1/tasks/{task_id}",
            json={
                "status": "completed",
                "outcome_result": "achieved",
                "outcome_evidence_ref": "photo:ev-1",
            },
        )
        assert closed.status_code == 200, closed.text
        assert closed.json()["outcome_recorded"] is False
        assert closed.json()["outcome_reason"] == "disabled"
        assert "outcome" not in (await w.work_order(wo_id))["payload"]

    _run(monkeypatch, scenario)


def test_a_generic_task_close_has_nothing_to_attribute(monkeypatch):
    monkeypatch.setenv(FLAG, "1")

    async def scenario(w: _World):
        task_id = await w.owner.fetchval(
            "INSERT INTO field_tasks (tenant_id, field_id, task_type) VALUES ($1::uuid, $2,"
            " 'scouting') RETURNING task_id::text",
            w.tenants["a"],
            w.fields["a"],
        )
        w.act_as("a")
        closed = await w.client.patch(
            f"/api/v1/tasks/{task_id}",
            json={
                "status": "completed",
                "outcome_result": "achieved",
                "outcome_evidence_ref": "photo:ev-2",
            },
        )
        assert closed.status_code == 200, closed.text
        assert closed.json()["outcome_recorded"] is False
        assert closed.json()["outcome_reason"] == "no_linked_work_order"

    _run(monkeypatch, scenario)
