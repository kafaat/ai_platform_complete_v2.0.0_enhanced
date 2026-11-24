"""Pin inspection hand-off, evidence versions, close gate and task cost trace (live PG, v274-v277).

Owner decision 2026-11-14: the task and inspection work carrier D #1439 held back is rebuilt under
field-management-service, the owner of field_tasks. This file drives the real code against a
migrated Postgres through a NOBYPASSRLS login role, never a fake connection:

* field-management-service's gateway routes (``/internal/field-tasks/...``, reached through
  nginx as ``/api/v1/field-tasks/...``) over HTTP into its FastAPI app, with the trusted identity
  headers and the dedicated token nginx injects;
* the platform's ``PATCH /api/v1/tasks/{id}`` over HTTP into the platform app, where v277's
  trigger refuses an unreviewed or stale close and the platform answers 409;
* the platform's inspector-only meter gate (``api.task_irrigation_observations``) on a real
  connection under the same role.

Per table: rows of one tenant are invisible to another. Hand-off: accept, exact replay, reassign,
submit, review bound to an evidence version, stale revision and self-review refused. P3: a photo
added after the approval invalidates it (the evidence version names the scout photo evidence
record by id and digest). Cost: the trigger writes the history whoever updates the task, and
the history is append-only. Expense link: the farm and field of the entry must be the task's.
Negative controls disable the v277 trigger and the v276 guard inside a rolled-back transaction
and show the refused writes then pass, so the refusals measured here come from them.

Only rows the auth or scout-ingest services would write (users, scout photo evidence) and the
farm-book entries are seeded by the schema owner.
"""

from __future__ import annotations

import asyncio
import hashlib
import importlib.util
import os
import sys
import uuid
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import pytest

pytestmark = [pytest.mark.integration]

# Switch read before any import: on a certifying runner a missing dependency must fail the
# module, not importorskip it into a green skip (certification-switch-before-importorskip).
_CERTIFICATION_REQUIRED = os.getenv("FIELD_TASK_CERTIFICATION_REQUIRED") == "1"

try:
    import asyncpg
    import fastapi  # noqa: F401
    import httpx
except ImportError:
    if _CERTIFICATION_REQUIRED:
        raise
    asyncpg = pytest.importorskip("asyncpg")
    httpx = pytest.importorskip("httpx")
    pytest.importorskip("fastapi")

ROOT = Path(__file__).resolve().parents[1]
PLATFORM = ROOT / "services" / "sahool-platform"
FIELD_MGMT_MAIN = ROOT / "services" / "field-management-service" / "main.py"
DSN = os.getenv(
    "TEST_DATABASE_URL", "postgresql://sahool_test:test_password@127.0.0.1:5433/sahool_test"
)
ADMIN_DSN = os.getenv("TEST_DATABASE_ADMIN_URL", DSN)
TABLES = (
    "inspection_evidence_versions",
    "inspection_handoffs",
    "task_expense_links",
    "task_cost_history",
)
TOKEN = "field-tasks-live-" + uuid.uuid4().hex


async def _probe() -> str:
    try:
        conn = await asyncpg.connect(ADMIN_DSN, timeout=5)
    except Exception as exc:  # noqa: BLE001 - any failure means "no database here"
        return f"{type(exc).__name__}: {exc}"
    try:
        for table in (*TABLES, "field_tasks", "scout_photo_evidence", "farm_ledger_entries"):
            if await conn.fetchval("SELECT to_regclass($1)", f"public.{table}") is None:
                return f"schema not migrated ({table} missing)"
        if not await conn.fetchval(
            "SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname = current_user"
        ):
            return (
                "TEST_DATABASE_ADMIN_URL must name the schema owner (it seeds other services' rows)"
            )
    finally:
        await conn.close()
    return ""


_WHY = asyncio.run(_probe())
if _WHY and _CERTIFICATION_REQUIRED:
    raise RuntimeError(
        f"FIELD_TASK_CERTIFICATION_REQUIRED=1 but the live database is unusable: {_WHY}"
    )
pytestmark.append(pytest.mark.skipif(bool(_WHY), reason=f"declared skip (not a pass): {_WHY}"))


def _with_credentials(dsn: str, user: str, password: str) -> str:
    parts = urlsplit(dsn)
    host = parts.hostname or "127.0.0.1"
    netloc = f"{user}:{password}@{host}" + (f":{parts.port}" if parts.port else "")
    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))


class Live:
    """Two tenants, a temporary NOBYPASSRLS login role, both apps wired to it."""

    def __init__(self):
        self.tenant = str(uuid.uuid4())
        self.other_tenant = str(uuid.uuid4())
        self.role = None
        self.app_dsn = DSN
        self.due_at = (datetime.now(UTC) + timedelta(days=2)).replace(microsecond=0)

    async def _app_role(self) -> str:
        conn = await asyncpg.connect(self.app_dsn)
        try:
            return await conn.fetchval("SELECT current_user")
        finally:
            await conn.close()

    async def __aenter__(self):
        self.admin = await asyncpg.connect(ADMIN_DSN)
        probe = await asyncpg.connect(DSN)
        try:
            bypass = await probe.fetchval(
                "SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname = current_user"
            )
        finally:
            await probe.close()
        if bypass:
            self.role = f"fti_{uuid.uuid4().hex[:10]}"
            password = uuid.uuid4().hex
            await self.admin.execute(
                f"CREATE ROLE \"{self.role}\" LOGIN PASSWORD '{password}' "
                "NOSUPERUSER NOBYPASSRLS NOINHERIT;"
                f'GRANT USAGE ON SCHEMA public TO "{self.role}";'
                f'GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO "{self.role}";'
                f'GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO "{self.role}";'
                f'GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO "{self.role}";'
            )
            self.app_dsn = _with_credentials(ADMIN_DSN, self.role, password)
        check = await asyncpg.connect(self.app_dsn)
        try:
            flags = await check.fetchrow(
                "SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user"
            )
        finally:
            await check.close()
        assert (flags["rolsuper"], flags["rolbypassrls"]) == (False, False)
        # The same post-GRANT REVOKE the bootstrap scripts apply to the runtime role (#1460, v276).
        app_role = await self._app_role()
        await self.admin.execute(
            f'REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON task_cost_history FROM "{app_role}";'
            f'REVOKE EXECUTE ON FUNCTION public.record_field_task_cost() FROM "{app_role}"'
        )
        await self._seed()
        await self._wire()
        return self

    async def _seed(self):
        a = self.admin
        self.users = {}
        for tenant in (self.tenant, self.other_tenant):
            for name, role in (
                ("manager", "manager"),
                ("inspector", "worker"),
                ("inspector2", "farmer"),
                ("reviewer", "agronomist"),
                ("viewer", "viewer"),
            ):
                self.users[(tenant, name)] = str(
                    await a.fetchval(
                        "INSERT INTO users (email, password_hash, full_name, role, tenant_id, active)"
                        " VALUES ($1, 'x', $2, $3, $4::uuid, true) RETURNING id",
                        f"{name}.{uuid.uuid4().hex[:10]}@example.org",
                        name,
                        role,
                        tenant,
                    )
                )
        suffix = uuid.uuid4().hex[:8]
        self.farm, self.other_farm = f"fti-farm-{suffix}", f"fti-farm2-{suffix}"
        self.field, self.field2 = f"fti-f1-{suffix}", f"fti-f2-{suffix}"
        self.foreign_field = f"fti-fx-{suffix}"
        self.pin, self.foreign_pin = f"fti-pin-{suffix}", f"fti-pinx-{suffix}"
        for farm, tenant in (
            (self.farm, self.tenant),
            (self.other_farm, self.tenant),
            (f"fti-farmx-{suffix}", self.other_tenant),
        ):
            await a.execute(
                "INSERT INTO farms (farm_id, tenant_id, name) VALUES ($1, $2::uuid, $1)",
                farm,
                tenant,
            )
        for field, farm, tenant in (
            (self.field, self.farm, self.tenant),
            (self.field2, self.farm, self.tenant),
            (self.foreign_field, f"fti-farmx-{suffix}", self.other_tenant),
        ):
            await a.execute(
                "INSERT INTO fields (field_id, name, farm_id, tenant_id) VALUES ($1, $1, $2, $3::uuid)",
                field,
                farm,
                tenant,
            )
        for pin, field, tenant in (
            (self.pin, self.field, self.tenant),
            (self.foreign_pin, self.foreign_field, self.other_tenant),
        ):
            await a.execute(
                "INSERT INTO scouting_pins (pin_id, tenant_id, field_id, lat, lng, issue_category)"
                " VALUES ($1, $2::uuid, $3, 15.3, 44.2, 'pest')",
                pin,
                tenant,
                field,
            )

    async def _wire(self):
        os.environ["DATABASE_URL"] = self.app_dsn
        os.environ["FIELD_TASKS_SERVICE_TOKEN"] = TOKEN
        spec = importlib.util.spec_from_file_location("field_mgmt_live_main", FIELD_MGMT_MAIN)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        self.fm = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=mod.app, raise_app_exceptions=False),
            base_url="http://field-management",
            timeout=60,
        )
        if str(PLATFORM) not in sys.path:
            sys.path.insert(0, str(PLATFORM))
        import api.main as platform_main

        self.platform_main = platform_main
        self.pool = await asyncpg.create_pool(self.app_dsn, min_size=1, max_size=4)
        self._saved_pool = platform_main._DB_POOL
        platform_main._DB_POOL = self.pool
        self.acting = {"user": None}
        platform_main.app.dependency_overrides[platform_main.get_current_user] = lambda: (
            self.acting["user"]
        )
        self.platform = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=platform_main.app, raise_app_exceptions=False),
            base_url="http://platform",
            timeout=60,
        )

    def headers(self, name: str, *, tenant: str | None = None, role: str | None = None):
        tenant = tenant or self.tenant
        roles = {
            "manager": "manager",
            "inspector": "worker",
            "inspector2": "farmer",
            "reviewer": "agronomist",
            "viewer": "viewer",
        }
        return {
            "X-Field-Tasks-Token": TOKEN,
            "X-Tenant-Id": tenant,
            "X-User-Id": self.users[(tenant, name)],
            "X-User-Role": role or roles[name],
        }

    def platform_user(self, name: str, role: str):
        from core.canonical_schemas import UserRole, UserSchema

        self.acting["user"] = UserSchema(
            user_id=self.users[(self.tenant, name)],
            tenant_id=self.tenant,
            role=UserRole(role),
            name_ar="u",
        )

    async def photo(self, sha: str) -> str:
        return str(
            await self.admin.fetchval(
                """INSERT INTO scout_photo_evidence
                    (tenant_id, field_id, pin_id, object_ref, content_sha256, mime_type, size_bytes,
                     image_width, image_height, uploaded_by)
                   VALUES ($1::uuid,$2,$3,$4,$5,'image/jpeg',100,10,10,$6) RETURNING evidence_id""",
                self.tenant,
                self.field,
                self.pin,
                f"s3://bucket/scouting-photos/v1/{self.tenant}/{self.pin}/{sha}",
                sha,
                self.users[(self.tenant, "inspector")],
            )
        )

    async def assign(self) -> str:
        res = await self.fm.post(
            f"/internal/field-tasks/fields/{self.field}/pins/{self.pin}/inspection-task",
            json={
                "assigned_to": int(self.users[(self.tenant, "inspector")]),
                "due_at": self.due_at.isoformat(),
                "priority": 2,
            },
            headers=self.headers("manager"),
        )
        assert res.status_code == 200, res.text
        return res.json()["task"]["task_id"]

    async def handoff(self, task: str, verb: str, name: str, body: dict):
        return await self.fm.post(
            f"/internal/field-tasks/fields/{self.field}/tasks/{task}/handoff/{verb}",
            json=body,
            headers=self.headers(name),
        )

    async def state(self, task: str, name: str = "manager"):
        res = await self.fm.get(
            f"/internal/field-tasks/fields/{self.field}/tasks/{task}/handoff",
            headers=self.headers(name),
        )
        assert res.status_code == 200, res.text
        return res.json()

    async def patch(self, task: str, body: dict, name: str = "manager", role: str = "manager"):
        self.platform_user(name, role)
        return await self.platform.patch(f"/api/v1/tasks/{task}", json=body)

    async def ledger(self, *, farm, field, entry_type="expense", task=None, reverses=None):
        entry = f"fti-e-{uuid.uuid4().hex[:12]}"
        await self.admin.execute(
            """INSERT INTO farm_ledger_entries
                (entry_id, tenant_id, client_operation_id, request_digest, entry_type, direction,
                 payment_method, category, amount, occurred_on, farm_id, field_id, task_id,
                 reverses_entry_id, created_by)
               VALUES ($1,$2::uuid,$1,repeat('a',64),$3,$4,'cash','labour',10,$5,$6,$7,$8,$9,'seed')""",
            entry,
            self.tenant,
            entry_type,
            "outflow" if entry_type == "expense" else "inflow",
            date.today(),
            farm,
            field,
            task,
            reverses,
        )
        return entry

    async def __aexit__(self, *exc):
        a = self.admin
        try:
            await self.fm.aclose()
            await self.platform.aclose()
            self.platform_main.app.dependency_overrides.pop(
                self.platform_main.get_current_user, None
            )
            self.platform_main._DB_POOL = self._saved_pool
            await self.pool.close()
        finally:
            try:
                # Append-only tables refuse DELETE by trigger; the schema owner disables them
                # for the cleanup of this file's own tenants only.
                await a.execute("SET session_replication_role = replica")
                for table in (
                    "inspection_handoffs",
                    "inspection_evidence_versions",
                    "task_expense_links",
                    "task_cost_history",
                    "farm_ledger_entries",
                    "irrigation_manual_execution_events",
                    "irrigation_manual_executions",
                    "field_tasks",
                    "scout_photo_evidence",
                    "scouting_pins",
                    "fields",
                    "farms",
                    "users",
                ):
                    await a.execute(
                        f"DELETE FROM {table} WHERE tenant_id = ANY($1::uuid[])",
                        [self.tenant, self.other_tenant],
                    )
                await a.execute("SET session_replication_role = DEFAULT")
            finally:
                if self.role:
                    await a.execute(f'DROP OWNED BY "{self.role}"; DROP ROLE "{self.role}"')
                await a.close()


