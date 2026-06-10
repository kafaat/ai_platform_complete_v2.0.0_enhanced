#!/usr/bin/env python3
"""
SAHOOL Guardrails Engine — Multi-Tier Safety System
Inspired by: NVIDIA NemoClaw + OWASP MCP Security + NeMo Guardrails

Tiers:
  1. Chemical Safety — Banned substances, max dosages
  2. Environmental Safety — Water limits, carbon, soil health
  3. Economic Safety — Investment limits, ROI checks, farmer capacity

Features:
  - Human-in-the-Loop for critical decisions
  - Diff generation for rejected vs accepted actions
  - Arabic explanation of all rejections
"""

import os
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any, Literal

import jwt as _jwt
from diff_generator import ActionDiffGenerator
from fastapi import Depends, FastAPI, HTTPException
from fastapi import Header as _Header
from fastapi.middleware.cors import CORSMiddleware
from human_in_loop import HumanApprovalWorkflow
from pydantic import BaseModel, Field
from tiers.chemical_tier import ChemicalSafetyTier
from tiers.economic_tier import EconomicSafetyTier
from tiers.environmental_tier import EnvironmentalSafetyTier


class GuardrailsRequest(BaseModel):
    action_type: Literal[
        "irrigation", "fertilization", "pesticide", "harvest", "contract", "investment", "loan"
    ]
    action_data: dict[str, Any] = Field(..., description="Action parameters")
    farm_context: dict[str, Any] = Field(..., description="Current farm state")
    user_id: str
    tenant_id: str
    request_source: Literal["agent", "user", "system", "edge"] = "agent"
    auto_approve_low_risk: bool = Field(default=True)


class GuardrailsResult(BaseModel):
    allowed: bool
    tier_checks: list[dict[str, Any]]
    overall_risk: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    requires_human_approval: bool
    approval_workflow_id: str | None = None
    diff: dict[str, Any] | None = None  # Diff vs safe alternative
    arabic_explanation: str
    english_explanation: str | None = None
    suggested_modifications: list[dict[str, Any]] = Field(default_factory=list)
    processing_time_ms: int


