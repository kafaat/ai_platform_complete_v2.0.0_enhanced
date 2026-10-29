import pytest
from api.canonical_water_stress import canonical_water_stress
from core.crop_intelligence.spectral import build_canonical_spectral_state


@pytest.mark.parametrize(
    "quality",
    [
        None,
        "unknown",
        "invalid",
        "insufficient",
        "unavailable",
        "degraded",
        "estimated",
        "validated",
        [],
        {},
    ],
)
def test_consumers_agree_on_quality(quality):
    row = dict(
        depletion_mm=90,
        taw_mm=100,
        depletion_confidence=0.9,
        ndmi=-0.1,
        msi=1.222222,
        ndmi_date="2026-10-27",
        msi_date="2026-10-27",
        quality_status=quality,
    )
    water = canonical_water_stress(row, as_of="2026-10-28", max_spectral_age_days=12)
    crop = build_canonical_spectral_state(
        ndmi=row["ndmi"], msi=row["msi"], temporal_compatible=True, quality_status=quality
    )
    expected = quality == "validated"
    assert water["spectral_confirmation_available"] is expected
    assert crop["water_stress"]["confirmation_available"] is expected
    assert water["escalation_eligible"] is expected
    if not expected:
        assert water["spectral_stress_detected"] is None
