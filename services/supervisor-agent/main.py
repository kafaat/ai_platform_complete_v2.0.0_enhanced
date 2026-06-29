#!/usr/bin/env python3
"""
SAHOOL Supervisor Agent — Hybrid Skills + Hierarchical Routing
"""

import logging
import os
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any, Optional

from fastapi import Depends, FastAPI, HTTPException
from fastapi.security import HTTPBearer
from mcp_client import MCPClient
from pydantic import BaseModel, Field
from router import HierarchicalRouter
from skills.advisory_skill import AdvisorySkill
from skills.crop_model_skill import CropModelSkill
from skills.market_skill import MarketSkill
from skills.remote_sensing_skill import RemoteSensingSkill
from tool_contracts import (
    ExecutionJournal,
    ToolRegistry,
    bootstrap_default_tools,
)

# تسجيل منظّم موحّد (JSON) — طبقة التنسيق الحرجة تستحقّ رؤية كاملة.
try:
    from shared.logging_config import setup_logging

    logger = setup_logging("supervisor-agent")
except ImportError:
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger("supervisor-agent")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # بدء التشغيل
    logger.info("بدء supervisor-agent")
    yield
    # الإيقاف: أغلق عملاء httpx لتجنّب تسرّب الاتّصالات (async resource leak)
    try:
        await mcp_client.close()
        logger.info("أُغلقت عملاء MCP بنظافة")
    except Exception as e:  # noqa: BLE001
        logger.warning("تعذّر إغلاق عملاء MCP: %s", type(e).__name__)


app = FastAPI(title="SAHOOL Supervisor Agent", version="2026.1", lifespan=lifespan)
security = HTTPBearer(auto_error=False)
# المُصدِرون الداخليّون المسموح بهم — يُفرَض بعد فكّ التوكن (تدقيق B: iss لم يُفحَص).
_ALLOWED_ISS = {"sahool-auth", "sahool-platform"}

mcp_client = MCPClient(
    servers={
        "sentinel-hub": os.getenv(
            "MCP_SENTINEL_HUB_URL", "http://sahool-sentinel-hub-mcp:8000/mcp/v1"
        ),
        "weather": os.getenv("MCP_WEATHER_URL", "http://sahool-weather-mcp:8000/mcp/v1"),
        "wofost": os.getenv("MCP_WOFOST_URL", "http://sahool-wofost-mcp:8000/mcp/v1"),
        "market": os.getenv("MCP_MARKET_URL", "http://sahool-market-mcp:8000/mcp/v1"),
    },
    token=os.getenv("SAHOOL_AGENT_TOKEN", ""),
)

# بوّابة القرار المركزيّة — التوصيات تمرّ عبرها (حَوكمة موحّدة)
GUARDRAILS_URL = os.getenv("GUARDRAILS_URL", "http://sahool-guardrails-engine:8000")
# المنصّة — لجلب الحالة القانونيّة للحقل (Canonical Field State) وإرفاقها بسياق
# الحَوكمة، فتمرّ قرارات guardrails عبر مصدر الحقيقة الواحد. نعتمد PLATFORM_SERVICE_URL
# (نفس اسم field_intelligence_adapters) مع PLATFORM_URL توافقاً خلفيّاً.
PLATFORM_URL = os.getenv(
    "PLATFORM_SERVICE_URL", os.getenv("PLATFORM_URL", "http://sahool-platform:8000")
)


async def _fetch_field_state(client, field_id, tenant_id):
    """best-effort: يجلب الحالة القانونيّة للحقل من المنصّة عبر القناة الداخليّة
    (X-Agent-Token + tenant صريح). يُرجِع dict أو None — fail-safe: أيّ تعذّر ⇒
    None فيتابع التحقّق بلا الحالة (لا يكسر مسار الحَوكمة الحاليّ)."""
    if not field_id or not tenant_id:
        return None
    try:
        r = await client.get(
            f"{PLATFORM_URL}/internal/fields/{field_id}/state",
            params={"tenant_id": str(tenant_id)},
            headers={"X-Agent-Token": os.getenv("SAHOOL_AGENT_TOKEN", "")},
        )
        if r.status_code == 200:
            return r.json()
    except Exception:  # noqa: BLE001 — best-effort، لا يكسر الحَوكمة
        return None
    return None


