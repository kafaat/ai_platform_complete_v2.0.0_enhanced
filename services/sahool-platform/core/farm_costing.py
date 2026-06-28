"""core/farm_costing.py — موازنة الموسم، الانحرافات، الربحية، وإسقاط ERP اختياري.

هذه النواة نقية ولا تتصل بقاعدة بيانات. دورها تحويل سجلات Farm Operations Ledger
إلى موازنة/انحرافات/ربحية وتوصيات تحفظية قابلة للشرح. لا تنفّذ محاسبة مزدوجة ولا
تدّعي تعلماً آلياً؛ أي توصية هنا rule-based ومعلنة provenance.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class GrowthStage(str, Enum):
    PREPARATION = "preparation"
    PLANTING = "planting"
    EMERGENCE = "emergence"
    VEGETATIVE = "vegetative"
    FLOWERING = "flowering"
    FRUITING = "fruiting"
    MATURITY = "maturity"
    HARVEST = "harvest"
    TRANSPORT = "transport"
    PACKAGING = "packaging"
    STORAGE = "storage"
    WHOLE_SEASON = "whole_season"


class CostCategory(str, Enum):
    WATER = "water"
    ENERGY = "energy"
    SEED = "seed"
    FERTILIZER = "fertilizer"
    PESTICIDE = "pesticide"
    LABOR = "labor"
    EQUIPMENT = "equipment"
    MAINTENANCE = "maintenance"
    HARVEST = "harvest"
    TRANSPORT = "transport"
    PACKAGING = "packaging"
    STORAGE = "storage"
    ADMINISTRATION = "administration"
    SUPERVISION = "supervision"
    SECURITY = "security"
    OVERHEAD = "overhead"
    OTHER = "other"


class AllocationMethod(str, Enum):
    PER_HECTARE = "per_hectare"
    PER_OPERATION = "per_operation"
    PROPORTIONAL_DIRECT_COST = "proportional_direct_cost"
    MANUAL = "manual"


@dataclass(frozen=True)
class SeasonBudgetLine:
    line_id: str
    season_id: str
    category: str
    stage: str = GrowthStage.WHOLE_SEASON.value
    planned_quantity: float | None = None
    unit: str | None = None
    planned_unit_cost: float | None = None
    planned_cost: float = 0.0
    currency: str = "YER"
    source: str = "manual"
    editable: bool = True


@dataclass(frozen=True)
class ActualCostLine:
    source_id: str
    season_id: str
    category: str
    stage: str = GrowthStage.WHOLE_SEASON.value
    actual_quantity: float | None = None
    unit: str | None = None
    actual_cost: float = 0.0
    currency: str = "YER"
    source: str = "farm_operations_ledger"


@dataclass(frozen=True)
class VarianceLine:
    season_id: str
    category: str
    stage: str
    planned_cost: float
    actual_cost: float
    variance_amount: float
    variance_percent: float | None
    severity: str
    explanation: str


@dataclass(frozen=True)
class IndirectCostPool:
    pool_id: str
    category: str
    amount: float
    allocation_method: AllocationMethod
    currency: str = "YER"
    manual_allocations: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class ProductionUnitBasis:
    production_unit_id: str
    area_ha: float | None = None
    operation_count: int = 0
    direct_cost: float = 0.0


@dataclass(frozen=True)
class ProfitabilitySummary:
    season_id: str
    revenue: float
    total_cost: float
    gross_margin: float
    margin_percent: float | None
    yield_quantity: float | None
    unit: str | None
    cost_per_unit: float | None
    revenue_per_unit: float | None
    currency: str = "YER"


@dataclass(frozen=True)
class CostRecommendation:
    code: str
    title_ar: str
    message_ar: str
    severity: str
    evidence: dict[str, Any]
    provenance: dict[str, Any] = field(
        default_factory=lambda: {
            "source": "farm_costing_rule_engine",
            "prediction": False,
            "recommendation": True,
            "requires_human_review": True,
        }
    )


@dataclass(frozen=True)
class ErpProjectionLine:
    category: str
    amount: float
    currency: str
    cost_center: str | None
    project: str | None
    memo: str


def _non_negative(value: float | int | None, *, field_name: str) -> float | None:
    if value is None:
        return None
    v = float(value)
    if v < 0:
        raise ValueError(f"{field_name} must be >= 0")
    return v


def normalize_budget_line(line: SeasonBudgetLine) -> SeasonBudgetLine:
    qty = _non_negative(line.planned_quantity, field_name="planned_quantity")
    unit_cost = _non_negative(line.planned_unit_cost, field_name="planned_unit_cost")
    cost = _non_negative(line.planned_cost, field_name="planned_cost") or 0.0
    if cost == 0.0 and qty is not None and unit_cost is not None:
        cost = qty * unit_cost
    return SeasonBudgetLine(**{**line.__dict__, "planned_cost": cost})


def compute_variances(
    budget_lines: Iterable[SeasonBudgetLine],
    actual_lines: Iterable[ActualCostLine],
    *,
    warn_percent: float = 10.0,
    critical_percent: float = 25.0,
) -> list[VarianceLine]:
    planned: dict[tuple[str, str], float] = {}
    actual: dict[tuple[str, str], float] = {}
    season_id = ""
    for b in budget_lines:
        b = normalize_budget_line(b)
        season_id = season_id or b.season_id
        key = (b.stage, b.category)
        planned[key] = planned.get(key, 0.0) + b.planned_cost
    for a in actual_lines:
        _non_negative(a.actual_cost, field_name="actual_cost")
        season_id = season_id or a.season_id
        key = (a.stage, a.category)
        actual[key] = actual.get(key, 0.0) + a.actual_cost

    lines: list[VarianceLine] = []
    for stage, category in sorted(set(planned) | set(actual)):
        p = planned.get((stage, category), 0.0)
        a = actual.get((stage, category), 0.0)
        diff = a - p
        pct = (diff / p * 100.0) if p > 0 else (None if a == 0 else 100.0)
        abs_pct = abs(pct or 0.0)
        if abs_pct >= critical_percent:
            severity = "critical"
        elif abs_pct >= warn_percent:
            severity = "watch"
        else:
            severity = "normal"
        if p == 0 and a > 0:
            explanation = "تكلفة فعلية بدون بند موازنة مخطط؛ راجع خطة الموسم أو صنّف العملية."
        elif diff > 0:
            explanation = "تجاوز تكلفة عن المخطط؛ يحتاج مراجعة السبب قبل اعتماد توصية تخفيض."
        elif diff < 0:
            explanation = "أقل من المخطط؛ قد يكون توفيراً أو نقص تنفيذ يحتاج تحققاً ميدانياً."
        else:
            explanation = "مطابق للمخطط."
        lines.append(
            VarianceLine(season_id, category, stage, p, a, diff, pct, severity, explanation)
        )
    return lines


def allocate_indirect_costs(
    pools: Iterable[IndirectCostPool],
    bases: Iterable[ProductionUnitBasis],
) -> dict[str, dict[str, float]]:
    basis_list = list(bases)
    result: dict[str, dict[str, float]] = {b.production_unit_id: {} for b in basis_list}
    for pool in pools:
        amount = _non_negative(pool.amount, field_name="pool.amount") or 0.0
        if pool.allocation_method == AllocationMethod.MANUAL:
            for unit_id, share in pool.manual_allocations.items():
                result.setdefault(unit_id, {})[pool.category] = (
                    result.setdefault(unit_id, {}).get(pool.category, 0.0) + share
                )
            continue
        if pool.allocation_method == AllocationMethod.PER_HECTARE:
            total_basis = sum((b.area_ha or 0.0) for b in basis_list)

            def value(b: ProductionUnitBasis) -> float:
                return b.area_ha or 0.0

        elif pool.allocation_method == AllocationMethod.PER_OPERATION:
            total_basis = sum(b.operation_count for b in basis_list)

            def value(b: ProductionUnitBasis) -> float:
                return float(b.operation_count)

        else:
            total_basis = sum(b.direct_cost for b in basis_list)

            def value(b: ProductionUnitBasis) -> float:
                return b.direct_cost

        if total_basis <= 0:
            continue
        for b in basis_list:
            share = amount * (value(b) / total_basis)
            result[b.production_unit_id][pool.category] = (
                result[b.production_unit_id].get(pool.category, 0.0) + share
            )
    return result


def compute_profitability(
    season_id: str,
    *,
    revenue: float,
    cost_lines: Iterable[ActualCostLine],
    yield_quantity: float | None = None,
    unit: str | None = None,
    currency: str = "YER",
) -> ProfitabilitySummary:
    revenue = _non_negative(revenue, field_name="revenue") or 0.0
    y = (
        _non_negative(yield_quantity, field_name="yield_quantity")
        if yield_quantity is not None
        else None
    )
    total_cost = sum(
        (_non_negative(c.actual_cost, field_name="actual_cost") or 0.0) for c in cost_lines
    )
    margin = revenue - total_cost
    return ProfitabilitySummary(
        season_id=season_id,
        revenue=revenue,
        total_cost=total_cost,
        gross_margin=margin,
        margin_percent=(margin / revenue * 100.0) if revenue > 0 else None,
        yield_quantity=y,
        unit=unit,
        cost_per_unit=(total_cost / y) if y else None,
        revenue_per_unit=(revenue / y) if y else None,
        currency=currency,
    )


def generate_cost_recommendations(
    variances: Iterable[VarianceLine],
    *,
    max_items: int = 8,
) -> list[CostRecommendation]:
    recs: list[CostRecommendation] = []
    for v in variances:
        if v.severity == "normal" or v.variance_amount <= 0:
            continue
        code = f"cost_variance_{v.stage}_{v.category}"
        title = f"مراجعة تكلفة {v.category} في مرحلة {v.stage}"
        pct = f"{v.variance_percent:.1f}%" if v.variance_percent is not None else "غير محدد"
        message = (
            f"التكلفة الفعلية تجاوزت المخطط بمقدار {v.variance_amount:.2f} "
            f"({pct}). راجع الكمية، السعر، وسبب العملية قبل تعديل الخطة أو تقليل الصرف."
        )
        recs.append(
            CostRecommendation(
                code,
                title,
                message,
                v.severity,
                {
                    "season_id": v.season_id,
                    "stage": v.stage,
                    "category": v.category,
                    "planned_cost": v.planned_cost,
                    "actual_cost": v.actual_cost,
                    "variance_amount": v.variance_amount,
                    "variance_percent": v.variance_percent,
                },
            )
        )
    recs.sort(key=lambda r: (r.severity != "critical", -float(r.evidence["variance_amount"])))
    return recs[:max_items]


def project_to_erp_lines(
    actual_lines: Iterable[ActualCostLine],
    *,
    cost_center: str | None = None,
    project: str | None = None,
    currency: str = "YER",
) -> list[ErpProjectionLine]:
    grouped: dict[str, float] = {}
    for line in actual_lines:
        grouped[line.category] = grouped.get(line.category, 0.0) + (
            _non_negative(line.actual_cost, field_name="actual_cost") or 0.0
        )
    return [
        ErpProjectionLine(
            category=category,
            amount=amount,
            currency=currency,
            cost_center=cost_center,
            project=project,
            memo="SAHOOL operational ledger financial projection; source records remain in SAHOOL.",
        )
        for category, amount in sorted(grouped.items())
        if amount > 0
    ]
