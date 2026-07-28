from core.crop_intelligence.engine import build_crop_intelligence_state
from core.crop_intelligence.models import CropIntelligenceInput


def _weather(gdd=321.5, available=True):
    return {
        "product_id": "canonical_weather_state",
        "state_id": "wx-state-1",
        "source_snapshot_id": "wx-snapshot-1",
        "availability": {"gdd": available},
        "products": {
            "gdd": {
                "accumulated_gdd": gdd,
                "thresholds_used": {"method": "modified"},
                "calculation_version": "gdd/daily/1.0.0",
                "limitations": [],
            }
        },
        "quality": "validated",
    }


def test_canonical_weather_gdd_wins_over_legacy_scalar():
    out = build_crop_intelligence_state(
        CropIntelligenceInput(
            crop="wheat",
            gdd_cumulative=9999,
            gdd_to_maturity=None,
            weather_state=_weather(),
        )
    )
    assert out["phenology"]["gdd_cumulative"] == 321.5
    assert out["phenology"]["gdd_to_maturity"] == 2000.0
    assert out["canonical_input_sources"]["weather"] == "canonical_weather_state"
    assert out["evidence_ids"] == ["wx-state-1", "wx-snapshot-1"]


def test_malformed_canonical_weather_fails_closed_without_scalar_fallback():
    out = build_crop_intelligence_state(
        CropIntelligenceInput(
            crop="wheat",
            gdd_cumulative=500,
            gdd_to_maturity=2000,
            weather_state={"product_id": "some_other_weather"},
        )
    )
    assert out["phenology"]["status"] == "unavailable"
    assert "weather_state_is_not_canonical_weather_state" in out["limitations"]


def test_legacy_scalar_path_is_explicitly_marked():
    out = build_crop_intelligence_state(
        CropIntelligenceInput(crop="wheat", gdd_cumulative=100, gdd_to_maturity=2000)
    )
    assert out["canonical_input_sources"]["weather"] == "legacy_scalar_compatibility"
    assert "legacy_gdd_scalar_compatibility_bridge" in out["limitations"]
