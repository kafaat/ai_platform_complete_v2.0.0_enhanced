"""F-D04 — a model promotion never serves without an external ack, and leaves the queue, live PG.

The legacy promotion lane had three faults, measured here on PostgreSQL with the real writer
(``phase_runtime_store.persist_phase10_learning_outputs``) under a NOSUPERUSER / NOBYPASSRLS
role and the real worker (``phase_runtime_workers.run_model_registry_once``):

1. the writer upserted ``model_serving_aliases_runtime`` without a status on decision
   ``promote``, so the v108 column default wrote the alias ``active`` with no acknowledgement
   from any serving backend;
2. the worker's claim filter was ``decision='promote'`` with no terminal state, so in the
   default deployed configuration (``MODEL_SERVING_ENABLED`` unset, docker-compose.v9.yml) the
   same blocked row was claimed again on every cycle;
3. with serving enabled, the same promotion was requested again (``_publish_nats``) on every
   cycle.

Only the NATS publish is replaced (by a recorder): it is the network side effect being counted,
not the database. The database is the DSN's own when it is already migrated (CI applies the
manifest before this job); otherwise the module builds a throwaway database with the canonical
MANIFEST runner and drops it at the end. Each test works under its own tenant, whose rows are
deleted at the end, with the restricted role (NOLOGIN, entered by ``SET ROLE``) dropped too. A
re-claim is seen on the row itself: a claim and its release each rewrite the row, so its
``xmin`` moves; a row left alone by a cycle keeps it.

Run: ``TEST_DATABASE_ADMIN_URL=postgresql://<superuser>@host:port/<db> pytest -m integration
<this file>``. ``FD04_CERTIFICATION_REQUIRED=1`` turns any skip into a failure.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import unquote, urlsplit, urlunsplit

import pytest

pytestmark = [pytest.mark.integration]

# Switch read before any import: on a certifying runner a missing dependency must fail the
# module, not importorskip it into a green skip (certification-switch-before-importorskip).
_REQUIRED = os.getenv("FD04_CERTIFICATION_REQUIRED") == "1"

try:
    import asyncpg
except ImportError:
    if _REQUIRED:
        raise
    asyncpg = pytest.importorskip("asyncpg", reason="asyncpg is not installed")

_ROOT = Path(__file__).resolve().parents[1]
_PLATFORM = _ROOT / "services" / "sahool-platform"
_DSN = os.getenv("TEST_DATABASE_ADMIN_URL") or ""
if not _DSN and _REQUIRED:
    raise RuntimeError(
        "FD04_CERTIFICATION_REQUIRED=1 without TEST_DATABASE_ADMIN_URL: the job claims a "
        "certification with no database to certify on."
    )

pytestmark.append(pytest.mark.skipif(not _DSN, reason="needs TEST_DATABASE_ADMIN_URL (superuser)"))

_ALIAS = "yield-production"
_TABLES = (
    "model_promotion_history_runtime",
    "model_serving_aliases_runtime",
    "model_versions_runtime",
)
_TENANTS: list[uuid.UUID] = []


def _dsn_for(db: str) -> str:
    return urlunsplit(urlsplit(_DSN)._replace(path=f"/{db}"))


def _apply_manifest(db: str) -> None:
    """The canonical runner (scripts/ci/apply_migration_manifest.sh) on the throwaway database."""
    parts = urlsplit(_DSN)
    env = dict(os.environ, PGPASSWORD=unquote(parts.password or ""))
    proc = subprocess.run(
        [
            "bash",
            "scripts/ci/apply_migration_manifest.sh",
            "--host",
            parts.hostname or "localhost",
            "--port",
            str(parts.port or 5432),
            "--user",
            unquote(parts.username or ""),
            "--db",
            db,
        ],
        cwd=_ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=900,
        check=False,
    )
    assert proc.returncode == 0, (
        f"manifest on {db} failed:\n{proc.stdout[-2000:]}\n{proc.stderr[-4000:]}"
    )


@pytest.fixture(scope="module")
def migrated_db():
    """(dsn, role): a migrated database and a NOLOGIN NOSUPERUSER NOBYPASSRLS role on it."""
    role = f"fd04_app_{uuid.uuid4().hex[:8]}"
    throwaway: str | None = None

    async def migrated(dsn: str) -> bool:
        conn = await asyncpg.connect(dsn)
        try:
            return (
                await conn.fetchval("SELECT to_regclass('model_promotion_history_runtime')")
                is not None
            )
        finally:
            await conn.close()

    async def create_db(db: str) -> None:
        admin = await asyncpg.connect(_DSN)
        try:
            await admin.execute(f'CREATE DATABASE "{db}" TEMPLATE template0')
        finally:
            await admin.close()

    async def create_role(dsn: str) -> None:
        conn = await asyncpg.connect(dsn)
        try:
            await conn.execute(f'CREATE ROLE "{role}" NOLOGIN NOSUPERUSER NOBYPASSRLS')
            for table in _TABLES:
                await conn.execute(f'GRANT SELECT, INSERT, UPDATE ON {table} TO "{role}"')
        finally:
            await conn.close()

    async def teardown(dsn: str) -> None:
        conn = await asyncpg.connect(dsn)
        try:
            if throwaway is None and _TENANTS:
                for table in _TABLES:
                    await conn.execute(
                        f"DELETE FROM {table} WHERE tenant_id = ANY($1::uuid[])",  # noqa: S608
                        _TENANTS,
                    )
            if await conn.fetchval("SELECT 1 FROM pg_roles WHERE rolname=$1", role):
                await conn.execute(f'DROP OWNED BY "{role}"')
                await conn.execute(f'DROP ROLE "{role}"')
        finally:
            await conn.close()
        if throwaway is not None:
            admin = await asyncpg.connect(_DSN)
            try:
                await admin.execute(f'DROP DATABASE IF EXISTS "{throwaway}" WITH (FORCE)')
            finally:
                await admin.close()

    dsn = _DSN
    try:
        if not asyncio.run(migrated(dsn)):
            throwaway = f"fd04_{uuid.uuid4().hex[:10]}"
            asyncio.run(create_db(throwaway))
            dsn = _dsn_for(throwaway)
            _apply_manifest(throwaway)
        asyncio.run(create_role(dsn))
        yield dsn, role
    finally:
        asyncio.run(teardown(dsn))


def _platform():
    if str(_PLATFORM) not in sys.path:
        sys.path.insert(0, str(_PLATFORM))
    from api import phase_runtime_store, phase_runtime_workers

    return phase_runtime_store, phase_runtime_workers


class Live:
    """Owner pool for seeding, measuring and the worker; the restricted pool for the writer.

    The worker claims across tenants before binding each one's GUC, so it runs on the owner DSN
    as the deployed worker runs on the BYPASSRLS jobs role. The writer runs on the app role.
    """

    def __init__(self, monkeypatch, migrated_db):
        self.mp = monkeypatch
        self.dsn, self.role = migrated_db
        self.tenant = uuid.uuid4()
        _TENANTS.append(self.tenant)
        self.published: list[tuple[str, dict]] = []

    async def __aenter__(self):
        role = self.role

        async def as_app_role(conn):
            await conn.execute(f'SET ROLE "{role}"')

        self.owner = await asyncpg.create_pool(self.dsn, min_size=1, max_size=2)
        self.app_pool = await asyncpg.create_pool(
            self.dsn, min_size=1, max_size=2, setup=as_app_role
        )
        self.store, self.workers = _platform()

        async def record(subject, payload, *, msg_id=None):
            self.published.append((subject, payload))

        self.mp.setattr(self.workers, "_publish_nats", record)
        self.mp.delenv("MODEL_SERVING_ENABLED", raising=False)
        self.mp.delenv("MODEL_SERVING_BACKEND_URL", raising=False)
        self.mp.setenv("PHASE_RUNTIME_PERSISTENCE_REQUIRED", "true")
        return self

    async def __aexit__(self, *exc):
        await self.app_pool.close()
        await self.owner.close()

    async def persist(self, promotion: dict, *, model_id: str | None = None):
        request = SimpleNamespace(
            headers={"x-tenant-id": str(self.tenant)},
            app=SimpleNamespace(state=SimpleNamespace(db_pool=self.app_pool)),
        )
        champion = None
        if model_id:
            champion = {
                "model_id": model_id,
                "model_name": "yield",
                "version": model_id,
                "task": "yield_forecast",
                "artifact_uri": f"s3://models/{model_id}",
                "artifact_hash": f"sha256:{model_id}",
            }
        outputs = {"model_registry_runtime": {"champion": champion, "serving_promotion": promotion}}
        return await self.store.persist_phase10_learning_outputs(request, outputs)

    async def cycle(self, promotion_id: str) -> bool:
        """One worker cycle; True when it claimed this promotion row (its xmin moved)."""
        before = await self._xmin(promotion_id)
        await self.workers.run_model_registry_once(self.owner)
        return await self._xmin(promotion_id) != before

    async def _xmin(self, promotion_id: str) -> str:
        async with self.owner.acquire() as conn:
            return await conn.fetchval(
                "SELECT xmin::text FROM model_promotion_history_runtime "
                "WHERE tenant_id=$1 AND promotion_id=$2",
                self.tenant,
                promotion_id,
            )

    async def alias(self, alias: str = _ALIAS):
        async with self.owner.acquire() as conn:
            return await conn.fetchrow(
                "SELECT model_id, status, promotion_id FROM model_serving_aliases_runtime "
                "WHERE tenant_id=$1 AND alias=$2",
                self.tenant,
                alias,
            )

    async def promotion(self, promotion_id: str):
        async with self.owner.acquire() as conn:
            return await conn.fetchrow(
                "SELECT * FROM model_promotion_history_runtime "
                "WHERE tenant_id=$1 AND promotion_id=$2",
                self.tenant,
                promotion_id,
            )


def _promotion(pid: str, *, target: str = "m-b", decision: str = "promote") -> dict:
    return {
        "promotion_id": pid,
        "alias": _ALIAS,
        "decision": decision,
        "target_model_id": target,
        "previous_model_id": "m-a",
        "challenger_model_id": target,
        "metric_delta": {"mae": -0.4},
        "reasons": ["challenger_better"],
    }


def _run(coro):
    return asyncio.run(coro)


def test_a_promoted_alias_is_written_pending_external_ack_not_active(monkeypatch, migrated_db):
    async def body():
        async with Live(monkeypatch, migrated_db) as live:
            assert await live.persist(_promotion("p-1"), model_id="m-b") == {"persisted": True}
            row = await live.alias()
            assert row is not None and row["model_id"] == "m-b"
            assert row["status"] == "pending_external_ack", (
                f"the alias is written {row['status']!r} with no acknowledgement from a "
                "serving backend"
            )

    _run(body())


def test_a_promotion_over_a_serving_alias_does_not_make_the_new_model_active(
    monkeypatch, migrated_db
):
    async def body():
        async with Live(monkeypatch, migrated_db) as live:
            async with live.owner.acquire() as conn:
                await conn.execute(
                    "INSERT INTO model_serving_aliases_runtime "
                    "(tenant_id, alias, model_id, promotion_id, status) "
                    "VALUES ($1,$2,'m-a','p-0','active')",
                    live.tenant,
                    _ALIAS,
                )
            await live.persist(_promotion("p-2"), model_id="m-b")
            row = await live.alias()
            assert (row["model_id"], row["status"]) == ("m-b", "pending_external_ack")

    _run(body())


def test_the_default_disabled_configuration_does_not_reclaim_the_row_every_cycle(
    monkeypatch, migrated_db
):
    async def body():
        async with Live(monkeypatch, migrated_db) as live:
            await live.persist(_promotion("p-3"), model_id="m-b")
            assert await live.cycle("p-3") is True
            assert await live.cycle("p-3") is False, "the blocked promotion was claimed again"
            assert await live.cycle("p-3") is False
            row = await live.promotion("p-3")
            assert (row["status"], row["status_reason"]) == ("blocked", "model_serving_disabled")
            assert row["claim_token"] is None
            assert live.published == []
            assert (await live.alias())["status"] == "pending_external_ack"

    _run(body())


def test_an_enabled_promotion_is_requested_once_and_waits_for_the_ack(monkeypatch, migrated_db):
    async def body():
        async with Live(monkeypatch, migrated_db) as live:
            monkeypatch.setenv("MODEL_SERVING_ENABLED", "true")
            monkeypatch.setenv("MODEL_SERVING_BACKEND_URL", "http://serving.invalid")
            await live.persist(_promotion("p-4"), model_id="m-b")
            assert await live.cycle("p-4") is True
            assert await live.cycle("p-4") is False, "the requested promotion was claimed again"
            mine = [p for s, p in live.published if p.get("promotion_id") == "p-4"]
            assert len(mine) == 1, f"the promotion was requested {len(mine)} times"
            row = await live.promotion("p-4")
            assert (row["status"], row["status_reason"]) == ("requested", None)
            alias = await live.alias()
            assert (alias["model_id"], alias["status"]) == ("m-b", "pending_external_ack")

    _run(body())


def test_a_promotion_whose_publish_fails_stays_queued_and_is_sent_on_recovery(
    monkeypatch, migrated_db
):
    """Devin on #1587: 'requested' was committed before the publish, so a broker outage lost it.

    The row is now marked requested only after the publish succeeds; a failed publish releases
    the claim with the row still pending, and the next cycle sends it, under a stable msg id.
    """

    async def body():
        async with Live(monkeypatch, migrated_db) as live:
            monkeypatch.setenv("MODEL_SERVING_ENABLED", "true")
            monkeypatch.setenv("MODEL_SERVING_BACKEND_URL", "http://serving.invalid")
            sent: list[tuple[str, dict, str | None]] = []
            broker_down = [True]

            async def flaky(subject, payload, *, msg_id=None):
                if broker_down[0]:
                    raise ConnectionError("nats is restarting")
                sent.append((subject, payload, msg_id))

            monkeypatch.setattr(live.workers, "_publish_nats", flaky)
            await live.persist(_promotion("p-6"), model_id="m-b")

            assert await live.cycle("p-6") is True
            row = await live.promotion("p-6")
            assert (row["status"], row["status_reason"]) == (
                "pending",
                "publish_failed:ConnectionError",
            )
            assert row["claim_token"] is None, "a failed publish must release the claim"
            assert (await live.alias())["status"] == "pending_external_ack"
            assert sent == []

            broker_down[0] = False
            assert await live.cycle("p-6") is True, "the unsent promotion was not retried"
            assert sent == [
                (
                    "sahool.model.promotion.requested",
                    {"promotion_id": "p-6", "alias": _ALIAS, "target_model_id": "m-b"},
                    f"model-promotion-requested:{row['id']}",
                )
            ]
            row = await live.promotion("p-6")
            assert (row["status"], row["status_reason"]) == ("requested", None)
            assert await live.cycle("p-6") is False, "a sent promotion was claimed again"
            assert len(sent) == 1

    _run(body())


def test_a_retried_older_promotion_never_overwrites_a_newer_alias(monkeypatch, migrated_db):
    """Devin on #1587: A's publish fails, B's succeeds, and the retry of A wrote A over B.

    The alias names the newest promotion; an older one is superseded: it leaves the queue as
    skipped with its reason, and is neither published nor written over the alias.
    """

    async def body():
        async with Live(monkeypatch, migrated_db) as live:
            monkeypatch.setenv("MODEL_SERVING_ENABLED", "true")
            monkeypatch.setenv("MODEL_SERVING_BACKEND_URL", "http://serving.invalid")
            sent: list[str] = []

            async def a_fails_once(subject, payload, *, msg_id=None):
                if payload["promotion_id"] == "p-a" and "p-a" not in failed:
                    failed.add("p-a")
                    raise ConnectionError("nats is restarting")
                sent.append(payload["promotion_id"])

            failed: set[str] = set()
            monkeypatch.setattr(live.workers, "_publish_nats", a_fails_once)
            await live.persist(_promotion("p-a", target="m-a2"), model_id="m-a2")
            await live.persist(_promotion("p-b", target="m-b2"), model_id="m-b2")

            await live.workers.run_model_registry_once(live.owner)
            await live.workers.run_model_registry_once(live.owner)

            alias = await live.alias()
            assert (alias["model_id"], alias["promotion_id"]) == ("m-b2", "p-b")
            older = await live.promotion("p-a")
            assert (older["status"], older["status_reason"]) == ("skipped", "superseded_by:p-b")
            assert (await live.promotion("p-b"))["status"] == "requested"
            assert sent == ["p-b"], f"published {sent}"

    _run(body())


def test_one_promotion_id_in_two_tenants_gets_two_message_ids(monkeypatch, migrated_db):
    """Devin on #1587: promotion_id is unique only per tenant; the stream dedups across all."""

    async def body():
        async with Live(monkeypatch, migrated_db) as one, Live(monkeypatch, migrated_db) as two:
            monkeypatch.setenv("MODEL_SERVING_ENABLED", "true")
            monkeypatch.setenv("MODEL_SERVING_BACKEND_URL", "http://serving.invalid")
            ids: list[str | None] = []

            async def record(subject, payload, *, msg_id=None):
                if payload["promotion_id"] == "p-shared":
                    ids.append(msg_id)

            monkeypatch.setattr(one.workers, "_publish_nats", record)
            await one.persist(_promotion("p-shared"), model_id="m-b")
            await two.persist(_promotion("p-shared"), model_id="m-b")
            await one.workers.run_model_registry_once(one.owner)

            rows = [await one.promotion("p-shared"), await two.promotion("p-shared")]
            assert [r["status"] for r in rows] == ["requested", "requested"]
            assert sorted(ids) == sorted(f"model-promotion-requested:{r['id']}" for r in rows)
            assert len(set(ids)) == 2

    _run(body())


