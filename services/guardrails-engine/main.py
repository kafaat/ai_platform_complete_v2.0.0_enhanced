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
from contracts import ECONOMIC_ACTIONS, contract_violations
from diff_generator import ActionDiffGenerator
from fastapi import FastAPI, HTTPException
from fastapi import Header as _Header
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from human_in_loop import APPROVER_ROLES, HumanApprovalWorkflow, WorkflowUnavailable
from pydantic import BaseModel, Field, field_validator, model_validator
from tiers.chemical_tier import ChemicalSafetyTier
from tiers.economic_tier import EconomicSafetyTier
from tiers.environmental_tier import EnvironmentalSafetyTier

from shared.security.cors_policy import parse_cors_origins


class GuardrailsRequest(BaseModel):
    action_type: Literal[
        "irrigation", "fertilization", "pesticide", "harvest", "contract", "investment", "loan"
    ]
    action_data: dict[str, Any] = Field(..., description="Action parameters")
    farm_context: dict[str, Any] = Field(..., description="Current farm state")
    user_id: int = Field(gt=0, le=2147483647)
    tenant_id: str
    request_source: Literal["agent", "user", "system", "edge"] = "agent"
    auto_approve_low_risk: bool = Field(default=True)

    @field_validator("user_id", mode="before")
    @classmethod
    def canonical_user_id(cls, value):
        if isinstance(value, str) and value.isascii() and value.isdecimal():
            value = int(value)
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError("user_id must be a positive users.id integer")
        return value

    @field_validator("tenant_id")
    @classmethod
    def canonical_tenant_id(cls, value):
        from uuid import UUID

        return str(UUID(value))

    @model_validator(mode="after")
    def validate_evidence(self):
        invalid = contract_violations(self.action_type, self.action_data, self.farm_context)
        if invalid:
            raise ValueError("Missing or invalid guardrails evidence: " + ", ".join(invalid))
        return self


class GuardrailsResult(BaseModel):
    allowed: bool
    tier_checks: list[dict[str, Any]]
    overall_risk: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    requires_human_approval: bool
    approval_workflow_id: str | None = None
    notification_delivery: Literal["not_configured"] | None = None
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

        # عقد الاكتمال (fail-closed): سياق ناقص لطبقة جوهريّة ⇒ رفض موثّق بدل حوكمة
        # شكليّة. لا يبتلع فحوص الطبقات اللاحقة — يسبقها فقط حين ينقص الجوهريّ.
        missing = contract_violations(
            request.action_type, request.action_data, request.farm_context
        )
        if missing:
            fields_ar = "، ".join(missing)
            return GuardrailsResult(
                allowed=False,
                tier_checks=[
                    {
                        "tier": "context_contract",
                        "passed": False,
                        "findings": [
                            {
                                "severity": "HIGH",
                                "rule": "incomplete_context",
                                "message_ar": f"سياق حوكمة ناقص: {fields_ar}",
                                "missing_fields": missing,
                            }
                        ],
                    }
                ],
                overall_risk="HIGH",
                requires_human_approval=False,
                arabic_explanation=(
                    f"❌ رُفض: سياق الحوكمة ناقص للنوع «{request.action_type}» — الحقول "
                    f"المطلوبة: {fields_ar}. لا يُقيَّم الإجراء بسياق ناقص (fail-closed)."
                ),
                processing_time_ms=int((datetime.now(UTC) - start_time).total_seconds() * 1000),
            )

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
        if request.action_type in ECONOMIC_ACTIONS:
            econ_check = await self.economic_tier.validate(
                action_type=request.action_type,
                action_data=request.action_data,
                farm_context=request.farm_context,
            )
            checks.append(econ_check)

        # Calculate overall risk
        overall_risk = self._calculate_overall_risk(checks)

        # Only LOW can be automatically approved, and only when the caller opted in.
        # Warnings and an explicit request for manual review create a durable workflow.
        allowed = (
            request.auto_approve_low_risk
            and overall_risk == "LOW"
            and all(check["passed"] for check in checks)
        )
        requires_human = not allowed

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
            notification_delivery="not_configured" if workflow_id else None,
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
            return f"🛑 **يتطلب موافقة بشرية**\n\nإجراء {action_name} يحمل مخاطر **{overall_risk}** ويتطلب مراجعة خبير زراعي قبل التنفيذ.\n\n**الأسباب:**\n{self._format_findings(checks)}\n\nحُفظ طلب المراجعة. تسليم إشعارات الخبراء غير مهيّأ؛ تابع حالة الطلب عبر بوابة الموافقات."

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
    # FINDING-001: لينشين عزل المستأجرين — ارفض الإقلاع إن تجاوز دور الاتّصال RLS
    # (fail-closed افتراضيّاً). guardrails يكتب قرارات الحوكمة/الموافقات في القاعدة.
    from shared.db_role_guard import assert_dsn_role_rls_safe

    await assert_dsn_role_rls_safe(os.getenv("DATABASE_URL", ""), service="guardrails-engine")
    yield


