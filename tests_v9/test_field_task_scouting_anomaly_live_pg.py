"""Vegetation anomaly -> stored ground-scouting task, once per request (live PG, W1-20, v282).

Findings remote-7 / scout-5: vegetation-analysis-service's ground-verification bridge asked for a
scouting task at a route no service served, so no anomaly could reach ``verification_requested``.
field-management-service, the owner of ``field_tasks``, now serves
``POST/GET /internal/field-tasks/scouting``. This file drives the real code end to end against a
migrated Postgres through a NOBYPASSRLS login role, never a fake connection:

* the vegetation anomaly comes from the anomaly engine (``detect_signals``), shaped as the detect
  route stores it;
* the vegetation bridge (``ground_verification_bridge.py``) sends it, with its service token and
  tenant assertion, over HTTP into field-management-service's FastAPI app;
* the stored row is read back by the schema owner.

Acceptance: the anomaly becomes one stored task with a task_id; a replay (sequential, and five
concurrent copies) returns the same task and writes nothing; the same key with another body and
a second key for the same anomaly are refused; another tenant can neither write a task on this
tenant's field nor list it; an assertion bound to another path is refused. Negative controls
show the v282 unique index and check constraint are what refuse a duplicate key and a keyless
anomaly task at the database, inside rolled-back transactions.
"""

from __future__ import annotations

import asyncio
import importlib.util
import os
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import pytest

pytestmark = [pytest.mark.integration]

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
FIELD_MGMT_MAIN = ROOT / "services" / "field-management-service" / "main.py"
VEGETATION = ROOT / "services" / "vegetation-analysis-service"
DSN = os.getenv(
    "TEST_DATABASE_URL", "postgresql://sahool_test:test_password@127.0.0.1:5433/sahool_test"
)
ADMIN_DSN = os.getenv("TEST_DATABASE_ADMIN_URL", DSN)
AGENT_TOKEN = "scouting-live-" + uuid.uuid4().hex
ASSERTION_KEY = "scouting-live-assertion-key-" + uuid.uuid4().hex
PATH = "/internal/field-tasks/scouting"


async def _probe() -> str:
    try:
        conn = await asyncpg.connect(ADMIN_DSN, timeout=5)
    except Exception as exc:  # noqa: BLE001 - any failure means "no database here"
        return f"{type(exc).__name__}: {exc}"
    try:
        if await conn.fetchval("SELECT to_regclass('public.field_tasks')") is None:
            return "schema not migrated (field_tasks missing)"
        if not await conn.fetchval(
            "SELECT count(*) = 1 FROM information_schema.columns"
            " WHERE table_name = 'field_tasks' AND column_name = 'scouting_idempotency_key'"
        ):
            return "schema not migrated (v282 missing)"
        if not await conn.fetchval(
            "SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname = current_user"
        ):
            return "TEST_DATABASE_ADMIN_URL must name the schema owner (it seeds fields)"
    finally:
        await conn.close()
    return ""


_WHY = asyncio.run(_probe())
if _WHY and _CERTIFICATION_REQUIRED:
    raise RuntimeError(
        f"FIELD_TASK_CERTIFICATION_REQUIRED=1 but the live database is unusable: {_WHY}"
    )
pytestmark.append(pytest.mark.skipif(bool(_WHY), reason=f"declared skip (not a pass): {_WHY}"))


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod  # dataclasses resolve their module while the class is built
    spec.loader.exec_module(mod)
    return mod


def _with_credentials(dsn: str, user: str, password: str) -> str:
    parts = urlsplit(dsn)
    host = parts.hostname or "127.0.0.1"
    netloc = f"{user}:{password}@{host}" + (f":{parts.port}" if parts.port else "")
    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))


