"""تحقّق V60.3 — عنقدة مناطق الإنتاجيّة متعدّدة المؤشّرات (NDVI + NDMI/RECI/MSAVI + انحدار).

منهجيّة Management Zone Analyst: العنقدة على **متّجه ميزات متعدّد الأبعاد** لا NDVI وحده،
كي تعكس المناطق الرطوبة (NDMI) والتغذية (RECI) والطوبوغرافيا (الانحدار) — لا الحيويّة فقط.

- ``kmeans_nd`` حتميّ (بلا numpy/عشوائيّة): نفس الإدخال ⇒ نفس المراكز، مستقلّ عن الترتيب.
- المعايرة min-max تمنع هيمنة مقياس واحد (الانحدار 0..90 مقابل NDVI −1..1).
- شبكة مساعدة تحمل إشارة مستقلّة عن NDVI ⇒ تقسيم يختلف عن NDVI وحده (قيمة حقيقيّة مضافة).
- سقوط آمن: شبكة مساعدة غير مُتراصفة ⇒ تُتجاهَل (مسار NDVI أحاديّ دون تغيير).
- التوافق الخلفيّ: بلا شبكات مساعدة ⇒ مطابق تماماً لـV60.1 (``ndvi_kmeans_clustering``).
- عبر عقد الأداة: ``basis="ndvi"`` صريح يحترم NDVI وحده؛ الافتراضيّ يستعمل المساعدة.

منطق صرف — وظيفة Unit Tests.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.ai_agronomist import productivity_zones as PZ  # noqa: E402
from services.ai_agronomist import productivity_zones_clustering as C  # noqa: E402

_BBOX = [44.0, 16.0, 44.4, 16.4]


# ── العنقدة متعدّدة الأبعاد الأساسيّة ───────────────────────────────────────────
def test_kmeans_nd_is_deterministic_and_order_independent():
    vecs = [[0.1, 0.9], [0.12, 0.88], [0.8, 0.1], [0.82, 0.12]]
    a = C.kmeans_nd(vecs, 2)
    b = C.kmeans_nd(list(reversed(vecs)), 2)
    assert a == b  # لا عشوائيّة، مستقلّ عن الترتيب
    assert len(a) == 2 and len(a[0]) == 2


def test_normalization_prevents_scale_dominance():
    # الميزة الثانية بمقياس ضخم (شبيه بالانحدار بالدرجات) لكن تفصل نفس المجموعات.
    grids = [
        [[0.5, 0.5], [0.5, 0.5]],  # NDVI ثابت (لا إشارة) — مُتغيّر السيّد فقط للصلاحية
        [[2.0, 2.0], [88.0, 88.0]],  # ميزة كبيرة المقياس تفصل شمال/جنوب
    ]
    pos, vecs = C._feature_vectors(grids, 2, 2)
    assert len(vecs) == 4
    # بعد المعايرة كلّ ميزة ضمن [0,1] فلا تهيمن الأكبر عدديّاً.
    for v in vecs:
        assert all(0.0 <= x <= 1.0 for x in v)


def test_multiindex_splits_differently_than_ndvi_only():
    # NDVI موحّد أفقيّاً (لا يفصل صفوفاً)، لكن مؤشّر الرطوبة يفصل الشمال (جافّ) عن الجنوب (رطب).
    # NDVI وحده ⇒ لا مجموعتان مكانيّتان؛ إضافة المساعدة ⇒ تقسيم شمال/جنوب حقيقيّ.
    ndvi = [[0.55, 0.55], [0.55, 0.55]]
    # NDVI مطابق تماماً ⇒ NDVI أحاديّ يعيد None (قيمة واحدة).
    assert C.zones_from_ndvi_grid(ndvi, _BBOX, 2) is None
    # مع شبكة رطوبة تفصل الصفوف ⇒ عنقدة N-بُعديّة تُنتج منطقتَين.
    ndmi = [[0.10, 0.10], [0.70, 0.70]]
    # NDVI يجب أن يحمل تبايناً طفيفاً كي تكون القيم المميَّزة ≥2 (شرط السيّد).
    ndvi2 = [[0.50, 0.52], [0.58, 0.60]]
    out = C.zones_from_ndvi_grid(ndvi2, _BBOX, 2, aux_grids={"ndmi": ndmi})
    assert out is not None
    assert out["feature_names"] == ["ndvi", "ndmi"]
    assert out["k_effective"] == 2
    assert len(out["zones"]) >= 2


def test_misaligned_aux_grid_is_ignored_failsafe():
    ndvi = [[0.15, 0.15], [0.80, 0.80]]
    # شبكة مساعدة بأبعاد خاطئة ⇒ تُتجاهَل ⇒ مسار NDVI أحاديّ (feature_names=["ndvi"]).
    bad_aux = {"slope": [[1.0, 2.0, 3.0]]}  # 1×3 لا يطابق 2×2
    out = C.zones_from_ndvi_grid(ndvi, _BBOX, 2, aux_grids=bad_aux)
    assert out is not None
    assert out["feature_names"] == ["ndvi"]


def test_backward_compat_no_aux_matches_ndvi_only():
    grid = [[0.15, 0.15, 0.15, 0.15]] * 2 + [[0.80, 0.80, 0.80, 0.80]] * 2
    baseline = C.zones_from_ndvi_grid(grid, _BBOX, 2)
    with_none = C.zones_from_ndvi_grid(grid, _BBOX, 2, aux_grids=None)
    assert baseline is not None and with_none is not None
    # نفس التصنيفات والمراكز — لا انحراف عن سلوك V60.1.
    assert baseline["ndvi_centroids"] == with_none["ndvi_centroids"]
    assert baseline["feature_names"] == ["ndvi"]
    assert {z["productivity_class"] for z in baseline["zones"]} == {"low", "high"}


def test_extract_aux_grids_dimension_match_only():
    ndvi = [[0.1, 0.2], [0.3, 0.4]]
    params = {
        "ndmi_grid": [[0.1, 0.2], [0.3, 0.4]],  # يطابق
        "slope_grid": [[1, 2, 3]],  # لا يطابق ⇒ يُسقَط
        "reci_grid": "not-a-grid",  # مشوّه ⇒ يُسقَط
    }
    aux = C.extract_aux_grids(params, None, ndvi_grid=ndvi)
    assert aux is not None
    assert set(aux.keys()) == {"ndmi"}


def test_extract_aux_grids_none_without_ndvi():
    assert C.extract_aux_grids({"ndmi_grid": [[0.1]]}, None, ndvi_grid=None) is None


# ── التكامل عبر عقد الأداة ──────────────────────────────────────────────────────
def test_propose_uses_multiindex_when_aux_present():
    ndvi = [[0.50, 0.52], [0.58, 0.60]]
    ndmi = [[0.10, 0.10], [0.70, 0.70]]
    out = PZ.propose_productivity_zones(
        {"bbox": _BBOX, "zone_count": 2, "ndvi_grid": ndvi, "ndmi_grid": ndmi},
        field_id="f",
    )
    assert out["method"] == "multi_index_kmeans_clustering"
    assert out["feature_names"] == ["ndvi", "ndmi"]
    assert out["requires_user_confirmation"] is True
    for z in out["productivity_zones"]:
        assert z["zoning_method"] == "multi_index_kmeans_clustering"
        assert "multi_index_grid_kmeans" in z["drivers"]
        assert "ndmi" in z["drivers"]  # صدق: الميزة الفعليّة تظهر كموجِّه


def test_propose_explicit_ndvi_basis_ignores_aux():
    ndvi = [[0.15, 0.15], [0.80, 0.80]]
    ndmi = [[0.70, 0.70], [0.10, 0.10]]
    out = PZ.propose_productivity_zones(
        {"bbox": _BBOX, "zone_count": 2, "basis": "ndvi", "ndvi_grid": ndvi, "ndmi_grid": ndmi},
        field_id="f",
    )
    # basis=ndvi صريح ⇒ لا تُستعمل الشبكات المساعدة.
    assert out["method"] == "ndvi_kmeans_clustering"
    assert out["feature_names"] == ["ndvi"]
    assert all("multi_index_grid_kmeans" not in z["drivers"] for z in out["productivity_zones"])


def test_propose_default_basis_is_multi_index_capable():
    # بلا basis صريح ⇒ الافتراض multi_index ⇒ يستعمل المساعدة عند توفّرها.
    ndvi = [[0.50, 0.52], [0.58, 0.60]]
    slope = [[2.0, 2.0], [40.0, 40.0]]
    out = PZ.propose_productivity_zones(
        {"bbox": _BBOX, "zone_count": 2, "ndvi_grid": ndvi, "slope_grid": slope},
        field_id="f",
    )
    assert out["basis"] == "multi_index"
    assert out["method"] == "multi_index_kmeans_clustering"
    assert "slope" in out["feature_names"]
