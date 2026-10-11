"""مدخلات دفتر الماء اليوميّ — شواهد سلوكيّة على الدوالّ النقيّة، وحارسٌ على التوصيل.

العامل اليوميّ في مسار GATE-01 مجمَّد، فالمنطقُ نُقِل إلى ``api.water_ledger_inputs``
ويُختبَر هنا سلوكيّاً؛ والتوصيلُ في العامل يُقرأ من المصدر (لا يُحمَّل العامل بلا قاعدة).
القيم المرجعيّة: FAO-56 Eq. 47 (الريح) · Fig. 34 (Kc) · Table 22 (p).
"""

from __future__ import annotations

import asyncio
from datetime import date, timedelta
from pathlib import Path

import pytest
from api import water_ledger_inputs as wli
from api.water_ledger_auto import CONFIDENCE_AUTO, CONFIDENCE_BOOTSTRAP, compute_daily_ledger_entry

TODAY = date(2026, 6, 1)


# ── الريح: المتوسّط على 10م ⇒ 2م بالمعادلة 47، والقصوى لا تُستعمَل ──


def test_wind_height_conversion_matches_fao56_eq47():
    assert wli.wind_2m_from_height(1.0, 10.0) == pytest.approx(0.748, abs=1e-3)
    assert wli.wind_2m_from_height(2.0, 2.0) == pytest.approx(2.0, abs=1e-2)


def test_mean_wind_is_converted_and_the_daily_maximum_is_never_used():
    inputs = wli.et0_weather_inputs(
        {
            "wind_mean_10m_ms": 4.0,
            "wind_max_ms": 11.0,
            "rh_mean_pct": 35,
            "solar_radiation_mj_m2": 24,
        }
    )
    assert inputs["wind_2m_ms"] == pytest.approx(4.0 * 0.748, abs=1e-2)
    assert inputs["rh_mean_pct"] == 35.0 and inputs["solar_rad_mj_m2"] == 24.0


def test_only_a_maximum_wind_leaves_wind_absent_not_borrowed():
    """القصوى وحدها ⇒ ``None``: يسقط المحرّك إلى Hargreaves معلَناً، لا يُضخَّم ET0."""
    inputs = wli.et0_weather_inputs({"wind_max_ms": 11.0, "rh_mean_pct": 40})
    assert inputs["wind_2m_ms"] is None


@pytest.mark.parametrize("rh", [None, -1, 101, float("nan"), True, "40"])
def test_invalid_humidity_is_absent(rh):
    assert wli.et0_weather_inputs({"rh_mean_pct": rh})["rh_mean_pct"] is None


def test_et0_reference_requires_penman_monteith():
    assert wli.et0_is_reference({"method": "fao56_penman_monteith"})
    assert not wli.et0_is_reference({"method": "hargreaves_fallback"})
    assert not wli.et0_is_reference({})


# ── Kc الطوريّ: لا منتصف موسمٍ كلَّ يوم ولا احتياطَ القمح ──


def test_a_maize_seedling_is_not_given_mid_season_kc():
    """بادرةُ الذرة (يوم 10) ⇒ Kc الابتدائيّ 0.30 لا 1.20 (كان العامل يكتب 1.20)."""
    kc = wli.daily_kc("maize", TODAY - timedelta(days=10), TODAY)
    assert kc is not None and kc.kc == pytest.approx(0.30) and kc.stage == "initial"


def test_maize_mid_season_and_late_season_follow_the_crop_card():
    mid = wli.daily_kc("maize", TODAY - timedelta(days=80), TODAY)
    late = wli.daily_kc("maize", TODAY - timedelta(days=139), TODAY)
    assert mid.kc == pytest.approx(1.20) and mid.stage == "mid"
    assert late.stage == "late" and late.kc < mid.kc


@pytest.mark.parametrize(
    "crop,sowing",
    [
        ("not-a-crop", TODAY - timedelta(days=30)),
        ("maize", None),
        ("maize", TODAY + timedelta(days=3)),
    ],
    ids=["unknown-crop", "no-sowing-date", "future-sowing"],
)
def test_unknowable_kc_is_none_never_a_wheat_or_mid_fallback(crop, sowing):
    assert wli.daily_kc(crop, sowing, TODAY) is None


# ── p: FAO-56 Table 22 مُعدَّلاً بـETc ──


