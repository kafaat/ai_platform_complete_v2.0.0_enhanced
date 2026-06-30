from __future__ import annotations

import os
from typing import Any

import httpx
from fastapi import FastAPI, Header, HTTPException, Response
from pydantic import BaseModel, Field

from . import ai_generation
from .decision_contracts import (
    EvidenceItem,
    EvidenceStrength,
    assert_no_decision_keys,
    compose_confidence,
)
from .tenant_policies import TenantPolicyStore

# مخزن سياسات المستأجِر (يُغذّى تشغيليّاً) — يحكم السماح بالتوليد لكلّ مستأجِر.
# الافتراضيّ فارغ ⇒ السماح يتبع الراية العامّة فقط (المنع الصريح للمستأجِر يُحترَم).
TENANT_POLICY = TenantPolicyStore()

VERSION = "2026.2-e2e-runtime"
RAG_BASE_URL = os.getenv("RAG_BASE_URL", "http://sahool-rag-retrieval:8000")
KNOWLEDGE_GRAPH_URL = os.getenv("KNOWLEDGE_GRAPH_URL", "http://sahool-knowledge-graph:8000")
PLATFORM_URL = os.getenv("PLATFORM_URL", "http://sahool-platform:8000")
GUARDRAILS_URL = os.getenv("GUARDRAILS_URL", "http://sahool-guardrails-engine:8000")
AGENT_TOKEN = os.getenv("SAHOOL_AGENT_TOKEN", "")

app = FastAPI(title="SAHOOL AI Agronomist Runtime", version=VERSION)


