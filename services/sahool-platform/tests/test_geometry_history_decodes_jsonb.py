"""GEOMETRY-HISTORY-RETURNS-JSONB-AS-STRING-01: سجلُّ هندسة الحقل يُعيد GeoJSON كائناً لا نصّاً.

**الفجوة:** عمودا ``field_geometry_history.geometry`` و``metadata`` من نوع ``JSONB NOT NULL``
(``migrations/v96_spatial_geometry_integrity.sql``)، والمنصّة لا تُسجِّل codec لـjsonb، فيُعيدهما
asyncpg **نصّاً**. كان ``GET /api/v1/fields/{field_id}/geometry/history`` يُمرِّر النصّ كما هو:
فيُسقِط ``toTurfFeature`` في الواجهة كلَّ مراجعة، ويسقط ``live_full_e2e.py`` بـ``AttributeError``.

**ما يُثبِته هذا الملفّ** بتطبيقٍ يحمل الموجِّه **الحقيقيّ** (الاتّصال وحده مُزيَّف، وصفوفه
تحمل العمودين نصَّ ``json.dumps`` تماماً كما يُعيدهما asyncpg):
  • ``geometry`` يخرج قاموسَ Polygon لا نصّاً.
  • ``metadata`` يخرج قاموساً — بمحتواه، وفارغاً حين يكون ``"{}"``.

**حدُّه:** بلا Postgres؛ صحّةُ الكتابة إلى السجلّ نفسها موضعُها اختباراتُ التكامل.
"""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from datetime import UTC, datetime

import pytest
from api.main import get_current_user
from api.routers import fields as mod
from core.canonical_schemas import UserRole, UserSchema
from fastapi import FastAPI
from fastapi.testclient import TestClient

pytestmark = pytest.mark.unit

_TENANT = "00000000-0000-0000-0000-000000000001"
_POLYGON = {
    "type": "Polygon",
    "coordinates": [[[44.0, 15.0], [44.01, 15.0], [44.01, 15.01], [44.0, 15.01], [44.0, 15.0]]],
}


def _user() -> UserSchema:
    return UserSchema(user_id="u1", tenant_id=_TENANT, role=UserRole.MANAGER, name_ar="مدير")


def _row(revision: int, metadata: dict) -> dict:
    """صفٌّ كما يُعيده asyncpg بلا codec لـjsonb: العمودان نصّان."""
    return {
        "revision": revision,
        "geometry": json.dumps(_POLYGON),
        "changed_by": "u1",
        "changed_at": datetime(2026, 9, 1, tzinfo=UTC),
        "reason": "edit",
        "source": "map",
        "metadata": json.dumps(metadata),
    }


class _Conn:
    """اتّصالٌ مُزيَّف: ``fetchval`` يرى الحقلَ للمستأجِر، و``fetch`` يُعيد السجلّ نصوصاً."""

    async def fetchval(self, sql, *args):
        return 1

    async def fetch(self, sql, *args):
        return [_row(2, {"vertices": 4}), _row(1, {})]


def test_history_returns_geometry_and_metadata_as_objects_not_strings(monkeypatch) -> None:
    @asynccontextmanager
    async def fake_tenant_connection(user):
        yield _Conn()

    monkeypatch.setattr(mod, "tenant_connection", fake_tenant_connection)
    app = FastAPI()
    app.include_router(mod.router)
    app.dependency_overrides[get_current_user] = _user

    resp = TestClient(app).get("/api/v1/fields/fld-1/geometry/history")

    assert resp.status_code == 200, resp.text
    newest, oldest = resp.json()["revisions"]
    assert newest["geometry"] == _POLYGON, "GeoJSON كائنٌ لا نصّ"
    assert oldest["geometry"] == _POLYGON
    assert newest["metadata"] == {"vertices": 4}
    assert oldest["metadata"] == {}
