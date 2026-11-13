"""اختبار نقطة التوأم الرقميّ (routers/field_twin) — استدعاء مباشر.

العلم المُطفأ ⇒ 404 قبل أيّ قاعدة. السلوك الكامل (تجميع من الجداول) يُغطّى تكاملاً.
"""

import api.main  # noqa: F401 — تهيئة api.main قبل استيراد الموجِّه
import pytest
from api.routers.field_twin import get_field_twin
from core.canonical_schemas import UserRole, UserSchema
from fastapi import HTTPException

pytestmark = pytest.mark.unit

_USER = UserSchema(
    user_id="u-twin",
    tenant_id="00000000-0000-0000-0000-000000000002",
    role=UserRole.OWNER,
    name_ar="مُراقِب",
)


async def test_twin_flag_off_404(monkeypatch):
    monkeypatch.delenv("SAHOOL_DECISION_DISPATCH", raising=False)
    with pytest.raises(HTTPException) as e:
        await get_field_twin(field_id="field_01", user=_USER)
    assert e.value.status_code == 404


def test_endpoint_reads_season_and_indicators_through_the_pure_adapters():
    """The router hands its rows to the tested adapters (no fake connection needed)."""
    import inspect

    import api.routers.field_twin as module

    src = inspect.getsource(module.get_field_twin)
    assert "FROM seasons" in src and "status = 'active'" in src
    assert "finite_indicator_readings(ind_rows)" in src
    assert "active_season_context(season_row)" in src
    assert 'out["decision_authority"] = "none"' in src


def test_fresh_evi_does_not_lend_its_date_to_old_ndvi():
    from datetime import UTC, datetime

    from core.field_twin import assemble_twin, finite_indicator_readings

    rows = [
        {"indicator_id": "ndvi", "value": 0.75, "recorded_at": datetime(2026, 10, 20, tzinfo=UTC)},
        {"indicator_id": "evi", "value": 0.60, "recorded_at": datetime(2026, 11, 13, tzinfo=UTC)},
        {
            "indicator_id": "savi",
            "value": float("nan"),
            "recorded_at": datetime(2026, 11, 13, tzinfo=UTC),
        },
        {"indicator_id": "ndwi", "value": "not-a-number", "recorded_at": None},
    ]
    indices, observed = finite_indicator_readings(rows)
    assert set(indices) == {"ndvi", "evi"}
    twin = assemble_twin(
        field_id="f1",
        crop="peanut",
        latest_indices=indices,
        observed_at=max(observed.values()),
        index_observed_at=observed,
        now=datetime(2026, 11, 13, tzinfo=UTC),
        open_decisions=[],
        last_execution=None,
    )
    assert twin.state == "stale"
    assert twin.observed_at == "2026-10-20"


def test_active_season_context_owns_crop_identity():
    from datetime import date

    from core.field_twin import active_season_context

    ctx = active_season_context(
        {
            "season_id": "s1",
            "crops": '["wheat"]',
            "cultivar": "habib",
            "sowing_date": date(2026, 10, 20),
        }
    )
    assert ctx == {
        "source": "seasons",
        "status": "active",
        "season_id": "s1",
        "crops": ["wheat"],
        "cultivar": "habib",
        "sowing_date": "2026-10-20",
    }
    missing = active_season_context(None)
    assert missing["status"] == "missing_active_season" and missing["crops"] == []
