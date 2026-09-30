"""RASTER-TENANT-TRUST-01 — مَن يحقّ له أن يُسمّي المستأجِر لدى raster-service.

العطلُ المقيس (التدقيق الحيّ 2026-09-29، وأُعيد إنتاجه هنا على PostgreSQL حيّ بدور
``NOBYPASSRLS``): المستأجِر كان ``X-Tenant-Id`` **أو** ``?tid=`` **أو** ``?tenant_id=`` بلا
سؤالٍ عمّن يُنادي. فكتب مُنادٍ داخليّ معرّفَ مستأجِرٍ آخر فوجد ملكيّةَ الحقل «مطابقة»
و``app.current_tenant`` مضبوطاً عليه، فأعادت الخدمة tilejson بحدوده وبلاطاتِه المُصيَّرة.
RLS لم تنكسر — أُعطيت المستأجِرَ الخطأ.

هذه الاختبارات تمرّ بالوسيط والحارس والمسار الحقيقيّة (القاعدة وحدَها مُحاكاة)، وتقيس
الهويّتين على المسار الداخليّ نفسه: A بتوكنه يقرأ حقلَه، وB لا يقرأه لا بتوكنه ولا بتزوير.
"""

from __future__ import annotations

import db_persist
import main
import pytest
import raster_security_context
import raster_settings
from fastapi.testclient import TestClient

from shared.security import trusted_tenant

TOKEN = "svc-token-boundary-0123456789"
A, B = "tenant-A", "tenant-B"
FIELD_A = "F-A"
A_BOUNDS = [44.1, 15.1, 44.2, 15.2]


@pytest.fixture
def world(monkeypatch):
    """حقلٌ يملكه A وأصلٌ جاهز له؛ القاعدة تُحاكى على مستوى الدالّتين اللتين تقرؤهما الخدمة."""
    main._layers.clear()
    main._field_layers.clear()
    main._field_owner_cache.clear()
    monkeypatch.setattr(raster_settings, "AGENT_TOKEN", TOKEN)
    seen: list[str | None] = []

    async def owner(field_id):
        return A if field_id == FIELD_A else None

    async def fetch_latest_asset(field_id, index_name, date=None, tenant_id=None):
        seen.append(tenant_id)
        if field_id == FIELD_A and tenant_id == A:  # RLS + الفلتر الصريح: صفّ A لـA وحدَه
            return {
                "cog_url": "s3://sahool-rasters/tenant-a/ndvi.tif",
                "index": index_name,
                "acquisition_date": "2026-09-01",
                "srid": 4326,
                "bounds_4326": A_BOUNDS,
            }
        return None

    monkeypatch.setattr(main, "_field_owner", owner)
    monkeypatch.setattr(db_persist, "fetch_latest_asset", fetch_latest_asset)
    return seen


def _enforce(monkeypatch, on: bool) -> None:
    monkeypatch.setenv(raster_security_context.TENANT_CREDENTIAL_ENFORCE_ENV, "1" if on else "0")


def _tilejson(headers=None, query=""):
    client = TestClient(main.app)
    return client.get(f"/v1/fields/{FIELD_A}/tilejson?index=ndvi{query}", headers=headers or {})


def test_the_comparator_is_the_shared_one_from_1069():
    """لا نسخةَ محلّيّة من المقارِن: ثابتُ الزمن ويفشل مغلقاً على سرٍّ فارغ في موضعٍ واحد."""
    assert raster_security_context.service_token_ok is trusted_tenant.service_token_ok


def test_identity_a_with_the_credential_reads_its_own_field(world, monkeypatch):
    _enforce(monkeypatch, True)
    resp = _tilejson({"X-Tenant-Id": A, "X-Agent-Token": TOKEN})
    assert resp.status_code == 200
    assert resp.json()["bounds"] == A_BOUNDS
    assert world[-1] == A


def test_identity_b_with_its_own_credential_cannot_read_a(world, monkeypatch):
    _enforce(monkeypatch, True)
    resp = _tilejson({"X-Tenant-Id": B, "X-Agent-Token": TOKEN})
    assert resp.status_code == 404  # hide_existence: لا يكشف حتّى وجود الحقل
    assert A not in world


