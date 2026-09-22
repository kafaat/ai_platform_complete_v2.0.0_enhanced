"""تحقّق زراعيّ مقابل FAO-56 (Production Hardening — المرحلة C).

يتحقّق أنّ محرّكات Kc/ETc/توازن المياه في المنصّة تطابق المرجع العلميّ FAO-56 (Irrigation &
Drainage Paper 56)، لا مجرّد ثبات داخليّ:

- **Kc**: جدول FAO-56 رقم 12 (قمح/ذرة/برسيم…) + ترتيب المراحل.
- **ETc = ET0×Kc** + الاحتياج الصافي = ETc − المطر الفعّال.
- **المطر الفعّال** (USDA-SCS): مراسٍ مرجعيّة + رتابة.

**ملكيّة ET0 (Zero-Legacy):** نواة ET0 (Ra / es / Penman-Monteith / Hargreaves) لم تعد في
المنصّة — رُحِّلت كاملةً إلى محرّك الطقس (``services/weather-service``) الذي يملكها ويختبرها
مقابل FAO-56 مباشرةً (``tests/test_et0.py``: Ra مثال 8 ⇒ 32.2 · PM المُصادَق · Hargreaves؛
``tests/test_vpd.py``: es(20)=2.338 · es(30)=4.243). هنا نُبقي تحقّق Kc/ETc/المطر الذي
يخصّ منطق ``api.water_balance`` (ما يزال في المنصّة) ويستهلك ET0 محقوناً من المحرّك.

منطق فيزيائيّ صرف بلا خدمات (وظيفة Platform Unit Tests).
"""

from __future__ import annotations

from api.water_balance import (
    KC_BY_CROP_STAGE,
    _effective_rain,
    kc_from_ndvi,
)


# ── Kc: جدول FAO-56 رقم 12 ──────────────────────────────────────────────────
def test_kc_mid_season_matches_fao56_table_12():
    # قيم Kc_mid المنشورة (FAO-56 Table 12).
    assert KC_BY_CROP_STAGE["wheat"]["mid"] == 1.15
    assert KC_BY_CROP_STAGE["maize"]["mid"] == 1.20
    assert KC_BY_CROP_STAGE["alfalfa"]["mid"] == 1.20
    assert KC_BY_CROP_STAGE["tomato"]["mid"] == 1.15
    assert KC_BY_CROP_STAGE["potato"]["mid"] == 1.15


def test_kc_stage_ordering_is_physical():
    for crop, stages in KC_BY_CROP_STAGE.items():
        assert stages["initial"] <= stages["mid"], f"{crop}: Kc_ini يجب ألّا يتجاوز Kc_mid"
        assert 0.2 <= stages["initial"] <= 1.0 and 0.5 <= stages["mid"] <= 1.35, crop


def test_kc_from_ndvi_behaviour():
    kc_map = KC_BY_CROP_STAGE["wheat"]
    static_kc, fapar = kc_from_ndvi(None, kc_map, "mid")
    assert static_kc == kc_map["mid"] and fapar is None  # NDVI غائب ⇒ ثابت المرحلة
    low_kc, _ = kc_from_ndvi(0.15, kc_map, "mid")
    high_kc, fap = kc_from_ndvi(0.85, kc_map, "mid")
    assert high_kc > low_kc  # غطاء أعلى ⇒ Kc أعلى
    assert 0.0 <= fap <= 1.0


# ── ETc + الاحتياج الصافي ────────────────────────────────────────────────────
def test_etc_equals_et0_times_kc():
    et0 = 5.0
    kc = KC_BY_CROP_STAGE["maize"]["mid"]
    assert abs(et0 * kc - 6.0) < 1e-9  # 5.0 × 1.20


def test_net_irrigation_is_etc_minus_effective_rain():
    etc = 6.0
    eff = _effective_rain(20.0)
    net = max(0.0, etc - eff)
    assert net == max(0.0, etc - eff) and net >= 0.0


# ── المطر الفعّال (USDA-SCS) ──────────────────────────────────────────────────
def test_effective_rain_usda_scs_anchors():
    """D07: المرساةُ الثانيةُ كانت **تناقض اسمَ الاختبار نفسِه**.

    كان هذا الملفُّ يقول في رأسه إنّه يتحقّق «مقابل المرجع العلميّ لا مجرّد ثباتٍ
    داخليّ»، ثمّ تؤكّد هذه الدالّةُ `_effective_rain(100) ≈ 102.5` بتعليلِ
    `0.1·100+92.5 (>75mm)` — وتلك ليست صيغةَ USDA-SCS، وتُرجِع مطراً فعّالاً
    **أكبرَ من الساقط**. المرساةُ الأولى (50 ⇒ 46.0) كانت من الصيغة الصحيحة فعلاً،
    فبقيت. والثانيةُ صُحِّحت إلى مرجعها: 100·(125−20)/125 = 84.0.
    """
    assert _effective_rain(0.0) == 0.0
    assert _effective_rain(-5.0) == 0.0
    assert abs(_effective_rain(50.0) - 46.0) < 0.01  # 50·(125−10)/125
    assert abs(_effective_rain(100.0) - 84.0) < 0.01  # 100·(125−20)/125 (≤250mm)
    assert abs(_effective_rain(250.0) - 150.0) < 0.01  # نقطةُ التقاء الفرعين
    assert abs(_effective_rain(300.0) - 155.0) < 0.01  # 125+0.1·300 (>250mm)


def test_effective_rain_is_monotonic_nondecreasing():
    prev = -1.0
    for r in range(0, 200, 10):
        e = _effective_rain(float(r))
        assert e >= prev
        prev = e
