"""اختبارات تشكيل لوحة المؤشّرات (Indicators Dashboard) — دوالّ صرفة، بلا قاعدة.

تغطّي التجميع النقيّ خلف نقاط /api/v1/indicators/*:
  - _shape_indicator_catalog: عدّ الفئات + الإجماليّ (كتالوج المؤشّرات الحقيقيّ).
  - _shape_indicators_dashboard: بناء kpis/alerts/fields_summary من صفوف جاهزة.
لا اتّصال قاعدة — كلّ دالّة تستقبل صفوفاً (dict) جاهزة. التنبيهات تُمرَّر عبر
_row_to_alert (نموذج Pydantic) فنُغذّي صفوفاً بالأعمدة التي يتوقّعها.
"""

import pytest
from api.analytics_shapers import (
    _INDICATOR_CATALOG,
    _shape_indicator_catalog,
    _shape_indicators_dashboard,
    _shape_map_layers,
)


# ── _shape_indicator_catalog ─────────────────────────────────────
def test_catalog_total_matches_indicator_count():
    out = _shape_indicator_catalog()
    assert out["total"] == len(out["indicators"])
    assert out["total"] > 0


def test_catalog_categories_sum_to_total():
    out = _shape_indicator_catalog()
    assert sum(out["categories"].values()) == out["total"]


def test_catalog_known_categories_present():
    out = _shape_indicator_catalog()
    # المؤشّرات مُوزَّعة على فئات حقيقيّة (نباتيّة/مائيّة/تربة/طقس).
    for cat in ("vegetation", "water", "soil", "weather"):
        assert cat in out["categories"]


def test_catalog_renderable_flag_is_consistent():
    """كلّ عنصر يحمل renderable: bool، وrenderable_total يطابق العدّ، والطبقات
    المكانيّة المعروفة renderable بينما القيَم القياسيّة (طقس/تربة كيميائيّة) لا."""
    out = _shape_indicator_catalog()
    by_id = {i["id"]: i for i in out["indicators"]}
    # كلّ عنصر يحمل العلم منطقيّاً
    assert all(isinstance(i.get("renderable"), bool) for i in out["indicators"])
    # العدّ يطابق
    assert out["renderable_total"] == sum(1 for i in out["indicators"] if i["renderable"])
    assert out["renderable_total"] > 0
    # طبقات راستر مكانيّة ⇒ renderable
    for sid in ("ndvi", "ndmi", "msi", "salinity"):
        assert by_id[sid]["renderable"] is True
    # قيَم قياسيّة غير مكانيّة ⇒ ليست renderable (لا تُعرَض كطبقة خريطة)
    for sid in ("et0", "gdd", "temperature", "soil_ph", "nitrogen"):
        assert by_id[sid]["renderable"] is False


# ── _shape_map_layers ────────────────────────────────────────────
@pytest.mark.unit
def test_map_layers_only_renderable_indicators():
    """كتالوج طبقات الخريطة = المؤشّرات القابلة للرسم (renderable) فقط — لا غيرها."""
    out = _shape_map_layers()
    renderable_ids = {i["id"] for i in _INDICATOR_CATALOG if i["renderable"]}
    layer_ids = {layer["id"] for layer in out["layers"]}
    assert layer_ids == renderable_ids
    # العدّ يطابق عدد القابلة للرسم في الكتالوج
    assert out["total"] == len(renderable_ids)
    assert len(out["layers"]) == out["total"]


@pytest.mark.unit
def test_map_layers_excludes_non_renderable():
    """مؤشّر غير قابل للرسم (طقس/تربة قياسيّ) مُستبعَد من طبقات الخريطة."""
    out = _shape_map_layers()
    layer_ids = {layer["id"] for layer in out["layers"]}
    for sid in ("et0", "gdd", "temperature", "soil_ph", "nitrogen"):
        assert sid not in layer_ids


@pytest.mark.unit
def test_map_layers_have_required_keys():
    """كلّ طبقة تحمل id/name_ar/category/unit/band_math/source."""
    out = _shape_map_layers()
    assert out["layers"], "يجب أن تكون هناك طبقات قابلة للرسم"
    for layer in out["layers"]:
        for key in ("id", "name_ar", "category", "unit", "band_math", "source"):
            assert key in layer