def test_depletion_fraction_follows_table22_and_the_etc_adjustment():
    assert wli.depletion_fraction("maize", 5.0) == (0.55, False)
    assert wli.depletion_fraction("maize", 8.0) == (pytest.approx(0.43), False)
    assert wli.depletion_fraction("potato", 5.0) == (0.35, False)


def test_a_crop_without_a_table_value_is_flagged_and_bounds_hold():
    p, is_default = wli.depletion_fraction("not-a-crop", 5.0)
    assert (p, is_default) == (0.5, True)
    assert wli.depletion_fraction("onion", 30.0)[0] == 0.1
    assert wli.depletion_fraction("cotton", 0.0)[0] == 0.8


# ── منطقة الجذور: القانونيّة أوّلاً، واحتياطُ القوام بعلَم ──


class _Profile:
    taw_mm = 140.0
    raw_mm = 77.0
    root_depth_m = 0.9


def _zone(monkeypatch, resolved):
    from api import canonical_root_zone_profile as crz

    async def _fake(conn, **kwargs):
        _fake.kwargs = kwargs
        return resolved

    monkeypatch.setattr(crz, "resolve_canonical_root_zone_profile", _fake)
    crop_kc = wli.daily_kc("maize", TODAY - timedelta(days=60), TODAY)
    zone = asyncio.run(
        wli.ledger_root_zone(
            None,
            tenant_id="t",
            field_id="f",
            season_id="s",
            crop_kc=crop_kc,
            variety=None,
            texture="loam",
            etc_mm_day=5.0,
        )
    )
    return zone, _fake.kwargs


def test_the_canonical_root_zone_is_used_with_the_crop_depletion_fraction(monkeypatch):
    zone, kwargs = _zone(monkeypatch, _Profile())
    assert zone["source"] == "canonical_root_zone"
    assert (zone["taw_mm"], zone["raw_mm"]) == (140.0, 77.0)
    assert zone["root_zone_texture_fallback"] is False
    assert kwargs["raw_fraction"] == 0.55, "p ثابتة 0.5 بدل جدول FAO-56 للمحصول"


def test_a_blocked_root_zone_falls_back_to_texture_with_a_flag(monkeypatch):
    zone, _ = _zone(monkeypatch, {"status": "blocked", "reason": "no_soil_profile"})
    assert zone["root_zone_texture_fallback"] is True
    assert zone["source"] == "texture_table_fallback:no_soil_profile"
    assert zone["raw_mm"] == pytest.approx(zone["taw_mm"] * 0.55, abs=0.05)


# ── الأعلام تدخل القيد وتُخفّض الثقة ──


def _entry(**flags):
    return compute_daily_ledger_entry(
        prev_depletion_mm=20.0,
        taw_mm=120.0,
        raw_mm=60.0,
        et0_mm=6.0,
        kc=1.0,
        rain_mm=0.0,
        irrigation_mm=5.0,
        **flags,
    )


def test_a_degraded_et0_or_a_texture_fallback_lowers_confidence():
    assert _entry()["confidence"] == CONFIDENCE_AUTO
    for flag in ("et0_reference_unavailable", "root_zone_texture_fallback"):
        entry = _entry(**{flag: True})
        assert flag in entry["notes"] and entry["confidence"] == CONFIDENCE_BOOTSTRAP


def test_a_default_depletion_fraction_is_declared_without_touching_depletion_confidence():
    entry = _entry(depletion_fraction_default=True)
    assert "depletion_fraction_default" in entry["notes"]
    assert entry["confidence"] == CONFIDENCE_AUTO


# ── التوصيل في العامل المجمَّد (مقروءٌ من المصدر) ──


def test_the_frozen_worker_is_wired_to_the_measured_inputs():
    src = (Path(__file__).parents[1] / "api" / "phase_runtime_workers.py").read_text(
        encoding="utf-8"
    )
    body = src[src.index("async def run_water_ledger_once") : src.index("async def loop_worker")]
    for gone in ('"mid",', "KC_BY_CROP_STAGE", 'day0.get("wind_max_ms")', 'sw["raw_fraction"]'):
        assert gone not in body, f"بقي في العامل: {gone}"
    for wired in (
        "daily_kc(",
        "**et0_weather_inputs(day0)",
        "ledger_root_zone(",
        "et0_reference_unavailable=not et0_is_reference(et0)",
        "root_zone_texture_fallback=",
        "crop_kc.stage",
    ):
        assert wired in body, f"غير موصول في العامل: {wired}"
