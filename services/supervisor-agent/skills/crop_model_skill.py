#!/usr/bin/env python3
"""
Crop Model Skill Library for SAHOOL Supervisor Agent
Handles: محاكاة الغلّة (عبر agriai-engine) · جدولة الريّ · توصيات التسميد

محاكاة الغلّة (``simulate_current``) تُفوَّض إلى مالكها ``agriai-engine`` عبر
``POST {AGRIAI_ENGINE_URL}/v1/simulate`` بتوكن الخدمة ``X-Agent-Token`` — لا إلى خادم
MCP ``wofost``. كانت المهارة تنادي أداة MCP ``run_wofost_simulation`` التي تردّ 501 بالتصميم
(``services/mcp_servers/wofost_server.py``: لا محرّك حقيقيّ هناك)، فكان مسار «توقّع المحصول»
ميتاً دائماً بينما المحرّك الحقيقيّ (PCSE) وبديله الحتميّ يعيشان في agriai.

ملاحظة صدق: المُخرَج يحمل ``provenance`` كما أعادها agriai حرفيّاً، ويُسمّي المحرّك منه:
``pcse_wofost_uncalibrated`` ⇒ PCSE/WOFOST 7.2 غير مُعايَر · ``deterministic_fallback`` ⇒
بديل حتميّ (قانون الحدّ الأدنى) **ليس WOFOST**. وسمٌ غائب أو مجهول ⇒ لا رقم (``unavailable``)
بدل التخمين. مسار PCSE يعمل الآن دون شبكة طرفاً لطرف (``wofost_adapter._pcse_run`` +
``pcse_inputs``)، لكنّ ``SIM_PCSE_ENABLED`` مطفأة افتراضاً (قرار المالك)، فالمُجاب في النشر ما زال
البديل الحتميّ حتى تُشعَل — ويُقال المحرّك للمستخدم في نصّ الردّ نفسه، ومعه افتراضات PCSE المُعلَنة
(تربة افتراضيّة، رطوبة ابتدائيّة، ريّ غير مُعلَن) من ``diagnostics.defaults_applied``.
"""

import asyncio
import math
import os
from typing import Any
from urllib.parse import quote

import httpx
from mcp_client import MCPClient
from pydantic import BaseModel, ConfigDict, Field, ValidationError


