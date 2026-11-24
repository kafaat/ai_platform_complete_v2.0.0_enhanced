"""Opt-in inspection bridge on real owner PostgreSQL and real vegetation SQLite.

The fixture reuses the existing inspection owner's migrated database and genuine
gateway identity/token checks. No database or authorization function is mocked.
Only transports and the vegetation backend are injected: FM's actual sender
reaches the actual receiver through ASGI. The PostgreSQL schema owner seeds rows
owned by auth/scout-ingest and fixture field geometry; runtime requests use the
NOBYPASSRLS role. SQLite evidence is not a PostgreSQL anomaly-store certificate.
"""

from __future__ import annotations

import asyncio
import importlib
import importlib.util
import json
import sys
import uuid
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path

import pytest
from test_field_task_inspection_live_pg import (
    _CERTIFICATION_REQUIRED,
    _WHY,
    ADMIN_DSN,
    FIELD_MGMT_MAIN,
    TOKEN,
    Live,
    asyncpg,
    httpx,
)

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(bool(_WHY), reason=f"declared skip (not a pass): {_WHY}"),
]

ROOT = Path(__file__).resolve().parents[1]
VEGETATION = ROOT / "services" / "vegetation-analysis-service"
AGENT_TOKEN = "bridge-live-agent-" + uuid.uuid4().hex
ASSERTION_KEY = "bridge-live-field-assertion-" + uuid.uuid4().hex
CALLBACK_TOKEN = "bridge-live-callback-" + uuid.uuid4().hex
CALLBACK_KEY = "bridge-live-verification-assertion-" + uuid.uuid4().hex
BRIDGE_TABLES = (
    "scouting_verification_outbox",
    "scouting_verification_assessments",
    "scouting_verification_versions",
    "scouting_verification_links",
)


def _module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def run(coro):
    return asyncio.run(coro)


