"""An inspection approval covers one evidence version; a worker links a receipt (live PG, v256).

These were fakes in services/sahool-platform/tests/test_inspection_evidence_version.py: a
connection stand-in answered each query by substring, so the gate was measured against the
answers the test wrote, not against the tables. Here the real routes run over HTTP into the
platform app, on a migrated Postgres, through a NOBYPASSRLS role:

1. a pin inspection task is assigned, accepted, submitted with photo 1 and approved (v1);
2. the task update path changes the photo: v1 stays the approved version, v2 is appended and
   pending, and closing is refused (also when the same request changes the photo);
3. once v2 is submitted and approved, the task closes;
4. a worker links a farm-book expense to the task (activity:execute): one task_expense_links
   row, linked_by the worker.

The permission refusals that never reach the database stay as unit tests in that file.
"""

from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

pytestmark = [pytest.mark.integration]

asyncpg = pytest.importorskip("asyncpg")
httpx = pytest.importorskip("httpx")
pytest.importorskip("fastapi")

ROOT = Path(__file__).resolve().parents[1]
PLATFORM = ROOT / "services" / "sahool-platform"
DSN = os.getenv(
    "TEST_DATABASE_URL", "postgresql://sahool_test:test_password@127.0.0.1:5433/sahool_test"
)
RING = [[44.200, 15.300], [44.204, 15.300], [44.204, 15.304], [44.200, 15.304], [44.200, 15.300]]
P1 = "https://evidence.example/visit/photo-1.jpg"
P2 = "https://evidence.example/visit/photo-2.jpg"
NOTES = "اصفرار في الطرف"
_TABLES = (
    "field_tasks",
    "fields",
    "farms",
    "scouting_pins",
    "users",
    "inspection_handoffs",
    "inspection_evidence_versions",
    "task_expense_links",
    "farm_ledger_entries",
)


async def _probe() -> str:
    try:
        conn = await asyncpg.connect(DSN, timeout=5)
    except Exception as exc:  # noqa: BLE001 - any failure means "no database here"
        return f"{type(exc).__name__}: {exc}"
    try:
        for table in _TABLES:
            if await conn.fetchval("SELECT to_regclass($1)", f"public.{table}") is None:
                return f"schema not migrated ({table} missing)"
    finally:
        await conn.close()
    return ""


_WHY = asyncio.run(_probe())
pytestmark.append(pytest.mark.skipif(bool(_WHY), reason=f"declared skip (not a pass): {_WHY}"))


def _platform():
    if str(PLATFORM) not in sys.path:
        sys.path.insert(0, str(PLATFORM))
    import api.main as main
    from api.routers import fields as fields_router

    return main, fields_router