class Live:
    """Two tenants with a field each, field-management wired to a NOBYPASSRLS role."""

    def __init__(self, monkeypatch):
        self.mp = monkeypatch
        self.tenant = str(uuid.uuid4())
        self.other_tenant = str(uuid.uuid4())
        self.role = None
        self.app_dsn = DSN

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
            self.role = f"fst_{uuid.uuid4().hex[:10]}"
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
        assert (flags["rolsuper"], flags["rolbypassrls"]) == (False, False), (
            "field-management must run as a NOBYPASSRLS role here"
        )
        suffix = uuid.uuid4().hex[:8]
        self.field, self.foreign_field = f"fst-f1-{suffix}", f"fst-fx-{suffix}"
        for farm, field, tenant in (
            (f"fst-farm-{suffix}", self.field, self.tenant),
            (f"fst-farmx-{suffix}", self.foreign_field, self.other_tenant),
        ):
            await self.admin.execute(
                "INSERT INTO farms (farm_id, tenant_id, name) VALUES ($1, $2::uuid, $1)",
                farm,
                tenant,
            )
            await self.admin.execute(
                "INSERT INTO fields (field_id, name, farm_id, tenant_id)"
                " VALUES ($1, $1, $2, $3::uuid)",
                field,
                farm,
                tenant,
            )
        env = {
            "DATABASE_URL": self.app_dsn,
            "SAHOOL_AGENT_TOKEN": AGENT_TOKEN,
            "SAHOOL_ENV": "development",
            "FIELD_SERVICE_ALLOWED_CALLERS": "vegetation-analysis-service,remote-sensing-workspace-bff",
            "FIELD_SERVICE_TENANT_ASSERTION_KEY": ASSERTION_KEY,
            "FIELD_SERVICE_TENANT_ASSERTION_KEY_ID": "current",
            "TASK_SERVICE_URL": "http://field-management",
        }
        for name, value in env.items():
            self.mp.setenv(name, value)
        self.mp.delenv("FIELD_SERVICE_ASSERTION_REDIS_URL", raising=False)
        fm = _load("field_mgmt_scouting_live_main", FIELD_MGMT_MAIN)
        transport = httpx.ASGITransport(app=fm.app, raise_app_exceptions=False)
        self.fm = httpx.AsyncClient(transport=transport, base_url="http://field-management")
        original = httpx.AsyncClient

        class ToFieldManagement(original):
            def __init__(self, *args, **kwargs):
                kwargs["transport"] = transport
                kwargs.pop("trust_env", None)
                super().__init__(*args, **kwargs)

        # The bridge's own HTTP client, routed into the owner's app (no network, no mock reply).
        self.mp.setattr(httpx, "AsyncClient", ToFieldManagement)
        if str(VEGETATION) not in sys.path:
            sys.path.append(str(VEGETATION))
        self.engine = _load("anomaly_engine_scouting_live", VEGETATION / "anomaly_engine.py")
        self.bridge = _load(
            "ground_bridge_scouting_live", VEGETATION / "ground_verification_bridge.py"
        ).GroundVerificationBridge()
        return self

    async def __aexit__(self, *exc):
        try:
            await self.fm.aclose()
        finally:
            try:
                for table in ("field_tasks", "fields", "farms"):
                    await self.admin.execute(
                        f"DELETE FROM {table} WHERE tenant_id = ANY($1::uuid[])",
                        [self.tenant, self.other_tenant],
                    )
            finally:
                if self.role:
                    await self.admin.execute(
                        f'DROP OWNED BY "{self.role}"; DROP ROLE "{self.role}"'
                    )
                await self.admin.close()

    def anomaly(self, *, observation: str = "obs_current", pct: str = "-22", tenant=None):
        """A signal anomaly as the detect route stores it (routers/anomalies.py)."""
        signal = self.engine.detect_signals(
            field_id=self.field,
            indicator="ndvi",
            comparisons=[
                {
                    "baseline_run_ref": "urn:sahool:processing-run:run_demo",
                    "baseline_type": "same_phenological_stage",
                    "primary_observation_ref": f"urn:sahool:observation:{observation}",
                    "deviation": "-0.12",
                    "deviation_percent": pct,
                    "expected_confidence": "0.75",
                    "sample_size": 4,
                }
            ],
            now=datetime(2026, 11, 16, 8, 0, tzinfo=UTC),
        )
        assert len(signal) == 1, "the engine must flag this deviation"
        return {
            **signal[0].to_dict(),
            "tenant_id": tenant or self.tenant,
            "field_id": self.field,
            "season_id": "sea-2026",
            "geometry_ref": None,
            "status": "detected",
        }

    async def send(self, anomaly, key, tenant=None):
        return await self.bridge.create_scouting_task(
            anomaly=anomaly, tenant_id=tenant or self.tenant, idempotency_key=key
        )

    async def rows(self, anomaly_ref):
        return await self.admin.fetch(
            "SELECT * FROM field_tasks WHERE anomaly_ref = $1 ORDER BY created_at", anomaly_ref
        )

    def service_headers(self, tenant, *, method="GET", path=PATH, caller=None):
        from shared.security.service_tenant_assertion import create_tenant_assertion

        caller = caller or "remote-sensing-workspace-bff"
        request_id = str(uuid.uuid4())
        return {
            "X-Agent-Token": AGENT_TOKEN,
            "X-Service-Name": caller,
            "X-Tenant-Id": tenant,
            "X-Request-Id": request_id,
            "X-Tenant-Assertion": create_tenant_assertion(
                ASSERTION_KEY, caller, tenant, method=method, path=path, request_id=request_id
            ),
        }