class BridgeLive(Live):
    """Shared fixture for success and independent counterexample tests.

    On entry task_a and task_b exist, both are pending and no inspection review,
    link or assessment exists. HTTP helpers return actual Response objects.
    """

    def __init__(self, monkeypatch, tmp_path):
        super().__init__()
        self.mp = monkeypatch
        self.tmp_path = tmp_path
        self.anomaly_by_task = {}
        self.last_link_body = None
        self.last_assessment_body = None
        self.link_id = None
        self.delivery_id = None

    async def __aenter__(self):
        probe = await asyncpg.connect(ADMIN_DSN)
        try:
            for table in BRIDGE_TABLES:
                exists = await probe.fetchval("SELECT to_regclass($1)", f"public.{table}")
                if exists is None:
                    reason = f"candidate bridge migration missing: {table}"
                    if _CERTIFICATION_REQUIRED:
                        raise RuntimeError(reason)
                    pytest.skip(reason)
        finally:
            await probe.close()
        await super().__aenter__()
        self.task_a = await self.make_anomaly_task()
        self.anomaly_ref = self.anomaly_by_task[self.task_a]
        self.task_b = await self.assign()
        self.original_a = await self.task_record(self.task_a)
        return self

    async def _seed(self):
        await super()._seed()
        self.geometry = {
            "type": "Polygon",
            "coordinates": [
                [[44.19, 15.29], [44.21, 15.29], [44.21, 15.31], [44.19, 15.31], [44.19, 15.29]]
            ],
        }
        await self.admin.execute(
            "UPDATE fields SET geometry=$1::jsonb WHERE tenant_id=$2::uuid AND field_id=$3",
            json.dumps(self.geometry),
            self.tenant,
            self.field,
        )
        self.season_id = str(uuid.uuid4())
        self.season_event_id = str(uuid.uuid4())
        self.photo_id = await self.photo("a" * 64)
        await self.admin.execute(
            "INSERT INTO season_records (id,tenant_id,field_id,observed_at_from,observed_at_to,"
            "trust_status,accepted_by,accepted_at,logbook_image_ref) "
            "VALUES ($1::uuid,$2::uuid,$3,$4,$4,'accepted',$5,now(),'s3://fixture/logbook')",
            self.season_id,
            self.tenant,
            self.field,
            date.today(),
            self.users[(self.tenant, "reviewer")],
        )
        await self.admin.execute(
            "INSERT INTO scout_photo_season_link_events "
            "(event_id,tenant_id,field_id,pin_id,season_id,action,actor_id) "
            "VALUES ($1::uuid,$2::uuid,$3,$4,$5::uuid,'link',$6)",
            self.season_event_id,
            self.tenant,
            self.field,
            self.pin,
            self.season_id,
            self.users[(self.tenant, "reviewer")],
        )
        for name in ("manager", "reviewer", "inspector", "inspector2"):
            await self.admin.execute(
                "INSERT INTO farm_access_grants (tenant_id,user_id,farm_id,granted_by) "
                "VALUES ($1::uuid,$2,$3,'fixture-owner')",
                self.tenant,
                self.users[(self.tenant, name)],
                self.farm,
            )

    async def _wire(self):
        # Live may create a broad temporary role for legacy inspection tests.
        # This bridge must not acquire the auth owner's farm-grant write powers.
        app_role = await self._app_role()
        quoted_role = '"' + app_role.replace('"', '""') + '"'
        await self.admin.execute(
            "REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON TABLE public.farm_access_grants "
            f"FROM {quoted_role};"
            f"GRANT SELECT ON TABLE public.farm_access_grants TO {quoted_role};"
        )
        check = await asyncpg.connect(self.app_dsn)
        try:
            self.grant_privileges = {
                privilege: await check.fetchval(
                    "SELECT has_table_privilege(current_user,'public.farm_access_grants',$1)",
                    privilege,
                )
                for privilege in ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE")
            }
        finally:
            await check.close()
        assert self.grant_privileges == {
            "SELECT": True,
            "INSERT": False,
            "UPDATE": False,
            "DELETE": False,
            "TRUNCATE": False,
        }
        env = {
            "DATABASE_URL": self.app_dsn,
            "FIELD_TASKS_SERVICE_TOKEN": TOKEN,
            "SAHOOL_AGENT_TOKEN": AGENT_TOKEN,
            "SAHOOL_ENV": "development",
            "FIELD_SERVICE_ALLOWED_CALLERS": "vegetation-analysis-service",
            "FIELD_SERVICE_TENANT_ASSERTION_KEY": ASSERTION_KEY,
            "FIELD_SERVICE_TENANT_ASSERTION_KEY_ID": "current",
            "FM_SCOUTING_VERIFICATION_ENABLED": "1",
            "VEGETATION_VERIFICATION_BRIDGE_ENABLED": "1",
            "VEGETATION_VERIFICATION_URL": "http://vegetation",
            "TASK_SERVICE_CALLBACK_TOKEN": CALLBACK_TOKEN,
            "VEGETATION_VERIFICATION_TENANT_ASSERTION_KEY": CALLBACK_KEY,
            "VEGETATION_VERIFICATION_TENANT_ASSERTION_KEY_ID": "current",
        }
        for name, value in env.items():
            self.mp.setenv(name, value)
        self.mp.delenv("FIELD_SERVICE_ASSERTION_REDIS_URL", raising=False)
        self.fm_main = _module("field_mgmt_verification_live_main", FIELD_MGMT_MAIN)
        self.fm = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.fm_main.app, raise_app_exceptions=False),
            base_url="http://field-management",
            timeout=30,
        )
        self.mp.syspath_prepend(str(VEGETATION))
        from anomaly_runtime import AnomalyStoreFacade
        from anomaly_store import AnomalyStore
        from fastapi import FastAPI

        self.anomaly_store = AnomalyStore(str(self.tmp_path / "bridge-anomalies.sqlite3"))
        self.receiver = _module(
            "vegetation_verification_live_router", VEGETATION / "routers" / "verification.py"
        )
        self.mp.setattr(self.receiver, "_store", AnomalyStoreFacade(self.anomaly_store))
        self.vegetation_app = FastAPI()
        self.vegetation_app.include_router(self.receiver.router)
        self.vegetation_http = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.vegetation_app, raise_app_exceptions=False),
            base_url="http://vegetation",
            timeout=30,
        )
        self.fm_verification = importlib.import_module("fm_verification")
        from fm_verification_client import VegetationVerificationClient

        self.remote_client = VegetationVerificationClient(self.vegetation_http)
        self.mp.setattr(self.fm_verification, "remote_client", self.remote_client)

    async def make_anomaly_task(self, *, season_id=None, geometry_ref=None):
        from shared.security.service_tenant_assertion import create_tenant_assertion

        anomaly_ref = f"urn:sahool:anomaly:bridge_{uuid.uuid4().hex}"
        key = "bridge-dispatch-" + uuid.uuid4().hex
        self.anomaly_store.upsert_detected(
            {
                "anomaly_ref": anomaly_ref,
                "tenant_id": self.tenant,
                "field_id": self.field,
                "season_id": season_id or self.season_id,
                "geometry_ref": geometry_ref,
                "status": "detected",
                "primary_observation_ref": "urn:sahool:observation:fixture",
            }
        )
        self.anomaly_store.reserve_verification(
            anomaly_ref, expected_version=1, idempotency_key=key, tenant_id=self.tenant
        )
        target = "/internal/field-tasks/scouting"
        request_id = uuid.uuid4().hex
        response = await self.fm.post(
            target,
            json={
                "anomaly_ref": anomaly_ref,
                "field_id": self.field,
                "season_id": season_id or self.season_id,
                "geometry_ref": geometry_ref,
                "priority": "medium",
                "reason_codes": ["SYNTHETIC_SIGNAL_FOR_BRIDGE_TEST"],
            },
            headers={
                "X-Agent-Token": AGENT_TOKEN,
                "X-Tenant-Id": self.tenant,
                "X-Service-Name": "vegetation-analysis-service",
                "X-Request-Id": request_id,
                "Idempotency-Key": key,
                "X-Tenant-Assertion": create_tenant_assertion(
                    ASSERTION_KEY,
                    "vegetation-analysis-service",
                    self.tenant,
                    method="POST",
                    path=target,
                    request_id=request_id,
                ),
            },
        )
        assert response.status_code == 201, response.text
        task_id = response.json()["task_id"]
        self.anomaly_store.attach_verification_task(
            anomaly_ref,
            expected_version=2,
            idempotency_key=key,
            task_ref=f"urn:sahool:task:{task_id}",
            tenant_id=self.tenant,
        )
        self.anomaly_by_task[task_id] = anomaly_ref
        return task_id

    async def context(
        self, *, task=None, inspection=None, name="reviewer", season_binding="accepted_record"
    ):
        return await self.fm.get(
            f"/internal/field-tasks/fields/{self.field}/tasks/{task or self.task_a}/verification-context",
            params={
                "inspection_task_id": inspection or self.task_b,
                "season_binding": season_binding,
            },
            headers=self.headers(name),
        )

    async def link(self, *, task=None, body=None, name="reviewer"):
        if body is None:
            context = await self.context(task=task, name=name)
            assert context.status_code == 200, context.text
            body = {
                "command_id": str(uuid.uuid4()),
                "inspection_task_id": self.task_b,
                "season_binding": "accepted_record",
                "expected_revision": context.json()["link_revision"],
                "expected_context_digest": context.json()["context_digest"],
                "reason": "Explicit owner-reviewed fixture link",
            }
        self.last_link_body = dict(body)
        response = await self.fm.post(
            f"/internal/field-tasks/fields/{self.field}/tasks/{task or self.task_a}/verification-links",
            json=body,
            headers=self.headers(name),
        )
        if response.status_code == 200:
            self.link_id = response.json()["link_id"]
        return response

    async def approve_inspection(self):
        accepted = await self.handoff(self.task_b, "accept", "inspector", {"expected_revision": 0})
        assert accepted.status_code == 200, accepted.text
        submitted = await self.handoff(
            self.task_b,
            "finding",
            "inspector",
            {
                "expected_revision": accepted.json()["revision"],
                "action": "submit",
                "reason": "Measured the stated signal at the inspection site",
                "notes": "Fixture observation; does not establish a causal diagnosis",
                "photo_evidence_id": self.photo_id,
            },
        )
        assert submitted.status_code == 200, submitted.text
        approved = await self.handoff(
            self.task_b,
            "finding",
            "reviewer",
            {
                "expected_revision": submitted.json()["revision"],
                "action": "approve",
                "reason": "Reviewed the current photo and notes",
                "evidence_version": submitted.json()["current_evidence"]["version"],
            },
        )
        assert approved.status_code == 200, approved.text
        self.approved = approved.json()
        return self.approved

    async def assess(self, *, link_id=None, body=None, name="reviewer"):
        if body is None:
            state = await self.state(self.task_b, name)
            revision = await self.admin.fetchval(
                "SELECT revision FROM scouting_verification_links WHERE link_id=$1::uuid",
                link_id or self.link_id,
            )
            body = {
                "command_id": str(uuid.uuid4()),
                "link_revision": revision,
                "expected_inspection_revision": state["revision"],
                "evidence_version": state["current_evidence"]["version"],
                "verification_result": "confirmed",
                "protocol": "manual-signal-field-check/v1",
                "coverage": "anomaly_target_reviewed",
                "observations": "Signal observed in fixture",
                "coverage_basis": "Explicit test protocol; no automatic extrapolation from a point",
                "limitations": "Synthetic local acceptance fixture, not agronomic evidence",
                "reason_codes": ["FIELD_CHECK_DOCUMENTED"],
            }
        self.last_assessment_body = dict(body)
        response = await self.fm.post(
            f"/internal/field-tasks/fields/{self.field}/verification-links/{link_id or self.link_id}/assessments",
            json=body,
            headers=self.headers(name),
        )
        if response.status_code == 200:
            self.delivery_id = response.json()["delivery_id"]
            self.assessment_id = response.json()["assessment_id"]
        return response

    async def deliver(self, *, delivery_id=None, name="reviewer"):
        return await self.fm.post(
            f"/internal/field-tasks/fields/{self.field}/verification-deliveries/"
            f"{delivery_id or self.delivery_id}/deliver",
            headers=self.headers(name),
        )

    async def task_record(self, task):
        row = await self.admin.fetchrow(
            "SELECT task_id,source_scouting_pin_id,anomaly_ref,status,completed_at "
            "FROM field_tasks WHERE tenant_id=$1::uuid AND task_id=$2::uuid",
            self.tenant,
            task,
        )
        return dict(row)

    @asynccontextmanager
    async def app_connection(self, name="reviewer"):
        from fm_gateway import Caller, caller_connection

        role = {"reviewer": "agronomist", "manager": "manager", "inspector": "worker"}[name]
        async with caller_connection(
            Caller(self.tenant, self.users[(self.tenant, name)], role)
        ) as conn:
            yield conn

    async def __aexit__(self, *exc):
        try:
            await self.fm.aclose()
            await self.vegetation_http.aclose()
        finally:
            try:
                # Schema-owner cleanup is isolated to this fixture's tenants.
                # No application assertion runs while the append-only guards are off.
                await self.admin.execute("SET session_replication_role=replica")
                for table in (
                    *BRIDGE_TABLES,
                    "inspection_handoffs",
                    "inspection_evidence_versions",
                    "task_expense_links",
                    "task_cost_history",
                    "farm_ledger_entries",
                    "irrigation_manual_execution_events",
                    "irrigation_manual_executions",
                    "field_tasks",
                    "scout_photo_season_link_events",
                    "scout_photo_evidence",
                    "season_records",
                    "scouting_pins",
                    "farm_access_grants",
                    "fields",
                    "farms",
                    "users",
                ):
                    await self.admin.execute(
                        f"DELETE FROM {table} WHERE tenant_id=ANY($1::uuid[])",
                        [self.tenant, self.other_tenant],
                    )
                await self.admin.execute("SET session_replication_role=DEFAULT")
            finally:
                if self.role:
                    await self.admin.execute(
                        f'DROP OWNED BY "{self.role}"; DROP ROLE "{self.role}"'
                    )
                await self.admin.close()


