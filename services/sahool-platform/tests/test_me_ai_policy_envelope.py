"""TTS-LOCAL-ONLY-FALLS-BACK-TO-EXTERNAL-PROVIDER-01: ``GET /api/v1/me`` يحمل غلافَ سياسة الذكاء.

**لماذا هنا:** tts-service يُرسِل نصَّ المستأجِر إلى مزوّدٍ خارجيّ، ولم تكن له سياسةٌ يقرؤها.
المنصّةُ سلطةُ السياسة (``core/ai_policy_envelope.py``)، وميزانيّةُ المسارات 629/629 بلا هامش،
فيُحمَل الغلافُ في ``/me`` القائم (أيُّ مستخدمٍ موثَّق يقرؤه) لا في مسارٍ جديد.

**ما يُثبته:** بالموجِّه **الحقيقيّ** (الاتّصالُ وحده مُزيَّف):
  • صفٌّ صريح ⇒ ``policy_mode`` منه، بمستأجِر المستخدم الموثَّق.
  • لا صفّ ⇒ الأشدّ (``local_only``) — لا افتراضَ متساهل.
  • عطلُ القاعدة ⇒ الأشدّ، **والهويّةُ تُعاد** (``/me`` لا يسقط بسقوط القراءة).
"""

from __future__ import annotations

from contextlib import asynccontextmanager

import api.main as platform_main
import pytest
from api.main import get_current_user
from api.routers import me as mod
from core.canonical_schemas import UserRole, UserSchema
from fastapi import FastAPI
from fastapi.testclient import TestClient

pytestmark = pytest.mark.unit

_TENANT = "00000000-0000-0000-0000-000000000001"


def _user() -> UserSchema:
    return UserSchema(user_id="u1", tenant_id=_TENANT, role=UserRole.WORKER, name_ar="عامل")


class _Conn:
    def __init__(self, row: dict | None) -> None:
        self.row = row
        self.calls: list[tuple] = []

    async def fetchrow(self, sql, *args):
        self.calls.append((sql, args))
        return self.row


def _client(monkeypatch, row: dict | None, *, db_error: bool = False):
    conn = _Conn(row)

    @asynccontextmanager
    async def fake_tenant_connection(user):
        if db_error:
            raise ConnectionError("pool down")
        yield conn

    monkeypatch.setattr(platform_main, "tenant_connection", fake_tenant_connection)
    app = FastAPI()
    app.include_router(mod.router)
    app.dependency_overrides[get_current_user] = _user
    return TestClient(app), conn


def test_an_explicit_policy_row_drives_the_envelope_for_the_authenticated_tenant(monkeypatch):
    client, conn = _client(
        monkeypatch,
        {"tenant_id": _TENANT, "external_data_sharing_level": "full_external"},
    )
    resp = client.get("/api/v1/me")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["tenant_id"] == _TENANT and body["user_id"] == "u1"
    assert body["ai_policy_envelope"]["policy_mode"] == "full_external"
    assert body["ai_policy_envelope"]["tenant_id"] == _TENANT
    assert [args for _sql, args in conn.calls] == [(_TENANT,)]


def test_no_policy_row_is_the_most_restrictive_envelope(monkeypatch):
    client, _ = _client(monkeypatch, None)
    body = client.get("/api/v1/me").json()
    assert body["ai_policy_envelope"]["policy_mode"] == "local_only"
    assert body["ai_policy_envelope"]["external_llm_allowed"] is False


def test_a_database_failure_keeps_identity_and_fails_the_envelope_closed(monkeypatch):
    client, _ = _client(monkeypatch, None, db_error=True)
    resp = client.get("/api/v1/me")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["tenant_id"] == _TENANT and body["role"] == "worker"
    assert body["ai_policy_envelope"]["policy_mode"] == "local_only"