def run(coro):
    return asyncio.run(coro)


# ── catalog ─────────────────────────────────────────────────────────────────


def test_the_four_tables_force_rls_and_the_triggers_are_installed():
    async def target():
        conn = await asyncpg.connect(ADMIN_DSN)
        try:
            rls = await conn.fetch(
                "SELECT relname, relrowsecurity, relforcerowsecurity FROM pg_class"
                " WHERE relname = ANY($1::text[]) AND relkind = 'r'",
                list(TABLES),
            )
            triggers = await conn.fetch(
                "SELECT tgname FROM pg_trigger WHERE tgrelid = 'field_tasks'::regclass"
                " AND NOT tgisinternal"
            )
            return rls, {t["tgname"] for t in triggers}
        finally:
            await conn.close()

    rls, triggers = run(target())
    assert {r["relname"] for r in rls} == set(TABLES)
    assert all(r["relrowsecurity"] and r["relforcerowsecurity"] for r in rls)
    assert {
        "record_field_task_cost",
        "field_task_inspection_close_gate",
        "field_task_inspection_reopen",
    } <= triggers


# ── hand-off state machine ──────────────────────────────────────────────────


def test_handoff_accept_reassign_finding_state_machine():
    async def target():
        out = {}
        async with Live() as live:
            task = await live.assign()
            # The same assignment replayed answers the stored task; a different one is refused.
            out["replay_assign"] = (await live.assign()) == task
            s0 = await live.state(task)
            out["s0"] = (s0["revision"], s0["review_state"], s0["accepted"])
            out["viewer_accept"] = (
                await live.handoff(task, "accept", "viewer", {"expected_revision": 0})
            ).status_code
            out["manager_accept"] = (
                await live.handoff(task, "accept", "manager", {"expected_revision": 0})
            ).status_code
            out["accept"] = (
                await live.handoff(task, "accept", "inspector", {"expected_revision": 0})
            ).json()
            out["accept_replay"] = (
                await live.handoff(task, "accept", "inspector", {"expected_revision": 0})
            ).json()["revision"]
            new = int(live.users[(live.tenant, "inspector2")])
            out["reassign_stale"] = (
                await live.handoff(
                    task,
                    "reassign",
                    "manager",
                    {"expected_revision": 0, "assigned_to": new, "reason": "shift"},
                )
            ).status_code
            out["reassign"] = (
                await live.handoff(
                    task,
                    "reassign",
                    "manager",
                    {"expected_revision": 1, "assigned_to": new, "reason": "shift"},
                )
            ).json()
            out["old_assignee_submit"] = (
                await live.handoff(
                    task,
                    "finding",
                    "inspector",
                    {"expected_revision": 2, "action": "submit", "reason": "seen"},
                )
            ).status_code
            out["accept2"] = (
                await live.handoff(task, "accept", "inspector2", {"expected_revision": 2})
            ).json()["revision"]
            submitted = (
                await live.handoff(
                    task,
                    "finding",
                    "inspector2",
                    {"expected_revision": 3, "action": "submit", "reason": "aphids", "notes": "n1"},
                )
            ).json()
            out["submitted"] = (submitted["revision"], submitted["review_state"])
            version = submitted["current_evidence"]["version"]
            out["self_review"] = (
                await live.handoff(
                    task,
                    "finding",
                    "inspector2",
                    {
                        "expected_revision": 4,
                        "action": "approve",
                        "reason": "ok",
                        "evidence_version": version,
                    },
                )
            ).status_code
            out["wrong_version"] = (
                await live.handoff(
                    task,
                    "finding",
                    "reviewer",
                    {
                        "expected_revision": 4,
                        "action": "approve",
                        "reason": "ok",
                        "evidence_version": version + 1,
                    },
                )
            ).status_code
            approved = (
                await live.handoff(
                    task,
                    "finding",
                    "reviewer",
                    {
                        "expected_revision": 4,
                        "action": "approve",
                        "reason": "ok",
                        "evidence_version": version,
                    },
                )
            ).json()
            out["approved"] = (approved["revision"], approved["evidence_approved"])
            out["approve_replay"] = (
                await live.handoff(
                    task,
                    "finding",
                    "reviewer",
                    {
                        "expected_revision": 4,
                        "action": "approve",
                        "reason": "ok",
                        "evidence_version": version,
                    },
                )
            ).json()["revision"]
            out["events"] = [e["action"] for e in approved["events"]]
            out["update"] = await _append_only(live, "inspection_handoffs", task)
        return out

    out = run(target())
    assert out["replay_assign"] is True
    assert out["s0"] == (0, "assigned", False)
    assert out["viewer_accept"] == 403  # the viewer role lacks observation:record
    assert out["manager_accept"] == 403  # not the assignee
    assert out["accept"]["revision"] == 1 and out["accept"]["accepted"] is True
    assert out["accept_replay"] == 1  # the exact replay answers the current state
    assert out["reassign_stale"] == 409
    assert out["reassign"]["revision"] == 2 and out["reassign"]["accepted"] is False
    assert out["old_assignee_submit"] == 403
    assert out["accept2"] == 3
    assert out["submitted"] == (4, "submit")
    assert out["self_review"] == 403
    assert out["wrong_version"] == 409
    assert out["approved"] == (5, True)
    assert out["approve_replay"] == 5
    assert out["events"] == ["accept", "reassign", "accept", "submit", "approve"]
    # No UPDATE policy: the app role changes nothing; the owner's UPDATE hits the trigger.
    assert out["update"] == ("UPDATE 0", "55000")


