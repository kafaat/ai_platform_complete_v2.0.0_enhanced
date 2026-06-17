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
