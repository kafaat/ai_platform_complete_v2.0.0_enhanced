"""حارس خريطة الطباعة المتجهة (A6) — الحُرّاس الأربعة + برهان سلبيّ.

① **انقلاب الاتجاهين** (يفكّ حظر A7): حدود حاضرة ⇒ admin_geometry_present=True · غائبة ⇒ **يبقى None**
   (تخطٍّ صادق، لا خريطة مزيّفة) — **لا False أبداً** (الغياب حالة لا فشل).
② **بيانات حدود حقيقيّة في SVG:** طبقات مستقلّة <g id="admin/field/indicator"> + مسارات ST_AsSVG فعليّة.
③ **تذييل الإسناد من المرجعيّة** لا نصّ ثابت (ثنائيّ اللغة؛ يتبدّل بتبدّل الرخصة/الإصدار).
④ **كتم الخصوصيّة على المتجه** (الأحدث): وحدة مكتومة ⇒ نمط «محجوب» بلا قيمة بيانات (لا تسريب باللون
   ما مُنِع بالرقم) — يمتدّ privacy_floor من النصّ إلى المتجه.

فحص صرف — ``pytest -m unit``.
"""

from __future__ import annotations

import os
import sys

import pytest

pytestmark = pytest.mark.unit

_GIS = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "services", "gis-workflow-service")
)
_RAS = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "services", "raster-service"))
for p in (_GIS, _RAS):
    if p not in sys.path:
        sys.path.insert(0, p)

import bulletin_figure as bf  # noqa: E402
import gis_boundaries_read as gbr  # noqa: E402
import svg_print_map as spm  # noqa: E402

_SRC = {
    "source": "HDX/OCHA Yemen COD-AB",
    "dataset_version": "2024.1",
    "license_title": "CC-BY-IGO 3.0",
    "retrieved_at": "2026-07-19T00:00:00Z",
}


# ── ① انقلاب الاتجاهين ──
def test_admin_geometry_present_flip_both_directions():
    b = {"governorates": [{"governorate": "Sanaa"}]}
    present = next(
        c
        for c in bf.bulletin_self_checks(b, admin_geometry_present=True)["checks"]
        if c["name"] == "admin_geometry_present"
    )
    assert present["passed"] is True  # حاضرة ⇒ pass
    absent = next(
        c for c in bf.bulletin_self_checks(b)["checks"] if c["name"] == "admin_geometry_present"
    )
    assert absent["passed"] is None  # غائبة ⇒ تخطٍّ صادق — **ليس False** (الاتجاه الثاني، الأخفى)
    # الغياب حالة لا فشل: الجودة لا تنهار (required سليمة).
    assert bf.bulletin_self_checks(b)["passed"] is True


# ── ② بيانات حدود حقيقيّة + طبقات مستقلّة ──
def test_svg_independent_layers_with_real_paths():
    svg = spm.assemble_print_map_svg(
        admin_paths=["M 0 0 L 10 0 L 10 10 Z"],
        field_paths=["M 2 2 L 4 2 L 4 4 Z"],
        attribution_source=_SRC,
    )
    assert '<g id="admin">' in svg and '<g id="field">' in svg and '<g id="indicator">' in svg
    assert "M 0 0 L 10 0 L 10 10 Z" in svg  # مسار الحدّ الفعليّ حاضر (لا خريطة فارغة)


# ── ③ تذييل الإسناد من المرجعيّة (لا نصّ ثابت) ──
def test_attribution_footer_derived_from_provenance():
    ar, en = spm.attribution_footer_lines(_SRC)
    assert "CC-BY-IGO 3.0" in ar and "CC-BY-IGO 3.0" in en  # الرخصة من السجلّ
    assert "2024.1" in ar and "HDX/OCHA Yemen COD-AB" in en  # الإصدار/المصدر من السجلّ
    assert "الحدود الإداريّة" in ar and "Administrative boundaries" in en  # ثنائيّ اللغة
    # يتبدّل بتبدّل الرخصة (مشتقّ لا منقول): إعادة تحميل A7 برخصة جديدة ⇒ تذييل جديد.
    ar2, _ = spm.attribution_footer_lines({**_SRC, "license_title": "CC-BY 4.0"})
    assert "CC-BY 4.0" in ar2 and "CC-BY-IGO 3.0" not in ar2


# ── ④ كتم الخصوصيّة على المتجه (البرهان السلبيّ الأحدث) ──
def test_privacy_suppression_extends_to_vector():
    """مديريّة مكتومة ⇒ SVG بلا قيمة بيانات لها (نمط «محجوب» + class)، والمكشوفة بلونها."""
    svg = spm.assemble_print_map_svg(
        admin_paths=None,
        field_paths=None,
        indicator_units=[
            {
                "path": "M 0 0 L 1 0 L 1 1 Z",
                "fill": "#2e7d32",
                "suppressed": False,
            },  # مكشوفة: لونها
            {
                "path": "M 5 5 L 6 5 L 6 6 Z",
                "suppressed": True,
                "fill": "#2e7d32",
            },  # مكتومة: يُتجاهَل fill
        ],
        attribution_source=_SRC,
    )
    # المكتومة: نمط محجوب + class للحارس، **بلا** لون البيانات (#2e7d32) على مسارها.
    assert 'class="suppressed-no-data"' in svg and "url(#suppressed)" in svg
    suppressed_path = 'd="M 5 5 L 6 5 L 6 6 Z"'
    seg = svg[svg.index(suppressed_path) : svg.index(suppressed_path) + 160]
    assert "#2e7d32" not in seg, "لون البيانات تسرّب على مديريّة مكتومة (كتم بصريّ مخروق)"
    assert "suppressed-no-data" in seg
    # المكشوفة تحمل لونها (لا كتم زائد).
    assert "#2e7d32" in svg and 'class="ndvi-value"' in svg


# ── مطهِّر bbox (حارس ضدّ الوحشيّ) ──
def test_bbox_sanitizer_rejects_monster_and_malformed():
    assert gbr.sanitize_bbox("44.0,15.0,45.0,16.0") == (44.0, 15.0, 45.0, 16.0)
    assert gbr.sanitize_bbox(None) is None and gbr.sanitize_bbox("") is None
    for bad in ("-180,-90,180,90", "a,b,c,d", "1,2,3", "45,16,44,15", "999,15,1000,16"):
        with pytest.raises(ValueError):
            gbr.sanitize_bbox(bad)  # وحشيّ/غير رقميّ/مقلوب/خارج المدى ⇒ fail-closed
