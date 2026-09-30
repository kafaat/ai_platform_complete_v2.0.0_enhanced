"""GEOMETRY-HISTORY-RETURNS-JSONB-AS-STRING-01: ``/geometry/history`` يُعيد GeoJSON كائناً لا نصّاً.

**الفجوة (تدقيق المالك المحلّيّ §3.10، سببُها الجذريّ مُتحقَّقٌ على main):**
``field_geometry_history.geometry`` و``metadata`` من نوع JSONB (``v96_spatial_geometry_integrity.sql``)
ولا codec لـjsonb في المنصّة، فيُعيدهما asyncpg **نصّاً**؛ مسارُ الاستعادة في الملفّ نفسه
يفكّه، والسجلّ لم يفكّه. النتيجة: الواجهةُ (``toTurfFeature``) تُسقِط كلَّ مراجعة، والـE2E
يسقط بـ``AttributeError: 'str' object has no attribute 'get'``.

**ما يُثبته** بالموجِّه الحقيقيّ (الاتّصالُ وحده مُزيَّف ويُعيد ما يُعيده asyncpg فعلاً: نصّاً):
  • الهندسةُ والبياناتُ الوصفيّة كائنان.
  • المُخزَّنُ التالف ⇒ ``geometry: null`` للمراجعة وحدها، لا 500 للسجلّ كلّه.
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
_POLY = {"type": "Polygon", "coordinates": [[[44, 15], [44.01, 15], [44.01, 15.01], [44, 15]]]}


def _user() -> UserSchema:
    return UserSchema(user_id="u1", tenant_id=_TENANT, role=UserRole.MANAGER, name_ar="مدير")


def _row(revision: int, geometry: str, metadata: str = "{}") -> dict:
    return {
        "revision": revision,
        "geometry": geometry,
        "changed_by": "u1",
        "changed_at": datetime(2026, 9, 30, tzinfo=UTC),
        "reason": "edit",
        "source": "api",
        "metadata": metadata,
    }


class _Conn:
    def __init__(self, rows: list[dict]) -> None:
        self.rows = rows

    async def fetchval(self, sql, *args):
        return 1  # الحقلُ ضمن المستأجِر

    async def fetch(self, sql, *args):
        return self.rows


def _client(monkeypatch, rows: list[dict]) -> TestClient:
    @asynccontextmanager
    async def fake_tenant_connection(user):
        yield _Conn(rows)

    monkeypatch.setattr(mod, "tenant_connection", fake_tenant_connection)
    app = FastAPI()
    app.include_router(mod.router)
    app.dependency_overrides[get_current_user] = _user
    return TestClient(app)


def test_history_returns_geojson_objects_not_json_strings(monkeypatch) -> None:
    client = _client(
        monkeypatch,
        [_row(2, json.dumps(_POLY), json.dumps({"vertices": 4})), _row(1, json.dumps(_POLY))],
    )
    resp = client.get("/api/v1/fields/fld-1/geometry/history")
    assert resp.status_code == 200, resp.text
    revs = resp.json()["revisions"]
    assert [r["geometry"] for r in revs] == [_POLY, _POLY]
    assert revs[0]["metadata"] == {"vertices": 4}
    assert revs[1]["metadata"] == {}


def test_a_malformed_stored_revision_is_null_not_a_500(monkeypatch) -> None:
    client = _client(monkeypatch, [_row(2, json.dumps(_POLY)), _row(1, "{not json")])
    resp = client.get("/api/v1/fields/fld-1/geometry/history")
    assert resp.status_code == 200, resp.text
    assert [r["geometry"] for r in resp.json()["revisions"]] == [_POLY, None]