class CropModelSkill:
    """
    Domain skill for crop modeling and agronomic recommendations.
    """

    def __init__(self, mcp_client: MCPClient):
        # يبقى العميل لتوقيع المُنشِئ الموحّد بين المهارات؛ المحاكاة لم تعد تمرّ عبر MCP.
        self.mcp = mcp_client

    async def execute(  # ✅ timeout + fallback added
        self,
        intent: str,
        query: str = "",
        field_id: str | None = None,
        user_id: str = "",
        tenant_id: str = "",
        context: dict[str, Any] = None,
        objectives: list[str] = None,
    ) -> dict[str, Any]:

        if intent == "simulate_current":
            return await self._simulate_via_agriai(context or {})

        elif intent == "irrigation_advice":
            return await self._irrigation_advice(field_id, context or {})

        elif intent == "fertilizer_advice":
            # No approved soil-specific prescription is exposed by this skill yet.
            # Crop/stage templates cannot establish a safe nutrient dose.
            return _unavailable(
                "fertilizer_prescription_required",
                "توصية التسميد الكمية غير متاحة: يلزم تحليل تربة معتمد ووصفة تسميد مراجعة للحقل.",
            )

        else:
            return {
                "type": "error",
                "response": f"نوعية استعلام نموذج المحصول غير معروفة: {intent}",
            }

    async def _simulate_via_agriai(self, context: dict) -> dict:
        crop = str(context.get("crop") or "").strip().lower()
        if not crop:
            # كان الافتراض الصامت "wheat" + تاريخ زرع 2026-01-15 + تربة medium: مدخلات مُختلَقة.
            return _unavailable("crop_required", "لا يمكن محاكاة الغلّة دون تحديد المحصول صراحةً.")
        weather = _dict(context.get("weather"))
        agronomic_context = _dict(context.get("agronomic_context"))
        if not (
            _has_weather(weather) or _has_weather(_dict(agronomic_context.get("weather_snapshot")))
        ):
            # البديل الحتميّ يُعيد غلّة 0 من طقس غائب (GDD=0) — رقمٌ بلا دليل لا يُعرَض كتوقّع.
            return _unavailable(
                "crop_model_weather_required",
                "لا يمكن محاكاة الغلّة دون بيانات طقس للموسم (درجات حراريّة تراكميّة أو سلسلة يوميّة).",
            )
        management = _dict(context.get("agromanagement"))
        if context.get("planting_date") and "planting_date" not in management:
            management["planting_date"] = context["planting_date"]
        payload = {
            "crop": {"name": crop},
            "weather": weather,
            "soil": _dict(context.get("soil")),
            "agromanagement": management,
            "agronomic_context": agronomic_context,
        }
        agriai = os.getenv("AGRIAI_ENGINE_URL", "http://sahool-agriai-engine:8000").rstrip("/")
        # تعذّر الوصول/مهلة/5xx غير مُصنَّف ⇒ يُرفَع httpx.HTTPError فيُحوّله المسار إلى ردّ
        # ``degraded`` (confidence=0، بلا أرقام) — نفس عقد الريّ أعلاه، لا رقم احتياطيّ.
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(
                f"{agriai}/v1/simulate",
                json=payload,
                headers={"X-Agent-Token": os.getenv("SAHOOL_AGENT_TOKEN", "")},
            )
        if resp.status_code in (422, 503):
            detail = _detail(resp)
            if resp.status_code == 503 and detail.get("error") == "simulation_unavailable":
                out = _unavailable(
                    "crop_simulation_unavailable",
                    "محرّك محاكاة المحصول غير متاح حالياً (فشل مُغلَق في agriai) — لا تقدير للغلّة.",
                )
                out["structured"]["engine_reason"] = str(detail.get("reason") or "")[:200]
                return out
            if resp.status_code == 422:
                out = _unavailable(
                    "crop_model_inputs_rejected",
                    "رفض محرّك المحاكاة مدخلات الحقل (سياق زراعيّ ناقص أو غير صالح) — لا تقدير للغلّة.",
                )
                # بُناة PCSE يُسمّون النقص (``weather_day_missing:3:vapour_pressure_hpa|...``) — يُنقَل
                # الرمز كما في 503، فلا يُختزَل «ما الذي ينقص» إلى «مرفوض» بلا سبب.
                out["structured"]["engine_reason"] = str(detail.get("reason") or "")[:200]
                if detail.get("detail"):
                    out["structured"]["engine_detail"] = str(detail["detail"])[:200]
                return out
        resp.raise_for_status()
        return _simulation_result(crop, resp.json())

    async def _irrigation_advice(self, field_id: str | None, context: dict) -> dict:
        state = context.get("field_state") or {}
        bearer = context.get("_platform_bearer")
        if not field_id or not bearer or state.get("validity") != "valid":
            return _unavailable(
                "canonical_field_evidence_required",
                "لا يمكن تحديد كمية ري آمنة دون حقل محدد وبيانات حقل صالحة من المنصة.",
            )
        platform = os.getenv(
            "PLATFORM_SERVICE_URL", os.getenv("PLATFORM_URL", "http://sahool-platform:8000")
        ).rstrip("/")
        field_path = f"{platform}/api/v1/fields/{quote(str(field_id), safe='')}"
        # Delegate all ET0/Kc/rain calculations to the existing owner. Never
        # interpret missing observations as dry weather or invent soil moisture.
        async with httpx.AsyncClient(timeout=20.0) as client:
            headers = {"Authorization": f"Bearer {bearer}"}
            async with asyncio.timeout(20.0):
                advice_resp, field_resp = await asyncio.gather(
                    client.get(f"{field_path}/weather/irrigation-advice", headers=headers),
                    client.get(field_path, headers=headers),
                )
            advice_resp.raise_for_status()
            field_resp.raise_for_status()
            advice, field = advice_resp.json(), field_resp.json()
        try:
            if not isinstance(advice, dict) or not isinstance(field, dict):
                raise ValueError("invalid canonical payload")
            if advice.get("field_id") != field_id or field.get("field_id") != field_id:
                raise ValueError("field identity mismatch")
            evidence = _IrrigationInputs(
                water_mm=advice.get("recommended_mm"),
                area_ha=field.get("area_ha"),
                irrigation_efficiency_pct=field.get("irrigation_efficiency_pct"),
                field_id=field_id,
            )
            # The owner's recommendation is NET crop demand. Withdrawal limits
            # govern GROSS water: preserve both and apply only explicit canonical
            # field efficiency (ADR-0032); never assume an irrigation system's efficiency.
            net_water_m3 = evidence.water_mm * evidence.area_ha * 10
            action = IrrigationAction(
                **evidence.model_dump(),
                net_water_m3=net_water_m3,
                water_m3=net_water_m3 / evidence.irrigation_efficiency_pct * 100,
            )
        except (KeyError, TypeError, ValueError) as exc:
            if isinstance(exc, ValidationError) and any(
                error["loc"] == ("irrigation_efficiency_pct",) for error in exc.errors()
            ):
                return _unavailable(
                    "canonical_irrigation_efficiency_required",
                    "كفاءة الري غير متاحة أو غير صالحة؛ لا يمكن حساب حجم السحب الإجمالي للتحقق من حدود المياه.",
                )
            return _unavailable(
                "canonical_irrigation_incomplete",
                "بيانات توصية الري أو مساحة الحقل غير مكتملة؛ لا يمكن إصدار كمية آمنة.",
            )
        return {
            "type": "irrigation_advice",
            "advice": advice.get("rationale_ar", ""),
            "amount_mm": action.water_mm,
            "timing": advice.get("timing_ar", "غير محدد"),
            "actionable": True,
            "action_type": "irrigation",
            "structured": action.model_dump(),
            "farm_context": {
                "field_id": field_id,
                "field_area_ha": action.area_ha,
                "water_source": field.get("water_source"),
                "field_state": state,
            },
            "sources": [
                "SAHOOL field irrigation advice",
                advice.get("source") or "weather-service",
            ],
        }


