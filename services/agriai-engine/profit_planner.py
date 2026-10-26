"""SAHOOL agriai-engine — profit_planner.py (وحدة صرفة، بلا FastAPI).

مُخطِّط واعٍ بالربح: لكلّ مرشّح (محصول/إجراء) بتقدير غلّة (من المُحوِّل) وسعر وبنود
كلفة (بذور/ماء/سماد/عمالة)، يحسب:

    expected_profit = yield_kg_ha * price_per_kg - Σ(costs)

ثمّ يرتّب المرشّحين تنازليّاً بالربح، ويُرجع خطّة مرتّبة مع تفصيل لكلّ مرشّح وبصمة
حزمة الأدلّة الحاكمة. حتميّ تماماً؛ كسر التعادل حتميّ (بالاسم تصاعديّاً).

مرشّحٌ بلا غلّة أو بلا سعر موجب أو بلا بنود كلفة (أو ببندٍ غير رقميّ) **غير كافٍ**: لا يُكلَّف
صفراً ولا يدخل الترتيب ولا ``best`` — يُدرَج في ``insufficient`` مع أسماء المدخلات الناقصة.
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


def _finite(value: Any) -> float | None:
    """رقمٌ منتهٍ أو ``None`` — الغياب/النصّ/NaN/inf/bool نقصٌ يُسمّى لا صفرٌ يُفترَض."""
    if value is None or isinstance(value, bool):
        return None
    out = _num(value, float("nan"))
    return None if out != out else out


def _sum_costs(costs: Any) -> tuple[float, dict[str, float], list[str]]:
    """يجمع بنود الكلفة (dict اسم→قيمة أو list من {name,amount}).

    يُرجع (المجموع، التفصيل، الناقص). غياب البنود أو بندٌ بلا قيمة رقميّة يُسمّى في الناقص.
    """
    breakdown: dict[str, float] = {}
    missing: list[str] = []
    items: list[tuple[str, Any]] = []
    if isinstance(costs, dict):
        items = [(str(key), val) for key, val in costs.items()]
    elif isinstance(costs, list):
        for item in costs:
            if isinstance(item, dict):
                name = str(item.get("name", item.get("kind", "cost")))
                items.append((name, item.get("amount", item.get("value"))))
            else:
                missing.append("costs.item")
    if not items:
        missing.append("costs")
    for name, raw in items:
        val = _finite(raw)
        if val is None:
            missing.append(f"costs.{name}")
            continue
        breakdown[name] = round(breakdown.get(name, 0.0) + val, _ROUND)
    total = round(sum(breakdown.values()), _ROUND)
    return total, breakdown, missing


def evaluate_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    """يقيّم مرشّحاً واحداً ⇒ تفصيل إيراد/كلفة/ربح متوقّع (حتميّ).

    عند حمل المرشّح ``yield_interval`` (من مُحوِّل المحاكاة) يُشتقّ **مدى ربح** صادق
    (منخفض/مرتفع) من حدّي الغلّة — لا رقم ربح واحد يُوهِم يقيناً غير موجود.
    """
    name = str(candidate.get("name", candidate.get("id", candidate.get("crop", "candidate"))))
    yield_kg_ha = _finite(candidate.get("yield_kg_ha"))
    price = _finite(candidate.get("price_per_kg", candidate.get("price")))
    total_cost, cost_breakdown, missing = _sum_costs(candidate.get("costs"))
    if price is None or price <= 0:
        missing.insert(0, "price_per_kg")
    if yield_kg_ha is None:
        missing.insert(0, "yield_kg_ha")
    if missing or yield_kg_ha is None or price is None:
        # غير كافٍ: لا إيراد ولا ربح من أصفار مُفترَضة، ولا مدى ربح.
        return {
            "name": name,
            "status": "insufficient",
            "missing_inputs": missing,
            "yield_kg_ha": None if yield_kg_ha is None else round(yield_kg_ha, _ROUND),
            "price_per_kg": None if price is None else round(price, _ROUND),
            "revenue": None,
            "total_cost": None,
            "cost_breakdown": cost_breakdown,
            "expected_profit": None,
        }
    revenue = round(yield_kg_ha * price, _ROUND)
    expected_profit = round(revenue - total_cost, _ROUND)
    result = {
        "name": name,
        "status": "costed",
        "yield_kg_ha": round(yield_kg_ha, _ROUND),
        "price_per_kg": round(price, _ROUND),
        "revenue": revenue,
        "total_cost": total_cost,
        "cost_breakdown": cost_breakdown,
        "expected_profit": expected_profit,
    }

    # تمرير عدم اليقين: مدى ربح من حدّي الغلّة (إن توفّر النطاق النموذجيّ بحدّين منتهيين).
    interval = candidate.get("yield_interval")
    if isinstance(interval, dict):
        low_y = _finite(interval.get("low_kg_ha"))
        high_y = _finite(interval.get("high_kg_ha"))
        if low_y is not None and high_y is not None:
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
    costed = [e for e in evaluated if e["status"] == "costed"]
    insufficient = sorted(
        (e for e in evaluated if e["status"] != "costed"), key=lambda e: e["name"]
    )
    # ربح تنازليّ (سالب للفرز التنازليّ)، ثمّ اسم تصاعديّ لكسر التعادل حتميّاً.
    costed.sort(key=lambda e: (-e["expected_profit"], e["name"]))
    ranked = []
    for idx, ev in enumerate(costed, start=1):
        ranked.append({"rank": idx, **ev})
    return {
        "schema": "sahool.agriai.profit_plan/1",
        "evidence_hash": str(evidence_hash) if evidence_hash is not None else None,
        "ranked": ranked,
        "insufficient": insufficient,
        "best": ranked[0]["name"] if ranked else None,
        "best_expected_profit": ranked[0]["expected_profit"] if ranked else None,
    }