app = FastAPI(
    title="SAHOOL Guardrails Engine",
    version="9.1.0",
    description="Multi-Tier Agricultural AI Safety System",
    lifespan=lifespan,
)


@app.exception_handler(RequestValidationError)
async def invalid_request_handler(_request, exc):
    # Do not echo untrusted amounts (including NaN/Infinity) into JSON error bodies.
    errors = [{"type": e["type"], "loc": e["loc"], "msg": e["msg"]} for e in exc.errors()]
    return JSONResponse(status_code=422, content={"detail": errors})


@app.exception_handler(WorkflowUnavailable)
async def workflow_unavailable_handler(_request, _exc):
    return JSONResponse(
        status_code=503,
        content={
            "detail": {
                "code": "approval_store_unavailable",
                "message_ar": "تعذّر حفظ أو قراءة طلب الموافقة؛ الإجراء غير معتمد.",
            }
        },
    )


app.add_middleware(
    CORSMiddleware,
    allow_origins=parse_cors_origins(os.getenv("CORS_ORIGINS"), allow_credentials=True),
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
    allow_credentials=True,
)

# ── مصادقة بوابة الموافقة البشريّة (أمان) ──
_GR_JWT_PUBLIC = os.getenv("JWT_PUBLIC_KEY", "")
_GR_JWT_SECRET = _GR_JWT_PUBLIC if _GR_JWT_PUBLIC else os.getenv("JWT_SECRET", "")
_GR_JWT_ALG = "RS256" if _GR_JWT_PUBLIC else "HS256"
# المُصدِرون الداخليّون المسموح بهم — يُفرَض بعد فكّ التوكن (تدقيق B: iss لم يُفحَص).
_ALLOWED_ISS = {"sahool-auth", "sahool-platform"}

# تحصين الإنتاج (fail-closed، تماثُل مع auth/المنصّة): RS256 إلزاميّ — HS256 سرّ متماثل
# مشترَك لا يُنهي shared trust domain (أيّ خدمة تحمله تُزوّر توكناً). في الإنتاج بلا
# JWT_PUBLIC_KEY نرفض الإقلاع ما لم يُعطَّل صراحةً (مهرب ترحيل SAHOOL_ALLOW_HS256_IN_PROD=1).
if (
    not os.getenv("JWT_PUBLIC_KEY", "").strip()
    and os.getenv("SAHOOL_ENV", "development").strip().lower() == "production"
    and os.getenv("SAHOOL_ALLOW_HS256_IN_PROD", "").strip().lower()
    not in {"1", "true", "yes", "on"}
):
    raise RuntimeError(
        "RS256 مطلوب في الإنتاج: اضبط JWT_PUBLIC_KEY (HS256 لا يُنهي shared trust domain). "
        "للترحيل المؤقّت فقط: SAHOOL_ALLOW_HS256_IN_PROD=1."
    )
# توكن خدمة للنداءات خدمة-لخدمة على /validate (supervisor → guardrails)
_GR_AGENT_TOKEN = os.getenv("SAHOOL_AGENT_TOKEN", "")