class _IrrigationInputs(BaseModel):
    """Explicit canonical inputs; missing efficiency cannot become full efficiency."""

    model_config = ConfigDict(strict=True, allow_inf_nan=False, extra="forbid")
    field_id: str
    water_mm: float = Field(ge=0, description="Net crop demand in mm")
    area_ha: float = Field(gt=0)
    irrigation_efficiency_pct: float = Field(gt=0, le=100)


class IrrigationAction(_IrrigationInputs):
    """Keep net crop demand separate from gross withdrawal sent to governance."""

    net_water_m3: float = Field(ge=0)
    water_m3: float = Field(ge=0, description="Gross withdrawal volume in m3")


def _unavailable(code: str, message: str) -> dict:
    return {
        "type": "unavailable",
        "response": message,
        "actionable": False,
        "structured": {"status": "unavailable", "reason": code},
        "sources": [],
    }


# وسم agriai ⇒ هويّة المحرّك. المفاتيح هي ``status_enum`` في
# ``services/agriai-engine/simulation_capability.py`` (عدا ``simulation_unavailable`` = 503).
# ``water_use`` بالملّيمتر في المحرّكين: كان ``_pcse_run`` يُعيد CTRAT بالسنتيمتر فيُضرَب هنا ×10؛
# صار المُحوِّل يُحوّله (عقد المخطّط)، وضربٌ ثانٍ هنا كان سيُضخّم ماء PCSE عشرة أضعاف.
_ENGINES: dict[str, dict[str, Any]] = {
    "pcse_wofost_uncalibrated": {
        "engine": "pcse_wofost72_wlp_fd",
        "label_ar": "PCSE/WOFOST 7.2 (إنتاج محدود بالمياه) — غير مُعايَر",
        "source": "PCSE Wofost72_WLP_FD (uncalibrated)",
        "water_to_mm": 1.0,
        "yield_basis_ar": " (مادّة جافّة للأعضاء المخزِّنة)",  # TWSO — لا رطوبة مفترَضة
    },
    "deterministic_fallback": {
        "engine": "deterministic_fallback",
        "label_ar": "بديل حتميّ (قانون الحدّ الأدنى: حرارة × ماء) — ليس WOFOST ولا PCSE",
        "source": "agriai deterministic fallback (not WOFOST)",
        "water_to_mm": 1.0,
        "yield_basis_ar": "",
    },
}

