"""D1 — أوامرُ الكتابة المملوكة: ``routers/registry_writes.py`` + دالّتا الحفظ في ``db_persist``.

الصنف: ``raster_registry`` و``raster_cache_invalidations`` جدولان يملكهما raster-service
وكانت المنصّة تكتبهما بـSQL مباشر (``dual-writer`` في فرز الملكيّة). هنا تُقاس واجهةُ
الكتابة التي يملكها المالك — لا نصُّها بل سلوكُها: التوكن، وإسنادُ المستأجِر من السياق
الموثوق لا من الجسم، وحجبُ حقلٍ مجهولٍ أو لمستأجِرٍ آخر، وidempotency بمفتاح الطلب،
والعزلُ الصريح في SQL فوق RLS. القاعدةُ تُحاكى باتّصالٍ مُسجِّل — لا PostgreSQL هنا؛
الشاهدُ الحيّ في ``tests_v9/test_d1_raster_invalidation_owner_api_integration.py``.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parents[1]
for _p in (_HERE, _ROOT):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import db_persist  # noqa: E402
import raster_security_context  # noqa: E402
import raster_settings  # noqa: E402
from routers import registry_writes as rw  # noqa: E402

TENANT = "11111111-1111-1111-1111-111111111111"
OTHER_TENANT = "22222222-2222-2222-2222-222222222222"
FIELD = "fld_d1_test"


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture
def owner_api(monkeypatch):
    """توكنُ خدمةٍ مضبوط، قاعدةٌ «مُهيّأة»، حقلٌ مرئيٌّ مملوكٌ للمستأجِر، ومستأجِرٌ في السياق."""
    monkeypatch.setattr(raster_settings, "AGENT_TOKEN", "svc-token")
    monkeypatch.setattr(db_persist, "DATABASE_URL", "postgresql://stub/for-tests")

    async def _owned_by_tenant(_field_id):
        return TENANT

    monkeypatch.setattr(raster_security_context, "field_owner", _owned_by_tenant)
    token = raster_security_context.REQ_TENANT.set(TENANT)
    try:
        yield
    finally:
        raster_security_context.REQ_TENANT.reset(token)


# ── الإعلان ─────────────────────────────────────────────────────────────────────
def test_both_owner_write_paths_are_declared_on_the_auto_registered_router():
    """``router_registry`` يضمّ أيَّ ``routers/*.py`` يُصدّر ``router``؛ المساران هما ما يطلبه
    عميلُ المنصّة حرفيّاً (حارسُ عقد المسارات العابرة يقيس القفزة)."""
    paths = {(next(iter(r.methods)), r.path) for r in rw.router.routes}
    assert ("POST", "/v1/fields/{field_id}/cache-invalidations") in paths
    assert ("POST", "/v1/registry/cogs") in paths
    assert Path(rw.__file__).parent.name == "routers"


# ── إسنادُ المستأجِر ─────────────────────────────────────────────────────────────
def test_tenant_comes_from_the_trusted_context_and_the_body_cannot_override_it(owner_api):
    assert rw._authenticated_tenant(None) == TENANT
    assert rw._authenticated_tenant(TENANT) == TENANT
    with pytest.raises(HTTPException) as ei:
        rw._authenticated_tenant(OTHER_TENANT)
    assert ei.value.status_code == 403


def test_a_write_command_without_a_tenant_context_is_refused():
    token = raster_security_context.REQ_TENANT.set(None)
    try:
        with pytest.raises(HTTPException) as ei:
            rw._authenticated_tenant(None)
        assert ei.value.status_code == 403
    finally:
        raster_security_context.REQ_TENANT.reset(token)


# ── طابورُ الإبطال ────────────────────────────────────────────────────────────────
def _invalidation(**over):
    base = {
        "reason": "field.geometry.updated",
        "request_id": "field.geometry.updated:fld_d1_test:rev3",
        "metadata": {"geometry_revision": 3, "scope": ["tiles"]},
    }
    base.update(over)
    return rw.CacheInvalidationCommand(**base)


def test_invalidation_command_is_persisted_under_the_context_tenant(owner_api, monkeypatch):
    seen: dict = {}

    async def _enqueue(**kwargs):
        seen.update(kwargs)
        return {"id": 7, "status": "pending", "created_at": "2026-09-21", "deduplicated": False}

    monkeypatch.setattr(db_persist, "enqueue_cache_invalidation", _enqueue)
    out = _run(rw.enqueue_field_cache_invalidation(FIELD, _invalidation(), "svc-token"))
    assert out["accepted"] is True and out["deduplicated"] is False
    assert out["invalidation"] == {"id": 7, "status": "pending", "created_at": "2026-09-21"}
    assert seen["tenant_id"] == TENANT and seen["field_id"] == FIELD
    assert seen["request_id"] == "field.geometry.updated:fld_d1_test:rev3"
    assert seen["metadata"]["geometry_revision"] == 3


def test_a_retried_command_reports_deduplicated_instead_of_a_second_row(owner_api, monkeypatch):
    async def _enqueue(**_kwargs):
        return {"id": 7, "status": "processed", "created_at": "t", "deduplicated": True}

    monkeypatch.setattr(db_persist, "enqueue_cache_invalidation", _enqueue)
    out = _run(rw.enqueue_field_cache_invalidation(FIELD, _invalidation(), "svc-token"))
    assert out["deduplicated"] is True and out["invalidation"]["status"] == "processed"


def test_invalidation_refuses_a_bad_service_token(owner_api, monkeypatch):
    called = False

    async def _enqueue(**_kwargs):
        nonlocal called
        called = True

    monkeypatch.setattr(db_persist, "enqueue_cache_invalidation", _enqueue)
    with pytest.raises(HTTPException) as ei:
        _run(rw.enqueue_field_cache_invalidation(FIELD, _invalidation(), "wrong"))
    assert ei.value.status_code == 401 and called is False


def test_invalidation_refuses_a_field_proven_to_belong_to_another_tenant(owner_api, monkeypatch):
    async def _other_owner(_field_id):
        return OTHER_TENANT

    monkeypatch.setattr(raster_security_context, "field_owner", _other_owner)
    with pytest.raises(HTTPException) as ei:
        _run(rw.enqueue_field_cache_invalidation(FIELD, _invalidation(), "svc-token"))
    assert ei.value.status_code == 403


def test_invalidation_refuses_a_field_that_is_not_visible_yet(owner_api, monkeypatch):
    """صارم: مجهولٌ ⇒ 404 — لا إدراجَ لمعرّفٍ وهميّ تحت المستأجِر. الأوامرُ تصل بعد COMMIT."""

    async def _unknown(_field_id):
        return None

    monkeypatch.setattr(raster_security_context, "field_owner", _unknown)
    with pytest.raises(HTTPException) as ei:
        _run(rw.enqueue_field_cache_invalidation(FIELD, _invalidation(), "svc-token"))
    assert ei.value.status_code == 404


def test_invalidation_fails_closed_when_ownership_cannot_be_proven(owner_api, monkeypatch):
    async def _unavailable(_field_id):
        raise db_persist.OwnerLookupUnavailable("db down")

    monkeypatch.setattr(raster_security_context, "field_owner", _unavailable)
    with pytest.raises(HTTPException) as ei:
        _run(rw.enqueue_field_cache_invalidation(FIELD, _invalidation(), "svc-token"))
    assert ei.value.status_code == 503


def test_invalidation_is_503_without_a_database_or_when_the_queue_write_fails(
    owner_api, monkeypatch
):
    monkeypatch.setattr(db_persist, "DATABASE_URL", "")
    with pytest.raises(HTTPException) as ei:
        _run(rw.enqueue_field_cache_invalidation(FIELD, _invalidation(), "svc-token"))
    assert ei.value.status_code == 503

    monkeypatch.setattr(db_persist, "DATABASE_URL", "postgresql://stub")

    async def _none(**_kwargs):
        return None

    monkeypatch.setattr(db_persist, "enqueue_cache_invalidation", _none)
    with pytest.raises(HTTPException) as ei:
        _run(rw.enqueue_field_cache_invalidation(FIELD, _invalidation(), "svc-token"))
    assert ei.value.status_code == 503


def test_invalidation_rejects_an_unsafe_field_id_or_request_id(owner_api):
    with pytest.raises(HTTPException) as ei:
        _run(rw.enqueue_field_cache_invalidation("../etc", _invalidation(), "svc-token"))
    assert ei.value.status_code == 400
    with pytest.raises(ValidationError):
        _invalidation(request_id="has space")
    with pytest.raises(ValidationError):
        _invalidation(reason="")


# ── الكتالوج ─────────────────────────────────────────────────────────────────────
def _cog(**over):
    base = {
        "field_id": FIELD,
        "scene_id": "S2A_X",
        "product_date": "2026-09-08",
        "index_type": "ndvi",
        "cog_url": "https://cdn.example/ndvi.tif",
        "cloud_pct": 3.5,
        "quality_score": 91,
        "resolution_m": 10,
        "bbox": [44.3, 16.7, 44.4, 16.8],
        "bands": {"ndvi": 1},
        "metadata": {"quality": {"score": 91}},
    }
    base.update(over)
    return rw.CogRegistryCommand(**base)


def test_cog_command_is_upserted_under_the_context_tenant_and_the_row_is_returned(
    owner_api, monkeypatch
):
    seen: dict = {}

    async def _upsert(**kwargs):
        seen.update(kwargs)
        return {"id": "r-1", "tenant_id": kwargs["tenant_id"], "field_id": kwargs["field_id"]}

    monkeypatch.setattr(db_persist, "upsert_raster_registry_entry", _upsert)
    out = _run(rw.register_cog_entry(_cog(), "svc-token"))
    assert out == {
        "registered": True,
        "entry": {"id": "r-1", "tenant_id": TENANT, "field_id": FIELD},
    }
    assert seen["tenant_id"] == TENANT and seen["quality_score"] == 91
    assert seen["metadata"] == {"quality": {"score": 91}}


def test_cog_command_refuses_another_tenants_field_and_a_bad_token(owner_api, monkeypatch):
    with pytest.raises(HTTPException) as ei:
        _run(rw.register_cog_entry(_cog(), "wrong"))
    assert ei.value.status_code == 401

    async def _other_owner(_field_id):
        return OTHER_TENANT

    monkeypatch.setattr(raster_security_context, "field_owner", _other_owner)
    with pytest.raises(HTTPException) as ei:
        _run(rw.register_cog_entry(_cog(), "svc-token"))
    assert ei.value.status_code == 403


def test_cog_command_validates_its_shape_at_the_boundary():
    with pytest.raises(ValidationError):
        _cog(field_id="")
    with pytest.raises(ValidationError):
        _cog(quality_score=101)
    with pytest.raises(ValidationError):
        _cog(product_date="2026-9")


def test_cog_command_is_503_when_the_catalogue_write_does_not_return_a_row(owner_api, monkeypatch):
    async def _none(**_kwargs):
        return None

    monkeypatch.setattr(db_persist, "upsert_raster_registry_entry", _none)
    with pytest.raises(HTTPException) as ei:
        _run(rw.register_cog_entry(_cog(), "svc-token"))
    assert ei.value.status_code == 503


# ── db_persist: الاتّصالُ المُسجِّل ──────────────────────────────────────────────
class UniqueViolationError(Exception):
    """اسمُ استثناء asyncpg — الدالّة تميّزه بالاسم كي لا تستورد asyncpg عند التحميل."""


class _RecordingConn:
    def __init__(self, fetchrow_script):
        self.executed: list[tuple[str, tuple]] = []
        self.fetched: list[tuple[str, tuple]] = []
        self._script = list(fetchrow_script)
        self.closed = False

    async def execute(self, sql, *args):
        self.executed.append((sql, args))
        return "OK"

    async def fetchrow(self, sql, *args):
        self.fetched.append((sql, args))
        step = self._script.pop(0)
        if isinstance(step, Exception):
            raise step
        return step

    async def close(self):
        self.closed = True


def _install(monkeypatch, conn):
    async def _connect():
        return conn

    monkeypatch.setattr(db_persist, "_connect", _connect)


def test_enqueue_sets_the_tenant_guc_and_predicates_the_tenant_explicitly(monkeypatch):
    conn = _RecordingConn([None, {"id": 3, "status": "pending", "created_at": "t"}])
    _install(monkeypatch, conn)
    out = _run(
        db_persist.enqueue_cache_invalidation(
            tenant_id=TENANT,
            field_id=FIELD,
            reason="field.created",
            request_id="field.created:fld_d1_test:rev1",
            metadata={"geometry_revision": 1},
        )
    )
    assert out == {"id": 3, "status": "pending", "created_at": "t", "deduplicated": False}
    guc_sql, guc_args = conn.executed[0]
    assert "set_config('app.current_tenant'" in guc_sql and guc_args == (TENANT,)
    lookup_sql, lookup_args = conn.fetched[0]
    assert "tenant_id = $1::uuid" in lookup_sql and "metadata->>'request_id' = $3" in lookup_sql
    assert lookup_args == (TENANT, FIELD, "field.created:fld_d1_test:rev1")
    insert_sql, insert_args = conn.fetched[1]
    assert "INSERT INTO raster_cache_invalidations" in insert_sql
    assert insert_args[0] == TENANT and insert_args[1] == FIELD
    stored_meta = json.loads(insert_args[3])
    assert stored_meta == {"geometry_revision": 1, "request_id": "field.created:fld_d1_test:rev1"}
    assert conn.closed


def test_enqueue_returns_the_existing_row_and_does_not_insert_twice(monkeypatch):
    conn = _RecordingConn([{"id": 3, "status": "processed", "created_at": "t"}])
    _install(monkeypatch, conn)
    out = _run(
        db_persist.enqueue_cache_invalidation(
            tenant_id=TENANT, field_id=FIELD, reason="r", request_id="req-1"
        )
    )
    assert out["deduplicated"] is True and out["id"] == 3
    assert len(conn.fetched) == 1  # lookup only — no INSERT


def test_enqueue_resolves_a_concurrent_insert_race_through_the_unique_index(monkeypatch):
    conn = _RecordingConn(
        [None, UniqueViolationError("dup"), {"id": 9, "status": "pending", "created_at": "t"}]
    )
    _install(monkeypatch, conn)
    out = _run(
        db_persist.enqueue_cache_invalidation(
            tenant_id=TENANT, field_id=FIELD, reason="r", request_id="req-race"
        )
    )
    assert out == {"id": 9, "status": "pending", "created_at": "t", "deduplicated": True}


def test_enqueue_refuses_invalid_identities_before_touching_the_database(monkeypatch):
    async def _never():
        raise AssertionError("must not connect")

    monkeypatch.setattr(db_persist, "_connect", _never)
    bad = [
        dict(tenant_id="not-a-uuid", field_id=FIELD, reason="r", request_id="x"),
        dict(tenant_id=TENANT, field_id="a/b", reason="r", request_id="x"),
        dict(tenant_id=TENANT, field_id=FIELD, reason="r", request_id="has space"),
        dict(tenant_id=TENANT, field_id=FIELD, reason="  ", request_id="x"),
    ]
    for kwargs in bad:
        assert _run(db_persist.enqueue_cache_invalidation(**kwargs)) is None


def test_enqueue_swallows_database_failures_into_none(monkeypatch):
    conn = _RecordingConn([RuntimeError("relation does not exist")])
    _install(monkeypatch, conn)
    out = _run(
        db_persist.enqueue_cache_invalidation(
            tenant_id=TENANT, field_id=FIELD, reason="r", request_id="req"
        )
    )
    assert out is None and conn.closed


def test_registry_upsert_returns_the_persisted_row_with_json_columns_decoded(monkeypatch):
    conn = _RecordingConn(
        [
            {
                "id": "r-1",
                "tenant_id": TENANT,
                "field_id": FIELD,
                "scene_id": "S",
                "product_date": "2026-09-08",
                "index_type": "ndvi",
                "cog_url": "https://cdn.example/x.tif",
                "cloud_pct": 3.5,
                "quality_score": 91,
                "resolution_m": 10.0,
                "bbox": "[44.3, 16.7, 44.4, 16.8]",
                "bands": '{"ndvi": 1}',
                "metadata": '{"quality": {"score": 91}}',
                "created_at": "t",
            }
        ]
    )
    _install(monkeypatch, conn)
    row = _run(
        db_persist.upsert_raster_registry_entry(
            tenant_id=TENANT,
            field_id=FIELD,
            scene_id="S",
            product_date="2026-09-08T00:00:00Z",
            index_type="ndvi",
            cog_url="https://cdn.example/x.tif",
            cloud_pct=3.5,
            quality_score=91,
            bbox=[44.3, 16.7, 44.4, 16.8],
            bands={"ndvi": 1},
            metadata={"quality": {"score": 91}},
        )
    )
    assert row["bbox"] == [44.3, 16.7, 44.4, 16.8] and row["bands"] == {"ndvi": 1}
    assert row["metadata"] == {"quality": {"score": 91}}
    sql, args = conn.fetched[0]
    assert "ON CONFLICT (tenant_id, field_id, product_date, index_type, cog_url)" in sql
    assert "RETURNING" in sql and args[0] == TENANT and args[3] == "2026-09-08"
    assert conn.executed[0][1] == (TENANT,)  # app.current_tenant before the write


def test_the_pipeline_bridge_still_reports_success_through_the_shared_upsert(monkeypatch):
    conn = _RecordingConn([{"id": "r-2", "bbox": None, "bands": "{}", "metadata": "{}"}])
    _install(monkeypatch, conn)
    ok = _run(
        db_persist.insert_raster_registry_entry(
            tenant_id=TENANT,
            field_id=FIELD,
            scene_id=None,
            product_date="2026-09-08",
            index_type="ndvi",
            cog_url="file:///x.tif",
            cloud_pct=None,
            quality_score=None,
        )
    )
    assert ok is True
    assert "INSERT INTO raster_registry" in conn.fetched[0][0]