def test_a_non_promote_decision_writes_no_alias_and_leaves_the_queue_once(monkeypatch, migrated_db):
    async def body():
        async with Live(monkeypatch, migrated_db) as live:
            monkeypatch.setenv("MODEL_SERVING_ENABLED", "true")
            monkeypatch.setenv("MODEL_SERVING_BACKEND_URL", "http://serving.invalid")
            await live.persist(_promotion("p-5", decision="hold"), model_id="m-b")
            assert await live.alias() is None
            await live.cycle("p-5")
            assert await live.cycle("p-5") is False
            row = await live.promotion("p-5")
            assert (row["status"], row["status_reason"]) == ("skipped", "decision_hold")
            assert [p for _, p in live.published if p.get("promotion_id") == "p-5"] == []
            assert await live.alias() is None

    _run(body())


def test_the_schema_refuses_an_unknown_promotion_status_and_defaults_the_alias_to_pending(
    monkeypatch, migrated_db
):
    async def body():
        async with Live(monkeypatch, migrated_db) as live:
            async with live.owner.acquire() as conn:
                with pytest.raises(asyncpg.CheckViolationError):
                    await conn.execute(
                        "INSERT INTO model_promotion_history_runtime "
                        "(tenant_id, promotion_id, alias, decision, status) "
                        "VALUES ($1,'p-x',$2,'promote','active')",
                        live.tenant,
                        _ALIAS,
                    )
                await conn.execute(
                    "INSERT INTO model_serving_aliases_runtime (tenant_id, alias, model_id) "
                    "VALUES ($1,'no-status','m-z')",
                    live.tenant,
                )
            assert (await live.alias("no-status"))["status"] == "pending_external_ack"

    _run(body())


