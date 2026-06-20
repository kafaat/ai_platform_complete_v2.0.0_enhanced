"""api/routers/portfolio_command.py — مركز قيادة المحفظة (compute، توصية فقط، #8)

نقطة واحدة محروسة بعلم ``FEATURE_PORTFOLIO_COMMAND`` (مُطفأة افتراضاً ⇒ 404، نمط
``decision_dispatch``):

  • ``POST /api/v1/portfolio/command`` — يقارن عدّة **سياسات ريّ** على نفس حقول
    المزرعة/المصادر، فيُبرز لكلّ سياسة **الربح والمخاطر معاً** تحت **قيود الآبار/
    المضخّات/المحاور**، ويُرشّح الأفضل **كتوصية فقط** (لا تنفيذ، لا حجز، لا كتابة قاعدة).

**الصدق**: الهوامش/الطلبات/السعات لكلّ سياسة **يمرّرها المستدعي** (تُحسب من
``/crop-twin/decision/profit-aware`` لكلّ سياسة، كنمط ScenarioCompare) — لا تُلفَّق.
الطبقة النقيّة ``compare_portfolio_policies`` تشكّل المقارنة حتميّاً، ``calibrated=False``.
compute صرف (لا قاعدة) كشقيقه ``field_portfolio`` — المصادقة فقط حارساً.
"""

from __future__ import annotations

import os

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.main import UserSchema, get_current_user
from api.portfolio_allocation import PortfolioField
from api.portfolio_command import (
    ConstraintSource,
    PolicyScenario,
    compare_portfolio_policies,
)

router = APIRouter()

_TRUTHY = {"1", "true", "yes", "on"}


def _portfolio_command_enabled() -> bool:
    """هل ميزة مركز قيادة المحفظة مُفعَّلة؟ (مُطفأة افتراضاً — إنضاج تدريجيّ)."""
    return os.getenv("FEATURE_PORTFOLIO_COMMAND", "").strip().lower() in _TRUTHY


class CommandFieldModel(BaseModel):
    field_id: str
    expected_margin: float  # هامش الحقل تحت هذه السياسة (من profit-aware)
    water_demand_m3: float  # احتياجه المائيّ تحت هذه السياسة (م³)
    priority: int = 1
    min_water_fraction: float = 0.0
    source_ids: list[str] = Field(default_factory=list)  # تغطية المحور = مصادر بعينها


class CommandSourceModel(BaseModel):
    source_id: str
    capacity_m3: float
    kind: str = "well"  # well | pump | pivot | network
    max_rate_m3_per_day: float | None = None  # حدّ تدفّق المضخّة (م³/يوم)
    window_days: float | None = None  # نافذة التخطيط لتحويل التدفّق إلى سعة فعّالة


class PolicyScenarioModel(BaseModel):
    policy_label: str
    fields: list[CommandFieldModel] = Field(default_factory=list)
    sources: list[CommandSourceModel] = Field(default_factory=list)


class PortfolioCommandRequest(BaseModel):
    scenarios: list[PolicyScenarioModel] = Field(default_factory=list)
    risk_aversion: float = 1.0  # 0 = ربح صرف؛ أعلى = أكثر نُفوراً من المخاطرة


@router.post("/api/v1/portfolio/command")
def portfolio_command_endpoint(
    req: PortfolioCommandRequest,
    user: UserSchema = Depends(get_current_user),
) -> dict:
    """يقارن سياسات المحفظة على الربح×المخاطر تحت القيود — توصية فقط. 404 إن مُطفأ.

    لكلّ سياسة: توزيع ماء متعدّد المصادر تحت قيود البئر/المضخّة/المحور، ثمّ ربح ومخاطر
    ودرجة شفّافة، وترشيح الأفضل (ربح معدَّل بالنُّفور من المخاطرة). صدق: المدخلات مُمرَّرة
    لا مُختلقة؛ calibrated=False؛ **لا تنفيذ ولا حجز ماء**.
    """
    if not _portfolio_command_enabled():
        raise HTTPException(
            status_code=404,
            detail="ميزة مركز قيادة المحفظة غير مُفعَّلة (اضبط FEATURE_PORTFOLIO_COMMAND).",
        )
    scenarios = [
        PolicyScenario(
            policy_label=sc.policy_label,
            fields=[
                PortfolioField(
                    field_id=f.field_id,
                    expected_margin=f.expected_margin,
                    water_demand_m3=f.water_demand_m3,
                    priority=f.priority,
                    min_water_fraction=f.min_water_fraction,
                    source_ids=f.source_ids,
                )
                for f in sc.fields
            ],
            sources=[
                ConstraintSource(
                    source_id=s.source_id,
                    capacity_m3=s.capacity_m3,
                    kind=s.kind,
                    max_rate_m3_per_day=s.max_rate_m3_per_day,
                    window_days=s.window_days,
                )
                for s in sc.sources
            ],
        )
        for sc in req.scenarios
    ]
    out = compare_portfolio_policies(scenarios, risk_aversion=req.risk_aversion)
    out["tenant_id"] = str(user.tenant_id)  # أثر: لِمن هذه المقارنة
    return out
