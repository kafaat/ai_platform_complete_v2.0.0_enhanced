"""تحقّق V66.1 — وصل النشرة الإقليميّة بنقطة HTTP (محوّل الصفوف + حارس الراوت الساكن).

- ``bulletin_rows_to_records`` يحوّل صفوف DB (gov→governorate، NDVI، scene_count) لسجلّات.
- الراوت يعزل بالمستأجِر (tenant_connection) ويبني النشرة الصرف؛ لا NDVI ⇒ unknown.
- منطق المحوّل صرف (قابل للاختبار)؛ الاستعلام SQL يُغطّى بالتكامل (حارس ساكن هنا).
"""

from __future__ import annotations

import pathlib

from core.regional_bulletin import build_regional_bulletin, bulletin_rows_to_records

_RB_ROUTE = pathlib.Path(__file__).resolve().parents[1] / "api" / "routers" / "regional_bulletin.py"


def test_rows_to_records_maps_gov_and_ndvi():
    rows = [
        {
            "field_id": "f1",
            "gov": "Sanaa",
            "tenant_id": "t1",
            "ndvi_current": 0.6,
            "ndvi_historical_mean": 0.45,
            "scene_count": 8,
        }
    ]
    recs = bulletin_rows_to_records(rows)
    assert recs[0]["governorate"] == "Sanaa"  # gov → governorate
    assert recs[0]["ndvi_current"] == 0.6 and recs[0]["ndvi_historical_mean"] == 0.45


def test_rows_to_records_handles_null_ndvi_and_malformed():
    rows = [{"field_id": "f2", "gov": "Ibb", "tenant_id": "t1"}, "bad", None]
    recs = bulletin_rows_to_records(rows)
    assert len(recs) == 1  # المشوّه يُسقَط
    assert recs[0]["ndvi_current"] is None  # لا اختلاق


def test_end_to_end_rows_to_bulletin_with_privacy():
    # 6 حقول محافظة واحدة ⇒ منشورة؛ NDVI شذوذ +0.15 ⇒ exceptional.
    rows = [
        {
            "field_id": f"f{i}",
            "gov": "Dhamar",
            "tenant_id": "t1",
            "ndvi_current": 0.65,
            "ndvi_historical_mean": 0.50,
            "scene_count": 6,
        }
        for i in range(6)
    ]
    bulletin = build_regional_bulletin(bulletin_rows_to_records(rows))
    gov = bulletin["governorates"][0]
    assert gov["status"] == "published" and gov["condition"] == "exceptional"
    # صغيرة (2 حقول) ⇒ مكتومة للخصوصيّة.
    small = build_regional_bulletin(bulletin_rows_to_records(rows[:2]))["governorates"][0]
    assert small["status"] == "suppressed_for_privacy"


def test_null_ndvi_group_is_unknown_not_guessed():
    rows = [
        {"field_id": f"f{i}", "gov": "Taiz", "tenant_id": "t1", "scene_count": 0} for i in range(6)
    ]
    gov = build_regional_bulletin(bulletin_rows_to_records(rows))["governorates"][0]
    assert gov["status"] == "published"
    assert gov["condition"] == "unknown"  # لا NDVI ⇒ لا تخمين


# ── حارس ساكن للراوت: عزل مستأجِر + منطق صرف + إغلاق آمن + خصوصيّة ─────────────────
def test_route_is_tenant_scoped_and_privacy_safe():
    src = _RB_ROUTE.read_text(encoding="utf-8")
    assert "tenant_connection(user)" in src, "الراوت يجب أن يعزل بالمستأجِر (RLS)"
    assert "require_permission(Permission.FIELD_VIEW)" in src, "الراوت يجب أن يتطلّب صلاحيّة"
    assert "build_regional_bulletin" in src and "bulletin_rows_to_records" in src
    assert "_DB_POOL is None" in src, "القاعدة غير مفعّلة ⇒ نشرة فارغة موثَّقة (لا اختلاق)"
    assert "min_fields_privacy" in src, "أرضيّة الخصوصيّة مُمرَّرة"
    assert "status_code=503" in src  # تعذّر القاعدة ⇒ فشل موثَّق