async def _append_only(live, table: str, task: str):
    """(app role UPDATE status, schema owner UPDATE SQLSTATE) for one task's rows."""
    conn = await asyncpg.connect(live.app_dsn)
    try:
        async with conn.transaction():
            await conn.execute("SELECT set_config('app.current_tenant', $1, true)", live.tenant)
            try:
                async with conn.transaction():
                    app = await conn.execute(
                        f"UPDATE {table} SET task_id=task_id WHERE task_id=$1::uuid", task
                    )
            except asyncpg.PostgresError as exc:
                app = exc.sqlstate
    finally:
        await conn.close()
    conn = await asyncpg.connect(ADMIN_DSN)
    try:
        async with conn.transaction():
            try:
                await conn.execute(
                    f"UPDATE {table} SET task_id=task_id WHERE task_id=$1::uuid", task
                )
                owner = "allowed"
            except asyncpg.PostgresError as exc:
                owner = exc.sqlstate
    finally:
        await conn.close()
    return app, owner


# ── P3: evidence version and the close gate ─────────────────────────────────


async def _accepted_and_submitted(live, notes="n"):
    task = await live.assign()
    await live.handoff(task, "accept", "inspector", {"expected_revision": 0})
    s = (
        await live.handoff(
            task,
            "finding",
            "inspector",
            {"expected_revision": 1, "action": "submit", "reason": "seen", "notes": notes},
        )
    ).json()
    return task, s


def test_submit_replay_binds_an_explicit_photo_id_to_the_recorded_version():
    """An old revision can replay P1, but cannot acknowledge another requested photo P2.

    This goes through the real owner route and migrated PostgreSQL. P2 is a different
    request identity, not a replacement of the immutable v260 photo row: the current
    owner permits one insert-only photo per pin.
    """

    async def target():
        async with Live() as live:
            photo_id = await live.photo("a" * 64)
            task = await live.assign()
            accepted = await live.handoff(task, "accept", "inspector", {"expected_revision": 0})
            assert accepted.status_code == 200, accepted.text
            body = {
                "expected_revision": 1,
                "action": "submit",
                "reason": "observed photo",
                "notes": "field measurement recorded",
                "photo_evidence_id": photo_id,
            }
            submitted = await live.handoff(task, "finding", "inspector", body)
            assert submitted.status_code == 200, submitted.text
            before = await live.state(task, "inspector")
            assert before["current_evidence"]["photo_evidence_id"] == photo_id
            assert (before["revision"], len(before["events"]), len(before["evidence"])) == (
                2,
                2,
                1,
            )

            replay = await live.handoff(task, "finding", "inspector", body)
            after_replay = await live.state(task, "inspector")
            changed = await live.handoff(
                task,
                "finding",
                "inspector",
                body | {"photo_evidence_id": str(uuid.uuid4())},
            )
            after_changed = await live.state(task, "inspector")

            assert replay.status_code == 200, replay.text
            assert replay.json() == before
            assert after_replay == before, "an exact replay must not append a hand-off or evidence"
            assert after_changed == before, "a conflicting replay must not change stored evidence"
            assert changed.status_code == 409, (
                "a stale submit with another explicit photo id is not the recorded request: "
                f"{changed.status_code} {changed.text}"
            )

    run(target())


@pytest.mark.parametrize("name_photo_field", [False, True], ids=["omitted", "explicit-null"])
def test_legacy_submit_replay_without_photo_does_not_approve_a_later_photo(name_photo_field):
    """Keep the existing optional-photo contract without calling it exact-payload replay.

    Historical hand-offs do not store whether photo_evidence_id was omitted or null.
    Both requests mean the existing automatic-photo submit. The legal photo change is
    no-photo -> inserted-photo, since v260 forbids replacing a photo already present.
    Replaying the old receipt must not create a new version or approve the added photo.
    """

    async def target():
        async with Live() as live:
            task = await live.assign()
            accepted = await live.handoff(task, "accept", "inspector", {"expected_revision": 0})
            assert accepted.status_code == 200, accepted.text
            body = {
                "expected_revision": 1,
                "action": "submit",
                "reason": "observed before photo upload",
                "notes": "field measurement recorded",
            }
            if name_photo_field:
                body["photo_evidence_id"] = None
            submitted = await live.handoff(task, "finding", "inspector", body)
            assert submitted.status_code == 200, submitted.text
            version = submitted.json()["current_evidence"]["version"]
            assert submitted.json()["current_evidence"]["photo_evidence_id"] is None

            photo_id = await live.photo("b" * 64)
            before = await live.state(task, "inspector")
            replay = await live.handoff(task, "finding", "inspector", body)
            after_replay = await live.state(task, "inspector")
            refused = await live.handoff(
                task,
                "finding",
                "reviewer",
                {
                    "expected_revision": 2,
                    "action": "approve",
                    "reason": "approve the originally submitted version",
                    "evidence_version": version,
                },
            )
            after_review = await live.state(task, "inspector")

            assert replay.status_code == 200, replay.text
            assert replay.json() == before
            assert after_replay == before
            assert refused.status_code == 409, refused.text
            assert after_review == before
            assert before["current_evidence"]["photo_evidence_id"] == photo_id
            assert before["current_evidence"]["version"] is None
            assert before["evidence_pending_review"] is True
            assert before["evidence_approved"] is False
            assert (before["revision"], len(before["events"]), len(before["evidence"])) == (
                2,
                2,
                1,
            )
            assert before["evidence"][0]["photo_evidence_id"] is None

    run(target())


def test_close_needs_an_approval_and_a_photo_added_after_it_invalidates_it():
    async def target():
        out = {}
        async with Live() as live:
            task, submitted = await _accepted_and_submitted(live)
            out["unreviewed_close"] = (await live.patch(task, {"status": "completed"})).json()
            v1 = submitted["current_evidence"]["version"]
            approved = (
                await live.handoff(
                    task,
                    "finding",
                    "reviewer",
                    {
                        "expected_revision": 2,
                        "action": "approve",
                        "reason": "ok",
                        "evidence_version": v1,
                    },
                )
            ).json()
            out["approved_v1"] = (
                approved["evidence_approved"],
                approved["approved_evidence"]["photo_evidence_id"],
            )
            # scout-ingest stores the observation photo after the approval.
            sha = "b" * 64
            photo_id = await live.photo(sha)
            after = await live.state(task)
            out["after_photo"] = (
                after["evidence_approved"],
                after["evidence_pending_review"],
                after["current_evidence"]["version"],
                after["current_evidence"]["photo_evidence_id"] == photo_id,
            )
            out["stale_close"] = await live.patch(task, {"status": "completed"})
            out["stale_close"] = (out["stale_close"].status_code, out["stale_close"].json())
            # Negative control: without v277's trigger the same close goes through.
            conn = await asyncpg.connect(ADMIN_DSN)
            try:
                tx = conn.transaction()
                await tx.start()
                await conn.execute(
                    "ALTER TABLE field_tasks DISABLE TRIGGER field_task_inspection_close_gate"
                )
                out["control"] = await conn.fetchval(
                    "UPDATE field_tasks SET status='completed' WHERE task_id=$1::uuid RETURNING status",
                    task,
                )
                await tx.rollback()
            finally:
                await conn.close()
            # A new submit binds the photo; the reviewer approves that exact version.
            s2 = (
                await live.handoff(
                    task,
                    "finding",
                    "inspector",
                    {
                        "expected_revision": 3,
                        "action": "submit",
                        "reason": "with photo",
                        "notes": "n",
                        "photo_evidence_id": photo_id,
                    },
                )
            ).json()
            v2 = s2["current_evidence"]["version"]
            out["v2"] = (v2, s2["current_evidence"]["photo_content_sha256"] == sha)
            await live.handoff(
                task,
                "finding",
                "reviewer",
                {
                    "expected_revision": 4,
                    "action": "approve",
                    "reason": "ok",
                    "evidence_version": v2,
                },
            )
            ok = await live.patch(task, {"status": "completed"})
            out["close"] = (ok.status_code, ok.json().get("status"))
            # Replaying the close changes nothing and is not re-gated (#1423 replay).
            again = await live.patch(task, {"status": "completed"})
            out["close_replay"] = (again.status_code, again.json().get("status"))
            reopened = await live.patch(task, {"status": "pending"})
            out["reopen"] = reopened.status_code
            out["after_reopen"] = (await live.state(task))["review_state"]
            out["close_after_reopen"] = (await live.patch(task, {"status": "completed"})).json()
            out["versions"] = await live.admin.fetch(
                "SELECT version, photo_evidence_id::text AS photo FROM inspection_evidence_versions"
                " WHERE task_id=$1::uuid ORDER BY version",
                task,
            )
        return out

    out = run(target())
    assert out["unreviewed_close"]["detail"]["error"] == "inspection_review_required"
    assert out["approved_v1"] == (True, None)
    assert out["after_photo"] == (False, True, None, True)
    assert out["stale_close"][0] == 409
    assert out["stale_close"][1]["detail"]["error"] == "inspection_evidence_changed"
    assert out["control"] == "completed"
    assert out["v2"] == (2, True)
    assert out["close"] == (200, "completed")
    assert out["close_replay"] == (200, "completed")
    assert out["reopen"] == 200
    assert out["after_reopen"] == "reopen"
    assert out["close_after_reopen"]["detail"]["error"] == "inspection_review_required"
    # Every version stays: the approved v1 (no photo) and v2 (the photo record).
    assert [(r["version"], r["photo"] is None) for r in out["versions"]] == [(1, True), (2, False)]


