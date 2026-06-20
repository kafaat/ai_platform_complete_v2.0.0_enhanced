"""اختبار نقطة /api/v1/field-portfolio/optimize — استدعاء مباشر.

يثبت: (أ) شكل الاستجابة (تخصيص لكلّ حقل + إجماليّات)؛ (ب) الماء الشحيح للأعلى
إنتاجيّة؛ (ج) calibrated=false. بلا شبكة/قاعدة.
"""

import api.main  # noqa: F401 — تهيئة api.main قبل استيراد الموجِّه
import pytest
from api.routers.field_portfolio import (
    FieldPortfolioRequest,
    PortfolioFieldModel,
    optimize_portfolio,
)
from core.canonical_schemas import UserRole, UserSchema

pytestmark = pytest.mark.unit

_USER = UserSchema(
    user_id="u-portfolio",
    tenant_id="00000000-0000-0000-0000-000000000002",
    role=UserRole.OWNER,
    name_ar="محفظة",
)


def test_shape_and_totals():
    req = FieldPortfolioRequest(
        fields=[
            PortfolioFieldModel(field_id="A", expected_margin=1000.0, water_demand_m3=1000.0),
            PortfolioFieldModel(field_id="B", expected_margin=1500.0, water_demand_m3=1000.0),
        ],
        total_water_m3=1000.0,
    )
    out = optimize_portfolio(req=req, user=_USER)
    assert set(out) >= {
        "total_water_m3",
        "allocated_m3",
        "unallocated_m3",
        "total_expected_margin",
        "fields",
        "calibrated",
    }
    assert len(out["fields"]) == 2


def test_scarce_water_to_highest_productivity():
    req = FieldPortfolioRequest(
        fields=[
            PortfolioFieldModel(field_id="A", expected_margin=1000.0, water_demand_m3=1000.0),
            PortfolioFieldModel(field_id="B", expected_margin=1500.0, water_demand_m3=1000.0),
        ],
        total_water_m3=1000.0,
    )
    out = optimize_portfolio(req=req, user=_USER)
    by = {f["field_id"]: f for f in out["fields"]}
    assert by["B"]["status"] == "full"
    assert by["A"]["status"] == "unmet"
    assert out["total_expected_margin"] == pytest.approx(1500.0)


def test_allocate_protects_high_priority():
    from api.routers.field_portfolio import (
        AllocFieldModel,
        PortfolioAllocationRequest,
        WaterSourceModel,
        allocate_portfolio_endpoint,
    )

    req = PortfolioAllocationRequest(
        fields=[
            AllocFieldModel(
                field_id="f1", expected_margin=1000.0, water_demand_m3=1000.0, priority=5
            ),
            AllocFieldModel(
                field_id="f3", expected_margin=1200.0, water_demand_m3=1000.0, priority=1
            ),
        ],
        sources=[WaterSourceModel(source_id="well", capacity_m3=1000.0)],
    )
    out = allocate_portfolio_endpoint(req=req, user=_USER)
    by = {f["field_id"]: f for f in out["fields"]}
    assert by["f1"]["status"] == "full"  # محميّ
    assert by["f3"]["status"] == "unmet"  # مُجهَد لحماية الأعلى أولويّة
    assert "f3" in out["unmet_fields"]


def test_calibrated_false():
    req = FieldPortfolioRequest(
        fields=[PortfolioFieldModel(field_id="A", expected_margin=100.0, water_demand_m3=100.0)],
        total_water_m3=100.0,
    )
    assert optimize_portfolio(req=req, user=_USER)["calibrated"] is False


def test_empty_fields():
    req = FieldPortfolioRequest(fields=[], total_water_m3=500.0)
    out = optimize_portfolio(req=req, user=_USER)
    assert out["fields"] == []
    assert out["total_expected_margin"] == 0.0