class AdvisorQuery(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    tenant_id: str | None = None
    field_id: str | None = None
    crop: str | None = None
    region: str | None = None
    language: str = Field(default="ar", max_length=8)
    selected_imagery_date: str | None = None
    current_field_state: dict[str, Any] | None = None
    final_k: int = Field(default=5, ge=1, le=10)
    # نموذج الذكاء المختار من الواجهة (كتالوج AI_MODELS عبر مزوّد موحَّد، مثل
    # OpenRouter: DeepSeek/Claude Sonnet/Gemini). يُسجَّل ويُعاد صدى به للشفافيّة؛
    # التحقّق من قائمة السماح يقع في مُحلِّل المزوّد قبل أيّ استدعاء توليديّ.
    model: str | None = Field(default=None, max_length=128)


async def _get_json(client: httpx.AsyncClient, url: str) -> tuple[bool, Any]:
    try:
        resp = await client.get(url, timeout=3.0)
        return resp.status_code < 500, resp.json()
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


@app.get("/healthz")
async def healthz() -> dict[str, Any]:
    return {"status": "ok", "service": "ai-agronomist", "version": VERSION}


@app.get("/metrics")
async def metrics() -> Response:
    # Minimal Prometheus-compatible surface for runtime smoke checks.
    # Detailed per-request counters belong in the gateway/OTEL layer; this keeps
    # the service observable even in lightweight compose deployments.
    body = "\n".join(
        [
            "# HELP sahool_ai_agronomist_info Static service info",
            "# TYPE sahool_ai_agronomist_info gauge",
            f'sahool_ai_agronomist_info{{version="{VERSION}"}} 1',
            "# HELP sahool_ai_agronomist_evidence_only Evidence-only safety invariant",
            "# TYPE sahool_ai_agronomist_evidence_only gauge",
            "sahool_ai_agronomist_evidence_only 1",
            "",
        ]
    )
    return Response(content=body, media_type="text/plain; version=0.0.4")


@app.get("/readyz")
async def readyz() -> dict[str, Any]:
    async with httpx.AsyncClient() as client:
        rag_ok, rag = await _get_json(client, f"{RAG_BASE_URL.rstrip('/')}/readyz")
        kg_ok, kg = await _get_json(client, f"{KNOWLEDGE_GRAPH_URL.rstrip('/')}/readyz")
        guard_ok, guard = await _get_json(client, f"{GUARDRAILS_URL.rstrip('/')}/readyz")
    deps = {"rag": rag_ok, "knowledge_graph": kg_ok, "guardrails": guard_ok}
    if not (rag_ok and kg_ok and guard_ok):
        raise HTTPException(
            503,
            {
                "status": "not_ready",
                "dependencies": deps,
                "details": {"rag": rag, "knowledge_graph": kg, "guardrails": guard},
            },
        )
    return {"status": "ready", "service": "ai-agronomist", "dependencies": deps}


async def _fetch_canonical_field_state(
    client: httpx.AsyncClient, *, tenant_id: str, field_id: str | None
) -> dict[str, Any] | None:
    """Fetch CanonicalFieldState from sahool-platform through the internal S2S endpoint.

    This runtime is evidence-only. The field state is included as context and evidence; final decision
    authority remains with field_intelligence_coordinator and guardrails.
    """
    if not field_id:
        return None
    if not AGENT_TOKEN:
        return {"status": "unavailable", "reason": "SAHOOL_AGENT_TOKEN not configured"}
    try:
        resp = await client.get(
            f"{PLATFORM_URL.rstrip('/')}/internal/fields/{field_id}/state",
            params={"tenant_id": tenant_id},
            headers={"X-Agent-Token": AGENT_TOKEN},
            timeout=7.0,
        )
        if resp.status_code == 404:
            return {"status": "not_found", "field_id": field_id}
        if resp.status_code >= 400:
            return {
                "status": "unavailable",
                "http_status": resp.status_code,
                "detail": resp.text[:500],
            }
        return resp.json()
    except Exception as exc:  # noqa: BLE001
        return {"status": "unavailable", "reason": str(exc)}


def _extract_evidence_ids(rag_payload: dict[str, Any], kg_payload: dict[str, Any]) -> list[str]:
    ids: list[str] = []
    for row in rag_payload.get("annotations", []) or []:
        if isinstance(row, dict):
            ids.append(str(row.get("chunk_id") or row.get("id") or row.get("document_id") or "rag"))
    for row in kg_payload.get("edges", []) or []:
        if isinstance(row, dict):
            ids.append(
                str(
                    row.get("edge_id")
                    or f"{row.get('subject_id', 'kg')}:{row.get('relation', 'rel')}:{row.get('object_id', 'obj')}"
                )
            )
    return ids[:20]


def _confidence_from_payloads(
    rag_payload: dict[str, Any], kg_payload: dict[str, Any], field_state: dict[str, Any] | None
) -> float:
    items: list[EvidenceItem] = []
    for row in rag_payload.get("annotations", []) or []:
        if isinstance(row, dict):
            score = row.get("score") or row.get("confidence") or 0.5
            try:
                items.append(EvidenceItem(EvidenceStrength.RAG, float(score), verified=False))
            except Exception:  # noqa: BLE001
                items.append(EvidenceItem(EvidenceStrength.RAG, 0.5, verified=False))
    for row in kg_payload.get("edges", []) or []:
        if isinstance(row, dict):
            items.append(EvidenceItem(EvidenceStrength.KG, 0.65, verified=False))
    if field_state and field_state.get("status") not in {"unavailable", "not_found"}:
        # Field state is a verified platform context source, but this runtime still cannot emit decisions.
        items.append(EvidenceItem(EvidenceStrength.SATELLITE, 0.70, verified=True))
    return compose_confidence(items)


async def _record_ai_advice_event(
    *,
    tenant_id: str,
    field_id: str | None,
    question: str,
    evidence_ids: list[str],
    confidence: float,
    selected_imagery_date: str | None,
    endpoint_mode: str,
) -> dict[str, Any]:
    """Best-effort audit event for the AI advice runtime.

    This deliberately records an AI_SUGGESTION event only. It does not create
    prescriptions, tasks, actuator commands, or recommendations. Event failure
    must not hide the advisory answer, but the status is returned for runtime
    visibility and E2E verification.
    """
    if not AGENT_TOKEN:
        return {"status": "skipped", "reason": "SAHOOL_AGENT_TOKEN not configured"}
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{PLATFORM_URL.rstrip('/')}/internal/events/ai-advice",
                json={
                    "tenant_id": tenant_id,
                    "field_id": field_id,
                    "question": question,
                    "evidence_ids": evidence_ids,
                    "confidence": confidence,
                    "selected_imagery_date": selected_imagery_date,
                    "endpoint_mode": endpoint_mode,
                },
                headers={"X-Agent-Token": AGENT_TOKEN},
                timeout=3.0,
            )
        if resp.status_code >= 400:
            return {"status": "failed", "http_status": resp.status_code, "detail": resp.text[:300]}
        payload = resp.json()
        return {"status": "recorded", **payload}
    except Exception as exc:  # noqa: BLE001
        return {"status": "failed", "reason": str(exc)}