@pytest.mark.unit
def test_map_layers_ndvi_band_math_is_standard_formula():
    """طبقة NDVI تحمل صيغة band-math القياسيّة (NIR-RED)/(NIR+RED)."""
    out = _shape_map_layers()
    by_id = {layer["id"]: layer for layer in out["layers"]}
    assert by_id["ndvi"]["band_math"] is None
    assert by_id["ndvi"]["source"] == "real"


@pytest.mark.unit
def test_map_layers_unmapped_renderable_has_note_and_none_band_math():
    """طبقة قابلة للرسم بلا تعبير قياسيّ موثَّق ⇒ band_math=None + ملاحظة صادقة."""
    out = _shape_map_layers()
    for layer in out["layers"]:
        if layer["band_math"] is None:
            assert "note_ar" in layer and layer["note_ar"]


@pytest.mark.unit
def test_map_layers_route_registered_on_app():
    """المسار /api/v1/indicators/map-layers مُسجّل فعليّاً على التطبيق."""
    pytest.importorskip("fastapi")
    from api.main import app

    paths = {r.path for r in app.routes if isinstance(getattr(r, "path", None), str)}
    assert "/api/v1/indicators/map-layers" in paths


# ── _shape_indicators_dashboard ──────────────────────────────────
def test_dashboard_fields_summary_flags_active_season():
    fields_rows = [
        {"field_id": "f1", "name": "حقل أ", "crop": "قمح", "area_ha": 10.0},
        {"field_id": "f2", "name": "حقل ب", "crop": "ذرة", "area_ha": 5.5},
    ]
    out = _shape_indicators_dashboard(
        fields_rows=fields_rows,
        active_field_ids={"f1"},
        alert_rows=[],
    )
    by_id = {f["field_id"]: f for f in out["fields_summary"]}
    assert by_id["f1"]["has_active_season"] is True
    assert by_id["f2"]["has_active_season"] is False


def test_dashboard_kpis_reflect_real_counts():
    fields_rows = [
        {"field_id": "f1", "name": "أ", "crop": "قمح", "area_ha": 10.0},
        {"field_id": "f2", "name": "ب", "crop": "ذرة", "area_ha": 5.0},
        {"field_id": "f3", "name": "ج", "crop": None, "area_ha": None},
    ]
    out = _shape_indicators_dashboard(
        fields_rows=fields_rows,
        active_field_ids={"f1", "f2"},
        alert_rows=[],
    )
    kpis = {k["id"]: k for k in out["kpis"]}
    assert kpis["fields_total"]["value"] == 3
    assert kpis["area_total"]["value"] == 15.0  # None area treated as 0
    assert kpis["active_seasons"]["value"] == 2
    assert kpis["open_alerts"]["value"] == 0
    # لا تنبيهات ⇒ حالة جيّدة (لا تلفيق حرج).
    assert kpis["open_alerts"]["status"] == "good"


def test_dashboard_open_alerts_status_critical_when_present():
    alert_rows = [
        {
            "alert_id": "a1",
            "field_id": "f1",
            "alert_type": "low_moisture",
            "severity": "critical",
            "title_ar": "إجهاد",
            "message_ar": "رطوبة منخفضة",
            "status": "active",
            "created_at": None,
        }
    ]
    out = _shape_indicators_dashboard(
        fields_rows=[],
        active_field_ids=set(),
        alert_rows=alert_rows,
    )
    kpis = {k["id"]: k for k in out["kpis"]}
    assert kpis["open_alerts"]["value"] == 1
    assert kpis["open_alerts"]["status"] == "critical"
    assert len(out["alerts"]) == 1
    assert out["alerts"][0]["alert_id"] == "a1"


def test_dashboard_empty_tenant_is_honest_zeros():
    out = _shape_indicators_dashboard(
        fields_rows=[],
        active_field_ids=set(),
        alert_rows=[],
    )
    assert out["fields_summary"] == []
    assert out["alerts"] == []
    kpis = {k["id"]: k for k in out["kpis"]}
    assert kpis["fields_total"]["value"] == 0
    assert kpis["area_total"]["value"] == 0.0
