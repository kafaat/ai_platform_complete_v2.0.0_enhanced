"""SAHOOL v9.1.0 — services/agriai-engine/main.py
Agricultural AI Engine — crop recommendations and yield optimization.

المنطق كلّه في وحدات صرفة (بلا FastAPI) قابلة للاختبار في طبقة الوحدات:
  evidence_bundle · replay · wofost_adapter · profit_planner
المعالِجات هنا رفيعة: تجميع أدلّة ⇒ محاكاة ⇒ تخطيط ربح ⇒ توصية مع بصمتَي أدلّة/إعادة.
"""

import logging
import os
import sys
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from pydantic import BaseModel, Field

# مجلّد الخدمة في مسار الاستيراد كي تعمل الوحدات الصرفة (والاختبارات تحمّل main عبر spec).
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import agronomic_context as ac  # noqa: E402
import evidence_bundle as eb  # noqa: E402
import profit_planner as pp  # noqa: E402
import replay as rp  # noqa: E402
import wofost_adapter as wa  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format='{"time":"%(asctime)s","svc":"agriai","level":"%(levelname)s","msg":"%(message)s"}',
)
logger = logging.getLogger("agriai-engine")

VERSION = "10.0.0"
STRICT_AGRONOMIC_CONTEXT = os.getenv(
    "AGRIAI_STRICT_CONTEXT",
    "1" if os.getenv("SAHOOL_ENV", "development").lower() == "production" else "0",
) not in ("0", "false", "False", "")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("✅ agriai-engine started")
    yield
    logger.info("agriai-engine stopped")


app = FastAPI(title="SAHOOL AgriAI Engine", version=VERSION, lifespan=lifespan)


@app.get("/healthz")
async def healthz():
    return {"status": "alive", "service": "agriai-engine", "version": VERSION}


@app.get("/health", include_in_schema=False)
async def legacy_health():
    return await healthz()


@app.get("/readyz")
async def readyz():
    # في وضع الإنتاج، الجاهزيّة العلميّة تتطلّب مساراً **مُثبَتاً تكامليّاً** لا مجرّد توفّر
    # مكتبة pcse (بُناة الموفِّر أقلّاب حتى إكمال التكامل — SIM_PCSE_INTEGRATION_VERIFIED).
    # خارج الإنتاج تبقى الخدمة حوسبةً صرفةً جاهزةً بصدق مع وسم حالة المسار العلميّ.
    production_mode = os.getenv("AGRIAI_PRODUCTION_MODE", "0").lower() in {"1", "true", "yes", "on"}
    sci = wa.scientific_path_status()
    ready = (not production_mode) or sci["scientific_ready"]
    if sci["scientific_ready"]:
        pcse_state = "ready"
    elif production_mode:
        pcse_state = "verified_missing"  # مكتبة قد تكون متاحة لكن التكامل غير مُثبَت
    else:
        pcse_state = "optional_unverified"
    return {
        "status": "ready" if ready else "not_ready",
        "service": "agriai-engine",
        "ready": ready,
        "implemented_runtime": True,
        "runtime_mode": "pcse-required" if production_mode else "development-compatible",
        "scientific_path": sci,
        "dependencies": {"pcse": pcse_state},
    }


@app.get("/metrics")
async def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


# Runtime identity is read from a build-time generated, read-only image file.
# Mutable runtime environment values are deliberately not trusted.
@app.get("/runtime-identity", include_in_schema=True)
def runtime_evidence_identity():
    from shared.runtime_identity import load_build_identity

    return load_build_identity("agriai-engine")


# ── نماذج التحقّق ──


class EvidenceItemIn(BaseModel):
    """بند دليل مُصنَّف — strength ضمن هرميّة Lab>IoT>Weather>Satellite>RAG/KG."""

    source: str
    kind: str
    value: Any = None
    unit: str | None = None
    observed_at: str | None = None
    strength: str


class CandidateIn(BaseModel):
    """مرشّح محصول: بارامترات المحصول + سعر + بنود كلفة."""

    name: str
    crop: dict[str, Any] = Field(default_factory=dict)
    price_per_kg: float = 0.0
    costs: dict[str, Any] = Field(default_factory=dict)


class RecommendRequest(BaseModel):
    """طلب توصية — يقود خطّ الأنابيب كاملاً (أدلّة ⇒ محاكاة ⇒ ربح)."""

    field_id: str = ""
    crop: str = "wheat"
    ndvi: float = Field(0.5, ge=-1.0, le=1.0)
    soil_ph: float = Field(7.0, ge=0, le=14)
    evidence: list[EvidenceItemIn] = Field(default_factory=list)
    candidates: list[CandidateIn] = Field(default_factory=list)
    weather: dict[str, Any] = Field(default_factory=dict)
    soil: dict[str, Any] = Field(default_factory=dict)
    agromanagement: dict[str, Any] = Field(default_factory=dict)
    agronomic_context: dict[str, Any] = Field(default_factory=dict)


