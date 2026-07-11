"""WX-10.4 — GDD كـView تراكميّ فوق سلسلة canonical يوميّة: parity + نَسَب + تغطية.

يثبت: (أ) legacy parity (عقد GDD القديم byte-compatible)؛ (ب) نَسَب تراكميّ مستقلّ عن آخر
يوم؛ (ج) reorder-invariance بعد الترتيب القانونيّ؛ (د) إزالة تكرار حتميّة صريحة؛ (هـ) فصل
التغطية عن جودة البيانات؛ (و) لا يوم مفقود يُحتسَب صفراً؛ (ز) عتبات المحصول تُغيّر النتيجة
والنَّسَب؛ (ح) حدود base/upper مطابقة للنواة؛ (ط) حتميّة.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from canonical_daily_weather_series import (  # noqa: E402
    build_canonical_daily_series,
    gdd_view,
)
from gdd import gdd_agro_product  # noqa: E402

pytestmark = pytest.mark.unit

_CFG = dict(base_c=10.0, upper_cutoff_c=30.0, method="modified")


def _records(dates, tmins, tmaxs, snaps=None):
    out = []
    for i, d in enumerate(dates):
        r = {"date": d, "t_min_c": tmins[i], "t_max_c": tmaxs[i]}
        if snaps:
            r["weather_snapshot_id"] = snaps[i]
        out.append(r)
    return out


_DATES = ["2026-04-01", "2026-04-02", "2026-04-03"]
_TMIN = [12.0, 14.0, 16.0]
_TMAX = [26.0, 28.0, 32.0]


# ── (أ) legacy parity ────────────────────────────────────────────────────────
def test_gdd_view_legacy_contract_is_byte_compatible():
    series = build_canonical_daily_series(_records(_DATES, _TMIN, _TMAX))
    view = gdd_view(series, period_start="2026-04-01", period_end="2026-04-03", **_CFG)
    direct = gdd_agro_product(
        daily_t_min=_TMIN,
        daily_t_max=_TMAX,
        base_c=10.0,
        upper_cutoff_c=30.0,
        method="modified",
        start_date="2026-04-01",
        end_date="2026-04-03",
    )
    for k in (
        "product",
        "calculation_version",
        "unit",
        "daily_gdd",
        "accumulated_gdd",
        "thresholds_used",
        "valid_period",
        "input_completeness",
        "quality_status",
        "limitations",
    ):
        assert view[k] == direct[k], k


def test_gdd_view_adds_lineage_and_coverage_envelope():
    series = build_canonical_daily_series(_records(_DATES, _TMIN, _TMAX))
    view = gdd_view(series, period_start="2026-04-01", period_end="2026-04-03", **_CFG)
    assert view["derived_from"] == "canonical_daily_weather_series"
    assert view["gdd_lineage_id"].startswith("gddseq/")
    assert len(view["contributing_state_ids"]) == 3
    cov = view["coverage"]
    assert cov["expected_days"] == 3 and cov["observed_days"] == 3
    assert cov["missing_days"] == 0 and cov["coverage_ratio"] == 1.0
    assert cov["inclusive_dates"] is True


# ── (ب) نَسَب تراكميّ مستقلّ عن آخر يوم ────────────────────────────────────────
def test_lineage_changes_when_any_day_changes():
    a = gdd_view(build_canonical_daily_series(_records(_DATES, _TMIN, _TMAX)), **_CFG)
    tmax2 = [26.0, 28.0, 33.0]  # آخر يوم مختلف
    b = gdd_view(build_canonical_daily_series(_records(_DATES, _TMIN, tmax2)), **_CFG)
    assert a["gdd_lineage_id"] != b["gdd_lineage_id"]
    tmin2 = [11.0, 14.0, 16.0]  # أوّل يوم مختلف
    c = gdd_view(build_canonical_daily_series(_records(_DATES, tmin2, _TMAX)), **_CFG)
    assert c["gdd_lineage_id"] != a["gdd_lineage_id"]


def test_lineage_changes_with_threshold_or_method():
    base = gdd_view(build_canonical_daily_series(_records(_DATES, _TMIN, _TMAX)), **_CFG)
    thr = gdd_view(
        build_canonical_daily_series(_records(_DATES, _TMIN, _TMAX)),
        base_c=8.0,
        upper_cutoff_c=30.0,
        method="modified",
    )
    meth = gdd_view(
        build_canonical_daily_series(_records(_DATES, _TMIN, _TMAX)),
        base_c=10.0,
        upper_cutoff_c=30.0,
        method="simple",
    )
    assert thr["gdd_lineage_id"] != base["gdd_lineage_id"]
    assert meth["gdd_lineage_id"] != base["gdd_lineage_id"]


def test_lineage_not_attributed_to_last_snapshot_only():
    # تغيير هويّة لقطة يوم في المنتصف يغيّر النَّسَب (ليس آخر يوم فقط).
    snaps_a = ["s1", "s2", "s3"]
    snaps_b = ["s1", "sX", "s3"]
    a = gdd_view(build_canonical_daily_series(_records(_DATES, _TMIN, _TMAX, snaps_a)), **_CFG)
    b = gdd_view(build_canonical_daily_series(_records(_DATES, _TMIN, _TMAX, snaps_b)), **_CFG)
    assert a["gdd_lineage_id"] != b["gdd_lineage_id"]


# ── (ج) reorder-invariance ───────────────────────────────────────────────────
def test_input_reorder_does_not_change_result_after_canonical_ordering():
    fwd = _records(_DATES, _TMIN, _TMAX, ["s1", "s2", "s3"])
    rev = list(reversed(fwd))
    a = gdd_view(build_canonical_daily_series(fwd), **_CFG)
    b = gdd_view(build_canonical_daily_series(rev), **_CFG)
    assert a["gdd_lineage_id"] == b["gdd_lineage_id"]
    assert a["accumulated_gdd"] == b["accumulated_gdd"]
    assert a["contributing_state_ids"] == b["contributing_state_ids"]


# ── (د) إزالة تكرار حتميّة صريحة ──────────────────────────────────────────────
def test_duplicate_day_resolved_deterministically_not_double_counted():
    recs = _records(_DATES, _TMIN, _TMAX, ["s1", "s2", "s3"])
    dup = {"date": "2026-04-02", "t_min_c": 99.0, "t_max_c": 99.0, "weather_snapshot_id": "sZ"}
    series1 = build_canonical_daily_series([*recs, dup])
    series2 = build_canonical_daily_series([dup, *recs])  # ترتيب وصول مختلف
    assert series1["observed_days"] == 3  # لم يُحتسَب اليوم المكرّر مرّتين
    assert series1["duplicates_resolved"] == 1  # صُرِّح بالحسم (لا إسقاط صامت)
    # الاختيار حتميّ مستقلّ عن ترتيب الوصول.
    assert series1["ordered_days"] == series2["ordered_days"]


# ── (هـ) التغطية مفصولة عن جودة البيانات ──────────────────────────────────────
def test_coverage_gap_downgrades_series_quality_but_not_legacy():
    # يومان فقط من نطاق 3 أيّام (فجوة) — الأيّام الموجودة صحيحة.
    recs = _records(["2026-04-01", "2026-04-03"], [12.0, 16.0], [26.0, 28.0])
    view = gdd_view(
        build_canonical_daily_series(recs),
        period_start="2026-04-01",
        period_end="2026-04-03",
        **_CFG,
    )
    cov = view["coverage"]
    assert cov["expected_days"] == 3 and cov["observed_days"] == 2
    assert cov["missing_days"] == 1 and cov["coverage_ratio"] < 1.0
    # جودة البيانات القديمة تبقى validated (الأيّام الموجودة صحيحة)...
    assert view["quality_status"] == "validated"
    # ...لكنّ جودة السلسلة لا تُعطى validated لوجود فجوة (تغطية ≠ جودة).
    assert view["series_quality_status"] == "degraded_incomplete_coverage"


# ── (و) لا يوم مفقود يُحتسَب صفراً ────────────────────────────────────────────
def test_missing_temperature_day_is_none_not_zero():
    recs = _records(_DATES, [12.0, None, 16.0], [26.0, None, 28.0])
    view = gdd_view(
        build_canonical_daily_series(recs),
        period_start="2026-04-01",
        period_end="2026-04-03",
        **_CFG,
    )
    assert view["daily_gdd"][1] is None  # مفقود ≠ صفر
    assert view["quality_status"] == "degraded"  # النواة تخفض عند يوم غير محدود
    # التراكم يستثني اليوم المفقود.
    direct = gdd_agro_product(
        daily_t_min=[12.0, None, 16.0],
        daily_t_max=[26.0, None, 28.0],
        base_c=10.0,
        upper_cutoff_c=30.0,
        method="modified",
    )
    assert view["accumulated_gdd"] == direct["accumulated_gdd"]


# ── (ز) عتبات المحصول تُغيّر النتيجة ───────────────────────────────────────────
def test_different_crop_thresholds_change_accumulation_and_lineage():
    a = gdd_view(
        build_canonical_daily_series(_records(_DATES, _TMIN, _TMAX)),
        base_c=10.0,
        upper_cutoff_c=30.0,
        method="modified",
    )
    b = gdd_view(
        build_canonical_daily_series(_records(_DATES, _TMIN, _TMAX)),
        base_c=5.0,
        upper_cutoff_c=35.0,
        method="modified",
    )
    assert a["accumulated_gdd"] != b["accumulated_gdd"]
    assert a["gdd_lineage_id"] != b["gdd_lineage_id"]


# ── (ح) حدود base/upper مطابقة للنواة ─────────────────────────────────────────
def test_boundary_base_and_upper_match_kernel():
    # يوم كلّه تحت الأساس ⇒ 0؛ يوم فوق السقف ⇒ مقصوص.
    recs = _records(["2026-05-01", "2026-05-02"], [2.0, 20.0], [8.0, 40.0])
    view = gdd_view(
        build_canonical_daily_series(recs),
        period_start="2026-05-01",
        period_end="2026-05-02",
        **_CFG,
    )
    direct = gdd_agro_product(
        daily_t_min=[2.0, 20.0],
        daily_t_max=[8.0, 40.0],
        base_c=10.0,
        upper_cutoff_c=30.0,
        method="modified",
        start_date="2026-05-01",
        end_date="2026-05-02",
    )
    assert view["daily_gdd"] == direct["daily_gdd"]
    assert view["daily_gdd"][0] == 0.0  # كلّه تحت الأساس


# ── (ط) حتميّة + غياب base_c ──────────────────────────────────────────────────
def test_deterministic_same_series_same_config():
    s = build_canonical_daily_series(_records(_DATES, _TMIN, _TMAX))
    assert gdd_view(s, **_CFG) == gdd_view(s, **_CFG)


def test_missing_base_c_is_insufficient_no_fabrication():
    view = gdd_view(
        build_canonical_daily_series(_records(_DATES, _TMIN, _TMAX)),
        base_c=None,
        upper_cutoff_c=30.0,
        method="modified",
    )
    assert view["quality_status"] == "insufficient"
    assert view["accumulated_gdd"] is None


# ── حارس ساكن محصور بجسم agro_gdd ─────────────────────────────────────────────
def _top_level_func_body(src: str, name: str) -> str:
    lines = src.splitlines()
    out: list[str] = []
    capturing = False
    for line in lines:
        if line.startswith((f"async def {name}(", f"def {name}(")):
            capturing = True
            out.append(line)
            continue
        if capturing:
            if (
                line
                and not line[0].isspace()
                and line.startswith(("def ", "async def ", "class ", "@"))
            ):
                break
            out.append(line)
    assert out, f"لم يُعثَر على {name}"
    return "\n".join(out)


def test_agro_gdd_body_derives_from_series_not_kernel():
    src = (Path(__file__).resolve().parent.parent / "weather_runtime.py").read_text(
        encoding="utf-8"
    )
    body = _top_level_func_body(src, "agro_gdd")
    # فحص صيغة **النداء** (اسم + قوس) لا مجرّد ذكر في docstring.
    assert "gdd_agro_product(" not in body, "agro_gdd يجب ألّا يستدعي النواة مباشرةً"
    assert "gdd_daily(" not in body
    assert "build_canonical_daily_series(" in body and "gdd_view(" in body


def test_gdd_view_does_not_recompute_reads_kernel_only():
    import inspect

    src = inspect.getsource(gdd_view)
    # gdd_view يفوّض للنواة (gdd_agro_product) ولا يُعيد تنفيذ صيغة GDD (لا gdd_daily).
    assert "gdd_daily(" not in src


# ── (ي) حفظ byte-compat لعدم تطابق الطول + تشخيصات (فجوة مراجعة المستخدم) ─────
def test_legacy_length_mismatch_limitation_preserved_via_kernel_arrays():
    # المسار القديم: النواة ترى المصفوفتين الأصليّتين (3/2) ⇒ قيد mismatch محفوظ حرفيّاً.
    tmin = [10.0, 11.0, 12.0]
    tmax = [20.0, 21.0]  # أقصر
    # السلسلة تُبنى بالطول المُزدوَج الأدنى (للنَّسَب)، لكنّ النواة تُمرَّر لها الأصليّتان.
    recs = _records(["2026-04-01", "2026-04-02"], tmin[:2], tmax)
    view = gdd_view(
        build_canonical_daily_series(recs),
        base_c=5.0,
        period_start="2026-04-01",
        period_end="2026-04-02",
        kernel_daily_t_min=tmin,
        kernel_daily_t_max=tmax,
    )
    direct = gdd_agro_product(
        daily_t_min=tmin,
        daily_t_max=tmax,
        base_c=5.0,
        start_date="2026-04-01",
        end_date="2026-04-02",
    )
    assert view["limitations"] == direct["limitations"]  # قيد mismatch محفوظ
    assert any("length mismatch" in lim for lim in view["limitations"])
    assert view["valid_period"]["days"] == direct["valid_period"]["days"]
    assert view["daily_gdd"] == direct["daily_gdd"]


def test_diagnostics_surface_input_counts_and_drops():
    view = gdd_view(
        build_canonical_daily_series(_records(_DATES, _TMIN, _TMAX)),
        diagnostics={
            "input_t_min_count": 3,
            "input_t_max_count": 3,
            "input_date_count": None,
            "unmapped_temperature_pairs": 0,
        },
        **_CFG,
    )
    d = view["diagnostics"]
    assert d["invalid_records"] == 0
    assert d["input_t_min_count"] == 3 and d["input_t_max_count"] == 3
    assert d["unmapped_temperature_pairs"] == 0
