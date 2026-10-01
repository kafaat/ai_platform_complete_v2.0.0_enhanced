"""FARM-FIELDS-LIST-TRUSTS-RLS-ALONE-01: ``GET /api/v1/farms/{farm_id}/fields`` يفحص الملكيّة صراحةً.

**الفجوة (تدقيق المالك المحلّيّ §3.6، مُتحقَّقةٌ على main):** ``routers/farms.py`` كان يُعيد
حقولَ أيّ ``farm_id`` بلا فحص ملكيّة ولا ``tenant_id`` في الاستعلام — العزلُ كلُّه على RLS.
فمزرعةُ مستأجِرٍ آخر كانت تُعيد ``200 []`` (لا تمييزَ بين «ليست لك» و«بلا حقول»)، ودورٌ يتجاوز
RLS كان سيُعيد حقولَها.

**ما يُثبته:** بالموجِّه **الحقيقيّ** (الاتّصالُ وحده مُزيَّف):
  • مزرعةُ مستأجِرٍ آخر ⇒ 404 **ولا يُستعلَم عن الحقول**.
  • الاستعلامان يحملان ``tenant_id`` المستخدمِ الموثَّق (لا ترويسةَ العميل).
  • عطلُ القاعدة ⇒ 503 لا 500.

**حدُّه:** RLS الحقيقيّ لا يُشغَّل هنا (بلا Postgres) — موضعُه اختباراتُ التكامل.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime

import pytest
from api.main import get_current_user
from api.routers import farms as mod
from core.canonical_schemas import UserRole, UserSchema
from fastapi import FastAPI
from fastapi.testclient import TestClient

pytestmark = pytest.mark.unit

_TENANT = "00000000-0000-0000-0000-000000000001"
_OTHER = "ffffffff-ffff-ffff-ffff-ffffffffffff"


_OWNED = "tenant_id = $1::uuid AND farm_id = $2"


def _where(sql: str) -> str:
    """مُسنَدُ WHERE مُطبَّعَ المسافات، بلا ORDER BY."""
    clause = " ".join(sql.split()).split(" WHERE ", 1)[1]
    return clause.split(" ORDER BY ", 1)[0]


def _user() -> UserSchema:
    return UserSchema(user_id="u1", tenant_id=_TENANT, role=UserRole.MANAGER, name_ar="مدير")


class _Conn:
    """``farms`` يُمثَّل بقاموس farm_id → tenant_id؛ الاستعلامُ يُطبَّق بمعاملاته لا بافتراض."""

    def __init__(self, farms: dict[str, str]) -> None:
        self.farms = farms
        self.queries: list[tuple[str, tuple]] = []

    async def fetchval(self, sql, *args):
        self.queries.append((sql, args))
        tenant_id, farm_id = args
        return 1 if self.farms.get(farm_id) == tenant_id else None

    async def fetch(self, sql, *args):
        self.queries.append((sql, args))
        return [
            {
                "field_id": "fld-1",
                "name": "الحقل",
                "area_ha": 2.5,
                "crop": "wheat",
                "soil_type": "loam",
                "created_at": datetime(2026, 9, 30, tzinfo=UTC),
            }
        ]


def _client(monkeypatch, farms: dict[str, str], *, db_error: bool = False):
    conn = _Conn(farms)

    @asynccontextmanager
    async def fake_tenant_connection(user):
        if db_error:
            raise ConnectionError("pool down")
        yield conn

    monkeypatch.setattr(mod, "tenant_connection", fake_tenant_connection)
    app = FastAPI()
    app.include_router(mod.router)
    app.dependency_overrides[get_current_user] = _user
    return TestClient(app), conn


def test_own_farm_lists_its_fields_with_the_authenticated_tenant(monkeypatch) -> None:
    client, conn = _client(monkeypatch, {"frm_mine": _TENANT})
    resp = client.get("/api/v1/farms/frm_mine/fields", headers={"X-Tenant-Id": _OTHER})
    assert resp.status_code == 200, resp.text
    assert [f["field_id"] for f in resp.json()] == ["fld-1"]
    assert [q[1] for q in conn.queries] == [(_TENANT, "frm_mine")] * 2
    # المُسنَد كاملاً لا وجودُ عبارةٍ فيه: ``farm_id = $2 OR tenant_id = $1::uuid`` يحمل العبارةَ
    # نفسَها ويُسرِّب كلَّ المزارع حين لا يحجب RLS (مراجعةٌ مستقلّة: كان ينجو بالفحص النصّيّ).
    assert [_where(q[0]) for q in conn.queries] == [_OWNED] * 2, conn.queries


def test_another_tenants_farm_is_404_and_its_fields_are_never_queried(monkeypatch) -> None:
    client, conn = _client(monkeypatch, {"frm_theirs": _OTHER})
    resp = client.get("/api/v1/farms/frm_theirs/fields")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "farm_not_found_for_tenant"
    assert len(conn.queries) == 1, "الحقولُ لا تُقرأ قبل ثبوت الملكيّة"


def test_unknown_farm_is_404_not_an_empty_list(monkeypatch) -> None:
    client, _ = _client(monkeypatch, {})
    assert client.get("/api/v1/farms/frm_nowhere/fields").status_code == 404


def test_database_failure_is_503_not_500(monkeypatch) -> None:
    client, _ = _client(monkeypatch, {}, db_error=True)
    assert client.get("/api/v1/farms/frm_mine/fields").status_code == 503
