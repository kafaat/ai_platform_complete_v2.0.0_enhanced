"""حارس تنظيف مضلّع SAM2 (sam2-inference._mask_to_polygon) — العلّة الحيّة.

قناع SAM2 حدوده «درج بكسل» كثيف الرؤوس؛ بعد التحويل لـ4326 تنهار رؤوس غير متجاورة
إلى نفس الموضع (~سم) فتُطلِق تحذير «تقاطع ذاتيّ/رأس مكرّر» في حارس الواجهة
(drawingValidation.ts: ringSelfIntersectionRisk، مقارنة toFixed(7)). الإصلاح (بموافقة
المستخدم — الخيار المعتدل): تبسيط بمقياس أمتار + إزالة الرؤوس شبه المكرّرة + make_valid.

- تأكيدات الدوالّ النقيّة (_dedupe_ring / _tol_in_crs_units): بلا shapely/GPU ⇒ تعمل دوماً.
- تكامل _mask_to_polygon على قناع درجيّ اصطناعيّ: importorskip لـshapely/rasterio/numpy
  (غائبة في طبقة الوحدات الدنيا/بيئة المراجعة) — يتحقّق أنّ الناتج لا يُطلِق حدس الواجهة.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_SVC_DIR = Path(__file__).resolve().parents[1] / "services" / "sam2-inference"


def _load_sam2_main():
    pytest.importorskip("fastapi")
    if str(_SVC_DIR) not in sys.path:
        sys.path.insert(0, str(_SVC_DIR))
    mod = sys.modules.get("main")
    if mod is not None and "sam2-inference" not in getattr(mod, "__file__", "").replace("\\", "/"):
        sys.modules.pop("main", None)
    # P1 decomposition: منطق المعالجة انتقل إلى sam2_runtime.py الشقيقة — نتبع الرموز هناك.
    rt = sys.modules.get("sam2_runtime")
    if rt is not None and "sam2-inference" not in getattr(rt, "__file__", "").replace("\\", "/"):
        sys.modules.pop("sam2_runtime", None)
    import main
    import sam2_runtime

    assert "sam2-inference" in getattr(main, "__file__", "").replace("\\", "/"), (
        "استُورِدت وحدة main لخدمة أخرى (تصادم اسم)"
    )
    assert hasattr(sam2_runtime, "_mask_to_polygon"), "استُورِدت وحدة sam2_runtime خاطئة"
    return sam2_runtime


# ── دوالّ نقيّة (بلا shapely) ────────────────────────────────────────────────
def test_dedupe_ring_drops_near_duplicates_keeps_closure():
    main = _load_sam2_main()
    ring = [[0.0, 0.0], [0.0, 0.0], [1e-9, 1e-9], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0], [0.0, 0.0]]
    d = main._dedupe_ring(ring)
    assert d[0] == d[-1], "الحلقة يجب أن تبقى مغلقة"
    assert len(d) < len(ring), "الرؤوس شبه المكرّرة يجب أن تُحذَف"
    # لا رأسان متتاليان ضمن eps.
    for i in range(len(d) - 1):
        assert d[i] != d[i + 1] or i == len(d) - 2


def test_dedupe_ring_preserves_distinct_vertices():
    main = _load_sam2_main()
    square = [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0], [0.0, 0.0]]
    d = main._dedupe_ring(square)
    assert d == square, "المربّع النظيف يجب ألّا يتغيّر"


def test_tol_in_crs_units_projected_vs_geographic():
    main = _load_sam2_main()

    class _Proj:
        is_geographic = False

    class _Geo:
        is_geographic = True

    assert main._tol_in_crs_units(3.0, _Proj()) == pytest.approx(3.0), "UTM (متر) ⇒ كما هي"
    assert main._tol_in_crs_units(3.0, _Geo()) == pytest.approx(3.0 / 111_320.0, rel=1e-6)
    assert main._tol_in_crs_units(3.0, None) == pytest.approx(3.0), "بلا CRS ⇒ عامله كمُسقَط"


# ── تكامل: قناع درجيّ → مضلّع نظيف لا يُطلِق حدس الواجهة ───────────────────────
def test_mask_to_polygon_output_does_not_trip_frontend_heuristic():
    main = _load_sam2_main()
    np = pytest.importorskip("numpy")
    pytest.importorskip("shapely")
    pytest.importorskip("rasterio")
    from rasterio.crs import CRS
    from rasterio.transform import Affine

    mask = np.zeros((30, 30), dtype=np.uint8)
    mask[5:25, 5:25] = 1
    for i in range(5, 25):  # حافّة درجيّة (رؤوس كثيفة تُحاكي درج بكسل SAM2)
        mask[i, 25 + (i % 2)] = 1
    transform = Affine(10.0, 0, 500000, 0, -10.0, 4000000)  # بكسل 10م (UTM)
    crs = CRS.from_epsg(32638)  # UTM 38N (أمتار)

    poly = main._mask_to_polygon(mask, transform, crs)
    ring = poly["coordinates"][0]
    assert poly["type"] == "Polygon" and ring[0] == ring[-1], "مضلّع مغلق"

    # صلاحية GeoJSON: هندسة shapely صالحة (لا تقاطع ذاتيّ).
    from shapely.geometry import shape

    assert shape(poly).is_valid, "المضلّع الناتج يجب أن يكون صالحاً هندسيّاً (shapely.is_valid)"

    # عدد رؤوس معقول: بعد التبسيط المتريّ لا يبقى درج البكسل الكثيف (قناع 20×20 بكسل
    # درجيّ ⇒ عشرات الرؤوس خاماً؛ نتوقّع أقلّ بكثير بعد التبسيط).
    assert 4 <= len(ring) <= 40, f"عدد رؤوس غير معقول بعد التبسيط: {len(ring)}"

    # حدس الواجهة: أيّ رأسين غير متجاورين يتطابقان عند toFixed(7) ⇒ تحذير.
    seen: dict[tuple[float, float], int] = {}
    for i, p in enumerate(ring[:-1]):
        key = (round(p[0], 7), round(p[1], 7))
        prev = seen.get(key)
        assert prev is None or abs(prev - i) <= 1, (
            f"رأسان غير متجاورين متطابقان (توقّع تحذير الواجهة) عند {i} و{prev}"
        )
        seen[key] = i


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
