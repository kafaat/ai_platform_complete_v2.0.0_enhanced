from __future__ import annotations

import os
from typing import Any

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, Response
from pydantic import BaseModel, Field

from shared.security.gateway_deps import require_authenticated_user, require_trusted_tenant

from . import ai_generation, approval
from .agent_stores import build_approval_store, build_audit_store
from .ai_evidence_runtime import (
    _ai_context_memory_lines,  # noqa: F401 — إعادة تصدير (نمط main.X للراوترات/الحُرّاس)
    _build_agent_tool_fetcher,  # noqa: F401 — إعادة تصدير (نمط main.X للراوترات/الحُرّاس)
    _confidence_from_payloads,  # noqa: F401 — إعادة تصدير (نمط main.X للراوترات/الحُرّاس)
    _evidence_sources,  # noqa: F401 — إعادة تصدير (نمط main.X للراوترات/الحُرّاس)
    _extract_ai_context_pack,  # noqa: F401 — إعادة تصدير (نمط main.X للراوترات/الحُرّاس)
    _extract_evidence_ids,  # noqa: F401 — إعادة تصدير (نمط main.X للراوترات/الحُرّاس)
    _fetch_canonical_field_state,  # noqa: F401 — إعادة تصدير (نمط main.X للراوترات/الحُرّاس)
    _field_memory_evidence_ids,  # noqa: F401 — إعادة تصدير (نمط main.X للراوترات/الحُرّاس)
    _generation_allowed,  # noqa: F401 — إعادة تصدير (نمط main.X للراوترات/الحُرّاس)
    _grounding_context_text,  # noqa: F401 — إعادة تصدير (نمط main.X للراوترات/الحُرّاس)
    _record_ai_advice_event,  # noqa: F401 — إعادة تصدير (نمط main.X للراوترات/الحُرّاس)
    _source_count,  # noqa: F401 — إعادة تصدير (نمط main.X للراوترات/الحُرّاس)
    _utc_timestamp,
)
from .ai_evidence_runtime import (
    build_evidence_response as _build_evidence_response_runtime,
)

VERSION = "2026.2-e2e-runtime"
RAG_BASE_URL = os.getenv("RAG_BASE_URL", "http://sahool-rag-retrieval:8000")
KNOWLEDGE_GRAPH_URL = os.getenv("KNOWLEDGE_GRAPH_URL", "http://sahool-knowledge-graph:8000")
GUARDRAILS_URL = os.getenv("GUARDRAILS_URL", "http://sahool-guardrails-engine:8000")

app = FastAPI(title="SAHOOL AI Agronomist Runtime", version=VERSION)

# V58.2 — swappable, persistent-ready approval/audit stores (memory default; Redis via
# SAHOOL_AGENT_STORE_BACKEND=redis, fail-safe to memory). Replaces the v61.5 in-process
# ledgers so chat approvals/audits survive restarts + are multi-worker safe in production.
_AUDIT_STORE = build_audit_store()
_APPROVAL_STORE = build_approval_store()


def _save_agent_tool_audit(record: dict[str, Any]) -> None:
    _AUDIT_STORE.append(record)


def _save_pending_approval(request: dict[str, Any]) -> None:
    _APPROVAL_STORE.save(request)


def _approval_for_decision(incoming: dict[str, Any]) -> dict[str, Any]:
    approval_id = str(incoming.get("id") or "")
    saved = _APPROVAL_STORE.get(approval_id) if approval_id else None
    if saved:
        saved.update({k: v for k, v in incoming.items() if v is not None})
        return saved
    return dict(incoming)


def _approved_resume_envelope(decided: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "approved_ready_for_domain_execution",
        "tool": decided.get("tool"),
        "approval_id": decided.get("id"),
        "tenant_id": decided.get("tenant_id"),
        "field_id": (decided.get("params") or {}).get("field_id")
        if isinstance(decided.get("params"), dict)
        else None,
        "input_hash": decided.get("input_hash"),
        "requires_domain_service": True,
        "executes_in_chat_runtime": False,
    }


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
    # V57: طلبات أدوات اختياريّة ينتجها النموذج/الواجهة وتُنفّذ عبر حلقة Harness محوكَمة.
    # لا تُنفَّذ أداة مجهولة أو بلا قدرة؛ الأفعال المُعدِّلة تُحوَّل إلى طلب موافقة.
    tool_calls: list[dict[str, Any]] | None = None


class ApprovalDecisionRequest(BaseModel):
    approval: dict[str, Any]
    approver: str = Field(default="human", max_length=120)
    reason: str | None = Field(default=None, max_length=500)


async def _get_json(client: httpx.AsyncClient, url: str) -> tuple[bool, Any]:
    try:
        resp = await client.get(url, timeout=3.0)
        return resp.status_code < 500, resp.json()
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


