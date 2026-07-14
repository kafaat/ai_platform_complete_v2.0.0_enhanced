"""WX-I1 wiring — hourly energy-aware MPC recommendation route (server-owned, fail-closed).

يختبر أنّ المسار: (١) يأخذ tenant_id من JWT لا من الجسم؛ (٢) يمنع الحقل غير المملوك؛
(٣) يفوّض المنسّق الخادميّ ويمرّر horizon/persist بأمانة؛ (٤) يثبّت توصية-فقط
(`execution_allowed=False`) حتى على حمولة blocked. الحساب الحقيقيّ للمنسّق مُختبَر مستقلّاً
في test_irrigation_runtime_orchestrator.py — هنا نختبر التوصيل فقط.
"""

from __future__ import annotations

import contextlib

import pytest
from api.routers import irrigation_mpc as mod


class _FakeUser:
    def __init__(self, tenant_id: str):
        self.tenant_id = tenant_id


@contextlib.asynccontextmanager
async def _fake_tenant_conn(tenant_id):
    yield object()  # conn لا يُستعمَل فعليّاً (المنسّق مُموَّه)


@pytest.mark.asyncio
async def test_hourly_recommendation_delegates_and_is_server_owned(monkeypatch):
    seen = {}

    async def fake_owns(tenant_id, field_id):
        seen["owns"] = (tenant_id, field_id)
        return True

    async def fake_orch(conn, *, tenant_id, field_id, horizon_hours, persist):
        seen["orch"] = {
            "tenant_id": tenant_id,
            "field_id": field_id,
            "horizon_hours": horizon_hours,
            "persist": persist,
        }
        return {
            "status": "verified",
            "mode": "operational",
            "facts_source": "server_owned_canonical_truth",
            "execution_allowed": False,
            "persistence_status": "persisted",
        }

    monkeypatch.setattr(mod, "_field_belongs_to_tenant", fake_owns)
    monkeypatch.setattr(mod, "orchestrate_irrigation_recommendation", fake_orch)
    monkeypatch.setattr(mod, "tenant_connection", _fake_tenant_conn)

    req = mod.HourlyRecommendationRequest(horizon_hours=24, persist=False)
    out = await mod.irrigation_mpc_hourly_recommendation("field-1", req, user=_FakeUser("tenant-A"))

    # tenant من JWT لا من الجسم؛ horizon/persist مُمرَّران بأمانة.
    assert seen["owns"] == ("tenant-A", "field-1")
    assert seen["orch"] == {
        "tenant_id": "tenant-A",
        "field_id": "field-1",
        "horizon_hours": 24,
        "persist": False,
    }
    assert out["status"] == "verified"
    assert out["execution_allowed"] is False
    assert out["recommendation_only"] is True


@pytest.mark.asyncio
async def test_hourly_recommendation_blocks_unowned_field_without_orchestrating(monkeypatch):
    async def fake_owns(tenant_id, field_id):
        return False

    def _boom(*a, **k):  # يجب ألّا يُستدعى المنسّق للحقل غير المملوك
        raise AssertionError("orchestrator must not run for unowned field")

    monkeypatch.setattr(mod, "_field_belongs_to_tenant", fake_owns)
    monkeypatch.setattr(mod, "orchestrate_irrigation_recommendation", _boom)

    out = await mod.irrigation_mpc_hourly_recommendation(
        "field-x", mod.HourlyRecommendationRequest(), user=_FakeUser("tenant-A")
    )
    assert out["status"] == "blocked"
    assert out["reason"] == "field_not_owned"


@pytest.mark.asyncio
async def test_hourly_recommendation_pins_recommendation_only_on_blocked(monkeypatch):
    async def fake_owns(tenant_id, field_id):
        return True

    async def fake_orch(conn, **kwargs):
        # حمولة blocked مبكّرة من المنسّق (بلا execution_allowed/recommendation_only)
        return {"status": "blocked", "reason": "canonical_water_state_blocked"}

    monkeypatch.setattr(mod, "_field_belongs_to_tenant", fake_owns)
    monkeypatch.setattr(mod, "orchestrate_irrigation_recommendation", fake_orch)
    monkeypatch.setattr(mod, "tenant_connection", _fake_tenant_conn)

    out = await mod.irrigation_mpc_hourly_recommendation(
        "field-1", mod.HourlyRecommendationRequest(), user=_FakeUser("tenant-A")
    )
    assert out["status"] == "blocked"
    # العقد يبقى توصية-فقط حتى على blocked
    assert out["execution_allowed"] is False
    assert out["recommendation_only"] is True
