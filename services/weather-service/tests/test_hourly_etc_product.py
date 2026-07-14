from __future__ import annotations

from hourly_etc import build_hourly_etc_product


def _provider(hours: int = 3):
    return {
        "timezone": "UTC",
        "utc_offset_seconds": 0,
        "hourly": {
            "time": [f"2026-07-14T{h:02d}:00" for h in range(hours)],
            "et0_fao_evapotranspiration": [0.2, 0.3, 0.4][:hours],
            "precipitation": [0.0, 1.0, 0.0][:hours],
        },
    }


def test_builds_provider_native_hourly_etc_with_digests():
    out = build_hourly_etc_product(
        provider_payload=_provider(),
        lat=15.0,
        lon=44.0,
        horizon_hours=3,
        daily_kc_by_date={"2026-07-14": 0.8},
        daily_runoff_mm_by_date={"2026-07-14": 0.2},
    )
    assert out["status"] == "verified"
    assert out["quality_status"] == "provider_native"
    assert len(out["hours"]) == 3
    assert out["hours"][1]["et0_mm"] == 0.3
    assert out["hours"][1]["etc_mm"] == 0.24
    assert out["hours"][1]["effective_rain_mm"] == 0.8
    assert len(out["content_digest"]) == 64
    assert all(len(h["content_digest"]) == 64 for h in out["hours"])


def test_missing_kc_fails_closed():
    out = build_hourly_etc_product(
        provider_payload=_provider(),
        lat=15.0,
        lon=44.0,
        horizon_hours=3,
        daily_kc_by_date={},
    )
    assert out["status"] == "blocked"
    assert out["reason"] == "canonical_hourly_etc_input_incomplete"
    assert "kc" in out["missing"]


def test_incomplete_provider_horizon_fails_closed():
    out = build_hourly_etc_product(
        provider_payload=_provider(2),
        lat=15.0,
        lon=44.0,
        horizon_hours=3,
        daily_kc_by_date={"2026-07-14": 0.8},
    )
    assert out["status"] == "blocked"
    assert out["reason"] == "provider_hourly_horizon_incomplete"