@app.get("/healthz")
async def healthz() -> dict[str, Any]:
    return {"status": "ok", "service": "ai-agronomist", "version": VERSION}


@app.get("/healthz/ai-provider")
async def ai_provider_snapshot() -> dict[str, Any]:
    """لقطة مزوّد الذكاء الرصديّة (بلا أسرار) — يستهلكها الرصد/الواجهة كمصدر حالة
    واحد (راية التوليد، المزوّد وصنفه، توافره، الكتالوج، أوضاع مشاركة البيانات).
    يُغلِق توصية تدقيق V51 (Provider Snapshot)."""
    return ai_generation.public_provider_snapshot()


@app.get("/approvals/pending")
async def list_pending_approvals(
    tenant: str = Depends(require_trusted_tenant),
    _user_id: str = Depends(require_authenticated_user),
) -> dict[str, Any]:
    """يسرد طلبات الموافقة المعلّقة للمستأجِر الحاليّ — قراءة فقط لكونسول الموافقات.

    كان المخزن يملك ``list_pending()`` بلا نقطة تكشفه، فبقيت الموافقات مرئيّة فقط
    داخل رسالة المحادثة التي أنشأتها. الترشيح بـ``tenant_id`` المسجَّل في الطلب نفسه
    (build_approval_request) مقابل هويّة البوّابة الموثوقة — لا تسريب عبر المستأجِرين.
    السجلّات القديمة بلا tenant_id تُستبعَد (fail-closed) بدل عرضها للجميع.
    """
    pending = [
        rec
        for rec in _APPROVAL_STORE.list_pending()
        if str(rec.get("tenant_id") or "") == str(tenant)
    ]
    return {"pending": pending, "count": len(pending)}


@app.post("/approvals/approve")
async def approve_tool_request(
    req: ApprovalDecisionRequest,
    _tenant: str = Depends(require_trusted_tenant),
    user_id: str = Depends(require_authenticated_user),
) -> dict[str, Any]:
    """Normalize a human approval decision for a pending agent tool request.

    This endpoint does not execute the underlying mutating tool; execution must be handled
    by the owning domain service after authorization. It only records/returns the audited
    decision shape so the web UI can show a real approve/deny workflow without granting
    the model direct write access.

    SEC-3.1: the approver of record is the gateway-authenticated user id (``X-User-Id``),
    NOT the JSON body — a caller cannot spoof who approved by editing the payload.
    """
    base = _approval_for_decision(req.approval)
    try:
        decided = approval.approve(
            base,
            approver=user_id,
            decided_at=_utc_timestamp(),
        )
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    _save_pending_approval(decided)
    _save_agent_tool_audit(
        {
            "tool": decided.get("tool"),
            "params": decided.get("params") if isinstance(decided.get("params"), dict) else {},
            "tenant_id": decided.get("tenant_id"),
            "actor": decided.get("actor"),
            "outcome": "approved",
            "risk": decided.get("risk"),
            "capability": decided.get("capability"),
            "timestamp": decided.get("decided_at"),
            "field_id": (decided.get("params") or {}).get("field_id")
            if isinstance(decided.get("params"), dict)
            else None,
            "input_hash": decided.get("input_hash"),
            "result_summary": "human_approved_pending_domain_execution",
            "result": _approved_resume_envelope(decided),
        }
    )
    return {
        "status": "approved",
        "approval": decided,
        "executes_tool": False,
        "resume": _approved_resume_envelope(decided),
    }


@app.post("/approvals/deny")
async def deny_tool_request(
    req: ApprovalDecisionRequest,
    _tenant: str = Depends(require_trusted_tenant),
    user_id: str = Depends(require_authenticated_user),
) -> dict[str, Any]:
    """Normalize a human denial decision for a pending agent tool request.

    SEC-3.1: the denier of record is the gateway-authenticated user id, not the body.
    """
    base = _approval_for_decision(req.approval)
    try:
        decided = approval.deny(
            base,
            approver=user_id,
            decided_at=_utc_timestamp(),
            reason=req.reason or "denied_by_user",
        )
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    _save_pending_approval(decided)
    _save_agent_tool_audit(
        {
            "tool": decided.get("tool"),
            "params": decided.get("params") if isinstance(decided.get("params"), dict) else {},
            "tenant_id": decided.get("tenant_id"),
            "actor": decided.get("actor"),
            "outcome": "denied",
            "risk": decided.get("risk"),
            "capability": decided.get("capability"),
            "timestamp": decided.get("decided_at"),
            "field_id": (decided.get("params") or {}).get("field_id")
            if isinstance(decided.get("params"), dict)
            else None,
            "input_hash": decided.get("input_hash"),
            "result_summary": req.reason or "denied_by_user",
            "result": {"reason": req.reason or "denied_by_user"},
        }
    )
    return {"status": "denied", "approval": decided, "executes_tool": False}