def _key(anomaly) -> str:
    # The detect and verification-request routes' key (routers/anomalies.py).
    import hashlib

    return hashlib.sha256(f"{anomaly['anomaly_ref']}|verification".encode()).hexdigest()


def test_a_vegetation_anomaly_becomes_one_stored_task_and_a_replay_does_not_duplicate(
    monkeypatch,
):
    async def scenario():
        async with Live(monkeypatch) as live:
            anomaly = live.anomaly()
            first = await live.send(anomaly, _key(anomaly))
            assert first.persisted is True, first
            task_id = first.task_ref.removeprefix("urn:sahool:task:")
            assert str(uuid.UUID(task_id)) == task_id, f"a real task id: {first.task_ref}"
            rows = await live.rows(anomaly["anomaly_ref"])
            assert len(rows) == 1, f"one stored task, got {len(rows)}"
            row = rows[0]
            assert str(row["task_id"]) == task_id, "the reply names the stored row"
            assert (str(row["tenant_id"]), row["field_id"], row["season_id"]) == (
                live.tenant,
                live.field,
                "sea-2026",
            ), dict(row)
            assert (row["task_type"], row["status"], row["priority"]) == (
                "scouting",
                "pending",
                2,
            ), f"a pending scouting task, high severity => priority 2: {dict(row)}"
            assert row["requested_by_service"] == "vegetation-analysis-service", dict(row)
            assert row["source_event_type"] == "vegetation.signal_anomaly", dict(row)
            assert row["scouting_idempotency_key"] == _key(anomaly), dict(row)
            assert row["verification_deadline"] is not None, "the deadline travels with the task"

            replay = await live.send(anomaly, _key(anomaly))
            assert replay.task_ref == first.task_ref, "a replay names the same task"
            assert replay.raw["replayed"] is True, replay.raw
            assert len(await live.rows(anomaly["anomaly_ref"])) == 1, "a replay writes nothing"

    asyncio.run(scenario())


def test_concurrent_copies_of_one_request_store_one_task(monkeypatch):
    async def scenario():
        async with Live(monkeypatch) as live:
            anomaly = live.anomaly(observation="obs_concurrent")
            results = await asyncio.gather(*(live.send(anomaly, _key(anomaly)) for _ in range(5)))
            refs = {r.task_ref for r in results}
            assert len(refs) == 1, f"five copies, one task: {refs}"
            assert sum(1 for r in results if r.raw["replayed"] is False) == 1, (
                "exactly one copy created the task; the others replayed it"
            )
            assert len(await live.rows(anomaly["anomaly_ref"])) == 1, "one row in the table"

    asyncio.run(scenario())


def test_a_reused_key_or_a_second_key_for_the_anomaly_is_refused(monkeypatch):
    async def scenario():
        async with Live(monkeypatch) as live:
            anomaly = live.anomaly(observation="obs_conflict")
            first = await live.send(anomaly, _key(anomaly))
            changed = {**anomaly, "severity": "low"}
            with pytest.raises(RuntimeError, match="task_service_rejected:409"):
                await live.send(changed, _key(anomaly))
            with pytest.raises(RuntimeError, match="task_service_rejected:409"):
                await live.send(anomaly, "another-key-" + uuid.uuid4().hex)
            rows = await live.rows(anomaly["anomaly_ref"])
            assert len(rows) == 1, f"still one task, got {len(rows)}"
            assert rows[0]["priority"] == 2, "the stored task was not rewritten by the conflict"
            assert first.task_ref.endswith(str(rows[0]["task_id"])), first.task_ref

    asyncio.run(scenario())


