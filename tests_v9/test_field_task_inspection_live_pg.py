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
import importlib.util
import os
import sys
import uuid
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import pytest

pytestmark = [pytest.mark.integration]

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
if _WHY and os.getenv("FIELD_TASK_CERTIFICATION_REQUIRED") == "1":
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
            app = await conn.execute(
                f"UPDATE {table} SET task_id=task_id WHERE task_id=$1::uuid", task
            )
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
    assert out["append_only"] == ("UPDATE 0", "55000")


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