def test_a_review_of_a_submit_whose_photo_changed_since_is_refused():
    async def target():
        async with Live() as live:
            task, submitted = await _accepted_and_submitted(live)
            await live.photo("f" * 64)  # stored after the submit, before the review
            refused = await live.handoff(
                task,
                "finding",
                "reviewer",
                {
                    "expected_revision": 2,
                    "action": "approve",
                    "reason": "ok",
                    "evidence_version": submitted["current_evidence"]["version"],
                },
            )
            returned = await live.handoff(
                task,
                "finding",
                "reviewer",
                {
                    "expected_revision": 2,
                    "action": "return",
                    "reason": "photo arrived",
                    "evidence_version": submitted["current_evidence"]["version"],
                },
            )
            return refused.status_code, returned.status_code, returned.json()["review_state"]

    assert run(target()) == (409, 200, "return")


def test_a_version_cannot_name_another_pins_photo_or_a_forged_digest():
    async def target():
        out = {}
        async with Live() as live:
            task, _ = await _accepted_and_submitted(live)
            conn = await asyncpg.connect(live.app_dsn)
            try:
                for label, photo_sha, digest in (
                    ("forged_digest", None, "c" * 64),
                    ("foreign_photo", "d" * 64, None),
                ):
                    async with conn.transaction():
                        await conn.execute(
                            "SELECT set_config('app.current_tenant', $1, true),"
                            " set_config('app.current_user_id', $2, true)",
                            live.tenant,
                            live.users[(live.tenant, "inspector")],
                        )
                        photo_id = None
                        if photo_sha:
                            photo_id = str(uuid.uuid4())
                        try:
                            await conn.execute(
                                """INSERT INTO inspection_evidence_versions
                                    (tenant_id, field_id, task_id, version, pin_id,
                                     photo_evidence_id, photo_content_sha256, notes, digest,
                                     recorded_by)
                                   VALUES ($1::uuid,$2,$3::uuid,9,$4,$5::uuid,$6,NULL,$7,$8)""",
                                live.tenant,
                                live.field,
                                task,
                                live.pin,
                                photo_id,
                                photo_sha,
                                digest or "e" * 64,
                                live.users[(live.tenant, "inspector")],
                            )
                            out[label] = "allowed"
                        except asyncpg.PostgresError as exc:
                            out[label] = exc.sqlstate
            finally:
                await conn.close()
        return out

    out = run(target())
    assert out["forged_digest"] == "23514"
    assert out["foreign_photo"] in ("23514", "23503")


# ── the DB holds the gate for every writer on the shared role ───────────────


async def _as_app(live, name: str, sql: str, *args):
    """Run one statement as the NOBYPASSRLS app role for user ``name``: 'allowed' or SQLSTATE."""
    conn = await asyncpg.connect(live.app_dsn)
    try:
        async with conn.transaction():
            await conn.execute(
                "SELECT set_config('app.current_tenant', $1, true),"
                " set_config('app.current_user_id', $2, true)",
                live.tenant,
                live.users[(live.tenant, name)],
            )
            try:
                async with conn.transaction():
                    await conn.execute(sql, *args)
                return "allowed"
            except asyncpg.PostgresError as exc:
                return exc.sqlstate
    finally:
        await conn.close()


def test_a_pin_task_cannot_drop_its_pin_or_be_inserted_completed():
    async def target():
        out = {}
        async with Live() as live:
            task, _ = await _accepted_and_submitted(live)
            pin2 = f"{live.pin}-2"
            await live.admin.execute(
                "INSERT INTO scouting_pins (pin_id, tenant_id, field_id, lat, lng, issue_category)"
                " VALUES ($1, $2::uuid, $3, 15.3, 44.2, 'pest')",
                pin2,
                live.tenant,
                live.field,
            )
            out["clear_and_close"] = await _as_app(
                live,
                "manager",
                "UPDATE field_tasks SET source_scouting_pin_id=NULL, status='completed'"
                " WHERE task_id=$1::uuid",
                task,
            )
            out["clear"] = await _as_app(
                live,
                "manager",
                "UPDATE field_tasks SET source_scouting_pin_id=NULL WHERE task_id=$1::uuid",
                task,
            )
            out["move"] = await _as_app(
                live,
                "manager",
                "UPDATE field_tasks SET source_scouting_pin_id=$2 WHERE task_id=$1::uuid",
                task,
                pin2,
            )
            out["insert_completed"] = await _as_app(
                live,
                "manager",
                "INSERT INTO field_tasks (tenant_id, field_id, task_type, status,"
                " source_scouting_pin_id) VALUES ($1::uuid, $2, 'scouting', 'completed', $3)",
                live.tenant,
                live.field,
                pin2,
            )
            # Controls: an open pin task inserts, and a task without a pin closes freely.
            out["insert_open"] = await _as_app(
                live,
                "manager",
                "INSERT INTO field_tasks (tenant_id, field_id, task_type, status,"
                " source_scouting_pin_id) VALUES ($1::uuid, $2, 'scouting', 'pending', $3)",
                live.tenant,
                live.field,
                pin2,
            )
            out["insert_plain_completed"] = await _as_app(
                live,
                "manager",
                "INSERT INTO field_tasks (tenant_id, field_id, task_type, status)"
                " VALUES ($1::uuid, $2, 'weeding', 'completed')",
                live.tenant,
                live.field,
            )
            out["stored"] = dict(
                await live.admin.fetchrow(
                    "SELECT source_scouting_pin_id AS pin, status FROM field_tasks"
                    " WHERE task_id=$1::uuid",
                    task,
                )
            )
            out["pin"] = live.pin
        return out

    out = run(target())
    assert out["clear_and_close"] == "SH003"
    assert out["clear"] == "SH003"
    assert out["move"] == "SH003"
    assert out["insert_completed"] == "SH001"
    assert out["insert_open"] == "allowed"
    assert out["insert_plain_completed"] == "allowed"
    assert out["stored"] == {"pin": out["pin"], "status": "pending"}


def test_approving_a_superseded_version_does_not_close_and_revisions_are_consecutive():
    async def target():
        out = {}
        async with Live() as live:
            task, submitted = await _accepted_and_submitted(live, notes="n1")
            v1 = submitted["current_evidence"]["version"]
            notes = "n2"
            digest = hashlib.sha256(f"||{notes}".encode()).hexdigest()
            out["v2"] = await _as_app(
                live,
                "inspector",
                """INSERT INTO inspection_evidence_versions
                    (tenant_id, field_id, task_id, version, pin_id, notes, digest, recorded_by)
                   VALUES ($1::uuid,$2,$3::uuid,2,$4,$5,$6,current_setting('app.current_user_id'))""",
                live.tenant,
                live.field,
                task,
                live.pin,
                notes,
                digest,
            )
            handoff = """INSERT INTO inspection_handoffs
                (tenant_id, field_id, task_id, revision, action, previous_assignee, assignee,
                 actor, reason, evidence_version)
               VALUES ($1::uuid,$2,$3::uuid,$4,$5,$6,$6,current_setting('app.current_user_id'),
                       $7,$8)"""
            assignee = live.users[(live.tenant, "inspector")]
            out["gap"] = await _as_app(
                live,
                "inspector",
                handoff,
                live.tenant,
                live.field,
                task,
                1000,
                "submit",
                assignee,
                "far ahead",
                2,
            )
            out["submit_v2"] = await _as_app(
                live,
                "inspector",
                handoff,
                live.tenant,
                live.field,
                task,
                3,
                "submit",
                assignee,
                "second",
                2,
            )
            out["approve_v1"] = await _as_app(
                live,
                "reviewer",
                handoff,
                live.tenant,
                live.field,
                task,
                4,
                "approve",
                assignee,
                "ok",
                v1,
            )
            res = await live.patch(task, {"status": "completed"})
            out["close"] = (res.status_code, res.json().get("detail", {}).get("error"))
            out["status"] = await live.admin.fetchval(
                "SELECT status FROM field_tasks WHERE task_id=$1::uuid", task
            )
        return out

    out = run(target())
    assert out["v2"] == "allowed"
    assert out["gap"] == "SH004"
    assert (out["submit_v2"], out["approve_v1"]) == ("allowed", "allowed")
    assert out["close"] == (409, "inspection_review_required")
    assert out["status"] == "pending"


async def _as_app_tx(live, name: str, *statements):
    """Run ``(sql, *args)`` statements in one app-role transaction: 'allowed' or the SQLSTATE."""
    conn = await asyncpg.connect(live.app_dsn)
    try:
        async with conn.transaction():
            await conn.execute(
                "SELECT set_config('app.current_tenant', $1, true),"
                " set_config('app.current_user_id', $2, true)",
                live.tenant,
                live.users[(live.tenant, name)],
            )
            try:
                async with conn.transaction():
                    for sql, *args in statements:
                        await conn.execute(sql, *args)
                return "allowed"
            except asyncpg.PostgresError as exc:
                return exc.sqlstate
    finally:
        await conn.close()


_HANDOFF_AS = """INSERT INTO inspection_handoffs
    (tenant_id, field_id, task_id, revision, action, previous_assignee, assignee, actor, reason,
     evidence_version)
   VALUES ($1::uuid,$2,$3::uuid,$4,$5,$6,$7,current_setting('app.current_user_id'),$8,$9)"""