def test_real_owner_context_review_outbox_delivery_and_replay(monkeypatch, tmp_path):
    async def target():
        async with BridgeLive(monkeypatch, tmp_path) as live:
            context = await live.context()
            assert context.status_code == 200, context.text
            assert context.json()["scope"]["target"] == "field_signal"
            assert context.json()["scope"]["site_is_representative_of_target"] == "not_inferred"
            linked = await live.link()
            assert linked.status_code == 200, linked.text
            assert (await live.link(body=live.last_link_body)).json()["replayed"] is True
            approved = await live.approve_inspection()
            assert approved["evidence_approved"] is True
            assert (
                await live.admin.fetchval(
                    "SELECT count(*) FROM scouting_verification_outbox WHERE tenant_id=$1::uuid",
                    live.tenant,
                )
                == 0
            )
            before_b = await live.task_record(live.task_b)
            assessment = await live.assess()
            assert assessment.status_code == 200, assessment.text
            assert assessment.json()["delivery_state"] == "pending"
            assert assessment.json()["training_label_approved"] is False
            assert assessment.json()["execution_verified"] is False
            assert assessment.json()["diagnosis"] is None
            assert (
                live.anomaly_store.get(live.anomaly_ref, tenant_id=live.tenant)["aggregate_version"]
                == 3
            )
            replay = await live.assess(body=live.last_assessment_body)
            assert replay.status_code == 200 and replay.json()["replayed"] is True
            delivery = await live.deliver()
            assert delivery.status_code == 200, delivery.text
            assert delivery.json()["state"] == "delivered", delivery.text
            remote = live.anomaly_store.get(live.anomaly_ref, tenant_id=live.tenant)
            assert remote["status"] == "confirmed" and remote["aggregate_version"] == 4
            assert remote["task_ref"] == f"urn:sahool:task:{live.task_a}"
            assert (await live.deliver()).json() == delivery.json()
            assert live.anomaly_store.get(live.anomaly_ref, tenant_id=live.tenant) == remote
            assert await live.task_record(live.task_a) == live.original_a
            assert await live.task_record(live.task_b) == before_b
            assert before_b["source_scouting_pin_id"] == live.pin
            assert before_b["anomaly_ref"] is None
            assert live.original_a["source_scouting_pin_id"] is None
            async with live.app_connection() as conn:
                for table in BRIDGE_TABLES:
                    assert (
                        await conn.fetchval(
                            f"SELECT count(*) FROM {table} WHERE tenant_id=$1::uuid", live.tenant
                        )
                        == 1
                    )

    run(target())


