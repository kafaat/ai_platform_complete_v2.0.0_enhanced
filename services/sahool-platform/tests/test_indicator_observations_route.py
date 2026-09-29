"""M4 (مراجعة v25): المشاهداتُ القانونيّة لكلّ حقل عبر المنصّة — مسارٌ واحدٌ بـ``{view}`` مغلق.

**الفجوة:** indicators-service يُعرّف ``/v1/fields/{field_id}/observations`` و
``/v1/fields/{field_id}/observation-timeline``، والمنصّة لم تكشف إلّا catalog/map-layers/
dashboard. والراتشِت كان عند 628/629 فيُكشَف الاثنان خلف مسارٍ واحد.

**ما يُثبِته هذا الملفّ** بتطبيقٍ يحمل الموجِّه **الحقيقيّ** و``_assert_field_in_tenant``
**الحقيقيّ** (الاتّصال وحده مُزيَّف — RLS يُحاكى بـ``fetchval`` يُعيد ``None``) و
``httpx.MockTransport`` (لا شبكة):
  • كلٌّ من العرضين يبلغ مسارَ الخدمة الصحيح بـ``season_id``/``indicators`` ويُعيد جسمَها.
  • المستأجِرُ يُحقَن من المستخدم الموثَّق، وترويسةُ العميل ``X-Tenant-Id`` لا تُمرَّر.
  • عرضٌ خارج القائمة ⇒ 422 **بلا** نداءٍ للخدمة.
  • حقلُ مستأجِرٍ آخر ⇒ 404 **بلا** نداءٍ للخدمة (ترتيبُ الملكيّة قبل النداء).
  • أعطالُ الخدمة: ≥400 يُمرَّر برمزه وتفصيله، و``HTTPError`` ⇒ 502، وعطلُ القاعدة ⇒ 503.

**حدُّه:** RLS الحقيقيّ لا يُشغَّل هنا (بلا Postgres)؛ يُثبَت أنّ المسار يُنادي المُساعِدَ
القانونيّ ويحترم حكمَه — وصحّةُ RLS نفسها موضعُها اختباراتُ التكامل.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

import httpx
import pytest
from api.main import get_current_user
from api.routers import indicators as mod
from core.canonical_schemas import UserRole, UserSchema
from fastapi import FastAPI
from fastapi.testclient import TestClient

pytestmark = pytest.mark.unit

_TENANT = "00000000-0000-0000-0000-000000000001"
_BASE = "/api/v1/fields/fld-1/indicator-observations"


def _user() -> UserSchema:
    return UserSchema(user_id="u1", tenant_id=_TENANT, role=UserRole.MANAGER, name_ar="مدير")


class _Conn:
    """اتّصالٌ مُزيَّف: ``fetchval`` يُحاكي RLS — ``owned`` يقرّر هل يرى المستأجِرُ الحقل."""

    def __init__(self, owned: bool) -> None:
        self.owned = owned
        self.queries: list[tuple] = []

    async def fetchval(self, sql, *args):
        self.queries.append((sql, args))
        return 1 if self.owned else None


def _client(monkeypatch, *, owned: bool = True, handler=None, db_error: bool = False):
    conn = _Conn(owned)

    @asynccontextmanager
    async def fake_tenant_connection(user):
        if db_error:
            raise ConnectionError("pool down")
        yield conn

    monkeypatch.setattr(mod, "tenant_connection", fake_tenant_connection)
    monkeypatch.setenv("INDICATORS_SERVICE_URL", "http://indicators.test:8000/")

    upstream: list[httpx.Request] = []
    real = httpx.AsyncClient

    def recording(request: httpx.Request) -> httpx.Response:
        upstream.append(request)
        return (handler or (lambda r: httpx.Response(200, json={"canonical": True})))(request)

    monkeypatch.setattr(
        mod.httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(recording), **kw)
    )
    app = FastAPI()
    app.include_router(mod.router)
    app.dependency_overrides[get_current_user] = _user
    return TestClient(app), upstream, conn


@pytest.mark.parametrize("view", ["observations", "observation-timeline"])
def test_each_view_reaches_its_service_route_with_the_authenticated_tenant(
    monkeypatch, view
) -> None:
    body = {"field_id": "fld-1", "season_id": "s-1", "canonical": True, "view": view}
    client, upstream, conn = _client(monkeypatch, handler=lambda r: httpx.Response(200, json=body))
    resp = client.get(
        f"{_BASE}/{view}",
        params={"season_id": "s-1", "indicators": "ndvi,ndmi", "smuggled": "x"},
        headers={"X-Tenant-Id": "ffffffff-ffff-ffff-ffff-ffffffffffff"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json() == body
    (req,) = upstream
    assert req.url.host == "indicators.test"
    assert req.url.path == f"/v1/fields/fld-1/{view}"
    assert dict(req.url.params) == {"season_id": "s-1", "indicators": "ndvi,ndmi"}
    assert req.headers["x-tenant-id"] == _TENANT, "المستأجِر من JWT لا من ترويسة العميل"
    assert "authorization" not in req.headers
    assert conn.queries and conn.queries[0][1] == ("fld-1",), "الملكيّة فُحِصت قبل النداء"


def test_indicators_defaults_to_ndvi_like_the_service(monkeypatch) -> None:
    client, upstream, _ = _client(monkeypatch)
    assert client.get(f"{_BASE}/observations", params={"season_id": "s-1"}).status_code == 200
    assert dict(upstream[0].url.params) == {"season_id": "s-1", "indicators": "ndvi"}


@pytest.mark.parametrize("view", ["ownership", "timeline", "observations.json", "OBSERVATIONS"])
def test_a_view_outside_the_closed_set_is_422_and_never_proxied(monkeypatch, view) -> None:
    client, upstream, conn = _client(monkeypatch)
    resp = client.get(f"{_BASE}/{view}", params={"season_id": "s-1"})
    assert resp.status_code == 422, resp.text
    assert upstream == [] and conn.queries == []


def test_missing_season_id_is_422_and_never_proxied(monkeypatch) -> None:
    client, upstream, conn = _client(monkeypatch)
    assert client.get(f"{_BASE}/observations").status_code == 422
    assert upstream == [] and conn.queries == []


def test_a_field_of_another_tenant_is_404_and_never_proxied(monkeypatch) -> None:
    """RLS يُخفي حقلَ المستأجِر الآخر ⇒ ``_assert_field_in_tenant`` يرفع 404 — كبقيّة
    مسارات الحقل — ولا يُنادى indicators-service (الذي يثق بـ``X-Tenant-Id`` وحده)."""
    client, upstream, conn = _client(monkeypatch, owned=False)
    resp = client.get(f"{_BASE}/observations", params={"season_id": "s-1"})
    assert resp.status_code == 404
    assert upstream == [], "لا نداءَ للخدمة قبل ثبوت الملكيّة"
    assert len(conn.queries) == 1


@pytest.mark.parametrize(
    ("status", "payload"),
    [
        (424, {"detail": "no consistent real canonical observation available"}),
        (503, {"detail": "canonical observation store unavailable"}),
        (400, {"detail": "invalid X-Tenant-Id"}),
    ],
)
def test_upstream_errors_pass_through_with_their_status_and_detail(
    monkeypatch, status, payload
) -> None:
    client, _, _ = _client(monkeypatch, handler=lambda r: httpx.Response(status, json=payload))
    resp = client.get(f"{_BASE}/observation-timeline", params={"season_id": "s-1"})
    assert resp.status_code == status
    assert resp.json()["detail"] == payload["detail"]


def test_an_unreachable_service_is_502(monkeypatch) -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    client, _, _ = _client(monkeypatch, handler=refuse)
    resp = client.get(f"{_BASE}/observations", params={"season_id": "s-1"})
    assert resp.status_code == 502
    assert "indicators-service" in resp.json()["detail"]


def test_a_database_failure_during_the_ownership_check_is_503_not_proxied(monkeypatch) -> None:
    client, upstream, _ = _client(monkeypatch, db_error=True)
    resp = client.get(f"{_BASE}/observations", params={"season_id": "s-1"})
    assert resp.status_code == 503
    assert upstream == []


def test_the_route_is_registered_on_the_real_app() -> None:
    from api.main import app

    paths = {r.path for r in app.routes if isinstance(getattr(r, "path", None), str)}
    assert "/api/v1/fields/{field_id}/indicator-observations/{view}" in paths