def test_tenants_are_isolated_and_the_assertion_is_bound_to_the_route(monkeypatch):
    async def scenario():
        async with Live(monkeypatch) as live:
            anomaly = live.anomaly(observation="obs_tenant")
            first = await live.send(anomaly, _key(anomaly))
            # Another tenant naming this tenant's field: the field is invisible to it.
            foreign = live.anomaly(observation="obs_foreign", tenant=live.other_tenant)
            with pytest.raises(RuntimeError, match="task_service_rejected:404"):
                await live.send(foreign, _key(foreign), tenant=live.other_tenant)
            assert await live.rows(foreign["anomaly_ref"]) == [], "no task for the other tenant"

            params = {"field_id": live.field, "season_id": "sea-2026"}
            mine = await live.fm.get(PATH, params=params, headers=live.service_headers(live.tenant))
            assert mine.status_code == 200, mine.text
            assert [i["task_ref"] for i in mine.json()["items"]] == [first.task_ref], mine.json()
            assert mine.json()["items"][0]["anomaly_ref"] == anomaly["anomaly_ref"], mine.json()
            theirs = await live.fm.get(
                PATH, params=params, headers=live.service_headers(live.other_tenant)
            )
            assert theirs.status_code == 200, theirs.text
            assert theirs.json()["items"] == [], "another tenant lists nothing on this field"

            # A GET-bound assertion does not authorize a POST.
            misbound = await live.fm.post(
                PATH,
                json={
                    "anomaly_ref": anomaly["anomaly_ref"],
                    "field_id": live.field,
                    "season_id": "sea-2026",
                },
                headers={
                    **live.service_headers(live.tenant, method="GET"),
                    "Idempotency-Key": "k" * 64,
                },
            )
            assert misbound.status_code == 403, misbound.text

    asyncio.run(scenario())


def test_negative_controls_the_v280_index_and_check_are_what_refuse_at_the_database(monkeypatch):
    async def scenario():
        async with Live(monkeypatch) as live:
            a = live.admin
            insert = (
                "INSERT INTO field_tasks (tenant_id, field_id, task_type, anomaly_ref,"
                " scouting_idempotency_key, scouting_request_digest)"
                " VALUES ($1::uuid, $2, 'scouting', $3, $4, $5)"
            )
            digest = "0" * 64
            key = "nc-key-" + uuid.uuid4().hex
            # With the index: a second row for the same key is refused.
            tx = a.transaction()
            await tx.start()
            try:
                await a.execute(
                    insert, live.tenant, live.field, "urn:sahool:anomaly:nc1", key, digest
                )
                with pytest.raises(asyncpg.UniqueViolationError):
                    await a.execute(
                        insert, live.tenant, live.field, "urn:sahool:anomaly:nc2", key, digest
                    )
            finally:
                await tx.rollback()
            # Control: without it (dropped inside a rolled-back transaction) the duplicate passes.
            tx = a.transaction()
            await tx.start()
            try:
                await a.execute("DROP INDEX field_tasks_scouting_idempotency_uq")
                await a.execute(
                    insert, live.tenant, live.field, "urn:sahool:anomaly:nc1", key, digest
                )
                await a.execute(
                    insert, live.tenant, live.field, "urn:sahool:anomaly:nc2", key, digest
                )
            finally:
                await tx.rollback()
            # The check: an anomaly task needs its key and digest, and is never a pin task.
            tx = a.transaction()
            await tx.start()
            try:
                with pytest.raises(asyncpg.CheckViolationError):
                    await a.execute(
                        insert, live.tenant, live.field, "urn:sahool:anomaly:nc3", None, None
                    )
            finally:
                await tx.rollback()
            tx = a.transaction()
            await tx.start()
            try:
                await a.execute(
                    "ALTER TABLE field_tasks DROP CONSTRAINT field_task_anomaly_scope_ck"
                )
                await a.execute(
                    insert, live.tenant, live.field, "urn:sahool:anomaly:nc3", None, None
                )
            finally:
                await tx.rollback()
            assert (
                await a.fetchval(
                    "SELECT count(*) FROM field_tasks WHERE tenant_id = $1::uuid", live.tenant
                )
                == 0
            ), "the controls left no row behind"

    asyncio.run(scenario())
