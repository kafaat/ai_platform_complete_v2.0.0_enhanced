"""D1 — الإبطالُ نيّةٌ دائمة في معاملة الحقل، وتسليمٌ بعد الالتزام (فحصٌ صرف، ``-m unit``).

كانت ``mark_raster_cache_stale`` تُدرج في ``raster_cache_invalidations`` مباشرةً — جدولٌ
يملكه raster-service. صارت تكتب **نيّةً** في ``processing_jobs`` (مملوكٌ للمنصّة) على
اتّصال المعاملة نفسِه — لا HTTP داخل المعاملة — بمفتاح طلبٍ حتميّ من ``(reason, field_id,
geometry_revision)``. والمُوصِّلُ (قسمُ التسليم في ``spatial_sync``) يطالب النيّاتِ بعد الالتزام بإجارة،
ويُرسلها إلى الأمر المملوك عبر ``api.raster_service_client``، ولا يُكمِل النيّةَ إلّا
بإقرار المالك؛ الفشلُ يُعاد بمهلةٍ متزايدة والمفتاحِ نفسِه، والرفضُ الدائم يُوسَم ``failed``
بسببه. هنا تُقاس هذه الخواصّ باتّصالٍ مُسجِّل وبدالّةِ إرسالٍ مزيّفة — لا قاعدةَ ولا خدمة.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../services/sahool-platform"))

from api import raster_service_client as rsc  # noqa: E402
from api import spatial_sync  # noqa: E402
from api import spatial_sync as dispatch  # noqa: E402

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
TENANT = "11111111-1111-1111-1111-111111111111"


class _Savepoint:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        self.conn.savepoints += 1
        return self

    async def __aexit__(self, exc_type, exc, tb):
        if exc_type is not None:
            self.conn.rolled_back += 1
        return False


class _Conn:
    """اتّصالٌ مُسجِّل: ``fetchval`` يقرأ سيناريو، و``execute`` يُعيد عدَّ صفوفٍ مُهيَّأ."""

    def __init__(self, fetchval_script=(), execute_results=("UPDATE 1",), fetch_rows=()):
        self.calls: list[tuple[str, str, tuple]] = []
        self._fetchval = list(fetchval_script)
        self._execute = list(execute_results)
        self._fetch = list(fetch_rows)
        self.savepoints = 0
        self.rolled_back = 0

    def transaction(self):
        return _Savepoint(self)

    async def fetchval(self, sql, *args):
        self.calls.append(("fetchval", sql, args))
        step = self._fetchval.pop(0)
        if isinstance(step, Exception):
            raise step
        return step

    async def execute(self, sql, *args):
        self.calls.append(("execute", sql, args))
        return self._execute.pop(0) if self._execute else "UPDATE 1"

    async def fetch(self, sql, *args):
        self.calls.append(("fetch", sql, args))
        return list(self._fetch)


# ── مفتاحُ الطلب ────────────────────────────────────────────────────────────────
def test_request_id_is_deterministic_when_the_geometry_revision_is_known():
    a = spatial_sync.invalidation_request_id(
        field_id="fld_1", reason="field.geometry.updated", metadata={"geometry_revision": 4}
    )
    b = spatial_sync.invalidation_request_id(
        field_id="fld_1", reason="field.geometry.updated", metadata={"geometry_revision": 4}
    )
    assert a == b == "field.geometry.updated:fld_1:rev4"


def test_two_geometry_revisions_are_two_intents_not_one_retry():
    """تعديلُ الهندسة مرّتين ⇒ مفتاحان؛ الثاني لا يُسقَط بوصفه تكراراً للأوّل."""
    first = spatial_sync.invalidation_request_id(
        field_id="fld_1", reason="field.geometry.updated", metadata={"geometry_revision": 4}
    )
    second = spatial_sync.invalidation_request_id(
        field_id="fld_1", reason="field.geometry.updated", metadata={"geometry_revision": 5}
    )
    assert first != second


def test_request_id_declares_itself_random_when_no_revision_was_recorded():
    a = spatial_sync.invalidation_request_id(field_id="fld_1", reason="field.created")
    b = spatial_sync.invalidation_request_id(field_id="fld_1", reason="field.created")
    assert a != b and ":norev-" in a
    c = spatial_sync.invalidation_request_id(
        field_id="fld_1", reason="r", metadata={"geometry_revision": True}
    )
    assert ":norev-" in c  # bool ليس مراجعة


def test_request_id_is_safe_for_the_owner_pattern_and_bounded():
    rid = spatial_sync.invalidation_request_id(
        field_id="fld 1/x", reason="بسبب غريب", metadata={"geometry_revision": 1}
    )
    assert rid and len(rid) <= 128 and rid[0].isalnum()
    assert all(ch.isalnum() or ch in "._:-" for ch in rid)
    long = spatial_sync.invalidation_request_id(
        field_id="f" * 300, reason="r", metadata={"geometry_revision": 1}
    )
    assert len(long) == 128


# ── النيّةُ في المعاملة ─────────────────────────────────────────────────────────
def test_the_intent_is_written_on_the_callers_connection_inside_a_savepoint():
    conn = _Conn(fetchval_script=[None, 41])
    out = asyncio.run(
        spatial_sync.mark_raster_cache_stale(
            conn,
            tenant_id=TENANT,
            field_id="fld_9",
            reason="field.geometry.reverted",
            metadata={"geometry_revision": 12, "reverted_from_revision": 10},
        )
    )
    assert out == 41
    assert conn.savepoints == 1 and conn.rolled_back == 0
    kinds = [c[0] for c in conn.calls]
    assert kinds == ["fetchval", "fetchval"]
    lookup_sql, lookup_args = conn.calls[0][1], conn.calls[0][2]
    assert "processing_jobs" in lookup_sql and "parameters->>'request_id'" in lookup_sql
    assert lookup_args[:3] == (TENANT, "fld_9", spatial_sync.RASTER_INVALIDATION_JOB_TYPE)
    insert_sql, insert_args = conn.calls[1][1], conn.calls[1][2]
    assert "INSERT INTO processing_jobs" in insert_sql and "'pending'" in insert_sql
    assert "raster_cache_invalidations" not in insert_sql
    params = json.loads(insert_args[3])
    assert params["request_id"] == "field.geometry.reverted:fld_9:rev12"
    assert params["metadata"]["reverted_from_revision"] == 10


def test_a_repeated_intent_in_the_same_tenant_returns_the_existing_row_and_does_not_insert():
    conn = _Conn(fetchval_script=[17])
    out = asyncio.run(
        spatial_sync.mark_raster_cache_stale(
            conn, tenant_id=TENANT, field_id="fld_9", reason="r", metadata={"geometry_revision": 1}
        )
    )
    assert out == 17 and len(conn.calls) == 1


def test_a_failed_intent_write_is_swallowed_inside_its_savepoint_and_named():
    """أفضل-جهد كما كان: لا يكسر حفظَ الحقل ولا يُفسِد معاملةَ المُستدعي (savepoint)."""
    conn = _Conn(fetchval_script=[RuntimeError("relation processing_jobs is locked")])
    out = asyncio.run(
        spatial_sync.mark_raster_cache_stale(
            conn, tenant_id=TENANT, field_id="fld_9", reason="r", metadata=None
        )
    )
    assert out is None and conn.rolled_back == 1


def test_no_http_client_is_reachable_from_the_transactional_helper():
    """عقدُ ``_insert_field_within_tx``: لا I/O خارج conn — يُقاس على شجرة البناء.

    العميلُ يُستورَد كسولاً داخل ``run_once`` (المُوصِّل) وحده؛ جسمُ ``mark_raster_cache_stale``
    لا يذكر العميلَ ولا ``httpx``، والوحدةُ لا تستورد أيّاً منهما على مستواها.
    """
    import ast

    src = (ROOT / "services/sahool-platform/api/spatial_sync.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    top_imports = {
        (n.module if isinstance(n, ast.ImportFrom) else a.name)
        for n in tree.body
        if isinstance(n, (ast.Import, ast.ImportFrom))
        for a in n.names
    }
    assert not any("raster_service_client" in str(m) or "httpx" in str(m) for m in top_imports)
    fn = next(
        n
        for n in tree.body
        if isinstance(n, ast.AsyncFunctionDef) and n.name == "mark_raster_cache_stale"
    )
    names = {n.id for n in ast.walk(fn) if isinstance(n, ast.Name)} | {
        n.attr for n in ast.walk(fn) if isinstance(n, ast.Attribute)
    }
    assert not names & {
        "enqueue_raster_cache_invalidation",
        "raster_service_client",
        "httpx",
        "run_once",
    }
    assert "INSERT INTO raster_cache_invalidations" not in src


# ── المُوصِّل بعد الالتزام ──────────────────────────────────────────────────────
def _job(**over):
    base = {
        "id": 7,
        "tenant_id": TENANT,
        "field_id": "fld_9",
        "parameters": json.dumps(
            {
                "request_id": "field.geometry.updated:fld_9:rev3",
                "reason": "field.geometry.updated",
                "metadata": {"geometry_revision": 3},
            }
        ),
        "result": json.dumps({"lease": {"token": "tok-1", "expires_at": "later"}, "attempts": 0}),
    }
    base.update(over)
    return base


async def _send_ok(field_id, *, tenant_id, reason, request_id, metadata=None, timeout_s=5.0):
    return {"accepted": True, "deduplicated": False, "invalidation": {"id": 99}}


def test_claim_uses_skip_locked_and_only_this_job_type():
    conn = _Conn(fetch_rows=[_job()])
    rows = asyncio.run(dispatch.claim_due(conn, limit=5))
    assert rows and rows[0]["id"] == 7
    sql, args = conn.calls[0][1], conn.calls[0][2]
    assert "FOR UPDATE SKIP LOCKED" in sql and "status = 'pending'" in sql
    assert args[0] == spatial_sync.RASTER_INVALIDATION_JOB_TYPE and args[1] == 5


def test_delivery_completes_the_intent_only_with_the_owners_acknowledgement():
    conn = _Conn()
    seen: dict = {}

    async def _send(field_id, *, tenant_id, reason, request_id, metadata=None, timeout_s=5.0):
        seen.update(field_id=field_id, tenant_id=tenant_id, request_id=request_id)
        return {"accepted": True, "deduplicated": True, "invalidation": {"id": 5}}

    out = asyncio.run(dispatch.deliver(conn, _job(), send=_send))
    assert out == "delivered"
    assert seen == {
        "field_id": "fld_9",
        "tenant_id": TENANT,
        "request_id": "field.geometry.updated:fld_9:rev3",
    }
    sql, args = conn.calls[-1][1], conn.calls[-1][2]
    assert "UPDATE processing_jobs" in sql and "result->'lease'->>'token' = $3" in sql
    assert args[2] == "tok-1" and args[3] == "completed"
    patch = json.loads(args[4])
    assert patch["attempts"] == 1 and patch["ack"]["deduplicated"] is True


def test_a_transport_failure_is_retried_with_backoff_and_the_same_request_id():
    conn = _Conn()

    async def _down(*_a, **_k):
        raise ConnectionError("raster-service refused")

    out = asyncio.run(dispatch.deliver(conn, _job(), send=_down))
    assert out == "retry"
    sql, args = conn.calls[-1][1], conn.calls[-1][2]
    assert args[3] == "pending" and args[6] == float(dispatch.backoff_seconds(1))
    assert "next_attempt_at" in sql
    patch = json.loads(args[4])
    assert patch["attempts"] == 1 and "ConnectionError" in patch["last_error"]


def test_a_refusal_that_retrying_cannot_change_ends_in_failed_with_the_reason():
    from fastapi import HTTPException

    conn = _Conn()

    async def _forbidden(*_a, **_k):
        raise HTTPException(403, "الحقل لا يخصّ مستأجِرك")

    out = asyncio.run(dispatch.deliver(conn, _job(), send=_forbidden))
    assert out == "failed"
    args = conn.calls[-1][2]
    assert args[3] == "failed" and "403" not in (args[5] or "") or args[5]
    assert "الحقل لا يخصّ مستأجِرك" in args[5]


def test_a_not_found_is_retried_because_the_owners_negative_cache_may_lag_the_commit():
    from fastapi import HTTPException

    conn = _Conn()

    async def _missing(*_a, **_k):
        raise HTTPException(404, "الحقل غير موجود أو غير مرئيّ بعد")

    assert asyncio.run(dispatch.deliver(conn, _job(), send=_missing)) == "retry"


def test_attempts_are_bounded_and_the_last_failure_is_permanent():
    conn = _Conn()
    job = _job(
        result=json.dumps({"lease": {"token": "tok-1"}, "attempts": dispatch.MAX_ATTEMPTS - 1})
    )

    async def _down(*_a, **_k):
        raise ConnectionError("still down")

    assert asyncio.run(dispatch.deliver(conn, job, send=_down)) == "failed"
    assert conn.calls[-1][2][3] == "failed"


def test_a_lost_lease_never_overwrites_another_workers_work():
    conn = _Conn(execute_results=["UPDATE 0"])
    assert asyncio.run(dispatch.deliver(conn, _job(), send=_send_ok)) == "lease_lost"


def test_backoff_grows_and_saturates():
    seq = [dispatch.backoff_seconds(n) for n in range(1, dispatch.MAX_ATTEMPTS + 3)]
    assert seq == sorted(seq) and seq[-1] == seq[-2] == dispatch.BACKOFF_SECONDS[-1]


def test_run_once_claims_in_its_own_transaction_then_delivers_outside_it():
    class _Pool:
        def __init__(self, conn):
            self.conn = conn

        def acquire(self):
            pool = self

            class _Ctx:
                async def __aenter__(self_inner):
                    return pool.conn

                async def __aexit__(self_inner, *a):
                    return False

            return _Ctx()

    conn = _Conn(fetch_rows=[_job()])
    counts = asyncio.run(dispatch.run_once(_Pool(conn), send=_send_ok))
    assert counts["claimed"] == 1 and counts["delivered"] == 1
    assert conn.savepoints == 1  # المطالبةُ وحدَها داخل معاملة؛ التسليمُ خارجَها


def test_the_dispatch_task_is_registered_on_the_platform_scheduler():
    from api import scheduler as sched

    registered: dict = {}

    class _Sched:
        def register(self, name, interval, fn, enabled=True):
            registered[name] = (interval, fn)

    def _singleton(fn, *, task_name, pool_getter):
        return fn

    dispatch.register_dispatch_task(_Sched(), _singleton, pool_getter=lambda: None)
    assert dispatch.TASK_NAME in registered and registered[dispatch.TASK_NAME][0] > 0
    src = (ROOT / "services/sahool-platform/api/scheduler.py").read_text(encoding="utf-8")
    assert "register_dispatch_task(scheduler, cluster_singleton)" in src
    assert hasattr(sched, "register_default_tasks")


# ── العميل ─────────────────────────────────────────────────────────────────────
def test_client_builds_the_invalidation_command_the_owner_declares(monkeypatch):
    seen: dict = {}

    async def _post(path, *, tenant_id=None, payload=None, timeout_s=30.0):
        seen.update(path=path, tenant_id=tenant_id, payload=payload, timeout_s=timeout_s)
        return {"accepted": True}

    monkeypatch.setattr(rsc, "raster_post_json", _post)
    asyncio.run(
        rsc.enqueue_raster_cache_invalidation(
            "fld_3",
            tenant_id=TENANT,
            reason="field.updated",
            request_id="field.updated:fld_3:rev2",
            metadata={"geometry_revision": 2},
        )
    )
    assert seen["path"] == "/v1/fields/fld_3/cache-invalidations"
    assert seen["tenant_id"] == TENANT
    assert seen["payload"] == {
        "tenant_id": TENANT,
        "reason": "field.updated",
        "request_id": "field.updated:fld_3:rev2",
        "metadata": {"geometry_revision": 2},
    }


def test_client_builds_the_cog_registry_command_with_the_tenant_in_the_body(monkeypatch):
    seen: dict = {}

    async def _post(path, *, tenant_id=None, payload=None, timeout_s=30.0):
        seen.update(path=path, tenant_id=tenant_id, payload=payload)
        return {"registered": True, "entry": {}}

    monkeypatch.setattr(rsc, "raster_post_json", _post)
    asyncio.run(rsc.register_cog_asset(tenant_id=TENANT, payload={"field_id": "fld_3"}))
    assert seen["path"] == "/v1/registry/cogs"
    assert seen["payload"] == {"field_id": "fld_3", "tenant_id": TENANT}


def test_both_requested_paths_are_declared_by_the_owner_router():
    owner = (ROOT / "services" / "raster-service" / "routers" / "registry_writes.py").read_text(
        encoding="utf-8"
    )
    assert '@router.post("/v1/fields/{field_id}/cache-invalidations"' in owner
    assert '@router.post("/v1/registry/cogs"' in owner
