#!/usr/bin/env python3
import logging as _log
_audit = _log.getLogger("guardrails.economic_tier")
#!/usr/bin/env python3
"""
Tier 3: Economic Safety Guardrails
Validates actions against:
- Farmer investment capacity
- ROI thresholds
- Loan/credit risk
- Market price volatility
"""
from typing import Any, Dict, List


class EconomicSafetyTier:
    """
    Economic impact validation for farm actions.
    """

    # Maximum investment as % of annual farm revenue
    MAX_INVESTMENT_PCT = 0.30

    # Minimum ROI for investment approval (%)
    MIN_ROI_PCT = 15

    # Maximum debt-to-income ratio
    MAX_DEBT_TO_INCOME = 0.50

    # Emergency reserve (months of operating expenses)
    MIN_RESERVE_MONTHS = 2

    async def validate(self, action_type: str, action_data: Dict, farm_context: Dict) -> Dict:
        findings = []
        suggestions = []
        passed = True

        annual_revenue = farm_context.get("annual_revenue_usd", 0)
        annual_costs = farm_context.get("annual_costs_usd", 0)
        current_debt = farm_context.get("current_debt_usd", 0)
        cash_reserve = farm_context.get("cash_reserve_usd", 0)
        monthly_expenses = annual_costs / 12 if annual_costs > 0 else 0

        if action_type in ["irrigation", "fertilization", "pesticide"]:
            action_cost = action_data.get("cost_usd", 0)
            projected_revenue_increase = action_data.get("projected_revenue_increase_usd", 0)

            # Check investment capacity
            if annual_revenue > 0:
                investment_ratio = action_cost / annual_revenue
                if investment_ratio > self.MAX_INVESTMENT_PCT:
                    findings.append({
                        "severity": "HIGH",
                        "message": f"Action cost ${action_cost:.0f} is {investment_ratio:.0%} of annual revenue (max {self.MAX_INVESTMENT_PCT:.0%})",
                        "message_ar": f"تكلفة الإجراء ${action_cost:.0f} تمثل {investment_ratio:.0%} من الإيرادات السنوية (الحد الأقصى {self.MAX_INVESTMENT_PCT:.0%})",
                        "rule": "investment_capacity_exceeded"
                    })
                    passed = False
                    suggestions.append({
                        "field": "cost_usd",
                        "value": annual_revenue * self.MAX_INVESTMENT_PCT,
                        "text": "Reduce cost or phase implementation",
                        "text_ar": "قلل التكلفة أو قسّم التنفيذ على مراحل"
                    })

            # Check ROI
            if action_cost > 0:
                roi = (projected_revenue_increase - action_cost) / action_cost * 100
                if roi < self.MIN_ROI_PCT:
                    findings.append({
                        "severity": "MEDIUM",
                        "message": f"Projected ROI {roi:.1f}% below minimum threshold {self.MIN_ROI_PCT}%",
                        "message_ar": f"العائد المتوقع {roi:.1f}% أقل من الحد الأدنى ({self.MIN_ROI_PCT}%)",
                        "rule": "roi_below_threshold"
                    })
                    suggestions.append({
                        "field": "projected_revenue_increase_usd",
                        "value": action_cost * (1 + self.MIN_ROI_PCT / 100),
                        "text": "Reconsider timing or method to improve ROI",
                        "text_ar": "أعد النظر في التوقيت أو الطريقة لتحسين العائد"
                    })

            # Check cash reserve
            if cash_reserve < monthly_expenses * self.MIN_RESERVE_MONTHS:
                findings.append({
                    "severity": "MEDIUM",
                    "message": f"Cash reserve ${cash_reserve:.0f} below {self.MIN_RESERVE_MONTHS}-month minimum (${monthly_expenses*self.MIN_RESERVE_MONTHS:.0f})",
                    "message_ar": f"الاحتياطي النقدي ${cash_reserve:.0f} أقل من الحد الأدنى ({self.MIN_RESERVE_MONTHS} أشهر = ${monthly_expenses*self.MIN_RESERVE_MONTHS:.0f})",
                    "rule": "low_cash_reserve"
                })

        elif action_type == "loan":
            loan_amount = action_data.get("loan_amount_usd", 0)
            projected_annual_revenue = farm_context.get("projected_annual_revenue_usd", annual_revenue)

            # Check debt-to-income
            new_debt = current_debt + loan_amount
            if projected_annual_revenue > 0:
                debt_ratio = new_debt / projected_annual_revenue
                if debt_ratio > self.MAX_DEBT_TO_INCOME:
                    findings.append({
                        "severity": "HIGH",
                        "message": f"Debt-to-income ratio {debt_ratio:.0%} exceeds maximum {self.MAX_DEBT_TO_INCOME:.0%}",
                        "message_ar": f"نسبة الدين إلى الدخل {debt_ratio:.0%} تتجاوز الحد الأقصى ({self.MAX_DEBT_TO_INCOME:.0%})",
                        "rule": "debt_to_income_exceeded"
                    })
                    passed = False
                    suggestions.append({
                        "field": "loan_amount_usd",
                        "value": max(0, (self.MAX_DEBT_TO_INCOME * projected_annual_revenue) - current_debt),
                        "text": "Reduce loan amount or improve revenue projections",
                        "text_ar": "قلل مبلغ القرض أو حسّن توقعات الإيرادات"
                    })

        elif action_type == "contract":
            contract_value = action_data.get("contract_value_usd", 0)

            # Check if contract value is realistic vs farm capacity
            if annual_revenue > 0 and contract_value > annual_revenue * 2:
                findings.append({
                    "severity": "MEDIUM",
                    "message": f"Contract value ${contract_value:.0f} exceeds 2x annual revenue — verify capacity",
                    "message_ar": f"قيمة العقد ${contract_value:.0f} تتجاوض ضعفي الإيرادات السنوية — تحقق من القدرة",
                    "rule": "contract_capacity_check"
                })

        return {
            "tier": "economic",
            "passed": passed,
            "findings": findings,
            "suggestions": suggestions
        }