_V288 = _ROOT / "migrations" / "v288_model_promotion_terminal_state.sql"


_V288_DOWN = _ROOT / "migrations" / "v288_model_promotion_terminal_state.down.sql"


def test_v288_backfills_history_once_and_reports_aliases_active_before_it(monkeypatch, migrated_db):
    """First apply over a pre-v288 schema: history classified once, old active aliases reported.

    The schema is taken back to before v288 with its own down file, rows are written in the
    pre-v288 shape, and v288 is applied: hold -> skipped, a promote whose alias is already the
    worker's pending_external_ack request -> requested, every other promote stays pending. An
    alias active before v288 stays active and is reported as such, never as acknowledged
    (owner decision 2026-11-23). A second apply changes nothing.
    """

    async def body():
        async with Live(monkeypatch, migrated_db) as live:
            async with live.owner.acquire() as conn:
                notices: list[str] = []
                conn.add_log_listener(lambda _c, message: notices.append(message.message))
                await conn.execute(_V288_DOWN.read_text(encoding="utf-8"))
                try:
                    for pid, decision in (("p-h", "hold"), ("p-r", "promote"), ("p-n", "promote")):
                        await conn.execute(
                            "INSERT INTO model_promotion_history_runtime "
                            "(tenant_id, promotion_id, alias, decision, target_model_id) "
                            "VALUES ($1,$2,$3,$4,'m-b')",
                            live.tenant,
                            pid,
                            f"{_ALIAS}-{pid}",
                            decision,
                        )
                    # p-r was already requested: the worker's request branch wrote its alias.
                    await conn.execute(
                        "INSERT INTO model_serving_aliases_runtime "
                        "(tenant_id, alias, model_id, promotion_id, status) "
                        "VALUES ($1,$2,'m-b','p-r','pending_external_ack')",
                        live.tenant,
                        f"{_ALIAS}-p-r",
                    )
                    # An alias active before v288 (v108's default, no acknowledgement path).
                    await conn.execute(
                        "INSERT INTO model_serving_aliases_runtime "
                        "(tenant_id, alias, model_id, promotion_id, status) "
                        "VALUES ($1,'old-active','m-old','p-old','active')",
                        live.tenant,
                    )
                finally:
                    await conn.execute(_V288.read_text(encoding="utf-8"))
                first = [n for n in notices if "active before v288" in n]
                assert first, notices
                assert all("acknowledged" not in n for n in first), first
                await conn.execute(_V288.read_text(encoding="utf-8"))

            got = {}
            for pid in ("p-h", "p-r", "p-n"):
                row = await live.promotion(pid)
                got[pid] = (row["status"], row["status_reason"])
            assert got == {
                "p-h": ("skipped", "decision_hold"),
                "p-r": ("requested", None),
                "p-n": ("pending", None),
            }
            assert (await live.alias("old-active"))["status"] == "active"

    _run(body())