def test_a_pin_cannot_be_attached_to_a_task_inserted_completed_without_one():
    """Review finding 1: INSERT a completed task with no pin, then UPDATE it to name the pin."""

    async def target():
        out = {}
        async with Live() as live:
            plain = str(uuid.uuid4())
            out["insert"] = await _as_app(
                live,
                "manager",
                "INSERT INTO field_tasks (task_id, tenant_id, field_id, task_type, status)"
                " VALUES ($1::uuid, $2::uuid, $3, 'scouting', 'completed')",
                plain,
                live.tenant,
                live.field,
            )
            out["attach_pin"] = await _as_app(
                live,
                "manager",
                "UPDATE field_tasks SET source_scouting_pin_id=$2 WHERE task_id=$1::uuid",
                plain,
                live.pin,
            )
            out["stored"] = dict(
                await live.admin.fetchrow(
                    "SELECT source_scouting_pin_id AS pin, status FROM field_tasks"
                    " WHERE task_id=$1::uuid",
                    plain,
                )
            )
            # The real inspection task for the pin can still be created.
            res = await live.fm.post(
                f"/internal/field-tasks/fields/{live.field}/pins/{live.pin}/inspection-task",
                json={
                    "assigned_to": int(live.users[(live.tenant, "inspector")]),
                    "due_at": live.due_at.isoformat(),
                    "priority": 2,
                },
                headers=live.headers("manager"),
            )
            out["real_task"] = (res.status_code, res.json().get("task", {}).get("task_id") != plain)
        return out

    out = run(target())
    assert out["insert"] == "allowed"
    assert out["attach_pin"] == "SH003"
    assert out["stored"] == {"pin": None, "status": "completed"}
    assert out["real_task"] == (200, True)


def test_an_inspector_cannot_approve_their_own_finding_by_naming_another_assignee():
    """Review finding 3: the inspector writes 'approve' with assignee = the reviewer."""

    async def target():
        out = {}
        async with Live() as live:
            task, submitted = await _accepted_and_submitted(live)
            v1 = submitted["current_evidence"]["version"]
            inspector = live.users[(live.tenant, "inspector")]
            reviewer = live.users[(live.tenant, "reviewer")]
            other = live.users[(live.tenant, "inspector2")]
            out["forged_approve"] = await _as_app(
                live,
                "inspector",
                _HANDOFF_AS,
                live.tenant,
                live.field,
                task,
                3,
                "approve",
                reviewer,
                reviewer,
                "ok",
                v1,
            )
            res = await live.patch(task, {"status": "completed"})
            out["close"] = (res.status_code, res.json().get("detail", {}).get("error"))
            # Moving the task to someone else first keeps the chain, but the submitter still
            # cannot approve the version they submitted.
            out["reassign_then_self_approve"] = await _as_app_tx(
                live,
                "inspector",
                (
                    "UPDATE field_tasks SET assigned_to=$2 WHERE task_id=$1::uuid",
                    task,
                    other,
                ),
                (
                    _HANDOFF_AS,
                    live.tenant,
                    live.field,
                    task,
                    3,
                    "reassign",
                    inspector,
                    other,
                    "handover",
                    None,
                ),
                (
                    _HANDOFF_AS,
                    live.tenant,
                    live.field,
                    task,
                    4,
                    "approve",
                    other,
                    other,
                    "ok",
                    v1,
                ),
            )
            # Control: the reviewer approving with the real assignee is accepted.
            out["real_approve"] = await _as_app(
                live,
                "reviewer",
                _HANDOFF_AS,
                live.tenant,
                live.field,
                task,
                3,
                "approve",
                inspector,
                inspector,
                "ok",
                v1,
            )
            out["status"] = await live.admin.fetchval(
                "SELECT status FROM field_tasks WHERE task_id=$1::uuid", task
            )
        return out

    out = run(target())
    assert out["forged_approve"] == "SH006"
    assert out["close"] == (409, "inspection_review_required")
    assert out["reassign_then_self_approve"] == "SH007"
    assert out["real_approve"] == "allowed"
    assert out["status"] == "pending"


def test_leaving_completed_by_any_status_reopens_and_status_case_does_not_skip_the_gate():
    """Review finding 4: completed -> 'archived' -> completed reusing the approval; 'Completed'."""

    async def target():
        out = {}
        async with Live() as live:
            task, submitted = await _accepted_and_submitted(live)
            close_as = "UPDATE field_tasks SET status=$2 WHERE task_id=$1::uuid"
            out["case_variant_unreviewed"] = await _as_app(
                live, "manager", close_as, task, "Completed"
            )
            await live.handoff(
                task,
                "finding",
                "reviewer",
                {
                    "expected_revision": 2,
                    "action": "approve",
                    "reason": "ok",
                    "evidence_version": submitted["current_evidence"]["version"],
                },
            )
            ok = await live.patch(task, {"status": "completed"})
            out["close"] = (ok.status_code, ok.json().get("status"))
            out["archive"] = await _as_app(live, "manager", close_as, task, "archived")
            out["last_event"] = await live.admin.fetchval(
                "SELECT action FROM inspection_handoffs WHERE task_id=$1::uuid"
                " ORDER BY revision DESC LIMIT 1",
                task,
            )
            out["reclose"] = await _as_app(live, "manager", close_as, task, "completed")
            out["reclose_case"] = await _as_app(live, "manager", close_as, task, "Completed")
            out["status"] = await live.admin.fetchval(
                "SELECT status FROM field_tasks WHERE task_id=$1::uuid", task
            )
        return out

    out = run(target())
    assert out["case_variant_unreviewed"] == "SH001"
    assert out["close"] == (200, "completed")
    assert out["archive"] == "allowed"
    assert out["last_event"] == "reopen"
    assert out["reclose"] == "SH001"
    assert out["reclose_case"] == "SH001"
    assert out["status"] == "archived"


def test_the_platform_answers_the_gate_and_revision_race_sqlstates_with_409():
    """Review finding 5: SH003-SH007 and 23505 raised under PATCH are 409, not 503.

    The schema owner installs, for one plain task only, a trigger raising the SQLSTATE the real
    v275-v277 objects raise, so the real platform route meets it from the real database."""

    async def target():
        out = {}
        async with Live() as live:
            task = str(
                await live.admin.fetchval(
                    "INSERT INTO field_tasks (tenant_id, field_id, task_type, status)"
                    " VALUES ($1::uuid, $2, 'weeding', 'pending') RETURNING task_id",
                    live.tenant,
                    live.field,
                )
            )
            fn = f"fti_raise_{uuid.uuid4().hex[:10]}"
            await live.admin.execute(
                f"CREATE FUNCTION {fn}() RETURNS trigger LANGUAGE plpgsql AS $$"
                " BEGIN RAISE EXCEPTION 'injected' USING ERRCODE = TG_ARGV[0]; END $$"
            )
            try:
                for code in ("SH003", "SH006", "SH007", "23505"):
                    await live.admin.execute(
                        f"CREATE TRIGGER {fn} BEFORE UPDATE ON field_tasks FOR EACH ROW"
                        f" WHEN (OLD.task_id = '{task}'::uuid) EXECUTE FUNCTION {fn}('{code}')"
                    )
                    try:
                        res = await live.patch(task, {"notes": f"n-{code}"})
                        out[code] = (res.status_code, res.json().get("detail", {}).get("error"))
                    finally:
                        await live.admin.execute(f"DROP TRIGGER {fn} ON field_tasks")
            finally:
                await live.admin.execute(f"DROP FUNCTION {fn}()")
            ok = await live.patch(task, {"notes": "after"})
            out["control"] = ok.status_code
        return out

    out = run(target())
    assert out["SH003"] == (409, "inspection_pin_immutable")
    assert out["SH006"] == (409, "inspection_handoff_chain_broken")
    assert out["SH007"] == (409, "inspection_self_review")
    assert out["23505"] == (409, "inspection_handoff_conflict")
    assert out["control"] == 200


def test_cost_history_and_expense_links_cannot_be_forged_by_the_app_role():
    async def target():
        out = {}
        async with Live() as live:
            task = str(
                await live.admin.fetchval(
                    "INSERT INTO field_tasks (tenant_id, field_id, task_type, status)"
                    " VALUES ($1::uuid, $2, 'weeding', 'pending') RETURNING task_id",
                    live.tenant,
                    live.field,
                )
            )
            manager = live.users[(live.tenant, "manager")]
            out["forged_history"] = await _as_app(
                live,
                "manager",
                "INSERT INTO task_cost_history (tenant_id, task_id, changed_by, actual_usd, status)"
                " VALUES ($1::uuid, $2::uuid, $3, 999, 'pending')",
                live.tenant,
                task,
                manager,
            )
            entry = await live.ledger(farm=live.farm, field=live.field)
            link = (
                "INSERT INTO task_expense_links (tenant_id, entry_id, task_id, field_id, linked_by)"
                " VALUES ($1::uuid, $2, $3::uuid, $4, $5)"
            )
            out["forged_link"] = await _as_app(
                live,
                "manager",
                link,
                live.tenant,
                entry,
                task,
                live.field,
                live.users[(live.tenant, "viewer")],
            )
            # Controls: the same link as the acting user, and history through a task update.
            out["own_link"] = await _as_app(
                live, "manager", link, live.tenant, entry, task, live.field, manager
            )
            out["update"] = await _as_app(
                live,
                "manager",
                "UPDATE field_tasks SET actual_cost_usd=3 WHERE task_id=$1::uuid",
                task,
            )
            out["history"] = [
                (r["changed_by"], r["a"])
                for r in await live.admin.fetch(
                    "SELECT changed_by, actual_usd::text AS a FROM task_cost_history"
                    " WHERE task_id=$1::uuid ORDER BY change_id",
                    task,
                )
            ]
            out["manager"] = manager
        return out

    out = run(target())
    assert out["forged_history"] == "42501"  # no INSERT privilege on task_cost_history (#1460)
    assert out["forged_link"] == "42501"  # the INSERT policy binds linked_by to the user
    assert out["own_link"] == "allowed"
    assert out["update"] == "allowed"
    assert out["history"] == [(out["manager"], "3.00")]


