"""SAHOOL agriai-engine — profit_planner.py (وحدة صرفة، بلا FastAPI).

مُخطِّط واعٍ بالربح: لكلّ مرشّح (محصول/إجراء) بتقدير غلّة (من المُحوِّل) وسعر وبنود
كلفة (بذور/ماء/سماد/عمالة)، يحسب:

    expected_profit = yield_kg_ha * price_per_kg - Σ(costs)

ثمّ يرتّب المرشّحين تنازليّاً بالربح، ويُرجع خطّة مرتّبة مع تفصيل لكلّ مرشّح وبصمة
حزمة الأدلّة الحاكمة. حتميّ تماماً؛ كسر التعادل حتميّ (بالاسم تصاعديّاً).
"""

from __future__ import annotations

from typing import Any

_ROUND = 2


def _num(value: Any, default: float = 0.0) -> float:
    if isinstance(value, bool):
        return default
    try:
        out = float(value)
    except (TypeError, ValueError):
        return default
    return out if out == out and out not in (float("inf"), float("-inf")) else default


def _sum_costs(costs: Any) -> tuple[float, dict[str, float]]:
    """يجمع بنود الكلفة (dict اسم→قيمة أو list من {name,amount}) ويُرجع (المجموع، التفصيل)."""
    breakdown: dict[str, float] = {}
    if isinstance(costs, dict):
        for key, val in costs.items():
            breakdown[str(key)] = round(_num(val), _ROUND)
    elif isinstance(costs, list):
        for item in costs:
            if isinstance(item, dict):
                name = str(item.get("name", item.get("kind", "cost")))
                breakdown[name] = round(
                    breakdown.get(name, 0.0) + _num(item.get("amount", item.get("value"))), _ROUND
                )
    total = round(sum(breakdown.values()), _ROUND)
    return total, breakdown


def evaluate_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    """يقيّم مرشّحاً واحداً ⇒ تفصيل إيراد/كلفة/ربح متوقّع (حتميّ).

    عند حمل المرشّح ``yield_interval`` (من مُحوِّل المحاكاة) يُشتقّ **مدى ربح** صادق
    (منخفض/مرتفع) من حدّي الغلّة — لا رقم ربح واحد يُوهِم يقيناً غير موجود.
    """
    name = str(candidate.get("name", candidate.get("id", candidate.get("crop", "candidate"))))
    yield_kg_ha = _num(candidate.get("yield_kg_ha"))
    price = _num(candidate.get("price_per_kg", candidate.get("price")))
    revenue = round(yield_kg_ha * price, _ROUND)
    total_cost, cost_breakdown = _sum_costs(candidate.get("costs"))
    expected_profit = round(revenue - total_cost, _ROUND)
    result = {
        "name": name,
        "yield_kg_ha": round(yield_kg_ha, _ROUND),
        "price_per_kg": round(price, _ROUND),
        "revenue": revenue,
        "total_cost": total_cost,
        "cost_breakdown": cost_breakdown,
        "expected_profit": expected_profit,
    }

    # تمرير عدم اليقين: مدى ربح من حدّي الغلّة (إن توفّر النطاق النموذجيّ).
    interval = candidate.get("yield_interval")
    if isinstance(interval, dict) and interval.get("low_kg_ha") is not None:
        low_y = _num(interval.get("low_kg_ha"))
        high_y = _num(interval.get("high_kg_ha"))
        result["expected_profit_low"] = round(low_y * price - total_cost, _ROUND)
        result["expected_profit_high"] = round(high_y * price - total_cost, _ROUND)
        result["yield_confidence"] = str(interval.get("confidence", "unknown"))
    return result


def plan_profit(
    candidates: list[dict[str, Any]],
    *,
    evidence_hash: str | None = None,
) -> dict[str, Any]:
    """يبني خطّة مرتّبة تنازليّاً بالربح المتوقّع.

    كسر التعادل حتميّ: عند تساوي الربح يُرتَّب بالاسم تصاعديّاً كي يكون الترتيب مستقرّاً
    ومستقلّاً عن ترتيب الإدخال. يُرجع أيضاً بصمة حزمة الأدلّة الحاكمة (إن وُجدت).
    """
    evaluated = [evaluate_candidate(c) for c in candidates if isinstance(c, dict)]
    # ربح تنازليّ (سالب للفرز التنازليّ)، ثمّ اسم تصاعديّ لكسر التعادل حتميّاً.
    evaluated.sort(key=lambda e: (-e["expected_profit"], e["name"]))
    ranked = []
    for idx, ev in enumerate(evaluated, start=1):
        ranked.append({"rank": idx, **ev})
    return {
        "schema": "sahool.agriai.profit_plan/1",
        "evidence_hash": str(evidence_hash) if evidence_hash is not None else None,
        "ranked": ranked,
        "best": ranked[0]["name"] if ranked else None,
        "best_expected_profit": ranked[0]["expected_profit"] if ranked else None,
    }