# ``diagnostics.defaults_applied`` في مُخرَج PCSE ⇒ عبارة للمستخدم. ما لم يُسَمَّ هنا يبقى في
# ``structured.defaults_applied`` كما هو (أنغستروم مثلاً: تقنيّ، أثره على تبخّر التربة وحده).
_DEFAULT_LABELS_AR: tuple[tuple[str, str], ...] = (
    ("soil.", "تربة افتراضيّة (EC3-medium fine) لا تربة الحقل"),
    ("site.WAV", "رطوبة ابتدائيّة مُفترَضة عند السعة الحقليّة"),
    ("irrigation.none_declared", "بلا ريّ مُعلَن (بعليّ)"),
)


def _declared_defaults(diagnostics: dict) -> tuple[list[str], str]:
    applied = [str(d) for d in diagnostics.get("defaults_applied") or [] if isinstance(d, str)]
    labels = [
        label for prefix, label in _DEFAULT_LABELS_AR if any(d.startswith(prefix) for d in applied)
    ]
    return applied, (f" افتراضات مُعلَنة: {'، '.join(labels)}." if labels else "")


def _simulation_result(crop: str, data: Any) -> dict:
    data = data if isinstance(data, dict) else {}
    provenance = data.get("provenance")
    engine = _ENGINES.get(provenance) if isinstance(provenance, str) else None
    yield_kg_ha = _finite(data.get("yield_kg_ha"))
    if engine is None or yield_kg_ha is None:
        # لا تخمين للمحرّك في المهارة: رقم بلا وسم معروف لا يُعرَض.
        out = _unavailable(
            "crop_model_provenance_unrecognized",
            "أعاد محرّك المحاكاة نتيجة بلا مصدر محرّك معروف — لا تُعرَض كتقدير.",
        )
        out["structured"]["provenance"] = provenance if isinstance(provenance, str) else None
        return out
    water = _finite(data.get("water_use"))
    interval = _dict(data.get("yield_interval"))
    band = ""
    low, high = _finite(interval.get("low_kg_ha")), _finite(interval.get("high_kg_ha"))
    if low is not None and high is not None:
        band = f" (نطاق {low:,.0f}–{high:,.0f}، ثقة {interval.get('confidence', 'غير محدّدة')})"
    diagnostics = _dict(data.get("diagnostics"))
    defaults_applied, defaults_text = _declared_defaults(diagnostics)
    structured = {
        "status": "ok",
        "engine": engine["engine"],
        "provenance": provenance,
        "calibrated": False,  # لا محرّك في agriai مُعايَر قبل SIM-GOLDEN-01
        "yield_kg_ha": yield_kg_ha,
        "yield_interval": interval or None,
        "defaults_applied": defaults_applied,
    }
    return {
        "type": "crop_simulation",
        "response": (
            f"محاكاة {crop}: غلّة تقديريّة {yield_kg_ha:,.0f} كغ/هكتار"
            f"{engine['yield_basis_ar']}{band}. المحرّك: {engine['label_ar']}.{defaults_text}"
        ),
        "crop": crop,
        "engine": engine["engine"],
        "engine_label_ar": engine["label_ar"],
        "provenance": provenance,
        "calibrated": False,
        "yield_kg_ha": yield_kg_ha,
        "biomass_kg_ha": _finite(data.get("biomass")),
        "total_water_mm": None if water is None else water * engine["water_to_mm"],
        "stages": data.get("stages") if isinstance(data.get("stages"), list) else [],
        "yield_interval": interval or None,
        "diagnostics": diagnostics,
        "actionable": False,
        "structured": structured,
        "sources": ["agriai-engine /v1/simulate", engine["source"]],
    }


def _dict(value: Any) -> dict:
    return dict(value) if isinstance(value, dict) else {}


def _has_weather(weather: dict) -> bool:
    return weather.get("gdd") is not None or bool(weather.get("daily"))


def _finite(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value) if math.isfinite(value) else None


def _detail(resp: httpx.Response) -> dict:
    try:
        body = resp.json()
    except ValueError:
        return {}
    return _dict(body.get("detail")) if isinstance(body, dict) else {}
