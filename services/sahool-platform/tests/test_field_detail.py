"""اختبارات تفاصيل الحقل المتقدّمة (v37) — الأجزاء الصرفة offline.

تغطّي: نموذج التحديث الجزئيّ (FieldUpdateRequest) والتحقّقات (نطاق pH، طول
النصوص، قيم سالبة)، وبنّاء جملة UPDATE الجزئيّة (_build_field_update) — التمييز
بين «لم يُرسَل» و«أُرسِل null»، ترتيب القيم/الـplaceholders، ورفض التحديث الفارغ.
لا حاجة لقاعدة بيانات.
"""

import pytest
from api.main import (
    _FIELD_ADVANCED_COLUMNS,
    FieldDetail,
    FieldUpdateRequest,
    _build_field_update,
)
from pydantic import ValidationError


def test_build_update_only_sent_fields():
    # حقلان فقط مُرسَلان ⇒ جملة SET تشملهما بترتيب الأعمدة والقيم مطابقة.
    req = FieldUpdateRequest(soil_ph=6.8, owner_name="أبو محمد")
    clause, values = _build_field_update(req)
    assert clause == "soil_ph = $1, owner_name = $2"
    assert values == [6.8, "أبو محمد"]


def test_build_update_respects_column_order():
    # الترتيب يتبع _FIELD_ADVANCED_COLUMNS لا ترتيب الإدخال (registry_no آخِرها).
    req = FieldUpdateRequest(registry_no="REG-1", soil_ph=7.0)
    clause, values = _build_field_update(req)
    assert clause == "soil_ph = $1, registry_no = $2"
    assert values == [7.0, "REG-1"]


def test_build_update_explicit_null_clears_column():
    # أُرسِل null صراحةً ⇒ يُدرَج في SET (يمسح العمود) — يميّزه عن «لم يُرسَل».
    req = FieldUpdateRequest(aspect=None)
    clause, values = _build_field_update(req)
    assert clause == "aspect = $1"
    assert values == [None]


def test_build_update_unset_fields_ignored():
    # حقل لم يُرسَل لا يظهر في الجملة (لا يُداس بـnull).
    req = FieldUpdateRequest(soil_n=12.5)
    clause, values = _build_field_update(req)
    assert "soil_p" not in clause and "soil_k" not in clause
    assert clause == "soil_n = $1"
    assert values == [12.5]


def test_build_update_empty_raises():
    # لا حقول مُرسَلة ⇒ ValueError (الـendpoint يحوّلها 422؛ لا UPDATE فارغ).
    with pytest.raises(ValueError):
        _build_field_update(FieldUpdateRequest())


def test_build_update_placeholders_sequential():
    # الـplaceholders متسلسلة $1..$N بلا فجوات مهما تباعدت الأعمدة المُرسَلة.
    req = FieldUpdateRequest(soil_ph=6.5, elevation_m=1200.0, lease_years=5)
    clause, values = _build_field_update(req)
    assert clause == "soil_ph = $1, elevation_m = $2, lease_years = $3"
    assert values == [6.5, 1200.0, 5]


def test_update_request_rejects_ph_out_of_range():
    # pH خارج [0,14] ⇒ ValidationError (تربة لا تتجاوز هذا المدى).
    with pytest.raises(ValidationError):
        FieldUpdateRequest(soil_ph=15.0)
    with pytest.raises(ValidationError):
        FieldUpdateRequest(soil_ph=-1.0)


def test_update_request_rejects_negative_rainfall():
    # كميّات/تراكيز سالبة مرفوضة (ge=0).
    with pytest.raises(ValidationError):
        FieldUpdateRequest(annual_rainfall_mm=-5.0)
    with pytest.raises(ValidationError):
        FieldUpdateRequest(soil_ec=-0.1)


def test_update_request_rejects_overlong_strings():
    # aspect محدود بـ20 محرفاً (VARCHAR(20)).
    with pytest.raises(ValidationError):
        FieldUpdateRequest(aspect="x" * 21)
    with pytest.raises(ValidationError):
        FieldUpdateRequest(owner_name="ن" * 101)


def test_advanced_columns_match_model_fields():
    # كلّ عمود في القائمة المرجعيّة له حقل مطابق في النموذجين (لا انجراف).
    update_fields = set(FieldUpdateRequest.model_fields)
    detail_fields = set(FieldDetail.model_fields)
    for col in _FIELD_ADVANCED_COLUMNS:
        assert col in update_fields, col
        assert col in detail_fields, col


def test_field_detail_extends_summary():
    # FieldDetail يرث الملخّص (field_id/name_ar) ويضيف الأعمدة المتقدّمة.
    fd = FieldDetail(
        field_id="fld_x",
        farm_id="",
        name_ar="حقل",
        crop="wheat",
        area_ha=10.0,
        quality_grade="READY",
        health_summary_ar="—",
        soil_ph=6.9,
        owner_name="مالك",
    )
    assert fd.field_id == "fld_x"
    assert fd.soil_ph == 6.9
    assert fd.owner_name == "مالك"
    assert fd.soil_k is None  # غير مُعبّأ ⇒ None