def bind_field_context(context, field_state):
    """يحقن الحالة القانونيّة للحقل في سياق سؤال المستشار (دالّة نقيّة — grounding).

    يقلّل الهلوسة بربط الجواب بمصدر الحقيقة الواحد (Canonical Field State). صدق:
    لا يدهس مفاتيح أرسلها العميل (setdefault)، ولا يلفّق (يكتب المتاح فقط)، ولا يُعدّل
    الأصل. `field_state` dict الحالة (validity/execution_mode/confidence_level/
    remote_sensing/inputs...) أو None ⇒ يُعيد السياق كما هو.
    """
    out = dict(context or {})
    if not field_state:
        return out
    out["field_state"] = field_state
    rs = field_state.get("remote_sensing") or {}
    if rs.get("available") and rs.get("ndvi_mean") is not None:
        out.setdefault("ndvi_mean", rs.get("ndvi_mean"))
    inputs = field_state.get("inputs") or {}
    if inputs.get("weather_age_hours") is not None:
        out.setdefault("weather_age_hours", inputs.get("weather_age_hours"))
    return out


skill_libraries = {
    "remote_sensing": RemoteSensingSkill(mcp_client),
    "crop_model": CropModelSkill(mcp_client),
    "market": MarketSkill(mcp_client),
    "advisory": AdvisorySkill(mcp_client),
}

router = HierarchicalRouter(skill_libraries)


class AgentQuery(BaseModel):
    query: str = Field(..., description="استعلام المزارع/المهندس بالعربية أو الإنجليزية")
    field_id: str | None = None
    user_id: str
    tenant_id: str
    context: dict[str, Any] | None = Field(default_factory=dict)
    preferred_objectives: list[str] = Field(default=["balanced"])


class AgentResponse(BaseModel):
    response_ar: str
    response_en: str | None = None
    structured_data: dict[str, Any] | None = None
    actions_triggered: list[str] = Field(default_factory=list)
    governance: dict[str, Any] | None = None  # قرار البوّابة لو الإجراء قابل للتنفيذ
    confidence: float = Field(..., ge=0, le=1)
    sources: list[str] = Field(default_factory=list)
    processing_time_ms: int


async def _get_current_user(credentials: Optional = Depends(security)):
    if not credentials:
        raise HTTPException(401, "Authentication required")
    import jwt

    secret = os.getenv("JWT_SECRET", "")
    # فشل-مغلق: لا نقبل توكنات بمفتاح فارغ (كان يقبل أيّ توكن مزوّر)
    if len(secret) < 32:
        raise HTTPException(503, "JWT_SECRET غير مضبوط — الخدمة معطّلة بأمان")
    try:
        # RS256 (public key) لو مضبوط، وإلّا HS256 fallback
        _pub = os.getenv("JWT_PUBLIC_KEY", "")
        _vkey = _pub if _pub else secret
        _valg = "RS256" if _pub else "HS256"
        # FIX (اتّساق audience): auth/platform يُصدران aud="sahool" وmcp يتطلّبه.
        # الفكّ بلا audience يرمي InvalidAudienceError ويرفض توكنات auth الصالحة.
        payload = jwt.decode(
            credentials.credentials,
            _vkey,
            algorithms=[_valg],
            audience="sahool",
        )
        # تدقيق B: افرض المُصدِر بعد فكّ ناجح — مُصدِر مجهول ⇒ 401 كتوكن غير صالح.
        if payload.get("iss") not in _ALLOWED_ISS:
            raise ValueError("Invalid token issuer")
        return payload
    except Exception as e:
        # عدم كشف المعلومات: نُرجِع رسالة عامّة للعميل (لا تفاصيل PyJWT الداخليّة
        # كأيّ فحص فشل) حتى لا نُسرّب أيّ مؤشّر يُسهّل التزوير. السبب الحقيقيّ
        # يُسجَّل خادميّاً للمراقبة فقط، مع الحفاظ على سلسلة الاستثناء (from e).
        logger.warning("JWT verification failed: %s", e)
        raise HTTPException(401, "Invalid token") from e


def _degraded_response(
    start_time: datetime, domain: str, reason: str = "circuit_open"
) -> AgentResponse:
    """تدهور لطيف: خدمة MCP خلفيّة متعطّلة (القاطع مفتوح). نُرجِع 200 برسالة
    عربيّة واضحة + وسم `degraded` بدل 500 قاسٍ — المنصّة تبقى مستجيبة والقاطع
    يتعافى تلقائيّاً. الوسم في structured_data يتيح للعميل كشف الحالة وإعادة
    المحاولة. confidence=0 يمنع البناء على بيانات غائبة."""
    elapsed = int((datetime.now(UTC) - start_time).total_seconds() * 1000)
    return AgentResponse(
        response_ar=(
            "خدمة البيانات اللازمة لهذا الطلب متعطّلة مؤقّتاً ونحاول التعافي "
            "تلقائيّاً — يرجى المحاولة بعد قليل."
        ),
        confidence=0.0,
        sources=[],
        structured_data={"status": "degraded", "reason": reason, "domain": domain},
        processing_time_ms=elapsed,
    )