class SAHOOLGuardrailsEngine:
    """
    Production-grade guardrails combining policy + network + privacy layers.
    """

    def __init__(self):
        self.chemical_tier = ChemicalSafetyTier()
        self.environmental_tier = EnvironmentalSafetyTier()
        self.economic_tier = EconomicSafetyTier()
        self.human_workflow = HumanApprovalWorkflow()
        self.diff_generator = ActionDiffGenerator()

        # Risk scoring weights
        self.tier_weights = {"chemical": 0.4, "environmental": 0.3, "economic": 0.3}

        # Auto-approve thresholds
        self.auto_approve_risk = ["LOW"]
        self.human_required_risk = ["HIGH", "CRITICAL"]

    async def validate(self, request: GuardrailsRequest) -> GuardrailsResult:
        start_time = datetime.now(UTC)

        checks = []

        # Tier 1: Chemical Safety (highest priority for pesticide/fertilizer)
        if request.action_type in ["pesticide", "fertilization"]:
            chem_check = await self.chemical_tier.validate(
                action_type=request.action_type,
                action_data=request.action_data,
                farm_context=request.farm_context,
            )
            checks.append(chem_check)

        # Tier 2: Environmental Safety (all actions)
        env_check = await self.environmental_tier.validate(
            action_type=request.action_type,
            action_data=request.action_data,
            farm_context=request.farm_context,
        )
        checks.append(env_check)

        # Tier 3: Economic Safety (investment/contract/loan actions)
        if request.action_type in ["investment", "contract", "loan", "irrigation", "fertilization"]:
            econ_check = await self.economic_tier.validate(
                action_type=request.action_type,
                action_data=request.action_data,
                farm_context=request.farm_context,
            )
            checks.append(econ_check)

        # Calculate overall risk
        overall_risk = self._calculate_overall_risk(checks)

        # Determine if human approval required
        requires_human = overall_risk in self.human_required_risk

        # Auto-approve low risk if enabled
        allowed = overall_risk in self.auto_approve_risk
        if request.auto_approve_low_risk and overall_risk == "MEDIUM":
            # Medium risk: check if all tiers pass with warnings
            allowed = all(c["passed"] for c in checks)

        # If not allowed and human required, create approval workflow
        workflow_id = None
        diff = None
        if not allowed and requires_human:
            workflow_id = await self.human_workflow.create(
                request=request, checks=checks, risk_level=overall_risk
            )
        elif not allowed:
            # Generate diff: rejected vs safe alternative
            diff = await self.diff_generator.generate(
                original=request.action_data, checks=checks, farm_context=request.farm_context
            )

        # Generate Arabic explanation
        arabic_exp = self._generate_arabic_explanation(
            allowed=allowed,
            checks=checks,
            overall_risk=overall_risk,
            requires_human=requires_human,
            action_type=request.action_type,
        )

        # Suggest modifications
        suggestions = self._suggest_modifications(checks, request.action_data)

        elapsed = int((datetime.now(UTC) - start_time).total_seconds() * 1000)

        return GuardrailsResult(
            allowed=allowed,
            tier_checks=checks,
            overall_risk=overall_risk,
            requires_human_approval=requires_human,
            approval_workflow_id=workflow_id,
            diff=diff,
            arabic_explanation=arabic_exp,
            suggested_modifications=suggestions,
            processing_time_ms=elapsed,
        )

    def _calculate_overall_risk(self, checks: list[dict]) -> str:
        """Calculate weighted risk score from tier checks."""
        if not checks:
            return "LOW"

        # Map severity to score
        severity_scores = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1, "PASS": 0}

        max_severity = 0
        for check in checks:
            for finding in check.get("findings", []):
                sev = severity_scores.get(finding.get("severity", "LOW"), 1)
                if sev > max_severity:
                    max_severity = sev

        if max_severity >= 4:
            return "CRITICAL"
        elif max_severity >= 3:
            return "HIGH"
        elif max_severity >= 2:
            return "MEDIUM"
        else:
            return "LOW"

    def _generate_arabic_explanation(
        self,
        allowed: bool,
        checks: list[dict],
        overall_risk: str,
        requires_human: bool,
        action_type: str,
    ) -> str:
        """Generate natural Arabic explanation of guardrails decision."""

        action_names = {
            "irrigation": "الري",
            "fertilization": "التسميد",
            "pesticide": "المكافحة الكيميائية",
            "harvest": "الحصاد",
            "contract": "العقد",
            "investment": "الاستثمار",
            "loan": "القرض",
        }
        action_name = action_names.get(action_type, action_type)

        if allowed:
            if overall_risk == "LOW":
                return f"✅ **تمت الموافقة التلقائية**\n\nإجراء {action_name} آمن ويحترم جميع معايير السلامة."
            else:
                return f"⚠️ **تمت الموافقة مع تحذير**\n\nإجراء {action_name} مسموح به لكن يوجد ملاحظات:\n{self._format_findings(checks)}"

        if requires_human:
            return f"🛑 **يتطلب موافقة بشرية**\n\nإجراء {action_name} يحمل مخاطر **{overall_risk}** ويتطلب مراجعة خبير زراعي قبل التنفيذ.\n\n**الأسباب:**\n{self._format_findings(checks)}\n\nسيتم إرسال طلب موافقة إلى المشرف المختص."

        return f"❌ **تم الرفض**\n\nإجراء {action_name} مرفوض لأسباب السلامة.\n\n**الأسباب:**\n{self._format_findings(checks)}\n\n**البدائل المقترحة:**\n{self._format_suggestions(checks)}"

    def _format_findings(self, checks: list[dict]) -> str:
        lines = []
        for check in checks:
            tier_name = check.get("tier", "")
            for finding in check.get("findings", []):
                if finding.get("severity") in ["CRITICAL", "HIGH"]:
                    lines.append(
                        f"• [{tier_name}] {finding.get('message_ar', finding.get('message', ''))}"
                    )
        return "\n".join(lines) if lines else "• لا توجد مخالفات حرجة."

    def _format_suggestions(self, checks: list[dict]) -> str:
        lines = []
        for check in checks:
            for suggestion in check.get("suggestions", []):
                lines.append(f"• {suggestion.get('text_ar', suggestion.get('text', ''))}")
        return "\n".join(lines) if lines else "• لا توجد اقتراحات محددة."

    def _suggest_modifications(self, checks: list[dict], action_data: dict) -> list[dict]:
        suggestions = []
        for check in checks:
            for suggestion in check.get("suggestions", []):
                suggestions.append(
                    {
                        "field": suggestion.get("field", ""),
                        "current_value": action_data.get(suggestion.get("field", "")),
                        "suggested_value": suggestion.get("value"),
                        "reason_ar": suggestion.get("text_ar", ""),
                        "reason_en": suggestion.get("text", ""),
                    }
                )
        return suggestions


# Singleton instance
_guardrails_engine: SAHOOLGuardrailsEngine | None = None


def get_guardrails_engine() -> SAHOOLGuardrailsEngine:
    global _guardrails_engine
    if _guardrails_engine is None:
        _guardrails_engine = SAHOOLGuardrailsEngine()
    return _guardrails_engine


