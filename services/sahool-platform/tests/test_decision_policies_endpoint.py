"""اختبارات نقاط سجلّ سياسات القرار (routers/decision_policies) — استدعاء مباشر.

نختبر المعالِجات مباشرةً متفادين TestClient/المصادقة: العلم المُطفأ ⇒ 404 لكلّ نقطة
(إنشاء/سرد/استشارة)، وتشكيل الصفّ يفكّ JSONB. لا قاعدة في مسار 404.
"""

import api.main  # noqa: F401 — تهيئة api.main قبل استيراد الموجِّه (تفادي دورة استيراد)
import pytest
from api.routers.decision_policies import (
    PolicyCreateRequest,
    PolicyResolveRequest,
    _shape_policy_row,
    create_policy,
    list_policies,
    resolve_policy_endpoint,
)
from core.canonical_schemas import UserRole, UserSchema
from fastapi import HTTPException

pytestmark = pytest.mark.unit

_USER = UserSchema(
    user_id="u-pol",
    tenant_id="00000000-0000-0000-0000-000000000002",
    role=UserRole.OWNER,
    name_ar="مُحوكِم",
)


async def test_create_flag_off_404(monkeypatch):
    monkeypatch.delenv("SAHOOL_DECISION_DISPATCH", raising=False)
    with pytest.raises(HTTPException) as e:
        await create_policy(req=PolicyCreateRequest(name="x"), user=_USER)
    assert e.value.status_code == 404


async def test_list_flag_off_404(monkeypatch):
    monkeypatch.delenv("SAHOOL_DECISION_DISPATCH", raising=False)
    with pytest.raises(HTTPException) as e:
        await list_policies(enabled_only=False, limit=100, user=_USER)
    assert e.value.status_code == 404


async def test_resolve_flag_off_404(monkeypatch):
    monkeypatch.delenv("SAHOOL_DECISION_DISPATCH", raising=False)
    with pytest.raises(HTTPException) as e:
        await resolve_policy_endpoint(req=PolicyResolveRequest(action_type="spray"), user=_USER)
    assert e.value.status_code == 404


def test_shape_policy_row_decodes_jsonb_and_time():
    from datetime import UTC, datetime

    row = {
        "policy_id": "pol_1",
        "name": "احجب الرشّ قرب الحصاد",
        "scope": '{"action_type": "spray"}',  # JSONB كنصّ خام من asyncpg
        "effect": '{"auto_block": true}',
        "priority": 5,
        "enabled": True,
        "created_by": "u1",
        "created_at": datetime(2026, 6, 17, 9, 0, tzinfo=UTC),
    }
    out = _shape_policy_row(row)
    assert out["scope"] == {"action_type": "spray"}
    assert out["effect"] == {"auto_block": True}
    assert out["priority"] == 5
    assert out["created_at"].startswith("2026-06-17T09:00")
    # قيمة dict أصلاً تمرّ كما هي
    row2 = dict(row, scope={"crop": "dates"}, effect={})
    out2 = _shape_policy_row(row2)
    assert out2["scope"] == {"crop": "dates"}