async def _scenario(monkeypatch) -> dict:
    main, fields_router = _platform()
    from core.canonical_schemas import UserRole, UserSchema

    tenant = str(uuid.uuid4())
    owner = await asyncpg.connect(DSN)
    role = None
    if await owner.fetchval(
        "SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname = current_user"
    ):
        role = f"iev_rls_{uuid.uuid4().hex[:10]}"
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

    async def no_imagery(**_kwargs):  # field creation queues Sentinel work on other services
        return None

    monkeypatch.setattr(fields_router, "_kick_imagery_processing", no_imagery)
    roles = {
        "owner": UserRole.OWNER,
        "manager": UserRole.MANAGER,
        "worker": UserRole.WORKER,
        "agronomist": UserRole.AGRONOMIST,
    }
    ids = {}
    for name in roles:
        ids[name] = await owner.fetchval(
            "INSERT INTO users (email, password_hash, full_name, role, tenant_id, active)"
            " VALUES ($1, 'x', $2, $2, $3::uuid, true) RETURNING id",
            f"{name}.{uuid.uuid4().hex[:8]}@example.org",
            name,
            tenant,
        )
    acting = {"user": None}
    main.app.dependency_overrides[main.get_current_user] = lambda: acting["user"]
    out: dict = {}

    async def versions(task_id):
        return await owner.fetch(
            "SELECT version, photo_url, notes FROM inspection_evidence_versions"
            " WHERE tenant_id=$1::uuid AND task_id=$2::uuid ORDER BY version",
            tenant,
            task_id,
        )

    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=main.app, raise_app_exceptions=False),
            base_url="http://platform",
            timeout=60,
        ) as client:

            async def call(name, verb, path, body=None):
                acting["user"] = UserSchema(
                    user_id=str(ids[name]), tenant_id=tenant, role=roles[name], name_ar="u"
                )
                return await client.request(verb, path, json=body)

            farm = (await call("owner", "POST", "/api/v1/farms", {"name": "مزرعة"})).json()
            field = await call(
                "manager",
                "POST",
                "/api/v1/fields",
                {
                    "name": "حقل",
                    "crop": "wheat",
                    "farm_id": farm["farm_id"],
                    "geometry": {"type": "Polygon", "coordinates": [RING]},
                },
            )
            assert field.status_code == 201, field.text
            fid = field.json()["field_id"]
            pin = f"pin-{uuid.uuid4().hex[:8]}"
            made = await call(
                "worker",
                "POST",
                f"/api/v1/fields/{fid}/pins",
                {
                    "pin_id": pin,
                    "field_id": fid,
                    "lat": 15.302,
                    "lng": 44.202,
                    "issue_category": "pest",
                    "severity": "high",
                },
            )
            assert made.status_code in (200, 201), made.text
            due = (datetime.now(UTC) + timedelta(days=1)).isoformat()
            assigned = await call(
                "manager",
                "POST",
                f"/api/v1/fields/{fid}/pins/{pin}/inspection-task",
                {"assigned_to": ids["worker"], "due_at": due, "priority": 2},
            )
            assert assigned.status_code == 200, assigned.text
            task = assigned.json()["task"]["task_id"]
            handoff = f"/api/v1/fields/{fid}/tasks/{task}/handoff"

            async def step(name, action, body):
                r = await call(name, "POST", handoff + action, body)
                assert r.status_code == 200, (action, body, r.text)
                return r.json()

            await step("worker", "/accept", {"expected_revision": 0})
            submit = {"expected_revision": 1, "action": "submit", "reason": "رصد"}
            await step("worker", "/finding", submit | {"photo_url": P1, "notes": NOTES})
            approved = await step(
                "agronomist",
                "/finding",
                {"expected_revision": 2, "action": "approve", "reason": "ok"},
            )
            out["approved_v1"] = approved["approved_evidence"]["version"]

            changed = await call("manager", "PATCH", f"/api/v1/tasks/{task}", {"photo_url": P2})
            out["photo_change"] = changed.status_code
            view = (await call("manager", "GET", handoff)).json()
            out["after_change"] = (
                view["approved_evidence"]["photo_url"],
                view["current_evidence"]["photo_url"],
                view["current_evidence"]["version"],
                view["evidence_pending_review"],
                view["evidence_approved"],
            )
            stored_before = len(await versions(task))
            close = {"status": "completed"}
            out["close_on_unapproved"] = (
                await call("manager", "PATCH", f"/api/v1/tasks/{task}", close)
            ).status_code
            out["close_with_photo_change"] = (
                await call("manager", "PATCH", f"/api/v1/tasks/{task}", close | {"photo_url": P1})
            ).status_code
            out["versions_unchanged_by_refusals"] = len(await versions(task)) == stored_before
            out["status_after_refusals"] = await owner.fetchval(
                "SELECT status FROM field_tasks WHERE task_id=$1::uuid", task
            )

            resubmitted = await step(
                "worker", "/finding", {"expected_revision": 3, "action": "submit", "reason": "صورة"}
            )
            out["resubmit_binds"] = resubmitted["events"][-1]["evidence_version"]
            await step(
                "agronomist",
                "/finding",
                {"expected_revision": 4, "action": "approve", "reason": "v2"},
            )
            out["close_on_approved"] = (
                await call("manager", "PATCH", f"/api/v1/tasks/{task}", close)
            ).status_code
            out["history"] = [(v["version"], v["photo_url"]) for v in await versions(task)]

            entry = await call(
                "manager",
                "POST",
                "/api/v1/farm-book/entries",
                {
                    "client_operation_id": f"iev-{uuid.uuid4().hex}",
                    "entry_type": "expense",
                    "category": "labor",
                    "amount": "250",
                    "occurred_on": date(2026, 11, 12).isoformat(),
                    "farm_id": farm["farm_id"],
                    "field_id": fid,
                },
            )
            assert entry.status_code in (200, 201), entry.text
            entry_id = entry.json()["entry_id"]
            linked = await call(
                "worker", "POST", f"/api/v1/farm-book/entries/{entry_id}/task", {"task_id": task}
            )
            out["link"] = linked.status_code, linked.json()
            out["link_row"] = await owner.fetchrow(
                "SELECT task_id::text AS task_id, field_id, linked_by FROM task_expense_links"
                " WHERE tenant_id=$1::uuid AND entry_id=$2",
                tenant,
                entry_id,
            )
            out.update(task=task, field=fid, entry=entry_id, worker=str(ids["worker"]))
    finally:
        main.app.dependency_overrides.pop(main.get_current_user, None)
        await pool.close()
        try:
            if await owner.fetchval("SELECT rolsuper FROM pg_roles WHERE rolname = current_user"):
                # Ledger, hand-offs and versions are append-only by trigger/policy: a superuser
                # suspends triggers for this one transaction to remove the test's own tenant.
                async with owner.transaction():
                    await owner.execute("SET LOCAL session_replication_role = replica")
                    for table in _TABLES[::-1]:
                        await owner.execute(
                            f"DELETE FROM {table} WHERE tenant_id = $1::uuid", tenant
                        )
        finally:
            if role:
                await owner.execute(f'DROP OWNED BY "{role}"; DROP ROLE "{role}"')
            await owner.close()
    return out


@pytest.fixture(scope="module")
def scenario():
    mp = pytest.MonkeyPatch()
    try:
        yield asyncio.run(_scenario(mp))
    finally:
        mp.undo()


def test_the_approval_binds_the_first_version(scenario):
    assert scenario["approved_v1"] == 1


def test_a_photo_change_after_approval_appends_a_pending_version(scenario):
    assert scenario["photo_change"] == 200
    assert scenario["after_change"] == (P1, P2, 2, True, False)


def test_closing_on_evidence_changed_after_approval_is_refused(scenario):
    assert scenario["close_on_unapproved"] == 409


def test_closing_with_a_photo_change_in_the_same_request_is_refused(scenario):
    assert scenario["close_with_photo_change"] == 409
    assert scenario["versions_unchanged_by_refusals"] is True
    assert scenario["status_after_refusals"] != "completed"


def test_closing_on_the_approved_latest_version_is_allowed(scenario):
    assert scenario["resubmit_binds"] == 2
    assert scenario["close_on_approved"] == 200
    assert scenario["history"] == [(1, P1), (2, P2)]


def test_a_worker_links_a_receipt_to_the_task(scenario):
    status, body = scenario["link"]
    assert status == 200, body
    assert body == {"entry_id": scenario["entry"], "task_id": scenario["task"]}
    row = scenario["link_row"]
    assert (row["task_id"], row["field_id"], row["linked_by"]) == (
        scenario["task"],
        scenario["field"],
        scenario["worker"],
    )