# ══════════════════════════════════════════════════════════
# FastAPI Application (FIXED: was missing)
# ══════════════════════════════════════════════════════════
@asynccontextmanager
async def lifespan(app):
    get_guardrails_engine()  # warm up
    yield


app = FastAPI(
    title="SAHOOL Guardrails Engine",
    version="9.1.0",
    description="Multi-Tier Agricultural AI Safety System",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:3000").split(","),
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
    allow_credentials=True,
)

# ── مصادقة بوابة الموافقة البشريّة (أمان) ──
_GR_JWT_PUBLIC = os.getenv("JWT_PUBLIC_KEY", "")
_GR_JWT_SECRET = _GR_JWT_PUBLIC if _GR_JWT_PUBLIC else os.getenv("JWT_SECRET", "")
_GR_JWT_ALG = "RS256" if _GR_JWT_PUBLIC else "HS256"
# توكن خدمة للنداءات خدمة-لخدمة على /validate (supervisor → guardrails)
_GR_AGENT_TOKEN = os.getenv("SAHOOL_AGENT_TOKEN", "")


def _require_service_token(x_agent_token: str = _Header(None)):
    """يفرض توكن خدمة على /validate. صدق: بلا توكن مضبوط → فشل-مغلق.

    منع باب خلفي: لا يُقبل /validate من أيّ جهة بلا توكن الخدمة الصحيح.
    """
    if not _GR_AGENT_TOKEN:
        raise HTTPException(503, "SAHOOL_AGENT_TOKEN غير مضبوط — /validate معطّل بأمان")
    # L5 FIX: مقارنة بزمن ثابت (كـodoo-bridge) لإغلاق قناة توقيت جانبيّة.
    import hmac as _hmac

    if not x_agent_token or not _hmac.compare_digest(x_agent_token, _GR_AGENT_TOKEN):
        raise HTTPException(401, "توكن خدمة غير صالح لـ/validate")
    return True


def _gr_verify(authorization: str = _Header(None)) -> dict:
    # افشل بأمان: لا سرّ → لا موافقات (منع تزوير بمفتاح فارغ)
    if not _GR_JWT_SECRET or len(_GR_JWT_SECRET) < 32:
        raise HTTPException(503, "JWT_SECRET غير مضبوط — بوابة الموافقة معطّلة بأمان")
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "توكن مطلوب للموافقة")
    try:
        payload = _jwt.decode(
            authorization.split(" ", 1)[1],
            _GR_JWT_SECRET,
            algorithms=[_GR_JWT_ALG],
            audience="sahool",
        )
    except Exception:
        raise HTTPException(401, "توكن غير صالح") from None
    # الموافقة تتطلّب دور expert أو admin (بوابة بشريّة)
    if payload.get("role") not in ("expert", "admin"):
        raise HTTPException(403, "الموافقة تتطلّب صلاحيّة خبير أو مدير")
    if not payload.get("sub"):
        raise HTTPException(401, "توكن ناقص الهويّة")
    return payload


@app.post("/validate", response_model=GuardrailsResult)
async def validate_action(request: GuardrailsRequest, _svc: bool = Depends(_require_service_token)):
    """Main validation endpoint — checks action against 3 tiers.

    أمان: يتطلّب توكن خدمة (X-Agent-Token) — لا يُقبل من جهة غير موثوقة.
    tenant_id يأتي في الطلب من خدمة موثوقة (supervisor تشتقّه من توكن
    المستخدم المُتحقَّق، لا من جسم طلب المستخدم مباشرةً).
    """
    engine = get_guardrails_engine()
    return await engine.validate(request)


@app.post("/approve/{workflow_id}")
async def approve_workflow(
    workflow_id: str, approved: bool, reason: str = "", claims: dict = Depends(_gr_verify)
):
    """Human-in-the-Loop approval — الهويّة من التوكن المُتحقَّق لا من الطلب."""
    # الأمان: expert_id يُشتقّ من التوكن (لا يُقبل من العميل) — منع انتحال الخبير
    expert_id = str(claims["sub"])
    hil = HumanApprovalWorkflow()
    if approved:
        return await hil.approve(workflow_id, expert_id, reason)
    else:
        return await hil.reject(workflow_id, expert_id, reason)


@app.get("/workflow/{workflow_id}")
async def get_workflow(workflow_id: str):
    hil = HumanApprovalWorkflow()
    return hil.get_status(workflow_id)


@app.get("/healthz")
@app.get("/health")
async def healthz():
    return {"status": "alive", "service": "guardrails-engine", "tiers": 3}


@app.get("/readyz")
async def readyz():
    return {"status": "ready"}


@app.get("/metrics")
async def metrics_endpoint():
    from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
    from starlette.responses import Response

    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
