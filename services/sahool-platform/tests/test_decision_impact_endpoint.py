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
