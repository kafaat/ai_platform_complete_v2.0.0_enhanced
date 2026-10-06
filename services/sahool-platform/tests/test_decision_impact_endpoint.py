"""اختبارات نقاط الأثر/التعلُّم/الاقتصاد (routers/decision_impact) — استدعاء مباشر.

العلم المُطفأ ⇒ 404 لكلّ نقطة قبل أيّ قاعدة. السلوك الكامل (التجميع من السجلّ) يُغطّى تكاملاً.
"""

import api.main  # noqa: F401 — تهيئة api.main قبل استيراد الموجِّه
import pytest
from api.routers.decision_impact import (
    get_decision_economics,
    get_impact,
    get_learning,
)
from core.canonical_schemas import UserRole, UserSchema
from fastapi import HTTPException

pytestmark = pytest.mark.unit

_USER = UserSchema(
    user_id="u-imp",
    tenant_id="00000000-0000-0000-0000-000000000002",
    role=UserRole.OWNER,
    name_ar="مُحلِّل",
)


async def test_impact_flag_off_404(monkeypatch):
    monkeypatch.delenv("SAHOOL_DECISION_DISPATCH", raising=False)
    with pytest.raises(HTTPException) as e:
        await get_impact(field_id=None, limit=200, user=_USER)
    assert e.value.status_code == 404


async def test_learning_flag_off_404(monkeypatch):
    monkeypatch.delenv("SAHOOL_DECISION_DISPATCH", raising=False)
    with pytest.raises(HTTPException) as e:
        await get_learning(min_sample=5, limit=500, user=_USER)
    assert e.value.status_code == 404


async def test_economics_flag_off_404(monkeypatch):
    monkeypatch.delenv("SAHOOL_DECISION_DISPATCH", raising=False)
    with pytest.raises(HTTPException) as e:
        await get_decision_economics(
            field_id=None,
            area_ha=None,
            water_cost_per_m3=None,
            currency="YER",
            limit=500,
            user=_USER,
        )
    assert e.value.status_code == 404


# REQUESTED-MINUS-APPLIED-REPORTED-AS-WATER-SAVED-01 — الاستجابةُ نفسُها، عبر النقطة لا الدالّة النقيّة.
def _with_records(monkeypatch, records):
    import contextlib

    import api.routers.decision_impact as route
    from core.impact_measurement import ImpactRecord

    monkeypatch.setenv("SAHOOL_DECISION_DISPATCH", "true")

    @contextlib.asynccontextmanager
    async def _conn(_user):
        yield object()

    async def _collect(_conn, _field_id, _limit):
        return [ImpactRecord(**r) for r in records]

    monkeypatch.setattr(route, "tenant_connection", _conn)
    monkeypatch.setattr(route, "_collect_impact_records", _collect)


_UNDER_APPLIED = [
    {
        "action_type": "irrigation",
        "outcome": "executed",
        "water_requested_mm": 20.0,
        "water_applied_mm": 12.0,
    }
]


async def test_impact_response_reports_the_gap_not_a_saving(monkeypatch):
    _with_records(monkeypatch, _UNDER_APPLIED)
    out = await get_impact(field_id="f1", limit=200, user=_USER)
    assert out["requested_minus_applied_mm"] == 8.0
    assert "water_saved_mm" not in out
    assert "water_saved_mm" not in out["by_action"]["irrigation"]
    assert out["savings_claim"]["status"] == "not_established"


@pytest.mark.parametrize(("field_id", "volume"), [("f1", 160.0), (None, None)])
async def test_economics_response_prices_the_gap_and_never_calls_it_avoided_cost(
    monkeypatch, field_id, volume
):
    import json

    _with_records(monkeypatch, _UNDER_APPLIED)
    out = await get_decision_economics(
        field_id=field_id,
        area_ha=2.0,
        water_cost_per_m3=0.5,
        currency="YER",
        limit=500,
        user=_USER,
    )
    blob = json.dumps(out, ensure_ascii=False)
    assert "water_saved" not in blob and "cost_avoided" not in blob
    # 8مم × 2ها × 10 = 160م³ لحقلٍ واحد؛ وبلا حقلٍ محدّد لا تُضرب مليمتراتٌ مجموعة في مساحةٍ واحدة.
    assert out["requested_minus_applied_m3"] == volume
    assert out["savings_claim"]["status"] == "not_established"
