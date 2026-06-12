"""اختبارات إثراء التضاريس (offline صرف) — رياضيّات Horn + التصنيف + التفسير.

يتحقّق من: حساب المنحدر/السمت من نافذة DEM 3×3 (طريقة Horn) باتّجاهات معروفة،
تحويل السمت إلى بوصلة، تصنيف المنحدر/الارتفاع بعتباته، والتفسير الزراعي الموحّد
(بما فيه الصدق عند غياب البيانات). لا قاعدة/شبكة.
"""

import math

import pytest
from core.engines.dem_enrichment import (
    azimuth_to_aspect,
    classify_elevation,
    classify_slope,
    enrich_terrain,
    slope_aspect_from_window,
)

# ─── slope_aspect_from_window (Horn) ─────────────────────────────────────


def test_window_east_rising_faces_west():
    # الارتفاع يزيد شرقاً ⇒ المنحدر هابط نحو الغرب
    z = [[0, 0, 1], [0, 0, 1], [0, 0, 1]]
    out = slope_aspect_from_window(z, 1.0)
    assert out["aspect"] == "W"
    assert out["azimuth_deg"] == pytest.approx(270.0)
    assert out["slope_pct"] > 0


def test_window_north_rising_faces_south():
    # الارتفاع يزيد شمالاً ⇒ المنحدر هابط نحو الجنوب
    z = [[1, 1, 1], [0.5, 0.5, 0.5], [0, 0, 0]]
    out = slope_aspect_from_window(z, 1.0)
    assert out["aspect"] == "S"
    assert out["azimuth_deg"] == pytest.approx(180.0)


def test_window_flat_has_no_aspect():
    out = slope_aspect_from_window([[5, 5, 5], [5, 5, 5], [5, 5, 5]], 1.0)
    assert out["slope_pct"] == 0.0
    assert out["azimuth_deg"] is None
    assert out["aspect"] == "FLAT"


def test_window_slope_magnitude_matches_grade():
    # Horn يمتدّ على خليّتين (شمال↔جنوب): فرق 1م على 2×10م ⇒ ميل 5٪
    z = [[0, 0, 0], [0, 0, 0], [1, 1, 1]]  # يزيد جنوباً 1م
    out = slope_aspect_from_window(z, 10.0)
    assert out["slope_pct"] == pytest.approx(5.0, abs=0.01)
    assert out["aspect"] == "N"  # يزيد جنوباً ⇒ هابط شمالاً


def test_window_rejects_bad_shape_and_cell():
    with pytest.raises(ValueError):
        slope_aspect_from_window([[0, 0], [0, 0]], 1.0)
    with pytest.raises(ValueError):
        slope_aspect_from_window([[0, 0, 0]] * 3, 0.0)


# ─── azimuth_to_aspect ───────────────────────────────────────────────────


def test_azimuth_to_compass_cardinals():
    assert azimuth_to_aspect(0) == "N"
    assert azimuth_to_aspect(90) == "E"
    assert azimuth_to_aspect(180) == "S"
    assert azimuth_to_aspect(270) == "W"
    assert azimuth_to_aspect(45) == "NE"
    assert azimuth_to_aspect(359) == "N"  # يلتفّ حول الشمال
    assert azimuth_to_aspect(None) == "FLAT"


# ─── classify_slope ──────────────────────────────────────────────────────


def test_classify_slope_terracing_threshold():
    assert classify_slope(1.0)["class"] == "flat"
    assert classify_slope(5.0)["class"] == "gentle"
    assert classify_slope(10.0)["class"] == "moderate"
    assert classify_slope(20.0)["class"] == "steep"
    assert classify_slope(40.0)["class"] == "very_steep"
    # التدريج يُنصح به من المتوسّط فأعلى
    assert classify_slope(10.0)["terracing_advised"] is True
    assert classify_slope(5.0)["terracing_advised"] is False
    assert classify_slope(40.0)["erosion_risk"] == "high"


def test_classify_slope_handles_missing():
    assert classify_slope(None)["class"] == "unknown"
    assert classify_slope(-1.0)["class"] == "unknown"


# ─── classify_elevation ──────────────────────────────────────────────────


def test_classify_elevation_zones_and_frost():
    assert classify_elevation(300.0)["class"] == "coastal"
    assert classify_elevation(300.0)["frost_risk"] == "none"
    assert classify_elevation(1000.0)["class"] == "foothill"
    assert classify_elevation(1800.0)["class"] == "midland"
    assert classify_elevation(2500.0)["class"] == "highland"
    assert classify_elevation(2500.0)["frost_risk"] == "likely_winter"
    assert classify_elevation(None)["class"] == "unknown"


# ─── enrich_terrain (التفسير الموحّد) ────────────────────────────────────


def test_enrich_terrain_combines_advisories():
    # مرتفع شديد الانحدار مواجه للجنوب ⇒ تدريج + صقيع + تعرّض دافئ
    out = enrich_terrain(elevation_m=2500.0, slope_pct=20.0, aspect="S")
    assert out["display_only"] is True  # طبقة عرض لا تفرض قراراً
    assert out["has_terrain_data"] is True
    joined = " ".join(out["advisories_ar"])
    assert "تدريج" in joined  # منحدر شديد
    assert "صقيع" in joined  # مرتفعات
    assert out["aspect"]["exposure"] == "warm"  # جنوبي


def test_enrich_terrain_honest_when_no_data():
    out = enrich_terrain(elevation_m=None, slope_pct=None, aspect=None)
    assert out["has_terrain_data"] is False
    assert "لا بيانات" in out["honesty_note_ar"]  # صدق: لا اختراع


def test_enrich_terrain_flat_warns_drainage():
    out = enrich_terrain(elevation_m=400.0, slope_pct=1.0, aspect="FLAT")
    assert any("صرف" in a for a in out["advisories_ar"])  # أرض منبسطة ⇒ صرف


def test_horn_slope_is_finite_for_real_window():
    # نافذة واقعيّة (أمتار) ⇒ ميل منطقي ومحدود
    z = [[1200, 1205, 1210], [1198, 1203, 1208], [1196, 1201, 1206]]
    out = slope_aspect_from_window(z, 30.0)  # خليّة SRTM ~30م
    assert math.isfinite(out["slope_pct"])
    assert 0 <= out["slope_pct"] < 100
    assert out["aspect"] in ("N", "NE", "E", "SE", "S", "SW", "W", "NW", "FLAT")