def _require_service_token(x_agent_token: str = _Header(None)):
    """يفرض توكن خدمة على /v1/validate. صدق: بلا توكن مضبوط → فشل-مغلق.

    منع باب خلفي: لا يُقبل /v1/validate من أيّ جهة بلا توكن الخدمة الصحيح.
    """
    if not _GR_AGENT_TOKEN:
        raise HTTPException(503, "SAHOOL_AGENT_TOKEN غير مضبوط — /v1/validate معطّل بأمان")
    # L5 FIX: مقارنة بزمن ثابت (كـodoo-bridge) لإغلاق قناة توقيت جانبيّة.
    import hmac as _hmac

    if not x_agent_token or not _hmac.compare_digest(x_agent_token, _GR_AGENT_TOKEN):
        raise HTTPException(401, "توكن خدمة غير صالح لـ/v1/validate")
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
    # تدقيق B: افرض المُصدِر بعد فكّ ناجح — مُصدِر مجهول ⇒ 401 كتوكن غير صالح.
    if payload.get("iss") not in _ALLOWED_ISS:
        raise HTTPException(401, "مُصدِر التوكن غير مسموح")
    # Authenticated specialist roles must match the workflow role at mutation time.
    if payload.get("role") not in APPROVER_ROLES:
        raise HTTPException(403, "الموافقة تتطلّب صلاحيّة خبير أو مدير")
    if not payload.get("sub"):
        raise HTTPException(401, "توكن ناقص الهويّة")
    try:
        from uuid import UUID

        payload["tenant_id"] = str(UUID(payload.get("tenant_id", "")))
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(401, "توكن ناقص المستأجر") from None
    return payload


def _gr_authn(authorization: str = _Header(None)) -> dict:
    """تحقّق توكن فقط (بلا اشتراط دور خبير) — للقراءة المُصرّح بها لأيّ مستخدم.

    يُستخدم لقراءة حالة workflow: لا يحتاج صلاحيّة خبير (المزارع صاحب الإجراء
    يحقّ له متابعة حالته)، لكن لا بدّ من توكن صالح + تقييد بالمستأجر في النقطة.
    """
    if not _GR_JWT_SECRET or len(_GR_JWT_SECRET) < 32:
        raise HTTPException(503, "JWT_SECRET غير مضبوط")
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "توكن مطلوب")
    try:
        payload = _jwt.decode(
            authorization.split(" ", 1)[1],
            _GR_JWT_SECRET,
            algorithms=[_GR_JWT_ALG],
            audience="sahool",
        )
    except Exception:
        raise HTTPException(401, "توكن غير صالح") from None
    # تدقيق B: افرض المُصدِر بعد فكّ ناجح — مُصدِر مجهول ⇒ 401 كتوكن غير صالح.
    if payload.get("iss") not in _ALLOWED_ISS:
        raise HTTPException(401, "مُصدِر التوكن غير مسموح")
    if not payload.get("sub"):
        raise HTTPException(401, "توكن ناقص الهويّة")
    try:
        from uuid import UUID

        payload["tenant_id"] = str(UUID(payload.get("tenant_id", "")))
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(401, "توكن ناقص المستأجر") from None
    return payload


# ─── تسجيل تلقائيّ للراوترات المُستخرَجة (تفكيك محفوظ السلوك) ─────────────
# يُستدعى في **النهاية** بعد تعريف ``app`` وكلّ التبعيّات المشتركة (المحرّك/النماذج/
# المساعِدات/توكن الخدمة/الـauth)، فيُحلّ الاستيراد الدائريّ (وحدات ``routers/``
# تستورد رموزاً من ``main`` عبر ``main.X``). كلّ وحدة في ``routers/`` تُصدّر ``router``
# يُضمَّن **بلا prefix** (المسارات/الطرائق/الأجسام/المخرجات/المصادقة تبقى كما هي تماماً —
# توكن خدمة /validate ومنطق fail-safe محفوظان بايتاً ببايت).
from router_registry import register_routers  # noqa: E402

register_routers(app)