def test_cost_history_cannot_be_forged_through_a_temporary_trigger():
    """Review round 2 of #1460: pg_trigger_depth() was spoofed with a temp table and trigger."""

    async def target():
        out = {}
        async with Live() as live:
            task = str(
                await live.admin.fetchval(
                    "INSERT INTO field_tasks (tenant_id, field_id, task_type, status)"
                    " VALUES ($1::uuid, $2, 'weeding', 'pending') RETURNING task_id",
                    live.tenant,
                    live.field,
                )
            )
            manager = live.users[(live.tenant, "manager")]
            conn = await asyncpg.connect(live.app_dsn)
            try:
                async with conn.transaction():
                    await conn.execute(
                        "SELECT set_config('app.current_tenant', $1, true),"
                        " set_config('app.current_user_id', $2, true)",
                        live.tenant,
                        manager,
                    )
                    try:
                        async with conn.transaction():
                            await conn.execute(
                                "CREATE FUNCTION pg_temp.forge() RETURNS trigger LANGUAGE plpgsql AS $f$"
                                " BEGIN INSERT INTO task_cost_history (tenant_id, task_id, changed_by,"
                                " previous_usd, actual_usd, previous_status, status) VALUES"
                                f" ('{live.tenant}'::uuid, '{task}'::uuid, '{manager}', 77777, NULL,"
                                " 'forged', 'pending'); RETURN NEW; END $f$;"
                                " CREATE TEMP TABLE forge_x (i int);"
                                " CREATE TRIGGER forge_t AFTER INSERT ON forge_x"
                                " FOR EACH ROW EXECUTE FUNCTION pg_temp.forge();"
                                " INSERT INTO forge_x VALUES (1);"
                            )
                        out["temp_trigger"] = "allowed"
                    except asyncpg.PostgresError as exc:
                        out["temp_trigger"] = exc.sqlstate
            finally:
                await conn.close()
            out["forged_rows"] = await live.admin.fetchval(
                "SELECT count(*) FROM task_cost_history WHERE task_id=$1::uuid"
                " AND previous_status='forged'",
                task,
            )
            # Control: the legitimate path still records, through the SECURITY DEFINER trigger.
            out["update"] = await _as_app(
                live,
                "manager",
                "UPDATE field_tasks SET actual_cost_usd=5 WHERE task_id=$1::uuid",
                task,
            )
            out["history"] = await live.admin.fetchval(
                "SELECT count(*) FROM task_cost_history WHERE task_id=$1::uuid AND actual_usd=5",
                task,
            )
            out["definer"] = await live.admin.fetch(
                "SELECT p.proname, p.prosecdef, p.proconfig FROM pg_proc p"
                " WHERE p.proname IN ('record_field_task_cost', 'task_cost_history_guard',"
                " 'task_expense_link_guard') ORDER BY p.proname"
            )
        return out

    out = run(target())
    assert out["temp_trigger"] == "42501"
    assert out["forged_rows"] == 0
    assert out["update"] == "allowed"
    assert out["history"] == 1
    flags = {r["proname"]: (r["prosecdef"], r["proconfig"]) for r in out["definer"]}
    assert flags["record_field_task_cost"][0] is True
    assert "search_path=pg_catalog, pg_temp" in (flags["record_field_task_cost"][1] or [])
    assert flags["task_cost_history_guard"][0] is False
    assert flags["task_expense_link_guard"][0] is False


async def _app_conn(live, name: str):
    conn = await asyncpg.connect(live.app_dsn)
    await conn.execute(
        "SELECT set_config('app.current_tenant', $1, false), set_config('app.current_user_id', $2, false)",
        live.tenant,
        live.users[(live.tenant, name)],
    )
    return conn


async def _approved(live):
    task, submitted = await _accepted_and_submitted(live)
    v1 = submitted["current_evidence"]["version"]
    res = await live.handoff(
        task,
        "finding",
        "reviewer",
        {"expected_revision": 2, "action": "approve", "reason": "ok", "evidence_version": v1},
    )
    assert res.status_code == 200, res.text
    return task


def test_the_cost_definer_cannot_be_attached_to_another_relation():
    """Review round 3 of #1460: a temp table's trigger ran the definer and forged other tenants' rows."""

    async def target():
        out = {}
        async with Live() as live:
            conn = await _app_conn(live, "manager")
            try:
                try:
                    await conn.execute(
                        "CREATE TEMP TABLE fx (tenant_id uuid, task_id uuid, actual_cost_usd numeric,"
                        " status text);"
                        " CREATE TRIGGER fx_t AFTER INSERT ON fx FOR EACH ROW"
                        " EXECUTE FUNCTION public.record_field_task_cost();"
                    )
                    out["attach"] = "allowed"
                except asyncpg.PostgresError as exc:
                    out["attach"] = exc.sqlstate
            finally:
                await conn.close()
            acl = await live.admin.fetchrow(
                "SELECT has_function_privilege('public', 'public.record_field_task_cost()', 'EXECUTE')"
                " AS pub_exec,"
                " has_table_privilege('public', 'public.task_cost_history', 'INSERT') AS pub_ins"
            )
            out["public"] = (acl["pub_exec"], acl["pub_ins"])
            # The owner can still attach it, but the body refuses any relation but field_tasks.
            try:
                tx = live.admin.transaction()
                await tx.start()
                await live.admin.execute(
                    "CREATE TEMP TABLE fy (tenant_id uuid, task_id uuid, actual_cost_usd numeric,"
                    " status text);"
                    " CREATE TRIGGER fy_t AFTER INSERT ON fy FOR EACH ROW"
                    " EXECUTE FUNCTION public.record_field_task_cost();"
                )
                try:
                    await live.admin.execute(
                        "INSERT INTO fy VALUES ($1::uuid, gen_random_uuid(), 1, 'x')", live.tenant
                    )
                    out["owner_fire"] = "allowed"
                except asyncpg.PostgresError as exc:
                    out["owner_fire"] = exc.sqlstate
            finally:
                await tx.rollback()
        return out

    out = run(target())
    assert out["attach"] == "42501"  # no EXECUTE: a new trigger on the definer cannot be created
    assert out["public"] == (False, False)
    assert out["owner_fire"] == "42501"  # TG_RELID bound to public.field_tasks


def test_an_operator_planted_in_public_does_not_run_inside_the_definer():
    """Review round 4 of #1460: with CREATE on public, an exact-match varchar operator ran as owner."""

    async def target():
        out = {}
        async with Live() as live:
            app_role = await live._app_role()
            task = str(
                await live.admin.fetchval(
                    "INSERT INTO field_tasks (tenant_id, field_id, task_type, status,"
                    " actual_cost_usd) VALUES ($1::uuid, $2, 'weeding', 'pending', 5)"
                    " RETURNING task_id",
                    live.tenant,
                    live.field,
                )
            )
            await live.admin.execute(f'GRANT CREATE ON SCHEMA public TO "{app_role}"')
            conn = await _app_conn(live, "manager")
            try:
                await conn.execute(
                    "CREATE FUNCTION public.fti_hijack_eq(a varchar, b varchar) RETURNS boolean"
                    " LANGUAGE plpgsql AS $f$ BEGIN"
                    " RAISE EXCEPTION 'hijacked as %', current_user; END $f$;"
                    " CREATE OPERATOR public.= (LEFTARG = varchar, RIGHTARG = varchar,"
                    " FUNCTION = public.fti_hijack_eq);"
                )
                try:
                    async with conn.transaction():
                        await conn.execute(
                            # Cost unchanged, status changed: the definer compares the two
                            # varchar statuses, the comparison the planted operator targets.
                            "UPDATE public.field_tasks SET status='in_progress'"
                            " WHERE task_id=$1::uuid",
                            task,
                        )
                    out["update"] = "allowed"
                except asyncpg.PostgresError as exc:
                    out["update"] = f"{exc.sqlstate}:{exc}"
            finally:
                await conn.close()
                await live.admin.execute(
                    "DROP OPERATOR IF EXISTS public.= (varchar, varchar);"
                    " DROP FUNCTION IF EXISTS public.fti_hijack_eq(varchar, varchar);"
                    f' REVOKE CREATE ON SCHEMA public FROM "{app_role}"'
                )
            out["history"] = await live.admin.fetchval(
                "SELECT count(*) FROM task_cost_history WHERE task_id=$1::uuid"
                " AND status='in_progress'",
                task,
            )
        return out

    out = run(target())
    assert out["update"] == "allowed", out["update"]  # the planted operator never ran as owner
    assert out["history"] == 1


