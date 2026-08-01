from pathlib import Path

import pytest

pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[1]


def test_lightweight_season_simulation_is_screening_only() -> None:
    models = (ROOT / "services/sahool-platform/api/season_models.py").read_text(encoding="utf-8")
    router = (ROOT / "services/sahool-platform/api/routers/seasons.py").read_text(encoding="utf-8")
    assert 'model_role: str = "screening_only"' in models
    assert 'model_role="screening_only"' in router
    assert "eligible_for_calibration: bool = False" in models
    assert "eligible_for_calibration=False" in router
    assert "pcse_wofost" in models and "pcse_wofost" in router
