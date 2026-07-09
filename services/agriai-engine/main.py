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

import evidence_bundle as eb  # noqa: E402
import profit_planner as pp  # noqa: E402
import replay as rp  # noqa: E402
import wofost_adapter as wa  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format='{"time":"%(asctime)s","svc":"agriai","level":"%(levelname)s","msg":"%(message)s"}',
)
logger = logging.getLogger("agriai-engine")

VERSION = "9.1.0"


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
    # بلا تبعيّات خارجيّة قصداً: حوسبة صرفة (توصيات/تحسين غلّة بلا قاعدة/Redis/NATS).
    # لا شيء ننتظره ⇒ جاهز دائماً بصدق.
    return {"status": "ready", "service": "agriai-engine", "implemented_runtime": True}


@app.get("/metrics")
async def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


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


class SimulateRequest(BaseModel):
    crop: dict[str, Any] = Field(default_factory=dict)
    weather: dict[str, Any] = Field(default_factory=dict)
    soil: dict[str, Any] = Field(default_factory=dict)
    agromanagement: dict[str, Any] = Field(default_factory=dict)


class PlanRequest(BaseModel):
    candidates: list[CandidateIn] = Field(default_factory=list)
    weather: dict[str, Any] = Field(default_factory=dict)
    soil: dict[str, Any] = Field(default_factory=dict)
    agromanagement: dict[str, Any] = Field(default_factory=dict)
    evidence: list[EvidenceItemIn] = Field(default_factory=list)


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


@app.post("/recommend")
async def recommend(req: RecommendRequest, x_agent_token: str = Header(None)):
    """توصية مُدقَّقة: أدلّة ⇒ محاكاة ⇒ تخطيط ربح، مع بصمتَي evidence_hash + replay_hash."""
    _require_service_token(x_agent_token)

    bundle = _build_bundle(req.evidence, ndvi=req.ndvi, soil_ph=req.soil_ph)
    evidence_hash = eb.bundle_hash(bundle)
    confidence = eb.compose_confidence(bundle["items"])

    # مرشّحون صريحون أو مرشّح واحد افتراضيّ من req.crop (fail-closed: نُصرّح بالكفاية).
    candidates = req.candidates or [CandidateIn(name=req.crop, crop={}, price_per_kg=0.0, costs={})]
    plan_inputs = _candidates_to_plan(candidates, req.weather, req.soil, req.agromanagement)
    plan = pp.plan_profit(plan_inputs, evidence_hash=evidence_hash)

    # مدخلات إعادة التشغيل: قانونيّة وخالية من الطوابع الحيّة.
    replay_inputs = {
        "field_id": req.field_id,
        "evidence_bundle": bundle,
        "candidates": plan_inputs,
        "weather": req.weather,
        "soil": req.soil,
        "agromanagement": req.agromanagement,
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
        "plan": plan,
        "recommendation": {
            "crop": plan["best"],
            "expected_profit": plan["best_expected_profit"],
        },
        "notes": notes,
    }


@app.post("/simulate")
async def simulate(req: SimulateRequest, x_agent_token: str = Header(None)):
    """محاكاة غلّة/كتلة حيويّة/ماء عبر مُحوِّل PCSE/WOFOST (أو البديل الحتميّ)."""
    _require_service_token(x_agent_token)
    return wa.simulate(
        crop=req.crop, weather=req.weather, soil=req.soil, agromanagement=req.agromanagement
    )


@app.post("/plan")
async def plan(req: PlanRequest, x_agent_token: str = Header(None)):
    """خطّة ربح مرتّبة من مرشّحين، مع بصمة حزمة الأدلّة الحاكمة."""
    _require_service_token(x_agent_token)
    bundle = _build_bundle(req.evidence, ndvi=None, soil_ph=None)
    evidence_hash = eb.bundle_hash(bundle)
    plan_inputs = _candidates_to_plan(req.candidates, req.weather, req.soil, req.agromanagement)
    return pp.plan_profit(plan_inputs, evidence_hash=evidence_hash)


@app.post("/replay/verify")
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