class ApprovalResumeRequest(BaseModel):
    approval_id: str = Field(min_length=1, max_length=200)


@app.post("/approvals/resume")
async def resume_approved_tool(
    req: ApprovalResumeRequest,
    _tenant: str = Depends(require_trusted_tenant),
    _user: str = Depends(require_authenticated_user),
) -> dict[str, Any]:
    """V58.2 — resume a human-APPROVED agent tool as a governed execution handoff.

    Reads the STORED approval by id (a client cannot fabricate one), verifies it was
    approved, and returns the execution envelope for the owning domain service to run —
    this runtime still never executes the mutating tool itself
    (``executes_in_chat_runtime=False``). Unknown/not-approved ids fail closed.
    """
    stored = _APPROVAL_STORE.get(req.approval_id)
    if stored is None:
        raise HTTPException(404, "approval_not_found")
    if str(stored.get("status") or "") != approval.STATUS_APPROVED:
        raise HTTPException(409, f"approval_not_in_approved_state:{stored.get('status')}")
    envelope = _approved_resume_envelope(stored)
    _save_agent_tool_audit(
        {
            "tool": stored.get("tool"),
            "params": stored.get("params") if isinstance(stored.get("params"), dict) else {},
            "tenant_id": stored.get("tenant_id"),
            "user_id": stored.get("user_id"),
            "session_id": stored.get("session_id"),
            "actor": stored.get("actor"),
            "outcome": "resumed_for_domain_execution",
            "risk": stored.get("risk"),
            "capability": stored.get("capability"),
            "input_hash": stored.get("input_hash"),
            "timestamp": _utc_timestamp(),
            "result_summary": "handoff_to_domain_service",
            "result": envelope,
        }
    )
    return {"status": "resumed", "approval_id": req.approval_id, "resume": envelope}


class ExportPreviewRequest(BaseModel):
    prescription: dict[str, Any]
    format: str = Field(default="geojson", max_length=32)


@app.post("/prescription/export-preview")
async def prescription_export_preview(req: ExportPreviewRequest) -> dict[str, Any]:
    """V62.2 — build a machine-format export PREVIEW for a VRA prescription.

    Preview only: the returned payload is ``machine_executable=False`` /
    ``requires_approval=True``. Writing to a controller / exporting a real file stays
    the ``create_prescription_map`` high-risk approval + agronomist review — this
    endpoint never performs it.
    """
    from .prescription_export_adapters import build_prescription_export

    result = build_prescription_export(req.prescription, req.format)
    result.setdefault("executes_export", False)
    return result


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
                "service": "ai-agronomist",
                "dependencies": deps,
                "details": {"rag": rag, "knowledge_graph": kg, "guardrails": guard},
            },
        )
    return {"status": "ready", "service": "ai-agronomist", "dependencies": deps}


async def _build_evidence_response(
    req: AdvisorQuery,
    *,
    endpoint_mode: str,
    x_tenant_id: str | None,
    x_agent_token: str | None = None,
) -> dict[str, Any]:
    return await _build_evidence_response_runtime(
        req,
        endpoint_mode=endpoint_mode,
        x_tenant_id=x_tenant_id,
        x_agent_token=x_agent_token,
        save_agent_tool_audit=_save_agent_tool_audit,
        save_pending_approval=_save_pending_approval,
    )


@app.post("/query")
async def query(
    req: AdvisorQuery,
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    x_agent_token: str | None = Header(default=None, alias="X-Agent-Token"),
) -> dict[str, Any]:
    return await _build_evidence_response(
        req, endpoint_mode="query", x_tenant_id=x_tenant_id, x_agent_token=x_agent_token
    )


@app.post("/chat")
async def chat(
    req: AdvisorQuery,
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    x_agent_token: str | None = Header(default=None, alias="X-Agent-Token"),
) -> dict[str, Any]:
    return await _build_evidence_response(
        req, endpoint_mode="chat", x_tenant_id=x_tenant_id, x_agent_token=x_agent_token
    )


@app.post("/explain")
async def explain(
    req: AdvisorQuery,
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    x_agent_token: str | None = Header(default=None, alias="X-Agent-Token"),
) -> dict[str, Any]:
    return await _build_evidence_response(
        req, endpoint_mode="explain", x_tenant_id=x_tenant_id, x_agent_token=x_agent_token
    )


@app.post("/recommend")
async def recommend(
    req: AdvisorQuery,
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    x_agent_token: str | None = Header(default=None, alias="X-Agent-Token"),
) -> dict[str, Any]:
    # Kept for UI compatibility only. It intentionally returns evidence-only output and never prescriptions/tasks.
    return await _build_evidence_response(
        req,
        endpoint_mode="recommend_evidence_only",
        x_tenant_id=x_tenant_id,
        x_agent_token=x_agent_token,
    )