def test_assessment_and_outbox_roll_back_together_on_actual_insert_failure(monkeypatch, tmp_path):
    async def target():
        async with BridgeLive(monkeypatch, tmp_path) as live:
            assert (await live.link()).status_code == 200
            await live.approve_inspection()
            # A real SQL trigger fault, scoped by tenant, proves transactionality.
            function = f"bridge_reject_outbox_{uuid.uuid4().hex[:12]}"
            await live.admin.execute(
                f"CREATE FUNCTION {function}() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN "
                f"IF NEW.tenant_id='{live.tenant}'::uuid THEN RAISE EXCEPTION 'local outbox fault' "
                "USING ERRCODE='23514'; END IF; RETURN NEW; END $$;"
                f"CREATE TRIGGER {function} BEFORE INSERT ON scouting_verification_outbox "
                f"FOR EACH ROW EXECUTE FUNCTION {function}();"
            )
            try:
                response = await live.assess()
                assert response.status_code == 409, response.text
                for table in ("scouting_verification_assessments", "scouting_verification_outbox"):
                    assert (
                        await live.admin.fetchval(
                            f"SELECT count(*) FROM {table} WHERE tenant_id=$1::uuid", live.tenant
                        )
                        == 0
                    )
                assert (
                    live.anomaly_store.get(live.anomaly_ref, tenant_id=live.tenant)[
                        "aggregate_version"
                    ]
                    == 3
                )
            finally:
                await live.admin.execute(
                    f"DROP TRIGGER {function} ON scouting_verification_outbox; DROP FUNCTION {function}();"
                )

    run(target())