def test_a_function_planted_in_public_does_not_run_in_a_privileged_writers_trigger():
    """Review round 5 of #1460: public.btrim(varchar) ran as postgres inside the close-gate trigger."""

    async def target():
        out = {}
        async with Live() as live:
            app_role = await live._app_role()
            task, _ = await _accepted_and_submitted(live)
            await live.admin.execute(f'GRANT CREATE ON SCHEMA public TO "{app_role}"')
            conn = await _app_conn(live, "manager")
            try:
                await conn.execute(
                    "CREATE FUNCTION public.btrim(v varchar) RETURNS text LANGUAGE plpgsql AS $f$"
                    " BEGIN RAISE EXCEPTION 'hijacked as %', current_user; END $f$;"
                )
            finally:
                await conn.close()
            try:
                try:
                    async with live.admin.transaction():
                        # A privileged writer (migration, backfill) touching a pin task's status.
                        await live.admin.execute(
                            "UPDATE public.field_tasks SET status='in_progress' WHERE task_id=$1::uuid",
                            task,
                        )
                    out["privileged_update"] = "allowed"
                except asyncpg.PostgresError as exc:
                    out["privileged_update"] = f"{exc.sqlstate}:{exc}"
            finally:
                await live.admin.execute(
                    "DROP FUNCTION IF EXISTS public.btrim(varchar);"
                    f' REVOKE CREATE ON SCHEMA public FROM "{app_role}"'
                )
        return out

    out = run(target())
    assert out["privileged_update"] == "allowed", out["privileged_update"]


def test_a_padded_completed_status_is_still_gated():
    """Review round 4 of #1460: ' completed ' (padded) must take the close gate like 'completed'."""

    async def target():
        async with Live() as live:
            task, _ = await _accepted_and_submitted(live)
            return await _as_app(
                live,
                "manager",
                "UPDATE field_tasks SET status=' completed ' WHERE task_id=$1::uuid",
                task,
            )

    assert run(target()) == "SH001"


def test_temp_tables_cannot_shadow_the_inspection_and_cost_tables():
    """Review round 3 of #1460: unpinned search_path let pg_temp tables stand in for the real ones."""

    async def target():
        out = {}
        async with Live() as live:
            task, submitted = await _accepted_and_submitted(live)
            conn = await _app_conn(live, "manager")
            try:
                await conn.execute(
                    "CREATE TEMP TABLE inspection_handoffs AS SELECT * FROM public.inspection_handoffs"
                    " WITH NO DATA;"
                    " CREATE TEMP TABLE inspection_evidence_versions AS"
                    " SELECT * FROM public.inspection_evidence_versions WITH NO DATA;"
                    " CREATE TEMP TABLE task_cost_history AS SELECT * FROM public.task_cost_history"
                    " WITH NO DATA;"
                )
                await conn.execute(
                    "INSERT INTO pg_temp.inspection_handoffs (tenant_id, field_id, task_id, revision,"
                    " action, previous_assignee, assignee, actor)"
                    " VALUES ($1::uuid, $2, $3::uuid, 99, 'approve', '', '', 'x')",
                    live.tenant,
                    live.field,
                    task,
                )
                try:
                    async with conn.transaction():
                        await conn.execute(
                            "UPDATE public.field_tasks SET status='completed' WHERE task_id=$1::uuid",
                            task,
                        )
                    out["close"] = "allowed"
                except asyncpg.PostgresError as exc:
                    out["close"] = exc.sqlstate
                await conn.execute(
                    "UPDATE public.field_tasks SET actual_cost_usd=42 WHERE task_id=$1::uuid", task
                )
            finally:
                await conn.close()
            out["history"] = await live.admin.fetchval(
                "SELECT count(*) FROM public.task_cost_history WHERE task_id=$1::uuid AND actual_usd=42",
                task,
            )
            out["pinned"] = await live.admin.fetch(
                "SELECT proname, proconfig FROM pg_proc WHERE proname = ANY($1::text[]) ORDER BY proname",
                [
                    "field_mgmt_append_only",
                    "inspection_evidence_version_guard",
                    "inspection_handoff_revision_guard",
                    "inspection_handoff_chain_guard",
                    "task_cost_history_guard",
                    "task_expense_link_guard",
                    "record_field_task_cost",
                    "field_task_inspection_close_gate",
                    "field_task_inspection_reopen",
                ],
            )
        return out

    out = run(target())
    assert out["close"] == "SH001"  # the fake temp approval is not read
    assert out["history"] == 1  # the temp task_cost_history did not swallow the row
    assert len(out["pinned"]) == 9
    # No public at all (review round 5 of #1460): a caller-rights trigger runs as whoever writes
    # field_tasks, a superuser migration or the BYPASSRLS jobs role included.
    for row in out["pinned"]:
        assert "search_path=pg_catalog, pg_temp" in (row["proconfig"] or []), row["proname"]


def test_a_direct_handoff_racing_a_close_waits_and_is_refused():
    """Review round 3 of #1460: a direct writer's hand-off raced a close; the task closed under it.

    The service's own route already locks the task; this races a direct INSERT on the shared app role,
    which only the v275 chain guard's FOR UPDATE serialises.
    """

    async def target():
        out = {}
        async with Live() as live:
            task = await _approved(live)
            prior = await live.admin.fetchrow(
                "SELECT h.assignee, h.revision, t.assigned_to FROM inspection_handoffs h"
                " JOIN field_tasks t ON t.task_id = h.task_id WHERE h.task_id=$1::uuid"
                " ORDER BY h.revision DESC LIMIT 1",
                task,
            )
            closer = await _app_conn(live, "manager")
            racer_conn = await _app_conn(live, "manager")
            try:
                tx = closer.transaction()
                await tx.start()
                await closer.execute(
                    "UPDATE public.field_tasks SET status='completed' WHERE task_id=$1::uuid", task
                )

                async def insert_handoff():
                    try:
                        await racer_conn.execute(
                            "INSERT INTO public.inspection_handoffs (tenant_id, field_id, task_id,"
                            " revision, action, previous_assignee, assignee, actor, reason)"
                            " VALUES ($1::uuid, $2, $3::uuid, $4, 'reassign', $5, $6,"
                            " current_setting('app.current_user_id'), 'race')",
                            live.tenant,
                            live.field,
                            task,
                            prior["revision"] + 1,
                            prior["assignee"],
                            str(prior["assigned_to"] or ""),
                        )
                        return "allowed"
                    except asyncpg.PostgresError as exc:
                        return exc.sqlstate

                racer = asyncio.create_task(insert_handoff())
                await asyncio.sleep(1.0)
                out["blocked"] = not racer.done()
                await tx.commit()
                out["racer"] = await asyncio.wait_for(racer, timeout=30)
            finally:
                await closer.close()
                await racer_conn.close()
            row = await live.admin.fetchrow(
                "SELECT t.status, (SELECT action FROM inspection_handoffs h WHERE h.task_id=t.task_id"
                " ORDER BY revision DESC LIMIT 1) AS last FROM field_tasks t WHERE t.task_id=$1::uuid",
                task,
            )
            out["final"] = (row["status"], row["last"])
        return out

    out = run(target())
    assert out["blocked"] is True  # the direct hand-off waited on the task row lock
    assert out["racer"] == "SH008"  # refused once the close committed
    assert out["final"] == ("completed", "approve")


def test_the_bootstrap_scripts_revoke_cost_history_dml_after_their_blanket_grant():
    root = Path(__file__).resolve().parents[1] / "migrations"
    for name in ("bootstrap_postgres.sh", "apply_in_compose.sh"):
        text = (root / name).read_text(encoding="utf-8")
        grant = text.index("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public")
        revoke = text.index(
            "REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON TABLE public.task_cost_history"
        )
        assert revoke > grant, name
        execute = text.index("REVOKE EXECUTE ON FUNCTION public.record_field_task_cost()")
        assert execute > grant, name
    compose = (root / "apply_in_compose.sh").read_text(encoding="utf-8")
    jobs_grant = compose.index(
        'GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO :"jobs_role"'
    )
    tail = compose[jobs_grant:]
    assert "public.task_cost_history FROM %I', :'jobs_role'" in tail
    assert "public.record_field_task_cost() FROM %I', :'jobs_role'" in tail


# ── tenant isolation per table ──────────────────────────────────────────────


def test_rows_of_one_tenant_are_invisible_to_another():
    async def target():
        out = {}
        async with Live() as live:
            task, submitted = await _accepted_and_submitted(live)
            await live.handoff(
                task,
                "finding",
                "reviewer",
                {
                    "expected_revision": 2,
                    "action": "approve",
                    "reason": "ok",
                    "evidence_version": submitted["current_evidence"]["version"],
                },
            )
            await live.patch(task, {"status": "completed", "actual_cost_usd": 12.5})
            entry = await live.ledger(farm=live.farm, field=None)
            link = await live.fm.post(
                f"/internal/field-tasks/farm-book/entries/{entry}/task",
                json={"task_id": task},
                headers=live.headers("manager"),
            )
            out["link"] = link.status_code
            conn = await asyncpg.connect(live.app_dsn)
            try:
                for tenant in (live.tenant, live.other_tenant):
                    async with conn.transaction():
                        await conn.execute(
                            "SELECT set_config('app.current_tenant', $1, true)", tenant
                        )
                        out[tenant] = {
                            t: await conn.fetchval(
                                f"SELECT count(*) FROM {t} WHERE task_id=$1::uuid", task
                            )
                            for t in TABLES
                        }
            finally:
                await conn.close()
            other = live.headers("manager", tenant=live.other_tenant)
            out["other_handoff"] = (
                await live.fm.get(
                    f"/internal/field-tasks/fields/{live.field}/tasks/{task}/handoff",
                    headers=other,
                )
            ).status_code
            out["other_cost"] = (
                await live.fm.get(f"/internal/field-tasks/tasks/{task}/cost-trace", headers=other)
            ).status_code
            out["other_pin"] = (
                await live.fm.get(
                    f"/internal/field-tasks/fields/{live.field}/pins/{live.pin}/inspection-task",
                    headers=other,
                )
            ).status_code
            out["no_token"] = (
                await live.fm.get(
                    f"/internal/field-tasks/tasks/{task}/cost-trace",
                    headers={**live.headers("manager"), "X-Field-Tasks-Token": "wrong"},
                )
            ).status_code
        return out, live.tenant, live.other_tenant

    out, mine, theirs = run(target())
    assert out["link"] == 200
    assert all(n >= 1 for n in out[mine].values()), out[mine]
    assert out[theirs] == dict.fromkeys(TABLES, 0)
    assert (out["other_handoff"], out["other_cost"], out["other_pin"]) == (404, 404, 404)
    assert out["no_token"] == 401