def test_reapplying_v288_leaves_a_queued_promotion_pending(monkeypatch, migrated_db):
    """Hospital review of #1587: a re-run of v288 marked queued, unpublished promotions requested.

    This release's writer records a promote decision with the alias pending_external_ack on the
    same promotion, the very shape v288's backfill reads as 'already requested'. The backfill
    therefore runs only on the apply that adds the column; a re-run leaves the queue alone.
    """

    async def body():
        async with Live(monkeypatch, migrated_db) as live:
            await live.persist(_promotion("p-q"), model_id="m-b")
            alias = await live.alias()
            assert (alias["promotion_id"], alias["status"]) == ("p-q", "pending_external_ack")
            async with live.owner.acquire() as conn:
                await conn.execute(_V288.read_text(encoding="utf-8"))
            row = await live.promotion("p-q")
            assert (row["status"], row["status_reason"]) == ("pending", None), (
                "re-applying v288 closed a queued promotion that was never published"
            )

    _run(body())


def test_repointing_an_alias_active_before_v288_waits_for_the_external_ack(
    monkeypatch, migrated_db
):
    """Owner decision 2026-11-23: re-pointing an old active alias goes through pending too."""

    async def body():
        async with Live(monkeypatch, migrated_db) as live:
            monkeypatch.setenv("MODEL_SERVING_ENABLED", "true")
            monkeypatch.setenv("MODEL_SERVING_BACKEND_URL", "http://serving.invalid")
            async with live.owner.acquire() as conn:
                await conn.execute(
                    "INSERT INTO model_serving_aliases_runtime "
                    "(tenant_id, alias, model_id, promotion_id, status) "
                    "VALUES ($1,$2,'m-a','p-0','active')",
                    live.tenant,
                    _ALIAS,
                )
            await live.persist(_promotion("p-7"), model_id="m-b")
            assert (await live.alias())["status"] == "pending_external_ack"
            assert await live.cycle("p-7") is True
            assert (await live.promotion("p-7"))["status"] == "requested"
            alias = await live.alias()
            assert (alias["model_id"], alias["promotion_id"], alias["status"]) == (
                "m-b",
                "p-7",
                "pending_external_ack",
            )

    _run(body())