def test_bridge_link_does_not_relax_the_existing_pin_and_anomaly_guards(monkeypatch, tmp_path):
    async def target():
        async with BridgeLive(monkeypatch, tmp_path) as live:
            assert (await live.link()).status_code == 200
            async with live.app_connection() as conn:
                with pytest.raises(asyncpg.PostgresError) as reparent:
                    async with conn.transaction():
                        await conn.execute(
                            "UPDATE field_tasks SET source_scouting_pin_id=$1 "
                            "WHERE tenant_id=$2::uuid AND task_id=$3::uuid",
                            live.pin,
                            live.tenant,
                            live.task_a,
                        )
                assert reparent.value.sqlstate == "SH003"
                with pytest.raises(asyncpg.CheckViolationError) as hybrid:
                    async with conn.transaction():
                        await conn.execute(
                            "INSERT INTO field_tasks (tenant_id,field_id,task_type,status,"
                            "source_scouting_pin_id,anomaly_ref,scouting_idempotency_key,"
                            "scouting_request_digest,season_id) "
                            "VALUES ($1::uuid,$2,'scouting','pending',$3,$4,$5,repeat('a',64),$6)",
                            live.tenant,
                            live.field,
                            live.pin,
                            "urn:sahool:anomaly:hybrid_" + uuid.uuid4().hex,
                            "hybrid-operation-" + uuid.uuid4().hex,
                            live.season_id,
                        )
                assert hybrid.value.constraint_name == "field_task_anomaly_scope_ck"
            assert await live.task_record(live.task_a) == live.original_a
            assert (await live.task_record(live.task_b))["anomaly_ref"] is None

    run(target())
