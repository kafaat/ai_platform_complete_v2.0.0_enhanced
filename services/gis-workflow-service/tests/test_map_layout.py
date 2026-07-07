"""تحقّق — تخطيط خريطة النشر (منطق صرف): scale bar مستدير + caption صادق + legend/فئات.

لا matplotlib. يؤكّد: scale bar رقم 1/2/5×10ⁿ؛ caption ناقص ⇒ «غير متاح» (لا تلفيق)؛
تسميات الفئات من عتبات صاعدة؛ legend يُسقِط الشاذّ.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from map_layout import (  # noqa: E402
    build_map_layout,
    caption_lines,
    class_break_labels,
    format_distance_ar,
    legend_entries,
    nice_scale_bar_m,
)

pytestmark = pytest.mark.unit


def test_nice_scale_bar_is_round_1_2_5():
    # عرض 8000م، الربع=2000 ⇒ أكبر {1,2,5}×10ⁿ ≤2000 = 2000 (2 كم).
    sb = nice_scale_bar_m(8000)
    assert sb == {"length_m": 2000.0, "label": "2 كم"}
    # عرض 3000م، الربع=750 ⇒ 500 (500 م).
    assert nice_scale_bar_m(3000)["length_m"] == 500.0
    # عرض غير صالح ⇒ None (لا مقياس مُلفَّق).
    assert nice_scale_bar_m(0) is None and nice_scale_bar_m("x") is None


def test_format_distance_ar_units_and_missing():
    assert format_distance_ar(500) == "500 م"
    assert format_distance_ar(2000) == "2 كم"
    assert format_distance_ar(1500) == "1.5 كم"
    assert format_distance_ar(None) == "غير متاح"
    assert format_distance_ar(-5) == "غير متاح"


def test_caption_missing_fields_are_explicit_not_fabricated():
    lines = caption_lines({"source": "CDSE/Sentinel-2", "resolution_m": 10, "quality_score": 0.82})
    joined = "\n".join(lines)
    assert "المصدر: CDSE/Sentinel-2" in joined
    assert "الدقّة: 10 م" in joined
    assert "درجة الجودة: 82%" in joined
    # الحقول غير المُمرَّرة تُعلَن «غير متاح» صراحةً (لا اختلاق تاريخ/إسقاط).
    assert "تاريخ الالتقاط: غير متاح" in joined
    assert "الإسقاط: غير متاح" in joined


def test_caption_empty_meta_all_missing():
    lines = caption_lines(None)
    assert all(line.endswith("غير متاح") for line in lines)
    assert len(lines) == 7  # كلّ الحقول معلَنة


def test_class_break_labels_from_ascending_breaks():
    assert class_break_labels([0.2, 0.4, 0.6]) == ["< 0.2", "0.2–0.4", "0.4–0.6", "> 0.6"]
    # غير صاعدة/غير رقميّة ⇒ فارغ (لا فئات مُختلَقة).
    assert class_break_labels([0.4, 0.2]) == []
    assert class_break_labels(["a", "b"]) == []


def test_legend_entries_drops_malformed():
    classes = [
        {"label": "منخفض", "color": "#eee"},
        {"label": "", "color": "#333"},  # بلا تسمية
        {"color": "#111"},  # بلا تسمية
        "x",  # غير dict
    ]
    assert legend_entries(classes) == [{"label": "منخفض", "color": "#eee"}]


def test_build_map_layout_assembles_all_parts():
    layout = build_map_layout(
        {
            "title": "اتجاه NDVI — الجوف 2020–2024",
            "map_width_m": 8000,
            "classes": [{"label": "منخفض", "color": "#ffffcc"}],
            "meta": {"source": "CDSE", "resolution_m": 10},
        }
    )
    assert layout["title"].startswith("اتجاه NDVI")
    assert layout["scale_bar"]["label"] == "2 كم"
    assert layout["north_arrow"] == {"symbol": "N", "position": "top_right"}
    assert layout["legend"]["entries"] == [{"label": "منخفض", "color": "#ffffcc"}]
    assert any("المصدر: CDSE" in c for c in layout["caption"])