# ── cost trigger and trace ──────────────────────────────────────────────────


def test_the_cost_trigger_records_history_and_the_trace_hides_it_from_workers():
    async def target():
        out = {}
        async with Live() as live:
            task = str(
                await live.admin.fetchval(
                    "INSERT INTO field_tasks (tenant_id, field_id, task_type, status)"
                    " VALUES ($1::uuid, $2, 'spraying', 'pending') RETURNING task_id",
                    live.tenant,
                    live.field,
                )
            )
            r1 = await live.patch(task, {"status": "completed", "actual_cost_usd": 5})
            r2 = await live.patch(
                task, {"status": "completed", "actual_cost_usd": 7.25}, "inspector", "worker"
            )
            r3 = await live.patch(
                task, {"status": "completed", "actual_cost_usd": 7.25}, "inspector", "worker"
            )
            out["patches"] = (r1.status_code, r2.status_code, r3.status_code)
            out["history"] = [
                dict(r)
                for r in await live.admin.fetch(
                    "SELECT changed_by, previous_usd::text AS p, actual_usd::text AS a,"
                    " previous_status, status FROM task_cost_history WHERE task_id=$1::uuid"
                    " ORDER BY change_id",
                    task,
                )
            ]
            trace = await live.fm.get(
                f"/internal/field-tasks/tasks/{task}/cost-trace", headers=live.headers("manager")
            )
            out["trace"] = (trace.status_code, len(trace.json().get("changes", [])))
            out["worker_trace"] = (
                await live.fm.get(
                    f"/internal/field-tasks/tasks/{task}/cost-trace",
                    headers=live.headers("inspector"),
                )
            ).status_code
            out["append_only"] = await _append_only(live, "task_cost_history", task)
            out["manager"] = live.users[(live.tenant, "manager")]
            out["inspector"] = live.users[(live.tenant, "inspector")]
        return out

    out = run(target())
    assert out["patches"] == (200, 200, 200)
    assert out["history"] == [
        {
            "changed_by": out["manager"],
            "p": None,
            "a": "5.00",
            "previous_status": "pending",
            "status": "completed",
        },
        {
            "changed_by": out["inspector"],
            "p": "5.00",
            "a": "7.25",
            "previous_status": "completed",
            "status": "completed",
        },
    ]  # the unchanged replay (r3) wrote no row and no history
    assert out["trace"] == (200, 2)
    assert out["worker_trace"] == 403
    # The app role holds no UPDATE on the history (#1460); the owner's UPDATE hits the trigger.
    assert out["append_only"] == ("42501", "55000")


# ── expense link: field and farm ────────────────────────────────────────────


def test_an_expense_link_needs_the_tasks_farm_and_field():
    async def target():
        out = {}
        async with Live() as live:
            task = str(
                await live.admin.fetchval(
                    "INSERT INTO field_tasks (tenant_id, field_id, task_type, status)"
                    " VALUES ($1::uuid, $2, 'weeding', 'pending') RETURNING task_id",
                    live.tenant,
                    live.field,
                )
            )
            other_task = str(
                await live.admin.fetchval(
                    "INSERT INTO field_tasks (tenant_id, field_id, task_type, status)"
                    " VALUES ($1::uuid, $2, 'weeding', 'pending') RETURNING task_id",
                    live.tenant,
                    live.field,
                )
            )

            async def link(entry, task_id=task, name="manager"):
                res = await live.fm.post(
                    f"/internal/field-tasks/farm-book/entries/{entry}/task",
                    json={"task_id": task_id},
                    headers=live.headers(name),
                )
                return res.status_code, res.json().get("detail")

            out["other_farm"] = await link(await live.ledger(farm=live.other_farm, field=None))
            out["other_field"] = await link(await live.ledger(farm=live.farm, field=live.field2))
            out["income"] = await link(
                await live.ledger(farm=live.farm, field=None, entry_type="income")
            )
            good = await live.ledger(farm=live.farm, field=live.field)
            out["viewer"] = await link(good, name="viewer")
            out["good"] = await link(good)
            out["replay"] = await link(good)
            out["relink"] = await link(good, task_id=other_task)
            correction = await live.ledger(farm=live.farm, field=None, reverses=good)
            out["correction"] = await link(correction)
            trace = await live.fm.get(
                f"/internal/field-tasks/tasks/{task}/cost-trace", headers=live.headers("manager")
            )
            out["trace"] = (
                trace.status_code,
                sorted(e["entry_id"] for e in trace.json()["entries"])
                == sorted([good, correction]),
                trace.json()["expenses_by_currency"],
            )
            # The farm book (platform) filters by the linked task through the link overlay.
            live.platform_user("manager", "manager")
            book = await live.platform.get("/api/v1/farm-book/entries", params={"task_id": task})
            out["book"] = (
                book.status_code,
                sorted(
                    e["entry_id"] for e in book.json().get("items", book.json().get("entries", []))
                ),
                sorted([good, correction]),
            )
            # Negative control: the guard is what refuses the other farm's entry at the table.
            stray = await live.ledger(farm=live.other_farm, field=None)
            conn = await asyncpg.connect(ADMIN_DSN)
            try:
                tx = conn.transaction()
                await tx.start()
                await conn.execute(
                    "ALTER TABLE task_expense_links DISABLE TRIGGER task_expense_link_guard"
                )
                out["control"] = await conn.fetchval(
                    "INSERT INTO task_expense_links (tenant_id, entry_id, task_id, field_id, linked_by)"
                    " VALUES ($1::uuid,$2,$3::uuid,$4,'control') RETURNING entry_id",
                    live.tenant,
                    stray,
                    task,
                    live.field,
                )
                await tx.rollback()
            finally:
                await conn.close()
            out["stray"] = stray
        return out

    out = run(target())
    assert out["other_farm"] == (422, "task_location_mismatch")
    assert out["other_field"] == (422, "task_location_mismatch")
    assert out["income"] == (422, "original_expense_required")
    assert out["viewer"][0] == 403
    assert out["good"] == (200, None)
    assert out["replay"] == (200, None)
    assert out["relink"] == (409, "entry_already_linked")
    assert out["correction"] == (422, "original_expense_required")
    assert out["trace"][:2] == (200, True)
    assert out["trace"][2] == {"YER": "0.00"}  # the expense and its correction cancel
    assert out["book"][0] == 200 and out["book"][1] == out["book"][2], out["book"]
    assert out["control"] == out["stray"]


# ── inspector-only meter gate (platform, reads inspection_handoffs) ─────────


def test_the_meter_gate_admits_the_accepted_inspector_or_a_supervisor_only():
    async def target():
        out = {}
        async with Live() as live:
            if str(PLATFORM) not in sys.path:
                sys.path.insert(0, str(PLATFORM))
            from api.irrigation_observations import IrrigationObservationInput
            from api.task_irrigation_observations import record_observation
            from core.canonical_schemas import UserRole, UserSchema

            task = await live.assign()
            execution = str(uuid.uuid4())
            # The execution is the irrigation service's row; its provenance chain (v190) is not
            # what this test measures, so the owner seeds it with triggers off for this INSERT.
            await live.admin.execute("SET session_replication_role = replica")
            await live.admin.execute(
                """INSERT INTO irrigation_manual_executions
                    (execution_id, tenant_id, field_id, season_id, system_id, recommendation_id,
                     recommendation_digest, execution_mode, state, target_depth_mm, target_volume_m3,
                     valid_from, valid_until, idempotency_key, created_by)
                   VALUES ($1::uuid,$2::uuid,$3,'s','sys','r',repeat('a',64),'manual_measured',
                           'started',10,10,now()-interval '1 day',now()+interval '1 day',$1,'seed')""",
                execution,
                live.tenant,
                live.field,
            )
            await live.admin.execute("SET session_replication_role = DEFAULT")

            def reading():
                return IrrigationObservationInput(
                    observation_id=uuid.uuid4(),
                    execution_id=execution,
                    source="field_inspection",
                    outcome="irrigated",
                    occurred_at=datetime.now(UTC) - timedelta(minutes=5),
                    quantity_method="meter",
                    meter_start_m3=1.0,
                    meter_end_m3=3.0,
                )

            async def record(name, role):
                user = UserSchema(
                    user_id=live.users[(live.tenant, name)],
                    tenant_id=live.tenant,
                    role=UserRole(role),
                    name_ar="u",
                )
                conn = await asyncpg.connect(live.app_dsn)
                try:
                    async with conn.transaction():
                        await conn.execute(
                            "SELECT set_config('app.current_tenant', $1, true),"
                            " set_config('app.current_user_id', $2, true)",
                            live.tenant,
                            user.user_id,
                        )
                        await record_observation(conn, user, task, reading())
                        return 200
                except Exception as exc:  # noqa: BLE001 - the HTTPException status is the result
                    return getattr(exc, "status_code", type(exc).__name__)
                finally:
                    await conn.close()

            out["before_accept"] = await record("inspector", "worker")
            out["other_worker"] = await record("inspector2", "worker")
            out["supervisor"] = await record("manager", "manager")
            await live.handoff(task, "accept", "inspector", {"expected_revision": 0})
            out["after_accept"] = await record("inspector", "worker")
        return out

    out = run(target())
    assert out["before_accept"] == 409
    assert out["other_worker"] == 403
    assert out["supervisor"] == 200
    assert out["after_accept"] == 200
