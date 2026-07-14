"""WX-I1 — native hourly ETc product contract + math + determinism (pure, no I/O)."""

from __future__ import annotations

import hourly_etc as he


def _rec(hour, et0, kc=None, precip=0.0):
    return {"hour": hour, "et0_mm": et0, "kc": kc, "precip_mm": precip}


def test_schema_and_owner_contract():
    p = he.hourly_etc_product(records=[_rec("2026-07-14T10:00:00Z", 0.5, 0.9)])
    assert p["product_id"] == "etc_hourly"
    assert p["schema_version"] == he.SCHEMA_VERSION
    assert p["formula_version"].startswith("etc/fao56-dual/")
    assert p["owner"] == "weather-service"
    assert p["unit"] == "mm/h"
    assert p["weather_snapshot_id"].startswith("wsnap/")


def test_etc_is_kc_times_et0_per_hour():
    p = he.hourly_etc_product(
        records=[_rec("2026-07-14T10:00:00Z", 0.50, 0.90), _rec("2026-07-14T11:00:00Z", 0.40, 1.10)]
    )
    hours = {h["hour"]: h for h in p["hours"]}
    assert hours["2026-07-14T10:00:00Z"]["etc_mm"] == round(0.90 * 0.50, 4)
    assert hours["2026-07-14T11:00:00Z"]["etc_mm"] == round(1.10 * 0.40, 4)
    assert p["quality_status"] == "ok"
    assert p["hours_with_etc"] == 2


def test_missing_kc_omits_etc_and_flags_partial():
    p = he.hourly_etc_product(records=[_rec("2026-07-14T10:00:00Z", 0.5, None)])
    assert p["hours"][0]["etc_mm"] is None  # لا ETc مُختلَق بلا Kc
    assert p["hours"][0]["et0_mm"] == 0.5  # ET0 يبقى (المصدر القانونيّ)
    assert p["quality_status"] == "partial"
    assert any("Kc not injected" in x for x in p["limitations"])


def test_all_et0_missing_is_unavailable_not_raise():
    p = he.hourly_etc_product(records=[_rec("2026-07-14T10:00:00Z", None, 0.9)])
    assert p["quality_status"] == "unavailable"
    assert any("ET0 missing for all" in x for x in p["limitations"])


def test_empty_input_is_unavailable_no_exception():
    p = he.hourly_etc_product(records=[])
    assert p["quality_status"] == "unavailable"
    assert p["hours_count"] == 0


def test_effective_rain_fixed_fraction_and_declared():
    p = he.hourly_etc_product(
        records=[_rec("2026-07-14T10:00:00Z", 0.5, 0.9, precip=4.0)], infiltration_fraction=0.7
    )
    assert p["hours"][0]["effective_rain_mm"] == round(4.0 * 0.7, 4)
    assert any("fixed hourly infiltration" in x for x in p["limitations"])
    # لا هطول ⇒ صفر (لا None)
    dry = he.hourly_etc_product(records=[_rec("2026-07-14T11:00:00Z", 0.5, 0.9, precip=0.0)])
    assert dry["hours"][0]["effective_rain_mm"] == 0.0


def test_digest_is_deterministic_and_input_sensitive():
    a = he.hourly_etc_product(records=[_rec("2026-07-14T10:00:00Z", 0.5, 0.9)])
    b = he.hourly_etc_product(records=[_rec("2026-07-14T10:00:00Z", 0.5, 0.9)])
    c = he.hourly_etc_product(records=[_rec("2026-07-14T10:00:00Z", 0.6, 0.9)])
    assert a["weather_snapshot_id"] == b["weather_snapshot_id"]
    assert a["weather_snapshot_id"] != c["weather_snapshot_id"]


def test_hours_are_ordered_and_deduped():
    p = he.hourly_etc_product(
        records=[
            _rec("2026-07-14T11:00:00Z", 0.4, 0.9),
            _rec("2026-07-14T10:00:00Z", 0.5, 0.9),
            _rec("2026-07-14T10:00:00Z", 0.7, 0.9),  # duplicate hour — last wins
        ]
    )
    times = [h["hour"] for h in p["hours"]]
    assert times == ["2026-07-14T10:00:00Z", "2026-07-14T11:00:00Z"]  # sorted, deduped
    assert p["hours"][0]["et0_mm"] == 0.7  # last value for the duplicate hour


def test_matches_m3_consumer_keys():
    # M3 يقرأ per-hour: hour + etc_mm + effective_rain_mm (hourly_energy_aware_irrigation_mpc.py).
    p = he.hourly_etc_product(records=[_rec("2026-07-14T10:00:00Z", 0.5, 0.9, precip=2.0)])
    h = p["hours"][0]
    assert {"hour", "etc_mm", "effective_rain_mm"} <= set(h)
