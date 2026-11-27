"""Native PostgreSQL regressions for the v291 task delivery owner boundary.

Run on a disposable, fully migrated, loopback PostgreSQL database:
  FIELD_TASK_EXECUTION_CERTIFICATION_REQUIRED=1
  TEST_DATABASE_ADMIN_URL=postgresql://...@127.0.0.1:.../...
  pytest -q tests_v9/test_field_task_execution_delivery_live_pg.py

No SQLite, mocked connection, physical device, or agronomic fixture is used. A temporary
NOSUPERUSER NOBYPASSRLS login makes the application writes. Users, fields, pins, and synthetic
photo metadata are seeded by the schema owner, as their own services would seed them. Fixture
rows remain in the disposable database for evidence; the test role and its grants are removed.
The runner must drop its owned database after preserving evidence.

The direct SQL cases prove database constraints, RLS and append-only behavior. Synthetic
upstream receipt dictionaries prove the local receipt contract only, not an HTTP decision
outcome. Actual owner-store cases at the end execute the implementation against PostgreSQL.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import sys
import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import quote, urlsplit, urlunsplit

import pytest

pytestmark = [pytest.mark.integration]
_REQUIRED = os.getenv("FIELD_TASK_EXECUTION_CERTIFICATION_REQUIRED") == "1"
try:
    import asyncpg
except ImportError:
    if _REQUIRED:
        raise
    asyncpg = pytest.importorskip("asyncpg")

ROOT = Path(__file__).resolve().parents[1]
SERVICE = ROOT / "services" / "field-management-service"
if str(SERVICE) not in sys.path:
    sys.path.insert(0, str(SERVICE))

ADMIN_DSN = os.getenv("TEST_DATABASE_ADMIN_URL", "")
TABLES = (
    "field_task_execution_links",
    "field_task_execution_confirmations",
    "field_task_execution_outcome_receipts",
)
JSON_COLUMNS = {"receipt_payload", "actual", "metrics", "upstream_result"}
DUE = datetime(2031, 1, 2, 12, tzinfo=UTC)  # Explicit synthetic scheduling fixture.


async def _probe():
    if not ADMIN_DSN:
        return "TEST_DATABASE_ADMIN_URL is required"
    parts = urlsplit(ADMIN_DSN)
    if parts.hostname not in {"127.0.0.1", "::1", "localhost"} or not parts.path.strip("/"):
        return "the test requires an explicit loopback, disposable database URL"
    try:
        conn = await asyncpg.connect(ADMIN_DSN, timeout=5)
    except Exception as exc:
        return f"database unavailable ({type(exc).__name__})"
    try:
        if not (await conn.fetchval("SELECT version()")).startswith("PostgreSQL "):
            return "a native PostgreSQL server is required"
        if not await conn.fetchval(
            "SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname=current_user"
        ):
            return "TEST_DATABASE_ADMIN_URL must name the disposable schema owner"
        for table in (*TABLES, "inspection_handoffs", "inspection_evidence_versions"):
            if await conn.fetchval("SELECT to_regclass($1)", f"public.{table}") is None:
                return f"the canonical manifest and v291 must be applied ({table} missing)"
    finally:
        await conn.close()
    return ""


_WHY = asyncio.run(_probe())
if _WHY and _REQUIRED:
    raise RuntimeError(f"Required native PostgreSQL certification cannot run: {_WHY}")
pytestmark.append(pytest.mark.skipif(bool(_WHY), reason=f"declared skip, not a pass: {_WHY}"))


def _dsn_for_role(role, password):
    p = urlsplit(ADMIN_DSN)
    host = f"[{p.hostname}]" if ":" in p.hostname else p.hostname
    netloc = f"{quote(role)}:{quote(password)}@{host}"
    if p.port:
        netloc += f":{p.port}"
    return urlunsplit((p.scheme, netloc, p.path, p.query, p.fragment))


def _decoded(row):
    out = dict(row)
    for key in JSON_COLUMNS:
        if isinstance(out.get(key), str):
            out[key] = json.loads(out[key])
    return out


async def _insert(conn, table, values):
    # Only fixed tables/columns from these fixtures enter this helper.
    assert table in {*TABLES, "field_tasks", "inspection_evidence_versions", "inspection_handoffs"}
    columns = list(values)
    args = [json.dumps(values[k]) if k in JSON_COLUMNS else values[k] for k in columns]
    quoted = ",".join(f'"{c}"' for c in columns)
    slots = ",".join("$" + str(i) for i in range(1, len(args) + 1))
    return _decoded(
        await conn.fetchrow(f'INSERT INTO "{table}" ({quoted}) VALUES ({slots}) RETURNING *', *args)
    )


class Case:
    """Owned synthetic rows and actual scoped PostgreSQL connections; no source mocks."""

    async def __aenter__(self):
        from fm_gateway import Caller

        self.admin = await asyncpg.connect(ADMIN_DSN)
        self.role = f"fed_{uuid.uuid4().hex[:14]}"
        password = uuid.uuid4().hex
        await self.admin.execute(
            f'CREATE ROLE "{self.role}" LOGIN NOSUPERUSER NOBYPASSRLS NOINHERIT '
            f"PASSWORD '{password}'"
        )
        self.dsn = _dsn_for_role(self.role, password)
        await self.admin.execute(f'GRANT USAGE ON SCHEMA public TO "{self.role}"')
        await self.admin.execute(f'GRANT SELECT ON ALL TABLES IN SCHEMA public TO "{self.role}"')
        for table in (
            "field_tasks",
            "inspection_handoffs",
            "inspection_evidence_versions",
            *TABLES,
        ):
            await self.admin.execute(f'GRANT INSERT, UPDATE, DELETE ON "{table}" TO "{self.role}"')
        for table in TABLES:
            await self.admin.execute(f'GRANT TRUNCATE ON "{table}" TO "{self.role}"')
        await self.admin.execute(
            f'GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO "{self.role}"'
        )
        self.tenant, self.peer_tenant = str(uuid.uuid4()), str(uuid.uuid4())
        self.users = {}
        for tenant in (self.tenant, self.peer_tenant):
            for name, role in (
                ("manager", "manager"),
                ("inspector", "worker"),
                ("reviewer", "agronomist"),
                ("reviewer2", "agronomist"),
            ):
                uid = await self.admin.fetchval(
                    """INSERT INTO users(email,password_hash,full_name,role,tenant_id,active)
                       VALUES($1,'qualification-only',$2,$3,$4::uuid,true) RETURNING id""",
                    f"{name}.{uuid.uuid4().hex}@example.invalid",
                    name,
                    role,
                    tenant,
                )
                self.users[(tenant, name)] = str(uid)
        self.manager = Caller(self.tenant, self.users[(self.tenant, "manager")], "manager")
        self.inspector = Caller(self.tenant, self.users[(self.tenant, "inspector")], "worker")
        self.reviewer = Caller(self.tenant, self.users[(self.tenant, "reviewer")], "agronomist")
        self.reviewer2 = Caller(self.tenant, self.users[(self.tenant, "reviewer2")], "agronomist")
        self.peer = Caller(self.peer_tenant, self.users[(self.peer_tenant, "manager")], "manager")
        suffix = uuid.uuid4().hex[:12]
        self.field, self.field2, self.foreign_field = [f"fed-{x}-{suffix}" for x in ("a", "b", "x")]
        self.pin, self.pin2, self.foreign_pin = [f"fed-pin-{x}-{suffix}" for x in ("a", "b", "x")]
        for field, tenant in (
            (self.field, self.tenant),
            (self.field2, self.tenant),
            (self.foreign_field, self.peer_tenant),
        ):
            farm = "farm-" + field
            await self.admin.execute(
                "INSERT INTO farms(farm_id,tenant_id,name) VALUES($1::text,$2::uuid,$1::text)",
                farm,
                tenant,
            )
            await self.admin.execute(
                "INSERT INTO fields(field_id,name,farm_id,tenant_id) VALUES($1::text,$1::text,$2,$3::uuid)",
                field,
                farm,
                tenant,
            )
        for pin, field, tenant in (
            (self.pin, self.field, self.tenant),
            (self.pin2, self.field, self.tenant),
            (self.foreign_pin, self.foreign_field, self.peer_tenant),
        ):
            await self.admin.execute(
                """INSERT INTO scouting_pins(pin_id,tenant_id,field_id,lat,lng,issue_category)
                   VALUES($1,$2::uuid,$3,15.3,44.2,'pest')""",
                pin,
                tenant,
                field,
            )
        async with self.connection(self.manager) as conn:
            flags = await conn.fetchrow(
                "SELECT rolsuper,rolbypassrls FROM pg_roles WHERE rolname=current_user"
            )
            assert tuple(flags.values()) == (False, False)
        return self

    async def __aexit__(self, *args):
        # This removes only the randomly named fixture role's grants, never source-owned data.
        try:
            await self.admin.execute(f'DROP OWNED BY "{self.role}"')
            await self.admin.execute(f'DROP ROLE "{self.role}"')
        finally:
            await self.admin.close()

    @asynccontextmanager
    async def connection(self, caller):
        conn = await asyncpg.connect(self.dsn, statement_cache_size=0)
        try:
            async with conn.transaction():
                await conn.execute(
                    """SELECT set_config('app.current_tenant',$1,true),
                              set_config('app.current_user_id',$2,true),
                              set_config('app.current_role',$3,true)""",
                    caller.tenant_id,
                    caller.user_id,
                    caller.role,
                )
                yield conn
        finally:
            await conn.close()

    async def task(self, *, pin=None):
        async with self.connection(self.manager) as conn:
            return await _insert(
                conn,
                "field_tasks",
                {
                    "tenant_id": self.tenant,
                    "field_id": self.field,
                    "task_type": "scouting",
                    "source_scouting_pin_id": pin or self.pin,
                    "assigned_to": self.inspector.user_id,
                    "inspection_initial_assignee": self.inspector.user_id,
                    "inspection_assigned_by": self.manager.user_id,
                    "inspection_due_at": DUE,
                    "recommended_date": DUE.date(),
                    "priority": 3,
                },
            )

    def link_values(self, task, **overrides):
        request = "req_" + uuid.uuid4().hex
        values = {
            "tenant_id": self.tenant,
            "execution_request_id": request,
            "task_id": task["task_id"],
            "field_id": self.field,
            "pin_id": task["source_scouting_pin_id"],
            "operation_type": "field_inspection",
            "decision_id": "dec_" + uuid.uuid4().hex[:20],
            "execution_plan_id": "plan_" + uuid.uuid4().hex,
            "dispatch_authorization_id": "auth_" + uuid.uuid4().hex,
            "correlation_id": str(uuid.uuid4()),
            "assigned_to": self.inspector.user_id,
            "due_at": DUE,
            "priority": 3,
            "request_digest": hashlib.sha256(request.encode()).hexdigest(),
            "adapter_id": "field-inspection-regression",
            "receipt_id": "rec_" + uuid.uuid4().hex,
            "receipt_payload": {
                "task_id": str(task["task_id"]),
                "field_id": self.field,
                "pin_id": task["source_scouting_pin_id"],
            },
            "received_by": self.manager.user_id,
        }
        values.update(overrides)
        return values

    async def link(self, task, **overrides):
        values = self.link_values(task, **overrides)
        async with self.connection(self.manager) as conn:
            return await _insert(conn, TABLES[0], values)

    async def photo(self, pin=None):
        sha = hashlib.sha256(b"explicit synthetic photo byte fixture").hexdigest()
        row = await self.admin.fetchrow(
            """INSERT INTO scout_photo_evidence
               (tenant_id,field_id,pin_id,object_ref,content_sha256,mime_type,size_bytes,
                image_width,image_height,uploaded_by)
               VALUES($1::uuid,$2,$3,$4,$5,'image/png',8,1,1,$6) RETURNING *""",
            self.tenant,
            self.field,
            pin or self.pin,
            f"s3://qualification-fixture/{uuid.uuid4().hex}/{sha}",
            sha,
            self.inspector.user_id,
        )
        return dict(row)

    async def handoff(self, task, action, caller, *, version=None):
        async with self.connection(caller) as conn:
            await conn.execute(
                "SELECT task_id FROM field_tasks WHERE task_id=$1 FOR UPDATE", task["task_id"]
            )
            revision = 1 + await conn.fetchval(
                "SELECT coalesce(max(revision),0) FROM inspection_handoffs WHERE task_id=$1",
                task["task_id"],
            )
            return await _insert(
                conn,
                "inspection_handoffs",
                {
                    "tenant_id": self.tenant,
                    "field_id": self.field,
                    "task_id": task["task_id"],
                    "revision": revision,
                    "action": action,
                    "previous_assignee": self.inspector.user_id,
                    "assignee": self.inspector.user_id,
                    "actor": caller.user_id,
                    "reason": None if action == "accept" else "Synthetic reviewed finding",
                    "evidence_version": version,
                },
            )

    async def version(self, task, *, photo=None):
        async with self.connection(self.inspector) as conn:
            version = 1 + await conn.fetchval(
                "SELECT coalesce(max(version),0) FROM inspection_evidence_versions WHERE task_id=$1",
                task["task_id"],
            )
            photo_id, sha = (
                (photo["evidence_id"], photo["content_sha256"]) if photo else (None, None)
            )
            notes = f"Synthetic inspection notes, version {version}"
            digest = hashlib.sha256(f"{photo_id or ''}|{sha or ''}|{notes}".encode()).hexdigest()
            return await _insert(
                conn,
                "inspection_evidence_versions",
                {
                    "tenant_id": self.tenant,
                    "field_id": self.field,
                    "task_id": task["task_id"],
                    "version": version,
                    "pin_id": task["source_scouting_pin_id"],
                    "photo_evidence_id": photo_id,
                    "photo_content_sha256": sha,
                    "notes": notes,
                    "digest": digest,
                    "recorded_by": self.inspector.user_id,
                },
            )

    async def close(self, task):
        async with self.connection(self.reviewer) as conn:
            await conn.execute(
                "UPDATE field_tasks SET status='completed',completed_at=clock_timestamp() WHERE task_id=$1",
                task["task_id"],
            )

    async def reopen(self, task):
        async with self.connection(self.manager) as conn:
            await conn.execute(
                "UPDATE field_tasks SET status='pending' WHERE task_id=$1", task["task_id"]
            )

    async def reviewed(self, *, photo=None, task=None, link=None, accept=True):
        task = task or await self.task()
        link = link or await self.link(task)
        if accept:
            await self.handoff(task, "accept", self.inspector)
        version = await self.version(task, photo=photo)
        await self.handoff(task, "submit", self.inspector, version=version["version"])
        approval = await self.handoff(task, "approve", self.reviewer, version=version["version"])
        await self.close(task)
        return task, link, version, approval

    def confirmation_values(self, task, link, version, approval, **overrides):
        cid = "confirm_" + uuid.uuid4().hex
        values = {
            "confirmation_id": cid,
            "tenant_id": self.tenant,
            "execution_request_id": link["execution_request_id"],
            "task_id": task["task_id"],
            "field_id": self.field,
            "pin_id": task["source_scouting_pin_id"],
            "handoff_revision": approval["revision"],
            "evidence_version": version["version"],
            "evidence_digest": version["digest"],
            "photo_evidence_id": version["photo_evidence_id"],
            "photo_content_sha256": version["photo_content_sha256"],
            "inspector_id": self.inspector.user_id,
            "reviewer_id": self.reviewer.user_id,
            "verified_by": self.reviewer.user_id,
            "evidence_snapshot_id": "inspection_" + version["digest"][:32],
            "idempotency_key": cid,
            "actual": {"task_id": str(task["task_id"])},
            "metrics": {"inspection_completed": True},
        }
        values.update(overrides)
        return values

    async def confirmation(self, task, link, version, approval, **overrides):
        values = self.confirmation_values(task, link, version, approval, **overrides)
        async with self.connection(self.reviewer) as conn:
            return await _insert(conn, TABLES[1], values)

    def outcome_values(self, link, proof, **overrides):
        oid = "out_" + uuid.uuid4().hex[:20]
        result = {
            "status": "ok",
            "authoritative": True,
            "persisted": True,
            "replay": False,
            "outcome_id": oid,
            "execution_request_id": link["execution_request_id"],
            "execution_plan_id": link["execution_plan_id"],
            "dispatch_authorization_id": link["dispatch_authorization_id"],
            "decision_id": link["decision_id"],
            "receipt_id": link["receipt_id"],
            "verification_state": "verified_success",
            "success": True,
            "evidence_snapshot_id": proof["evidence_snapshot_id"],
            "verified_by": proof["verified_by"],
            "verified_at": datetime.now(UTC).isoformat(),
        }
        result.update(overrides)
        return {
            "tenant_id": self.tenant,
            "confirmation_id": proof["confirmation_id"],
            "execution_request_id": link["execution_request_id"],
            "task_id": proof["task_id"],
            "field_id": self.field,
            "outcome_id": oid,
            "upstream_result": result,
        }

    async def count(self, table, caller=None):
        assert table in {*TABLES, "field_tasks"}
        async with self.connection(caller or self.manager) as conn:
            return await conn.fetchval(f'SELECT count(*) FROM "{table}"')


def test_v291_rls_owner_peer_absent_blank_and_no_secret_storage():
    async def case():
        async with Case() as c:
            task, link, version, approval = await c.reviewed()
            proof = await c.confirmation(task, link, version, approval)
            async with c.connection(c.reviewer) as conn:
                await _insert(conn, TABLES[2], c.outcome_values(link, proof))
            async with c.connection(c.reviewer) as conn:
                flags = await conn.fetch(
                    "SELECT relname,relrowsecurity,relforcerowsecurity FROM pg_class WHERE relname=ANY($1::text[])",
                    list(TABLES),
                )
                assert len(flags) == 3 and all(
                    r["relrowsecurity"] and r["relforcerowsecurity"] for r in flags
                )
                for table in TABLES:
                    assert await c.count(table) == 1
                    assert await c.count(table, c.peer) == 0
                    assert (
                        await conn.fetchval(
                            "SELECT count(*) FROM information_schema.columns WHERE table_name=$1 AND column_name='delivery_token'",
                            table,
                        )
                        == 0
                    )
            # Fresh connection means a genuinely absent GUC, not set_config('', ...).
            for blank in (False, True):
                conn = await asyncpg.connect(c.dsn)
                try:
                    assert (
                        await conn.fetchval("SELECT current_setting('app.current_tenant',true)")
                        is None
                    )
                    if blank:
                        await conn.execute("SELECT set_config('app.current_tenant','',false)")
                    for table in TABLES:
                        assert await conn.fetchval(f'SELECT count(*) FROM "{table}"') == 0
                finally:
                    await conn.close()

    asyncio.run(case())


@pytest.mark.parametrize(
    "bad", ["tenant", "field", "pin", "assignee", "due", "priority", "operation", "token"]
)
def test_v291_link_rejects_misbindings(bad):
    async def case():
        async with Case() as c:
            task = await c.task()
            overrides = {
                "tenant": {"tenant_id": c.peer_tenant},
                "field": {"field_id": c.field2},
                "pin": {"pin_id": c.foreign_pin},
                "assignee": {"assigned_to": c.reviewer.user_id},
                "due": {"due_at": DUE + timedelta(hours=1)},
                "priority": {"priority": 4},
                "operation": {"operation_type": "irrigation"},
                "token": {"receipt_payload": {"nested": {"delivery_token": "must-never-persist"}}},
            }[bad]
            with pytest.raises(asyncpg.PostgresError) as error:
                await c.link(task, **overrides)
            assert error.value.sqlstate in {"23514", "23503", "42501"}
            assert await c.count(TABLES[0]) == 0

    asyncio.run(case())


def test_v291_link_user_scope_and_duplicate_request_task():
    async def case():
        async with Case() as c:
            first, second = await c.task(), await c.task(pin=c.pin2)
            first_values = c.link_values(first)
            with pytest.raises(asyncpg.InsufficientPrivilegeError):
                async with c.connection(c.reviewer) as conn:
                    await _insert(conn, TABLES[0], first_values)
            async with c.connection(c.manager) as conn:
                await _insert(conn, TABLES[0], first_values)
            with pytest.raises(asyncpg.UniqueViolationError):
                await c.link(first)
            with pytest.raises(asyncpg.UniqueViolationError):
                await c.link(second, execution_request_id=first_values["execution_request_id"])
            assert await c.count(TABLES[0]) == 1

    asyncio.run(case())


def test_v291_task_and_link_rollback_together_on_link_rejection():
    async def case():
        async with Case() as c:
            task_id = None
            with pytest.raises(asyncpg.CheckViolationError):
                async with c.connection(c.manager) as conn:
                    task = await _insert(
                        conn,
                        "field_tasks",
                        {
                            "tenant_id": c.tenant,
                            "field_id": c.field,
                            "task_type": "scouting",
                            "source_scouting_pin_id": c.pin,
                            "assigned_to": c.inspector.user_id,
                            "inspection_initial_assignee": c.inspector.user_id,
                            "inspection_assigned_by": c.manager.user_id,
                            "inspection_due_at": DUE,
                            "recommended_date": DUE.date(),
                            "priority": 3,
                        },
                    )
                    task_id = task["task_id"]
                    await _insert(conn, TABLES[0], c.link_values(task, request_digest="bad"))
            assert task_id is not None
            assert await c.count("field_tasks") == 0
            assert await c.count(TABLES[0]) == 0
            assert not await c.admin.fetchval(
                "SELECT EXISTS(SELECT 1 FROM field_tasks WHERE task_id=$1)", task_id
            )

    asyncio.run(case())


@pytest.mark.parametrize(
    "bad",
    [
        "pending",
        "revision",
        "digest",
        "reviewer",
        "inspector",
        "field",
        "task",
        "new_version",
        "old_submit_after_reopen",
        "task_type",
    ],
)
def test_v291_confirmation_requires_completed_current_independent_review(bad):
    async def case():
        async with Case() as c:
            task, link, version, approval = await c.reviewed()
            overrides = {}
            actor = c.reviewer
            if bad == "pending":
                await c.reopen(task)
            elif bad == "revision":
                overrides["handoff_revision"] = approval["revision"] - 1
            elif bad == "digest":
                overrides["evidence_digest"] = "a" * 64
            elif bad == "reviewer":
                actor = c.reviewer2
                overrides.update(reviewer_id=actor.user_id, verified_by=actor.user_id)
            elif bad == "inspector":
                overrides["inspector_id"] = c.manager.user_id
            elif bad == "field":
                overrides["field_id"] = c.field2
            elif bad == "task":
                overrides["task_id"] = str(uuid.uuid4())
            elif bad == "old_submit_after_reopen":
                await c.reopen(task)
                approval = await c.handoff(task, "approve", c.reviewer, version=version["version"])
                # v277 accepts this close, but v291 must demand a new submission after reopen.
                await c.close(task)
            elif bad == "task_type":
                async with c.connection(c.manager) as conn:
                    await conn.execute(
                        "UPDATE field_tasks SET task_type='irrigation' WHERE task_id=$1",
                        task["task_id"],
                    )
            elif bad == "new_version":
                # Existing v274 allows a new version after close. v291 must recheck max(version).
                await c.version(task)
            with pytest.raises(asyncpg.CheckViolationError):
                async with c.connection(actor) as conn:
                    await _insert(
                        conn,
                        TABLES[1],
                        c.confirmation_values(task, link, version, approval, **overrides),
                    )
            assert await c.count(TABLES[1]) == 0

    asyncio.run(case())


def test_v291_current_photo_guard_has_a_rolled_back_negative_control():
    async def case():
        async with Case() as c:
            task, link, version, approval = await c.reviewed()
            await c.photo()  # A source-valid new photo after the old no-photo approval.
            values = c.confirmation_values(task, link, version, approval)
            with pytest.raises(asyncpg.CheckViolationError):
                async with c.connection(c.reviewer) as conn:
                    await _insert(conn, TABLES[1], values)
            tx = c.admin.transaction()
            await tx.start()
            try:
                await c.admin.execute(
                    "ALTER TABLE field_task_execution_confirmations DISABLE TRIGGER field_task_execution_confirmation_guard"
                )
                accepted = await _insert(c.admin, TABLES[1], values)
                assert accepted["confirmation_id"] == values["confirmation_id"]
            finally:
                await tx.rollback()
            assert await c.count(TABLES[1]) == 0
            enabled = await c.admin.fetchval(
                "SELECT tgenabled::text FROM pg_trigger WHERE tgname='field_task_execution_confirmation_guard'"
            )
            assert enabled == "O"

    asyncio.run(case())


def test_v291_stale_snapshot_can_be_superseded_before_terminal_receipt_only():
    async def case():
        async with Case() as c:
            task, link, v1, h1 = await c.reviewed()
            p1 = await c.confirmation(task, link, v1, h1)
            photo = await c.photo()
            await c.reopen(task)
            _, _, v2, h2 = await c.reviewed(photo=photo, task=task, link=link, accept=False)
            p2 = await c.confirmation(task, link, v2, h2)
            assert p2["confirmation_id"] != p1["confirmation_id"]
            assert p2["evidence_version"] == 2 and await c.count(TABLES[1]) == 2
            async with c.connection(c.reviewer) as conn:
                await _insert(conn, TABLES[2], c.outcome_values(link, p2))
            await c.reopen(task)
            _, _, v3, h3 = await c.reviewed(photo=photo, task=task, link=link, accept=False)
            with pytest.raises(
                asyncpg.CheckViolationError, match="execution_outcome_already_recorded"
            ):
                await c.confirmation(task, link, v3, h3)
            assert await c.count(TABLES[1]) == 2 and await c.count(TABLES[2]) == 1

    asyncio.run(case())


@pytest.mark.parametrize(
    "key,value",
    [
        ("persisted", False),
        ("authoritative", False),
        ("status", "pending"),
        ("execution_request_id", "wrong"),
        ("execution_plan_id", "wrong"),
        ("dispatch_authorization_id", "wrong"),
        ("decision_id", "wrong"),
        ("receipt_id", "wrong"),
        ("evidence_snapshot_id", "wrong"),
        ("verified_by", "wrong"),
        ("verification_state", "unverified"),
        ("success", False),
        ("verified_at", ""),
    ],
)
def test_v291_outcome_receipt_requires_matching_authoritative_ack(key, value):
    async def case():
        async with Case() as c:
            task, link, version, approval = await c.reviewed()
            proof = await c.confirmation(task, link, version, approval)
            with pytest.raises(asyncpg.CheckViolationError):
                async with c.connection(c.reviewer) as conn:
                    await _insert(conn, TABLES[2], c.outcome_values(link, proof, **{key: value}))
            assert await c.count(TABLES[2]) == 0

    asyncio.run(case())


def test_v291_links_confirmations_receipts_are_append_only_even_with_dml_grants():
    async def case():
        async with Case() as c:
            task, link, version, approval = await c.reviewed()
            proof = await c.confirmation(task, link, version, approval)
            async with c.connection(c.reviewer) as conn:
                await _insert(conn, TABLES[2], c.outcome_values(link, proof))
            for table in TABLES:
                async with c.connection(c.reviewer) as conn:
                    assert (
                        await conn.execute(f'UPDATE "{table}" SET tenant_id=tenant_id')
                        == "UPDATE 0"
                    )
                    assert await conn.execute(f'DELETE FROM "{table}"') == "DELETE 0"
                for command in (
                    f'UPDATE "{table}" SET tenant_id=tenant_id WHERE tenant_id=$1::uuid',
                    f'DELETE FROM "{table}" WHERE tenant_id=$1::uuid',
                ):
                    with pytest.raises(asyncpg.ObjectNotInPrerequisiteStateError):
                        async with c.admin.transaction():
                            await c.admin.execute(command, c.tenant)
                assert await c.count(table) == 1
            with pytest.raises(asyncpg.ObjectNotInPrerequisiteStateError):
                async with c.connection(c.reviewer) as conn:
                    await conn.execute("TRUNCATE " + ",".join(TABLES))
            for table in TABLES:
                assert await c.count(table) == 1

    asyncio.run(case())


def _store_binding(case, **overrides):
    from fm_execution_tasks import ExecutionBinding

    synthetic_task = {"task_id": uuid.uuid4(), "source_scouting_pin_id": case.pin}
    values = case.link_values(synthetic_task, **overrides)
    return ExecutionBinding.from_record(values)


def test_owner_store_dual_receive_commits_one_task_and_one_link_with_separate_readback():
    async def case():
        from fm_execution_task_store import PostgresExecutionStore

        async with Case() as c:
            binding = _store_binding(c)
            barrier, pids = asyncio.Barrier(2), set()

            @asynccontextmanager
            async def simultaneous(caller):
                async with c.connection(caller) as conn:
                    pids.add(conn.get_server_pid())
                    await asyncio.wait_for(barrier.wait(), timeout=10)
                    yield conn

            racing_store = PostgresExecutionStore(connection_factory=simultaneous)
            results = await asyncio.wait_for(
                asyncio.gather(
                    racing_store.ensure_task(c.manager, binding),
                    racing_store.ensure_task(c.manager, binding),
                ),
                timeout=20,
            )
            assert len(pids) == 2
            assert {r["task_id"] for r in results} == {binding.task_id}
            assert await c.count("field_tasks") == await c.count(TABLES[0]) == 1
            store = PostgresExecutionStore(connection_factory=c.connection)
            replay = await store.ensure_task(c.manager, binding)
            readback = await store.readback(c.manager, binding)
            assert replay["task_id"] == readback["task_id"] == binding.task_id
            assert readback["receipt_payload"] == binding.receipt_payload()
            assert await store.get_link(c.peer, binding.execution_request_id) is None
            assert await store.list_links(c.peer, c.field) == []
            listed = await store.list_links(c.manager, c.field)
            assert len(listed) == 1
            assert listed[0]["assignee_name"] == "inspector"

    asyncio.run(case())


def test_owner_store_refuses_to_adopt_existing_manual_pin_task():
    async def case():
        from fastapi import HTTPException
        from fm_execution_task_store import PostgresExecutionStore

        async with Case() as c:
            manual = await c.task()
            binding = _store_binding(c)
            store = PostgresExecutionStore(connection_factory=c.connection)
            with pytest.raises(HTTPException) as error:
                await store.ensure_task(c.manager, binding)
            assert error.value.status_code == 409
            assert error.value.detail["code"] == "inspection_pin_already_has_another_task"
            assert await c.count("field_tasks") == 1 and await c.count(TABLES[0]) == 0
            assert str(
                await c.admin.fetchval(
                    "SELECT task_id FROM field_tasks WHERE tenant_id=$1::uuid AND source_scouting_pin_id=$2",
                    c.tenant,
                    c.pin,
                )
            ) == str(manual["task_id"])

    asyncio.run(case())


def test_owner_store_actual_link_check_failure_rolls_back_the_new_task():
    async def case():
        from fastapi import HTTPException
        from fm_execution_task_store import PostgresExecutionStore

        async with Case() as c:
            # A deliberate DB-boundary fault. binding_from_source normally computes valid SHA-256.
            binding = _store_binding(c, request_digest="bad")
            store = PostgresExecutionStore(connection_factory=c.connection)
            with pytest.raises(HTTPException) as error:
                await store.ensure_task(c.manager, binding)
            assert error.value.status_code == 409
            assert error.value.detail["code"] == "inspection_execution_store_conflict"
            assert await c.count("field_tasks") == await c.count(TABLES[0]) == 0
            assert not await c.admin.fetchval(
                "SELECT EXISTS(SELECT 1 FROM field_tasks WHERE task_id=$1::uuid)", binding.task_id
            )

    asyncio.run(case())


def test_owner_store_request_rebinding_and_mismatched_readback_are_refused():
    async def case():
        from dataclasses import replace

        from fastapi import HTTPException
        from fm_execution_task_store import PostgresExecutionStore

        async with Case() as c:
            binding = _store_binding(c)
            store = PostgresExecutionStore(connection_factory=c.connection)
            await store.ensure_task(c.manager, binding)
            with pytest.raises(HTTPException) as error:
                await store.ensure_task(c.manager, replace(binding, request_digest="c" * 64))
            assert error.value.status_code == 409
            with pytest.raises(HTTPException) as error:
                await store.readback(c.manager, replace(binding, assigned_to=c.manager.user_id))
            assert error.value.status_code == 409
            assert await c.count("field_tasks") == await c.count(TABLES[0]) == 1

    asyncio.run(case())


def test_owner_store_current_proof_supersedes_stale_snapshot_and_preserves_outcome_history():
    async def case():
        from fastapi import HTTPException
        from fm_execution_task_store import PostgresExecutionStore

        async with Case() as c:
            # The existing decision execute gate requires owner/manager. This manager is
            # independent from the assigned inspector; creation and review need not be distinct.
            c.reviewer = c.manager
            binding = _store_binding(c)
            store = PostgresExecutionStore(connection_factory=c.connection)
            link = await store.ensure_task(c.manager, binding)
            task = dict(
                await c.admin.fetchrow(
                    "SELECT * FROM field_tasks WHERE task_id=$1::uuid", binding.task_id
                )
            )
            await c.reviewed(task=task, link=link)
            with pytest.raises(HTTPException) as error:
                await store.read_execution_proof(c.tenant, binding.execution_request_id)
            assert error.value.status_code == 409  # Approval is not a committed confirmation.
            proof1 = await store.prepare_confirmation(c.manager, binding.task_id, c.field)
            read = await store.read_execution_proof(c.tenant, binding.execution_request_id)
            # Cross-owner contract: the real owner confirmation key must fit the decision
            # owner's canonical outcome_record column unchanged (v79 VARCHAR(80)).
            outcome_key_limit = await c.admin.fetchval(
                "SELECT character_maximum_length FROM information_schema.columns "
                "WHERE table_schema='public' AND table_name='outcome_record' "
                "AND column_name='idempotency_key'"
            )
            stored_key = await c.admin.fetchval(
                "SELECT idempotency_key FROM field_task_execution_confirmations "
                "WHERE tenant_id=$1::uuid AND confirmation_id=$2",
                c.tenant,
                proof1["confirmation_id"],
            )
            assert outcome_key_limit == 80
            assert stored_key == proof1["idempotency_key"] == read["idempotency_key"]
            assert 0 < len(stored_key) <= outcome_key_limit
            assert read["confirmation_id"] == proof1["confirmation_id"]
            assert read["actual"] == proof1["actual"] and read["metrics"] == proof1["metrics"]
            assert read["reviewer_id"] == c.manager.user_id != read["inspector_id"]
            assert datetime.fromisoformat(read["observed_at"]).tzinfo is not None
            assert await c.count(TABLES[1]) == 1 and await c.count(TABLES[2]) == 0

            photo = await c.photo()
            with pytest.raises(HTTPException) as error:
                await store.read_execution_proof(c.tenant, binding.execution_request_id)
            assert error.value.status_code == 409
            with pytest.raises(HTTPException) as error:
                await store.prepare_confirmation(c.manager, binding.task_id, c.field)
            assert error.value.status_code == 409
            assert await c.count(TABLES[1]) == 1

            await c.reopen(task)
            await c.reviewed(photo=photo, task=task, link=link, accept=False)
            proof2 = await store.prepare_confirmation(c.manager, binding.task_id, c.field)
            assert proof2["confirmation_id"] != proof1["confirmation_id"]
            assert proof2["evidence_version"] == 2 and await c.count(TABLES[1]) == 2
            result = c.outcome_values(link, proof2)["upstream_result"]
            receipt = await store.save_outcome(c.manager, proof2, result)
            replay = await store.save_outcome(c.manager, proof2, {**result, "replay": True})
            assert receipt["outcome_id"] == replay["outcome_id"] == result["outcome_id"]
            assert receipt["confirmation_id"] == proof2["confirmation_id"]

            await c.reopen(task)
            await c.reviewed(photo=photo, task=task, link=link, accept=False)
            with pytest.raises(HTTPException) as error:
                await store.prepare_confirmation(c.manager, binding.task_id, c.field)
            assert error.value.status_code == 409
            assert error.value.detail["code"] == "inspection_outcome_already_recorded"
            async with c.connection(c.manager) as conn:
                saved = _decoded(
                    await conn.fetchrow(
                        "SELECT * FROM field_task_execution_outcome_receipts WHERE tenant_id=$1::uuid",
                        c.tenant,
                    )
                )
            assert saved["confirmation_id"] == proof2["confirmation_id"]
            assert saved["upstream_result"] == result
            assert await c.count(TABLES[1]) == 2 and await c.count(TABLES[2]) == 1

    asyncio.run(case())
