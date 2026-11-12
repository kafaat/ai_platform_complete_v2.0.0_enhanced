"""اختبار نقطة التوأم الرقميّ (routers/field_twin) — استدعاء مباشر.

العلم المُطفأ ⇒ 404 قبل أيّ قاعدة. السلوك الكامل (تجميع من الجداول) يُغطّى تكاملاً.
"""

import api.main  # noqa: F401 — تهيئة api.main قبل استيراد الموجِّه
import pytest
from api.routers.field_twin import get_field_twin
from core.canonical_schemas import UserRole, UserSchema
from fastapi import HTTPException

pytestmark = pytest.mark.unit

_USER = UserSchema(
    user_id="u-twin",
    tenant_id="00000000-0000-0000-0000-000000000002",
    role=UserRole.OWNER,
    name_ar="مُراقِب",
)


async def test_twin_flag_off_404(monkeypatch):
    monkeypatch.delenv("SAHOOL_DECISION_DISPATCH", raising=False)
    with pytest.raises(HTTPException) as e:
        await get_field_twin(field_id="field_01", user=_USER)
    assert e.value.status_code == 404


@pytest.mark.asyncio
async def test_field_twin_uses_active_season_and_ndvi_timestamp(monkeypatch):
    from contextlib import asynccontextmanager
    from datetime import datetime, UTC

    import api.routers.field_twin as module

    monkeypatch.setenv("SAHOOL_DECISION_DISPATCH", "true")

    class FakeConn:
        async def fetchrow(self, sql, *args):
            if "FROM fields" in sql:
                return {"field_id": "f1", "name": "Field", "crop": "peanut"}
            if "FROM seasons" in sql:
                return {
                    "season_id": "s1",
                    "crops": ["wheat"],
                    "cultivar": "habib",
                    "sowing_date": None,
                }
            if "FROM execution_ledger" in sql:
                return None
            raise AssertionError(sql)

        async def fetch(self, sql, *args):
            if "FROM field_indicators" in sql:
                return [
                    {"indicator_id": "ndvi", "value": 0.75,
                     "recorded_at": datetime(2026, 10, 20, tzinfo=UTC)},
                    {"indicator_id": "evi", "value": 0.60,
                     "recorded_at": datetime(2026, 11, 13, tzinfo=UTC)},
                ]
            if "FROM dispatch_decisions" in sql:
                return []
            raise AssertionError(sql)

    @asynccontextmanager
    async def fake_connection(_user):
        yield FakeConn()

    monkeypatch.setattr(module, "tenant_connection", fake_connection)
    out = await module.get_field_twin("f1", user=_USER)
    assert out["state"] == "stale"
    assert out["observed_at"] == "2026-10-20"
    assert out["season_context"]["season_id"] == "s1"
    assert out["season_context"]["crops"] == ["wheat"]
    assert out["legacy_field_crop"] == "peanut"
    assert out["decision_authority"] == "none"