def _generation_allowed(tenant_id: str) -> bool:
    """بوّابة مزدوجة: الراية العامّة + سياسة المستأجِر (المنع الصريح يُحترَم)."""
    if not ai_generation.generation_enabled():
        return False
    return ai_generation.tenant_allows_generation(TENANT_POLICY.get_policy(tenant_id))


def _grounding_context_text(annotations: dict[str, Any]) -> str:
    """يحوّل أدلّة RAG+KG+حالة الحقل إلى نصّ سياق مقتضب يُمرَّر للنموذج كتأريض.

    لا تلفيق: يُلخّص الموجود فقط؛ غياب مصدر يُذكَر صراحةً كي يلتزم النموذج بالأدلّة.
    """
    lines: list[str] = []
    rag = annotations.get("rag") or []
    if rag:
        lines.append("• مقتطفات معرفيّة (RAG):")
        for item in rag[:6]:
            txt = (
                item.get("text") or item.get("content") or item.get("snippet")
                if isinstance(item, dict)
                else str(item)
            )
            if txt:
                lines.append(f"  - {str(txt)[:400]}")
    kg = annotations.get("knowledge_graph") or []
    if kg:
        lines.append("• روابط Knowledge Graph:")
        for edge in kg[:8]:
            if isinstance(edge, dict):
                s, p, o = edge.get("subject_id"), edge.get("predicate"), edge.get("object_id")
                lines.append(f"  - {s} —{p}→ {o}")
    fs = annotations.get("canonical_field_state")
    if isinstance(fs, dict) and fs:
        rs = fs.get("remote_sensing") or {}
        bits = []
        if rs.get("ndvi_mean") is not None:
            bits.append(f"NDVI={rs.get('ndvi_mean')} ({rs.get('ndvi_date', 'بلا تاريخ')})")
        if fs.get("validity"):
            bits.append(f"صلاحية={fs.get('validity')}")
        if bits:
            lines.append("• حالة الحقل القانونيّة: " + "، ".join(bits))
    return "\n".join(lines) if lines else "لا تتوفّر أدلّة كافية من RAG/KG/حالة الحقل."