@pytest.mark.parametrize(
    "headers, code, outcome",
    [
        ({"X-Tenant-Id": A}, 401, "uncredentialed"),
        ({"X-Tenant-Id": A, "X-Agent-Token": "guess"}, 401, "invalid_credential"),
        ({"X-Tenant-Id": A, "X-Agent-Token": ""}, 401, "uncredentialed"),
    ],
)
def test_a_forged_tenant_header_without_the_credential_is_rejected(
    world, monkeypatch, headers, code, outcome
):
    _enforce(monkeypatch, True)
    resp = _tilejson(headers)
    assert resp.status_code == code
    assert resp.json()["code"] == outcome
    assert A not in world, "the forged tenant must never reach the DB layer"


@pytest.mark.parametrize("enforce", [True, False])
@pytest.mark.parametrize("param", ["tid", "tenant_id"])
def test_a_query_parameter_tenant_is_ignored_in_every_mode(world, monkeypatch, enforce, param):
    _enforce(monkeypatch, enforce)
    resp = _tilejson(query=f"&{param}={A}")
    assert resp.status_code == 404
    assert A not in world
    tile = TestClient(main.app).get(f"/v1/fields/{FIELD_A}/tiles/14/1/1.png?{param}={A}")
    assert tile.status_code == 403
    assert A not in world


def test_enforcement_covers_thumbnails_and_every_route_not_just_tilejson(world, monkeypatch):
    """القرار في الوسيط: المُصغَّرات والبلاطات ونقاط التربة/التضاريس ترثه بلا نسيان."""
    _enforce(monkeypatch, True)
    client = TestClient(main.app)
    forged = {"X-Tenant-Id": A}
    for path in (
        f"/v1/fields/{FIELD_A}/cdse-thumbnail.png?index=ndvi",
        f"/v1/fields/{FIELD_A}/cdse-tilejson?index=ndvi",
        f"/v1/fields/{FIELD_A}/tiles/14/1/1.png",
        f"/v1/fields/{FIELD_A}/available-dates",
        "/v1/soil/tilejson",
        "/v1/elevation/hillshade/10/1/1.png",
    ):
        assert client.get(path, headers=forged).status_code == 401, path
    assert A not in world


def test_a_service_without_its_own_token_refuses_to_trust_any_tenant(world, monkeypatch):
    """عطلُ مشغّل (503) لا رفضُ مُنادٍ (401) — تمييز #1069 نفسه."""
    _enforce(monkeypatch, True)
    monkeypatch.setattr(raster_settings, "AGENT_TOKEN", "")
    resp = _tilejson({"X-Tenant-Id": A, "X-Agent-Token": ""})
    assert resp.status_code == 503
    assert resp.json()["code"] == "unconfigured"


def test_requests_that_assert_no_tenant_are_not_blocked(monkeypatch):
    _enforce(monkeypatch, True)
    assert TestClient(main.app).get("/healthz").status_code == 200


def test_observe_mode_accepts_but_counts_and_exposes_the_evidence(world, monkeypatch):
    """observe هو وضع Railway الانتقاليّ: السلوك القديم للترويسة، لكنّه معدودٌ في /metrics كي
    يُقاس شرطُ التفعيل (uncredentialed ثابت مع حركةٍ حقيقيّة) بدل أن يُفترَض."""
    _enforce(monkeypatch, False)
    counts = raster_security_context.TENANT_ASSERTION_COUNTS
    before = dict(counts)
    assert _tilejson({"X-Tenant-Id": A}).status_code == 200
    assert _tilejson({"X-Tenant-Id": A, "X-Agent-Token": TOKEN}).status_code == 200
    assert counts["uncredentialed"] == before["uncredentialed"] + 1
    assert counts["credentialed"] == before["credentialed"] + 1
    metrics = TestClient(main.app).get("/metrics").text
    assert 'sahool_raster_tenant_assertions_total{outcome="uncredentialed"}' in metrics
    assert "sahool_raster_tenant_credential_enforced 0" in metrics
    _enforce(monkeypatch, True)
    assert "sahool_raster_tenant_credential_enforced 1" in TestClient(main.app).get("/metrics").text
