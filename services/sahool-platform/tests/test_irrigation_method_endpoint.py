"""اختبار نقاط طريقة الريّ (routers/irrigation_method) — استدعاء مباشر.

يثبت: (أ) قائمة الطرق الخمس؛ (ب) ملمح طريقة (عربيّة)؛ (ج) gross = صافٍ ÷ كفاءة
(الغمر يسحب أكثر) + م³/ها؛ (د) كفاءة مُمرَّرة تتجاوز الطريقة. بلا شبكة/قاعدة.
"""

import api.main  # noqa: F401 — تهيئة api.main قبل استيراد الموجِّه
import pytest
from api.routers.irrigation_method import (
    GrossRequest,
    compute_gross,
    get_method,
    list_methods,
)
from core.canonical_schemas import UserRole, UserSchema

pytestmark = pytest.mark.unit

_USER = UserSchema(
    user_id="u-method",
    tenant_id="00000000-0000-0000-0000-000000000002",
    role=UserRole.OWNER,
    name_ar="طريقة",
)


def test_list_methods():
    out = list_methods(user=_USER)
    assert len(out["methods"]) == 5
    keys = {m["method"] for m in out["methods"]}
    assert {"flood", "furrow", "sprinkler", "pivot", "drip"} <= keys


def test_get_method_arabic():
    out = get_method(method="تقطير", user=_USER)
    assert out["method"] == "drip"
    assert out["application_efficiency"] == 0.90


def test_gross_flood_pulls_more_than_drip():
    flood = compute_gross(req=GrossRequest(net_mm=55.0, method="flood"), user=_USER)
    drip = compute_gross(req=GrossRequest(net_mm=55.0, method="drip"), user=_USER)
    assert flood["gross_mm"] == pytest.approx(100.0, abs=0.1)
    assert flood["gross_m3_ha"] == pytest.approx(1000.0, abs=1.0)
    assert flood["gross_mm"] > drip["gross_mm"]
    assert flood["pressurized"] is False


def test_explicit_efficiency_overrides():
    out = compute_gross(
        req=GrossRequest(net_mm=50.0, method="flood", application_efficiency=1.0), user=_USER
    )
    assert out["gross_mm"] == pytest.approx(50.0)
    assert out["application_efficiency"] == 1.0
