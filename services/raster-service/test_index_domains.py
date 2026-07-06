"""حارس تطابق: كلّ مؤشّر قابل للتصيير (له evalscript في ``INDEX_EXPR``) يجب أن يملك
نطاق ألوان صريحاً في ``tile_render._INDEX_DOMAIN``. بلا نطاق يسقط ``colorize`` إلى مدى
NDVI الافتراضيّ (−0.2..0.9)، فمؤشّرات كـreci/gci (نِسَب 0..~5) تُقصَّر كلّها إلى قمّة
المقياس وتظهر بلون مُشبَع واحد بلا معنًى. هذا الحارس يمنع رجوع تلك الفجوة عند إضافة مؤشّر.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit


def test_every_rendered_index_has_an_explicit_colormap_domain():
    import cdse_client
    import tile_render

    domains = set(tile_render._INDEX_DOMAIN)
    missing = sorted(i for i in cdse_client.INDEX_EXPR if i not in domains)
    assert not missing, f"مؤشّرات مُصيَّرة بلا نطاق ألوان صريح (ستُلوَّن بمدى NDVI الخاطئ): {missing}"


def test_advanced_top20_indices_have_sane_ranges():
    """المؤشّرات المتقدّمة نِسَبيّة المدى (reci/gci) يجب ألّا تُترك على مدى NDVI الضيّق."""
    import tile_render

    d = tile_render._INDEX_DOMAIN
    # reci/gci نِسَب (B08/Bx − 1) تصل ~5 — يجب أن يتجاوز الحدّ الأعلى مدى NDVI (0.9).
    for idx in ("reci", "gci"):
        assert idx in d, idx
        vmax = d[idx][1]
        assert vmax >= 2.0, f"{idx} vmax={vmax} ما زال ضيّقاً (مدى نِسبيّ ~0..5)"
    # bsi (تربة عارية) يجب أن يُعكَس تدرّجه (عالٍ = أحمر/سيّئ للغطاء).
    assert d["bsi"][2] is True, "bsi يجب أن يكون معكوس التدرّج (عالٍ = تربة عارية)"


def test_index_legend_uses_the_domain_not_default_for_advanced():
    """``index_legend`` يعكس النطاق الحقيقيّ (لا الافتراضيّ) للمؤشّرات المتقدّمة."""
    import tile_render

    leg = tile_render.index_legend("gci")
    assert leg["vmax"] >= 2.0  # ليس 0.9 الافتراضيّ
    bsi = tile_render.index_legend("bsi")
    assert bsi["invert"] is True
    assert bsi["palette"] == "RdYlGn_reversed"