class SimulateRequest(BaseModel):
    crop: dict[str, Any] = Field(default_factory=dict)
    weather: dict[str, Any] = Field(default_factory=dict)
    soil: dict[str, Any] = Field(default_factory=dict)
    agromanagement: dict[str, Any] = Field(default_factory=dict)
    agronomic_context: dict[str, Any] = Field(default_factory=dict)


class PlanRequest(BaseModel):
    candidates: list[CandidateIn] = Field(default_factory=list)
    weather: dict[str, Any] = Field(default_factory=dict)
    soil: dict[str, Any] = Field(default_factory=dict)
    agromanagement: dict[str, Any] = Field(default_factory=dict)
    evidence: list[EvidenceItemIn] = Field(default_factory=list)
    agronomic_context: dict[str, Any] = Field(default_factory=dict)


class ReplayVerifyRequest(BaseModel):
    inputs: dict[str, Any] = Field(default_factory=dict)
    prior_hash: str
    engine_version: str | None = None


AGENT_TOKEN = os.getenv("SAHOOL_AGENT_TOKEN", "")


def _require_service_token(x_agent_token: str = Header(None)) -> None:
    if not AGENT_TOKEN:
        raise HTTPException(503, "SAHOOL_AGENT_TOKEN غير مضبوط — معطّل بأمان")
    if x_agent_token != AGENT_TOKEN:
        raise HTTPException(401, "توكن خدمة غير صالح")


# ── مساعدات رفيعة تربط النماذج بالوحدات الصرفة ──


def _validated_context(context: dict[str, Any]) -> dict[str, Any]:
    result = ac.validate_context(context, strict=STRICT_AGRONOMIC_CONTEXT)
    if STRICT_AGRONOMIC_CONTEXT and not result["complete"]:
        raise HTTPException(422, {"error": "agronomic_context_incomplete", **result})
    return result


def _context_inputs(
    context: dict[str, Any], crop: dict, weather: dict, soil: dict, management: dict
):
    if not context:
        return crop, weather, soil, management
    ccrop, cweather, csoil, cmanagement = ac.normalized_engine_inputs(context)
    return ccrop or crop, cweather or weather, csoil or soil, cmanagement or management


def _build_bundle(
    req_evidence: list[EvidenceItemIn], *, ndvi: float | None, soil_ph: float | None
) -> dict[str, Any]:
    """يبني حزمة أدلّة قانونيّة من الأدلّة الصريحة + مشتقّات (NDVI/soil_ph) إن وُجدت."""
    items: list[dict[str, Any]] = []
    for ev in req_evidence:
        items.append(
            eb.make_evidence_item(
                source=ev.source,
                kind=ev.kind,
                value=ev.value,
                unit=ev.unit,
                observed_at=ev.observed_at,
                strength=ev.strength,
            )
        )
    if ndvi is not None:
        items.append(
            eb.make_evidence_item(
                source="satellite", kind="ndvi", value=ndvi, unit="index", strength="satellite"
            )
        )
    if soil_ph is not None:
        items.append(
            eb.make_evidence_item(
                source="lab", kind="soil_ph", value=soil_ph, unit="pH", strength="lab"
            )
        )
    return eb.assemble_bundle(items)


def _candidates_to_plan(
    candidates: list[CandidateIn],
    weather: dict[str, Any],
    soil: dict[str, Any],
    agromanagement: dict[str, Any],
) -> list[dict[str, Any]]:
    """يشغّل المُحوِّل لكلّ مرشّح ويبني مدخلات المُخطِّط (اسم/غلّة/سعر/كلفة)."""
    plan_inputs: list[dict[str, Any]] = []
    for c in candidates:
        sim = wa.simulate(crop=c.crop, weather=weather, soil=soil, agromanagement=agromanagement)
        plan_inputs.append(
            {
                "name": c.name,
                "yield_kg_ha": sim["yield_kg_ha"],
                "price_per_kg": c.price_per_kg,
                "costs": c.costs,
                "provenance": sim["provenance"],
            }
        )
    return plan_inputs


