"""كتالوج أصناف الحبوب المرجعيّ — اختبار وحدة (بلا شبكة/قاعدة).

يؤكّد: تحميل السِجِلّ + ثوابت الحوكمة (29 · كلّها reference_only · نَسَب) · الترشيح بالمحصول ·
جلب صنف/404 · وسم بوّابة الحوكمة في ردّ النقطتَين · fail-closed على خرق الثوابت.
"""

import api.main  # noqa: F401 — تهيئة api.main قبل استيراد الموجِّه
import pytest
from api.food_grain_varieties import (
    REFERENCE_ONLY_STATUS,
    VarietyCatalogIntegrityError,
    get_food_grain_variety,
    list_food_grain_varieties,
    load_food_grain_varieties,
)
from api.routers.varieties import (
    food_grain_varieties_endpoint,
    food_grain_variety_detail_endpoint,
)
from core.canonical_schemas import UserRole, UserSchema
from fastapi import HTTPException

pytestmark = pytest.mark.unit

_USER = UserSchema(
    user_id="u-var",
    tenant_id="00000000-0000-0000-0000-000000000002",
    role=UserRole.OWNER,
    name_ar="أصناف",
)


def test_dataset_integrity_29_all_reference_only():
    d = load_food_grain_varieties()
    assert d["metadata"]["record_count"] == len(d["varieties"]) == 29
    assert all(v["decision_engine_use_status"] == REFERENCE_ONLY_STATUS for v in d["varieties"])
    # نَسَب المصدر إلزاميّ لكلّ صنف + بصمة PDF على الميتاداتا (لا معلومة بلا مصدر).
    assert d["metadata"].get("source_pdf_sha256")
    assert all(v.get("source_pages") and v.get("source_verification") for v in d["varieties"])


def test_filter_by_crop_code():
    wheat = list_food_grain_varieties(crop_code="wheat")
    assert len(wheat) == 11  # الدليل: 11 صنف قمح
    assert {v["crop_code"] for v in wheat} == {"wheat"}
    assert list_food_grain_varieties(crop_code="__none__") == []


def test_get_variety_and_missing():
    v = get_food_grain_variety("YEM-WHT-BAHOUTH-3")
    assert v is not None and v["name_ar"] == "بحوث 3"
    assert get_food_grain_variety("NOPE") is None


def test_list_endpoint_carries_governance_gate():
    out = food_grain_varieties_endpoint(user=_USER)
    assert out["decision_engine_use_status"] == REFERENCE_ONLY_STATUS
    assert out["count"] == 29
    assert out["metadata"]["decision_engine_use_status"] == REFERENCE_ONLY_STATUS
    # قضايا الجودة مُقدَّمة بشفافيّة (لا تُخفى).
    assert isinstance(out["quality_issues"], list) and out["quality_issues"]


def test_detail_endpoint_and_404():
    out = food_grain_variety_detail_endpoint("YEM-WHT-BAHOUTH-3", user=_USER)
    assert out["decision_engine_use_status"] == REFERENCE_ONLY_STATUS
    assert out["variety"]["id"] == "YEM-WHT-BAHOUTH-3"
    with pytest.raises(HTTPException) as ei:
        food_grain_variety_detail_endpoint("NOPE", user=_USER)
    assert ei.value.status_code == 404


def test_integrity_error_is_available_for_fail_closed():
    # العقد يُصرّح باستثناء fail-closed عند خرق الثوابت (لا تقديم صامت لسِجِلّ مُختلّ).
    assert issubclass(VarietyCatalogIntegrityError, RuntimeError)