def test_a_newer_alias_written_while_the_worker_waits_is_never_overwritten(
    monkeypatch, migrated_db
):
    """Hospital review of #1587: the alias lock must hold across the decision and the write.

    A second connection holds the alias row while it re-points it to a newer, already
    requested promotion C. The worker, processing the older A, must wait on that row and then
    see C: A is superseded and the alias stays on C. When the check and the write ran in two
    transactions, A's write landed after C's commit and the alias ended on A.
    """

    async def body():
        async with Live(monkeypatch, migrated_db) as live:
            monkeypatch.setenv("MODEL_SERVING_ENABLED", "true")
            monkeypatch.setenv("MODEL_SERVING_BACKEND_URL", "http://serving.invalid")
            await live.persist(_promotion("p-a3", target="m-a3"), model_id="m-a3")
            async with live.owner.acquire() as conn:
                await conn.execute(
                    "INSERT INTO model_promotion_history_runtime "
                    "(tenant_id, promotion_id, alias, decision, target_model_id, status) "
                    "VALUES ($1,'p-c3',$2,'promote','m-c3','requested')",
                    live.tenant,
                    _ALIAS,
                )
            other = await asyncpg.connect(live.dsn)
            try:
                tx = other.transaction()
                await tx.start()
                await other.execute(
                    "UPDATE model_serving_aliases_runtime SET model_id='m-c3', promotion_id='p-c3' "
                    "WHERE tenant_id=$1 AND alias=$2",
                    live.tenant,
                    _ALIAS,
                )
                worker = asyncio.create_task(live.workers.run_model_registry_once(live.owner))
                await asyncio.sleep(1.0)
                assert not worker.done(), "the worker did not wait for the alias row"
                await tx.commit()
                await asyncio.wait_for(worker, timeout=30)
            finally:
                await other.close()

            alias = await live.alias()
            assert (alias["model_id"], alias["promotion_id"]) == ("m-c3", "p-c3")
            older = await live.promotion("p-a3")
            assert (older["status"], older["status_reason"]) == ("skipped", "superseded_by:p-c3")
            assert [p for _, p in live.published if p.get("promotion_id") == "p-a3"] == []

    _run(body())


def test_v288_refuses_a_role_subject_to_rls(monkeypatch, migrated_db):
    """FORCE RLS hides every row from such a role, so its backfill would silently do nothing."""

    async def body():
        async with Live(monkeypatch, migrated_db) as live:
            async with live.app_pool.acquire() as conn:
                with pytest.raises(asyncpg.RaiseError, match="subject to RLS"):
                    await conn.execute(_V288.read_text(encoding="utf-8"))

    _run(body())