async def _build_evidence_response(
    req: AdvisorQuery,
    *,
    endpoint_mode: str,
    x_tenant_id: str | None,
) -> dict[str, Any]:
    tenant_id = req.tenant_id or x_tenant_id
    if not tenant_id:
        raise HTTPException(400, "tenant_id is required from body or X-Tenant-Id")

    async with httpx.AsyncClient() as client:
        field_state = req.current_field_state
        if field_state is None:
            field_state = await _fetch_canonical_field_state(
                client, tenant_id=tenant_id, field_id=req.field_id
            )
        if (
            req.field_id
            and isinstance(field_state, dict)
            and field_state.get("status") in {"unavailable", "not_found"}
        ):
            raise HTTPException(
                502,
                {
                    "dependency": "canonical-field-state",
                    "field_id": req.field_id,
                    "detail": field_state,
                    "policy": "field-specific advice fails closed when field context is unavailable",
                },
            )

        rag_resp = await client.post(
            f"{RAG_BASE_URL.rstrip('/')}/search",
            json={
                "tenant_id": tenant_id,
                "query": req.question,
                "crop": req.crop,
                "field_id": req.field_id,
                "region": req.region,
                "source_type": None,
                "final_k": req.final_k,
            },
            timeout=10.0,
        )
        if rag_resp.status_code >= 400:
            raise HTTPException(502, {"dependency": "rag-retrieval", "detail": rag_resp.text})
        kg_resp = await client.get(
            f"{KNOWLEDGE_GRAPH_URL.rstrip('/')}/edges",
            params={"subject_id": req.crop} if req.crop else {},
            timeout=5.0,
        )
        if kg_resp.status_code >= 500:
            raise HTTPException(502, {"dependency": "knowledge-graph", "detail": kg_resp.text})

    rag_payload = rag_resp.json()
    kg_payload = kg_resp.json()
    annotations = {
        "rag": rag_payload.get("annotations", []),
        "knowledge_graph": kg_payload.get("edges", []),
        "canonical_field_state": field_state,
    }
    # Safety invariant: this runtime explains and gathers evidence only. It must not emit decision-shaped outputs.
    assert_no_decision_keys(
        {"rag": annotations["rag"], "knowledge_graph": annotations["knowledge_graph"]},
        layer="ai_agronomist_annotations",
    )

    evidence_ids = _extract_evidence_ids(rag_payload, kg_payload)
    confidence = _confidence_from_payloads(rag_payload, kg_payload, field_state)
    answer_ar = (
        "جمعتُ سياقاً معرفياً من RAG وKnowledge Graph"
        + (" وحالة الحقل القانونية" if field_state is not None else "")
        + ". هذه طبقة تفسير وتأصيل فقط؛ أي توصية تنفيذية نهائية يجب أن تمر عبر منسّق ذكاء الحقل والحواجز."
    )

    # توليد اختياريّ مؤرَّض فوق الأدلّة (مسار OpenRouter/سحابيّ) — خلف راية عامّة +
    # سياسة المستأجِر، بمفتاح من البيئة، مع سقوط آمن إلى جواب الأدلّة أعلاه عند أيّ
    # غياب/فشل. RAG+KG تبقى طبقة التأصيل الأساسيّة (تُمرَّر كأدلّة للنموذج).
    mode = "evidence_only"
    generation_model: str | None = None
    generation_provider: str | None = None
    if endpoint_mode == "chat" and _generation_allowed(tenant_id):
        context_text = _grounding_context_text(annotations)
        gen = await ai_generation.generate(req.question, context_text, req.model)
        if gen is not None:
            answer_ar = gen.text
            mode = "generated_grounded"
            generation_model = gen.model
            generation_provider = gen.provider

    audit_event = await _record_ai_advice_event(
        tenant_id=tenant_id,
        field_id=req.field_id,
        question=req.question,
        evidence_ids=evidence_ids,
        confidence=confidence,
        selected_imagery_date=req.selected_imagery_date,
        endpoint_mode=endpoint_mode,
    )

    return {
        "status": "ok",
        "mode": mode,
        "endpoint_mode": endpoint_mode,
        "answer_ar": answer_ar,
        "message": answer_ar,
        "tenant_id": tenant_id,
        "field_id": req.field_id,
        "selected_imagery_date": req.selected_imagery_date,
        "selected_model": req.model,
        "generation_model": generation_model,
        "generation_provider": generation_provider,
        "language": req.language,
        "annotations": annotations,
        "evidence_ids": evidence_ids,
        "confidence": confidence,
        "guardrail_result": {
            "status": "not_executed",
            "reason": "evidence-only endpoint; no decision emitted",
        },
        "audit_event": audit_event,
        "decision_authority": "field_intelligence_coordinator",
    }


@app.post("/query")
async def query(
    req: AdvisorQuery, x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id")
) -> dict[str, Any]:
    return await _build_evidence_response(req, endpoint_mode="query", x_tenant_id=x_tenant_id)


@app.post("/chat")
async def chat(
    req: AdvisorQuery, x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id")
) -> dict[str, Any]:
    return await _build_evidence_response(req, endpoint_mode="chat", x_tenant_id=x_tenant_id)


@app.post("/explain")
async def explain(
    req: AdvisorQuery, x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id")
) -> dict[str, Any]:
    return await _build_evidence_response(req, endpoint_mode="explain", x_tenant_id=x_tenant_id)


@app.post("/recommend")
async def recommend(
    req: AdvisorQuery, x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id")
) -> dict[str, Any]:
    # Kept for UI compatibility only. It intentionally returns evidence-only output and never prescriptions/tasks.
    return await _build_evidence_response(
        req, endpoint_mode="recommend_evidence_only", x_tenant_id=x_tenant_id
    )
