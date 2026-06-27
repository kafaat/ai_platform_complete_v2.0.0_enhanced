"""core/farm_closed_loop.py — إغلاق الحلقة التشغيلية الاقتصادية لـ Farm Ledger.

هذه النواة نقية: لا قاعدة بيانات، لا ERP write، لا خصم مخزون. دورها تحويل
الأحداث/السجلات الحالية إلى إسقاطات قابلة للمراجعة: autowrite preview، إسقاط مخزون،
حالة اقتصادية كنسية اختيارية، وتوصيات كفاءة تحفظية. كل المخرجات تعلن provenance
وتبقى خلف feature flags في الراوتر.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from core.farm_costing import ProfitabilitySummary, VarianceLine
from core.farm_operations_ledger import LedgerSummary


@dataclass(frozen=True)
class ResourceUse:
    resource_type: str
    quantity: float
    unit: str
    estimated_cost: float | None = None
    inventory_item_id: str | None = None


@dataclass(frozen=True)
class OperationEvent:
    event_id: str
    tenant_id: str
    occurred_on: date
    operation_type: str
    season_id: str | None = None
    farm_id: str | None = None
    field_id: str | None = None
    production_unit_id: str | None = None
    execution_mode: str = "self"
    cost_category: str | None = None
    cost_amount: float | None = None
    water_m3: float | None = None
    energy_kwh: float | None = None
    diesel_liters: float | None = None
    equipment_hours: float | None = None
    labor_hours: float | None = None
    inputs: tuple[ResourceUse, ...] = field(default_factory=tuple)
    source: str = "operation_event"


@dataclass(frozen=True)
class InventoryProjectionLine:
    resource_type: str
    inventory_item_id: str | None
    quantity: float
    unit: str
    estimated_cost: float | None
    direction: str = "outbound"
    posting_mode: str = "projection_only"
    disabled_reason: str | None = None


@dataclass(frozen=True)
class EfficiencyRecommendation:
    code: str
    title_ar: str
    message_ar: str
    severity: str
    evidence: dict[str, Any]
    provenance: dict[str, Any] = field(
        default_factory=lambda: {
            "source": "farm_closed_loop_rule_engine",
            "prediction": False,
            "recommendation": True,
            "requires_human_review": True,
        }
    )


@dataclass(frozen=True)
class EconomicState:
    season_id: str
    status: str
    total_cost: float
    direct_cost: float
    indirect_cost: float
    revenue: float | None
    gross_margin: float | None
    cost_per_ha: float | None
    water_m3_per_ha: float | None
    water_cost_per_m3: float | None
    energy_kwh_per_m3: float | None
    budget_variance_status: str
    profitability_status: str | None
    recommendations: tuple[EfficiencyRecommendation, ...]
    provenance: dict[str, Any]


def _non_negative(value: float | int | None, *, field_name: str) -> float | None:
    if value is None:
        return None
    v = float(value)
    if v < 0:
        raise ValueError(f"{field_name} must be >= 0")
    return v


def operation_event_to_ledger_payload(event: OperationEvent) -> dict[str, Any]:
    """يبني payload متوافقاً مع OperationLedgerIn دون أن يكتب في القاعدة.

    يستخدمه مسار autowrite-preview ومسار events لاحقاً. إذا لم يوجد field/farm/unit
    يرجع payload معلناً أنه غير قابل للحفظ بدلاً من اختراع نطاق.
    """
    if not event.tenant_id:
        raise ValueError("tenant_id required")
    scoped = bool(event.field_id or event.production_unit_id or event.farm_id)
    payload: dict[str, Any] = {
        "operation_date": event.occurred_on.isoformat(),
        "operation_type": event.operation_type,
        "season_id": event.season_id,
        "farm_id": event.farm_id,
        "field_id": event.field_id,
        "production_unit_id": event.production_unit_id,
        "execution_mode": event.execution_mode,
        "cost_amount": _non_negative(event.cost_amount, field_name="cost_amount"),
        "cost_category": event.cost_category,
        "sync_status": "control_only",
        "source_event_id": event.event_id,
        "autowrite_eligible": scoped,
        "disabled_reason": None if scoped else "missing_field_or_production_unit_or_farm",
        "provenance": {"source": event.source, "persisted": False},
    }
    if event.water_m3 is not None:
        payload["water"] = {
            "water_volume_m3": _non_negative(event.water_m3, field_name="water_m3"),
            "measurement_method": "event",
        }
    if event.energy_kwh is not None or event.diesel_liters is not None:
        payload["energy"] = {
            "energy_source": "unknown",
            "kwh": _non_negative(event.energy_kwh, field_name="energy_kwh"),
            "diesel_liters": _non_negative(event.diesel_liters, field_name="diesel_liters"),
        }
    if event.equipment_hours is not None:
        payload["equipment"] = [
            {
                "equipment_id": "unknown",
                "hours_worked": _non_negative(event.equipment_hours, field_name="equipment_hours"),
            }
        ]
    if event.labor_hours is not None:
        payload["labor"] = [{"hours": _non_negative(event.labor_hours, field_name="labor_hours")}]
    if event.inputs:
        payload["inputs"] = [
            {
                "input_type": r.resource_type,
                "inventory_item_id": r.inventory_item_id,
                "quantity": _non_negative(r.quantity, field_name="input.quantity"),
                "unit": r.unit,
                "estimated_cost": _non_negative(
                    r.estimated_cost, field_name="input.estimated_cost"
                ),
            }
            for r in event.inputs
        ]
    return payload


def build_inventory_projection(
    inputs: Iterable[ResourceUse],
    *,
    sync_enabled: bool,
) -> list[InventoryProjectionLine]:
    """يبني إسقاط خصم مخزون فقط؛ لا يخصم فعلياً من inventory-service."""
    disabled = None if sync_enabled else "feature_flag_off"
    lines: list[InventoryProjectionLine] = []
    for r in inputs:
        lines.append(
            InventoryProjectionLine(
                resource_type=r.resource_type,
                inventory_item_id=r.inventory_item_id,
                quantity=_non_negative(r.quantity, field_name="input.quantity") or 0.0,
                unit=r.unit,
                estimated_cost=_non_negative(r.estimated_cost, field_name="input.estimated_cost"),
                disabled_reason=disabled,
            )
        )
    return lines


def build_economic_state(
    season_id: str,
    summary: LedgerSummary,
    *,
    area_ha: float | None = None,
    profitability: ProfitabilitySummary | None = None,
    variances: Iterable[VarianceLine] = (),
) -> EconomicState:
    area = _non_negative(area_ha, field_name="area_ha") if area_ha is not None else None
    cost_per_ha = summary.total_cost / area if area and area > 0 else None
    water_per_ha = summary.water_volume_m3 / area if area and area > 0 else None
    water_cost = summary.cost_breakdown.get("water", 0.0)
    water_cost_per_m3 = (
        water_cost / summary.water_volume_m3 if summary.water_volume_m3 > 0 else None
    )
    energy_kwh_per_m3 = (
        summary.energy_kwh / summary.water_volume_m3 if summary.water_volume_m3 > 0 else None
    )

    variance_list = list(variances)
    if any(v.severity == "critical" for v in variance_list):
        budget_status = "critical"
    elif any(v.severity == "watch" for v in variance_list):
        budget_status = "watch"
    elif variance_list:
        budget_status = "normal"
    else:
        budget_status = "not_available"

    profitability_status = None
    gross_margin = None
    revenue = None
    if profitability is not None:
        revenue = profitability.revenue
        gross_margin = profitability.gross_margin
        profitability_status = "profitable" if profitability.gross_margin >= 0 else "loss"

    recs = tuple(generate_efficiency_recommendations(summary, area_ha=area))
    return EconomicState(
        season_id=season_id,
        status="computed",
        total_cost=summary.total_cost,
        direct_cost=summary.direct_cost,
        indirect_cost=summary.indirect_cost,
        revenue=revenue,
        gross_margin=gross_margin,
        cost_per_ha=cost_per_ha,
        water_m3_per_ha=water_per_ha,
        water_cost_per_m3=water_cost_per_m3,
        energy_kwh_per_m3=energy_kwh_per_m3,
        budget_variance_status=budget_status,
        profitability_status=profitability_status,
        recommendations=recs,
        provenance={
            "source": "farm_operations_ledger",
            "prediction": False,
            "canonical_state_write": False,
        },
    )


def generate_efficiency_recommendations(
    summary: LedgerSummary,
    *,
    area_ha: float | None = None,
    max_items: int = 6,
) -> list[EfficiencyRecommendation]:
    """توصيات تحفظية من مؤشرات فعلية فقط؛ لا ML ولا توقعات."""
    recs: list[EfficiencyRecommendation] = []
    area = _non_negative(area_ha, field_name="area_ha") if area_ha is not None else None
    if area and area > 0:
        water_per_ha = summary.water_volume_m3 / area
        if water_per_ha > 8000:
            recs.append(
                EfficiencyRecommendation(
                    "water_use_high_per_ha",
                    "مراجعة استهلاك المياه للهكتار",
                    "استهلاك المياه المسجل أعلى من 8000 م³/هكتار. راجع جدول الري، ET0، وكفاءة النظام قبل تقليل الري.",
                    "watch",
                    {"water_m3_per_ha": water_per_ha, "threshold": 8000},
                )
            )
    if summary.water_volume_m3 > 0 and summary.energy_kwh > 0:
        kwh_per_m3 = summary.energy_kwh / summary.water_volume_m3
        if kwh_per_m3 > 0.8:
            recs.append(
                EfficiencyRecommendation(
                    "energy_per_water_high",
                    "مراجعة كفاءة الضخ والطاقة",
                    "استهلاك الطاقة لكل متر مكعب ماء مرتفع. افحص المضخة، الفلتر، عمق الماء، وجدول تشغيل الطاقة.",
                    "watch",
                    {"kwh_per_m3": kwh_per_m3, "threshold": 0.8},
                )
            )
    if summary.indirect_cost > 0 and summary.total_cost > 0:
        indirect_pct = summary.indirect_cost / summary.total_cost * 100.0
        if indirect_pct > 25:
            recs.append(
                EfficiencyRecommendation(
                    "indirect_cost_share_high",
                    "مراجعة التكاليف الإدارية وغير المباشرة",
                    "حصة التكاليف غير المباشرة تتجاوز 25% من إجمالي التكلفة. راجع طريقة التوزيع ومصاريف الإدارة/الإشراف.",
                    "watch",
                    {"indirect_percent": indirect_pct, "threshold": 25},
                )
            )
    return recs[:max_items]