async def _validate_actions_via_guardrails(
    result: dict, query, user_id: str, tenant_id: str
) -> dict:
    """يمرّر إجراءات المهارة عبر Guardrails /validate — حَوكمة كلّ المسارات.

    يحدّد نوع الإجراء من المهارة (تسميد/مبيد/ريّ...) ويمرّره للبوّابة. صدق:
    عند التعذّر، التوصية تبقى استشاريّة موسومة (لا تنفيذ تلقائي، لا فراغ).
    """
    import httpx

    # نوع الإجراء من المهارة (المهارة تحدّده: pesticide/fertilization/...) — حَوكمة
    # فعليّة لا اسميّة: action_data بنية مهيكلة تفهمها الطبقات.
    action_type = result.get("action_type")
    structured = result.get("structured") or {}
    if action_type not in (
        "irrigation",
        "fertilization",
        "pesticide",
        "harvest",
        "contract",
        "investment",
        "loan",
    ):
        # لا نوع صريح + لا بنية → نصيحة معلوماتيّة خالصة، لا تُحكَم (تبويب صحيح)
        if not structured:
            return {
                "allowed": True,
                "overall_risk": "INFORMATIONAL",
                "status": "informational_advice",
                "source": "no-action",
                "note": "نصيحة معلوماتيّة لا إجراء قابل للتنفيذ — لا تحتاج حَوكمة",
            }
        action_type = "irrigation"
    payload = {
        "action_type": action_type,
        "action_data": structured or {"advisory": True},
        "farm_context": {"field_id": getattr(query, "field_id", None)},
        "user_id": user_id or "agent",
        "tenant_id": tenant_id or "",
        "request_source": "agent",
        "auto_approve_low_risk": True,
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            # Canonical Field State: أرفِق الحالة القانونيّة (best-effort) ليحكم
            # guardrails بها — قرار الحَوكمة يمرّ عبر مصدر الحقيقة الواحد.
            _fs = await _fetch_field_state(client, getattr(query, "field_id", None), tenant_id)
            if _fs is not None:
                payload["farm_context"]["field_state"] = _fs
            resp = await client.post(
                f"{GUARDRAILS_URL}/validate",
                json=payload,
                headers={"X-Agent-Token": os.getenv("SAHOOL_AGENT_TOKEN", "")},
            )
            resp.raise_for_status()
            r = resp.json()
        return {
            "allowed": r.get("allowed"),
            "overall_risk": r.get("overall_risk"),
            "requires_human_approval": r.get("requires_human_approval"),
            "approval_workflow_id": r.get("approval_workflow_id"),
            "status": "validated",
            "source": "guardrails-engine",
        }
    except Exception:  # noqa: BLE001 — صدق: استشاريّة موسومة لا فراغ
        return {
            "allowed": None,
            "overall_risk": "UNKNOWN",
            "status": "advisory_pending_validation",
            "source": "guardrails-unavailable",
            "error": "guardrails_unavailable",
            "note": "التوصية استشاريّة — بانتظار التحقّق، لا تُنفَّذ تلقائيّاً",
        }


async def _validate_via_guardrails(
    recommended: dict, rs: dict, cm: dict, query, x_user_id: str = None, trusted_tenant_id: str = ""
) -> dict:
    """يمرّر التوصية عبر Guardrails /validate — البوّابة حاكمة للمسار.

    بدل الاعتماد على رقم الخطر المحلّي في _generate_scenarios، نمرّر التوصية
    للبوّابة المركزيّة (3 طبقات + HITL) لتكون مرجع الحقيقة الوحيد للقرار.
    صدق: tenant من توكن المستخدم المُتحقَّق (لا من جسم الطلب — منع انتحال).
    عند تعذّر الوصول للبوّابة، نُبلّغ بوضوح (لا نتظاهر بموافقة).
    """
    import httpx

    payload = {
        "action_type": "irrigation",  # التوصية أساسها الريّ + التسميد
        "action_data": {
            "irrigation_mult": recommended.get("irrigation_mult"),
            "fertilizer_mult": recommended.get("fertilizer_mult"),
            "water_mm": recommended.get("water_mm"),
            "expected_yield_kg_ha": recommended.get("yield_kg_ha"),
        },
        "farm_context": {
            "field_id": getattr(query, "field_id", None),
            "ndvi": rs.get("ndvi_mean") if isinstance(rs, dict) else None,
            "crop": cm.get("crop") if isinstance(cm, dict) else None,
        },
        "user_id": x_user_id or "agent",
        "tenant_id": trusted_tenant_id or "",  # من التوكن المُتحقَّق لا الجسم
        "request_source": "agent",
        "auto_approve_low_risk": True,
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            # Canonical Field State: أرفِق الحالة القانونيّة (best-effort) ليحكم
            # guardrails بها — قرار الحَوكمة يمرّ عبر مصدر الحقيقة الواحد.
            _fs = await _fetch_field_state(
                client, getattr(query, "field_id", None), trusted_tenant_id
            )
            if _fs is not None:
                payload["farm_context"]["field_state"] = _fs
            resp = await client.post(
                f"{GUARDRAILS_URL}/validate",
                json=payload,
                headers={"X-Agent-Token": os.getenv("SAHOOL_AGENT_TOKEN", "")},
            )
            resp.raise_for_status()
            r = resp.json()
        return {
            "allowed": r.get("allowed"),
            "overall_risk": r.get("overall_risk"),
            "requires_human_approval": r.get("requires_human_approval"),
            "approval_workflow_id": r.get("approval_workflow_id"),
            "source": "guardrails-engine",
        }
    except Exception:  # noqa: BLE001 — صدق: لا نتظاهر بموافقة عند الفشل
        return {
            "allowed": None,
            "overall_risk": "UNKNOWN",
            "source": "guardrails-unavailable",
            "error": "guardrails_unavailable",
            "note": "تعذّر الوصول لبوّابة القرار — لا تُنفَّذ التوصية تلقائيّاً",
        }


def _format_arabic_response(result: dict) -> str:
    if result.get("type") == "ndvi_report":
        return f"""
📊 **تقرير صحة الحقل**

مؤشر NDVI: {result.get("ndvi_mean", "N/A")}
الحالة: {result.get("health_status", "غير معروفة")}

{result.get("recommendation", "")}
""".strip()
    elif result.get("type") == "irrigation_advice":
        return f"""
💧 **توصية الري**

{result.get("advice", "")}

الكمية المقترحة: {result.get("amount_mm", "N/A")} مم
التوقيت: {result.get("timing", "غير محدد")}
""".strip()
    elif result.get("type") == "pest_alert":
        return f"""
🐛 **تنبيه آفات**

{result.get("alert", "")}

الإجراء المقترح: {result.get("action", "")}
""".strip()
    else:
        return result.get("response", "تمت المعالجة بنجاح.")


def _generate_scenarios(rs: dict, cm: dict, mk: dict) -> list[dict]:
    base_yield = cm.get("yield_kg_ha", 2000)
    base_water = cm.get("total_water_mm", 400)
    scenarios = []
    for irr_mult in [0.8, 0.9, 1.0, 1.1, 1.2]:
        for fert_mult in [0.8, 0.9, 1.0, 1.1, 1.2]:
            yield_est = base_yield * (0.7 + 0.3 * irr_mult) * (0.8 + 0.2 * fert_mult)
            water_use = base_water * irr_mult
            cost = water_use * 0.5 + base_yield * fert_mult * 0.1
            profit = yield_est * mk.get("price_yer_kg", 300) / 1000 - cost
            carbon = water_use * 0.1
            scenarios.append(
                {
                    "irrigation_mult": irr_mult,
                    "fertilizer_mult": fert_mult,
                    "yield_kg_ha": round(yield_est, 2),
                    "profit_yer_ha": round(profit, 2),
                    "water_mm": round(water_use, 2),
                    "carbon_kg": round(carbon, 2),
                    "risk": round(abs(1 - irr_mult) * 10 + abs(1 - fert_mult) * 5, 2),
                }
            )
    return scenarios


def _pareto_optimal(scenarios: list[dict], objectives: list[str]) -> list[dict]:
    pareto = []
    for s in scenarios:
        dominated = False
        for other in scenarios:
            if other is s:
                continue
            if all(
                other.get(obj.replace("max_", "").replace("min_", ""), 0)
                >= s.get(obj.replace("max_", "").replace("min_", ""), 0)
                if obj.startswith("max")
                else other.get(obj.replace("max_", "").replace("min_", ""), 0)
                <= s.get(obj.replace("max_", "").replace("min_", ""), 0)
                for obj in objectives
            ):
                dominated = True
                break
        if not dominated:
            pareto.append(s)
    return sorted(pareto, key=lambda x: x["profit_yer_ha"], reverse=True)[:10]


def _select_balanced(pareto: list[dict], objectives: list[str]) -> dict:
    if not pareto:
        return {}
    if objectives == ["balanced"]:
        max_yield = max(p["yield_kg_ha"] for p in pareto)
        max_profit = max(p["profit_yer_ha"] for p in pareto)
        min_water = min(p["water_mm"] for p in pareto)
        best = None
        best_score = -1
        for p in pareto:
            score = (
                0.3 * p["yield_kg_ha"] / max_yield
                + 0.4 * p["profit_yer_ha"] / max_profit
                + 0.3
                * (
                    1
                    - (p["water_mm"] - min_water)
                    / (max(p["water_mm"] for p in pareto) - min_water + 1)
                )
            )
            if score > best_score:
                best_score = score
                best = p
        return best
    primary = objectives[0]
    if primary == "max_yield":
        return max(pareto, key=lambda x: x["yield_kg_ha"])
    elif primary == "max_profit":
        return max(pareto, key=lambda x: x["profit_yer_ha"])
    elif primary == "min_water":
        return min(pareto, key=lambda x: x["water_mm"])
    elif primary == "min_carbon":
        return min(pareto, key=lambda x: x["carbon_kg"])
    return pareto[0]


def _generate_tradeoff_arabic(recommended: dict, pareto: list[dict], objectives: list[str]) -> str:
    if not recommended:
        return "لا توجد بيانات كافية لتحليل المفاضلات."
    better_yield = [p for p in pareto if p["yield_kg_ha"] > recommended["yield_kg_ha"]]
    better_profit = [p for p in pareto if p["profit_yer_ha"] > recommended["profit_yer_ha"]]
    better_water = [p for p in pareto if p["water_mm"] < recommended["water_mm"]]
    explanation = f"""
✅ **الخيار المُوصى به (موازن):**

📈 الإنتاجية: {recommended["yield_kg_ha"]:,} كجم/هكتار
💰 الربح المتوقع: {recommended["profit_yer_ha"]:,} ر.ي/هكتار
💧 استهلاك المياه: {recommended["water_mm"]:,} مم
🌱 البصمة الكربونية: {recommended["carbon_kg"]:,} كجم CO₂

⚖️ **المفاضلات:**
"""
    if better_yield:
        max_y = max(better_yield, key=lambda x: x["yield_kg_ha"])
        explanation += f"• إذا أردت **إنتاجية أقصى** ({max_y['yield_kg_ha']:,} كجم)، فستحتاج {max_y['water_mm']:,} مم مياه (+{max_y['water_mm'] - recommended['water_mm']:.0f} مم)."
    if better_profit:
        max_p = max(better_profit, key=lambda x: x["profit_yer_ha"])
        explanation += f"• إذا أردت **ربحاً أقصى** ({max_p['profit_yer_ha']:,} ر.ي)، فستحتاج استثماراً أعلى في التسميد."
    if better_water:
        min_w = min(better_water, key=lambda x: x["water_mm"])
        explanation += f"• إذا أردت **توفير مياه** ({min_w['water_mm']:,} مم)، فستنخفض الإنتاجية إلى {min_w['yield_kg_ha']:,} كجم."
    explanation += (
        "💡 **التوصية:** الخيار المُوصى به يُوازن بين ربحك واستدامة مزرعتك على المدى الطويل."
    )
    return explanation.strip()


# ─── Tool Contracts + Execution Journal (Operational Semantics) ──
#
# المرجع: AI Orchestration review — "Execution Contract Engine"
# الميزة: كل tool invocation يمرّ بـcapability check + input validation +
#         timeout enforcement + journal recording.

_tool_registry = ToolRegistry()
_execution_journal = ExecutionJournal()
bootstrap_default_tools(_tool_registry)


# تسجيل تلقائيّ لراوترات routers/ في **نهاية** الملف بعد app وكلّ التبعيّات
# المشتركة — يحلّ الاستيراد الدائريّ (وحدات routers تستورد رموزاً من main).
from router_registry import register_routers  # noqa: E402

register_routers(app)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8096)