@app.post("/v1/recommend")
async def recommend(req: RecommendRequest, x_agent_token: str = Header(None)):
    """توصية مُدقَّقة: أدلّة ⇒ محاكاة ⇒ تخطيط ربح، مع بصمتَي evidence_hash + replay_hash."""
    _require_service_token(x_agent_token)

    context_validation = _validated_context(req.agronomic_context)
    crop_input, weather_input, soil_input, management_input = _context_inputs(
        req.agronomic_context, {}, req.weather, req.soil, req.agromanagement
    )
    veg = (req.agronomic_context.get("vegetation_snapshot") or {}) if req.agronomic_context else {}
    ndvi_item = (veg.get("indices") or {}).get("ndvi") or {}
    ndvi_value = ndvi_item.get("value", req.ndvi)
    soil_ph_value = (
        soil_input.get("ph", req.soil_ph) if isinstance(soil_input, dict) else req.soil_ph
    )
    bundle = _build_bundle(req.evidence, ndvi=ndvi_value, soil_ph=soil_ph_value)
    evidence_hash = eb.bundle_hash(bundle)
    confidence = eb.compose_confidence(bundle["items"])

    # مرشّحون صريحون أو مرشّح واحد افتراضيّ من req.crop (fail-closed: نُصرّح بالكفاية).
    candidates = req.candidates or [CandidateIn(name=req.crop, crop={}, price_per_kg=0.0, costs={})]
    plan_inputs = _candidates_to_plan(candidates, weather_input, soil_input, management_input)
    plan = pp.plan_profit(plan_inputs, evidence_hash=evidence_hash)

    # مدخلات إعادة التشغيل: قانونيّة وخالية من الطوابع الحيّة.
    replay_inputs = {
        "field_id": req.field_id,
        "evidence_bundle": bundle,
        "candidates": plan_inputs,
        "weather": weather_input,
        "soil": soil_input,
        "agromanagement": management_input,
        "agronomic_context": req.agronomic_context,
        "agronomic_context_hash": context_validation["context_hash"],
    }
    envelope = rp.build_envelope(replay_inputs, {"plan": plan}, evidence_hash=evidence_hash)

    evidence_sufficient = bool(bundle["items"])
    notes = []
    if not evidence_sufficient:
        notes.append("لا أدلّة كافية — الثقة منخفضة عمداً (fail-closed)")

    return {
        "field_id": req.field_id,
        "evidence_hash": evidence_hash,
        "replay_hash": envelope["replay_hash"],
        "engine_version": envelope["engine_version"],
        "evidence_sufficient": evidence_sufficient,
        "confidence": confidence,
        "agronomic_context_validation": context_validation,
        "vegetation_snapshot_hash": veg.get("snapshot_hash"),
        "plan": plan,
        "recommendation": {
            "crop": plan["best"],
            "expected_profit": plan["best_expected_profit"],
        },
        "notes": notes,
    }


@app.post("/v1/simulate")
async def simulate(req: SimulateRequest, x_agent_token: str = Header(None)):
    """محاكاة غلّة/كتلة حيويّة/ماء عبر مُحوِّل PCSE/WOFOST (أو البديل الحتميّ)."""
    _require_service_token(x_agent_token)
    context_validation = _validated_context(req.agronomic_context)
    crop, weather, soil, management = _context_inputs(
        req.agronomic_context, req.crop, req.weather, req.soil, req.agromanagement
    )
    result = wa.simulate(crop=crop, weather=weather, soil=soil, agromanagement=management)
    result["agronomic_context_validation"] = context_validation
    return result


@app.post("/v1/plan")
async def plan(req: PlanRequest, x_agent_token: str = Header(None)):
    """خطّة ربح مرتّبة من مرشّحين، مع بصمة حزمة الأدلّة الحاكمة."""
    _require_service_token(x_agent_token)
    context_validation = _validated_context(req.agronomic_context)
    crop, weather, soil, management = _context_inputs(
        req.agronomic_context, {}, req.weather, req.soil, req.agromanagement
    )
    bundle = _build_bundle(req.evidence, ndvi=None, soil_ph=None)
    evidence_hash = eb.bundle_hash(bundle)
    plan_inputs = _candidates_to_plan(req.candidates, weather, soil, management)
    result = pp.plan_profit(plan_inputs, evidence_hash=evidence_hash)
    result["agronomic_context_validation"] = context_validation
    return result


@app.post("/v1/replay/verify")
async def replay_verify(req: ReplayVerifyRequest, x_agent_token: str = Header(None)):
    """يتحقّق من حتميّة إعادة التشغيل: هل تُعيد المدخلاتُ إنتاجَ البصمة السابقة؟"""
    _require_service_token(x_agent_token)
    kwargs = {"engine_version": req.engine_version} if req.engine_version else {}
    ok = rp.verify_replay(req.inputs, req.prior_hash, **kwargs)
    return {
        "verified": ok,
        "recomputed_hash": rp.compute_replay_hash(req.inputs, **kwargs),
        "prior_hash": req.prior_hash,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
