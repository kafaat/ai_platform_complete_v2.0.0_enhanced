from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Any

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, Response
from pydantic import BaseModel, Field

from shared.security.gateway_deps import require_authenticated_user, require_trusted_tenant
from shared.security.trusted_tenant import (
    TrustedTenantError,
    resolve_trusted_tenant,
    service_token_ok,
)

from . import (
    advisory_contract,
    ai_generation,
    approval,
    harness_transparency,
    observation_context,
    policy_envelope,
    runtime_evidence,
    tool_loop,
)
from .agent_stores import build_approval_store, build_audit_store
from .decision_contracts import (
    EvidenceItem,
    EvidenceStrength,
    assert_no_decision_keys,
    compose_confidence,
)
from .field_boundary_ai import propose_boundaries
from .productivity_zones import propose_productivity_zones
from .soil_sampling_planner import plan_soil_sampling
from .tenant_policies import build_store_from_env, normalize_policy
from .vra_prescription_engine import generate_vra_prescription

# مخزن سياسات المستأجِر — يحكم السماح بالتوليد ومستوى مشاركة البيانات لكلّ مستأجِر.
# يُدِيم عبر ملفّ JSON إن ضُبِط ``TENANT_AI_POLICY_FILE`` (compose/k8s mount)، وإلّا
# محلّيّ-العمليّة (السماح يتبع الراية العامّة فقط؛ المنع الصريح للمستأجِر يُحترَم).
TENANT_POLICY = build_store_from_env()

VERSION = "2026.2-e2e-runtime"
RAG_BASE_URL = os.getenv("RAG_BASE_URL", "http://sahool-rag-retrieval:8000")
KNOWLEDGE_GRAPH_URL = os.getenv("KNOWLEDGE_GRAPH_URL", "http://sahool-knowledge-graph:8000")
PLATFORM_URL = os.getenv("PLATFORM_URL", "http://sahool-platform:8000")
GUARDRAILS_URL = os.getenv("GUARDRAILS_URL", "http://sahool-guardrails-engine:8000")
AGENT_TOKEN = os.getenv("SAHOOL_AGENT_TOKEN", "")

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
        ai_pack = _extract_ai_context_pack(field_state)
        if ai_pack:
            imagery = ai_pack.get("imagery_timeline") or {}
            weather = ai_pack.get("weather_history") or {}
            if isinstance(imagery, dict) and _source_count(imagery.get("total_dates")) > 0:
                items.append(EvidenceItem(EvidenceStrength.SATELLITE, 0.75, verified=True))
            if isinstance(weather, dict) and weather.get("available"):
                items.append(EvidenceItem(EvidenceStrength.WEATHER, 0.80, verified=True))
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


def _utc_timestamp() -> str:
    """وقت UTC موحّد لسجلات الأدوات (حتميّ في الاختبارات عبر حقنه خارجياً عند الحاجة)."""
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _build_agent_tool_fetcher(
    *,
    field_state: dict[str, Any] | None,
    ai_pack: dict[str, Any] | None,
    annotations: dict[str, Any],
) -> tool_loop.ToolFetcher:
    """جالب قراءة محليّ لحلقة الأدوات.

    هذه ليست طبقة قرارات ولا تستدعي خدمات خارجيّة جديدة؛ هي تجعل الأدوات القرائيّة
    تستند إلى الأدلّة الموجودة أصلاً في الطلب: CanonicalFieldState + AI Context Pack +
    RAG/KG. الأفعال المُعدِّلة لا تصل هنا أصلاً لأن ``tool_loop`` يؤجّلها للموافقة.
    """
    pack = ai_pack if isinstance(ai_pack, dict) else {}
    fs = field_state if isinstance(field_state, dict) else {}

    def fetcher(tool_name: str, params: dict[str, Any]) -> Any:
        field_id = params.get("field_id") or fs.get("field_id") or pack.get("field_id")
        if tool_name == "get_field_state":
            return {
                "field_id": field_id,
                "canonical_field_state": fs,
                "ai_context_readiness": pack.get("readiness") if pack else None,
            }
        if tool_name == "get_truecolor_scene":
            imagery = pack.get("imagery_timeline") or {}
            return {
                "field_id": field_id,
                "index": "truecolor",
                "requested_date": params.get("date"),
                "imagery_timeline": imagery,
                "readiness": pack.get("readiness") if pack else None,
            }
        if tool_name == "get_index_timeline":
            return {
                "field_id": field_id,
                "index": params.get("index"),
                "days": params.get("days"),
                "imagery_timeline": pack.get("imagery_timeline") or {},
            }
        if tool_name == "get_weather_history":
            return {
                "field_id": field_id,
                "days": params.get("days"),
                "weather_history": pack.get("weather_history") or {},
            }
        if tool_name == "get_operation_windows":
            return {
                "field_id": field_id,
                "operation_windows": pack.get("operation_windows")
                or pack.get("operation_windows_context")
                or {},
            }
        if tool_name == "get_alerts":
            return {"field_id": field_id, "alerts_context": pack.get("alerts_context") or {}}
        if tool_name == "get_drawings_and_zones":
            return {"field_id": field_id, "drawing_context": pack.get("drawing_context") or {}}
        if tool_name == "open_map_layer":
            return {
                "ui_action": "open_map_layer",
                "field_id": field_id,
                "layer": params.get("layer"),
                "date": params.get("date"),
                "note": "فعل واجهة منخفض الخطر؛ لا يغيّر بيانات الحقل.",
            }
        if tool_name == "detect_field_boundaries":
            # V62.2 — enrich with derived cloud_risk/ready so the degradation guard is real.
            return propose_boundaries(
                params,
                field_id=str(field_id) if field_id is not None else None,
                imagery_context=runtime_evidence.boundary_imagery_context(pack),
            )
        if tool_name == "generate_productivity_zones":
            # V62.2 — forward a real NDVI grid (if the raster pipeline supplied one).
            # V62.3-C — also attach the ndvi_grid_evidence contract (used by machine-
            # readiness downstream); None when no grid ⇒ unchanged behavior.
            zoning_ctx = runtime_evidence.zoning_evidence_context(pack)
            ndvi_ev = runtime_evidence.pack_ndvi_grid_evidence(pack)
            if ndvi_ev is not None:
                zoning_ctx["ndvi_grid_evidence"] = ndvi_ev
            return propose_productivity_zones(
                params,
                field_id=str(field_id) if field_id is not None else None,
                evidence_context=zoning_ctx,
            )
        if tool_name == "plan_soil_sampling":
            return plan_soil_sampling(
                params,
                field_id=str(field_id) if field_id is not None else None,
                evidence_context=pack,
            )
        if tool_name == "generate_vra_prescription":
            # V62.3-C — feed the VRA raster-quality gate a real ndvi_grid_evidence object
            # (from the pack's grid+quality). Additive: absent grid ⇒ gate stays None.
            vra_ctx = dict(pack)
            ndvi_ev = runtime_evidence.pack_ndvi_grid_evidence(pack)
            if ndvi_ev is not None:
                vra_ctx["ndvi_grid_evidence"] = ndvi_ev
            return generate_vra_prescription(
                params,
                field_id=str(field_id) if field_id is not None else None,
                evidence_context=vra_ctx,
            )
        if tool_name == "get_water_productivity":
            # V67.1 — إشارات المياه المتوفّرة في السياق (لا جلب خارجيّ، لا اختلاق).
            # فارغ ⇒ available=False بصدق (لا رقم مُختلَق حتّى يوصَل WaPOR/الميزان المائيّ).
            water: dict[str, Any] = {}
            for key in (
                "water_balance",
                "water_deficit_mm",
                "water_deficit",
                "water_use_efficiency",
                "irrigation_mm",
                "et0_mm",
                "water_productivity",
            ):
                for src in (fs, pack):
                    if isinstance(src, dict) and src.get(key) is not None:
                        water[key] = src.get(key)
                        break
            return {
                "field_id": field_id,
                "days": params.get("days"),
                "water_productivity": water,
                "available": bool(water),
                "note_ar": None
                if water
                else "لا إشارة إنتاجيّة مياه في السياق بعد (يُغذّيها الميزان المائيّ/WaPOR لاحقاً).",
            }
        if tool_name == "generate_report":
            # V67.1 — تقرير قراءة موحّد: هضم منظَّم لأدلّة السياق القائمة (لا إرسال، لا اختلاق).
            imagery = pack.get("imagery_timeline") if isinstance(pack, dict) else None
            imagery = imagery if isinstance(imagery, dict) else {}
            return {
                "field_id": field_id,
                "period": params.get("period"),
                "report_type": "read_only_field_digest",
                "sections": {
                    "state": fs or {"status": "missing"},
                    "imagery": {"total_dates": imagery.get("total_dates")},
                    "weather": pack.get("weather_history") or {"status": "missing"},
                    "alerts": pack.get("alerts_context") or {"status": "missing"},
                    "readiness": pack.get("readiness") if isinstance(pack, dict) else None,
                },
                "evidence_sources": sorted(k for k in pack if pack.get(k))
                if isinstance(pack, dict)
                else [],
                "note_ar": "تقرير قراءة مُجمَّع من أدلّة السياق (لا إرسال، لا اختلاق).",
            }
        # يفترض ألا يصل المجهول إلى الجالب بسبب البوابة، لكن نبقيه fail-closed.
        raise ValueError(f"unsupported_read_tool:{tool_name}")

    return fetcher


def _extract_ai_context_pack(field_state: dict[str, Any] | None) -> dict[str, Any] | None:
    """Return the two-year AI context pack whether it is embedded by the web UI or
    passed directly as the field state.

    The chat UI sends the pack under ``current_field_state.ai_context_pack``.
    Some server-to-server callers may send the pack itself. Both forms are
    accepted, but non-dict values are ignored rather than trusted.
    """
    if not isinstance(field_state, dict):
        return None
    embedded = field_state.get("ai_context_pack")
    if isinstance(embedded, dict):
        return embedded
    if any(
        k in field_state for k in ("imagery_timeline", "weather_history", "ai_context_summary_ar")
    ):
        return field_state
    return None


def _source_count(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _ai_context_memory_lines(pack: dict[str, Any] | None) -> list[str]:
    """Compact, evidence-only summary of the 2-year field memory for prompt grounding."""
    if not pack:
        return ["• ذاكرة الحقل لسنتين: غير مرفقة في الطلب الحالي."]

    lines = ["• ذاكرة الحقل لسنتين (Field AI Context Pack):"]
    summary = pack.get("ai_context_summary_ar")
    if summary:
        lines.append(f"  - الملخص: {str(summary)[:700]}")

    imagery = pack.get("imagery_timeline") or {}
    if isinstance(imagery, dict):
        lines.append(
            "  - المشاهد/المؤشرات التاريخية: "
            f"{_source_count(imagery.get('total_dates'))} مشهد/تاريخ ضمن النافذة."
        )
        per_indicator = imagery.get("per_indicator") or {}
        if isinstance(per_indicator, dict):
            indicator_bits = []
            for key, val in sorted(per_indicator.items()):
                if isinstance(val, dict):
                    indicator_bits.append(f"{key}={_source_count(val.get('total'))}")
            if indicator_bits:
                lines.append("  - توزيع المؤشرات: " + "، ".join(indicator_bits[:8]))

    weather = pack.get("weather_history") or {}
    if isinstance(weather, dict) and weather.get("available"):
        ws = weather.get("summary") or {}
        if isinstance(ws, dict):
            lines.append(
                "  - الطقس التاريخي: "
                f"{ws.get('days', '—')} يوم، مطر {ws.get('total_precipitation_mm', '—')} مم، "
                f"ET0 {ws.get('total_et0_mm', '—')} مم، متوسط حرارة {ws.get('avg_temp_c', '—')}°م."
            )
    else:
        lines.append("  - الطقس التاريخي: غير متاح أو غير مكتمل.")

    for label, key in (
        ("أحداث الحقل", "operations_timeline"),
        ("هندسات/محاور/مناطق", "drawing_context"),
        ("تنبيهات", "alerts_context"),
        ("توصيات محفوظة", "recommendations_context"),
    ):
        source = pack.get(key) or {}
        if isinstance(source, dict):
            lines.append(f"  - {label}: {_source_count(source.get('total'))}.")

    readiness = pack.get("readiness") or {}
    if isinstance(readiness, dict):
        warnings = readiness.get("warnings") or []
        if readiness.get("requires_imagery_backfill_24_months"):
            lines.append("  - جاهزية الصور: تحتاج تشغيل backfill سنتين قبل تحليل بصري كامل.")
        if warnings:
            lines.append("  - تحذيرات الجاهزية: " + "؛ ".join(str(w)[:180] for w in warnings[:4]))
    return lines


def _field_memory_evidence_ids(pack: dict[str, Any] | None) -> list[str]:
    if not pack:
        return []
    field_id = str(pack.get("field_id") or "field")
    ids: list[str] = []
    imagery = pack.get("imagery_timeline") or {}
    if isinstance(imagery, dict) and _source_count(imagery.get("total_dates")) > 0:
        ids.append(f"field-memory:{field_id}:imagery:{_source_count(imagery.get('total_dates'))}")
    weather = pack.get("weather_history") or {}
    if isinstance(weather, dict) and weather.get("available"):
        summary = weather.get("summary") or {}
        days = summary.get("days") if isinstance(summary, dict) else None
        ids.append(f"field-memory:{field_id}:weather:{days or pack.get('days', 'range')}")
    for key, label in (
        ("operations_timeline", "events"),
        ("drawing_context", "drawings"),
        ("alerts_context", "alerts"),
        ("recommendations_context", "saved-advice"),
    ):
        source = pack.get(key) or {}
        if isinstance(source, dict) and _source_count(source.get("total")) > 0:
            ids.append(f"field-memory:{field_id}:{label}:{_source_count(source.get('total'))}")
    return ids[:20]


def _evidence_sources(
    rag_payload: dict[str, Any], kg_payload: dict[str, Any], field_state: dict[str, Any] | None
) -> list[dict[str, Any]]:
    """User-facing evidence cards, without leaking raw private payloads or secrets."""
    pack = _extract_ai_context_pack(field_state)
    rag_count = len(rag_payload.get("annotations", []) or [])
    kg_count = len(kg_payload.get("edges", []) or [])
    sources: list[dict[str, Any]] = [
        {"key": "rag", "label_ar": "RAG", "available": rag_count > 0, "count": rag_count},
        {
            "key": "knowledge_graph",
            "label_ar": "Knowledge Graph",
            "available": kg_count > 0,
            "count": kg_count,
        },
    ]
    if isinstance(field_state, dict):
        sources.append(
            {"key": "field_state", "label_ar": "حالة الحقل", "available": True, "count": 1}
        )
    if pack:
        imagery = pack.get("imagery_timeline") or {}
        weather = pack.get("weather_history") or {}
        operations = pack.get("operations_timeline") or {}
        drawings = pack.get("drawing_context") or {}
        sources.extend(
            [
                {
                    "key": "imagery_timeline",
                    "label_ar": "صور/مؤشرات سنتين",
                    "available": _source_count(getattr(imagery, "get", lambda *_: 0)("total_dates"))
                    > 0
                    if isinstance(imagery, dict)
                    else False,
                    "count": _source_count(imagery.get("total_dates"))
                    if isinstance(imagery, dict)
                    else 0,
                },
                {
                    "key": "weather_history",
                    "label_ar": "طقس تاريخي",
                    "available": bool(weather.get("available"))
                    if isinstance(weather, dict)
                    else False,
                    "count": _source_count((weather.get("summary") or {}).get("days"))
                    if isinstance(weather, dict) and isinstance(weather.get("summary"), dict)
                    else 0,
                },
                {
                    "key": "operations_timeline",
                    "label_ar": "Timeline العمليات",
                    "available": _source_count(operations.get("total")) > 0
                    if isinstance(operations, dict)
                    else False,
                    "count": _source_count(operations.get("total"))
                    if isinstance(operations, dict)
                    else 0,
                },
                {
                    "key": "drawing_context",
                    "label_ar": "المناطق والرسوم",
                    "available": _source_count(drawings.get("total")) > 0
                    if isinstance(drawings, dict)
                    else False,
                    "count": _source_count(drawings.get("total"))
                    if isinstance(drawings, dict)
                    else 0,
                },
            ]
        )
    return sources


def _grounding_context_text(annotations: dict[str, Any]) -> str:
    """يحوّل أدلّة RAG+KG+حالة الحقل+ذاكرة سنتين إلى نصّ سياق مقتضب للتأريض.

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
                s = edge.get("subject_id") or edge.get("subject")
                p = edge.get("predicate") or edge.get("relation")
                o = edge.get("object_id") or edge.get("object")
                lines.append(f"  - {s} —{p}→ {o}")
    fs = annotations.get("canonical_field_state")
    if isinstance(fs, dict) and fs:
        rs = fs.get("remote_sensing") or {}
        bits = []
        if rs.get("ndvi_mean") is not None:
            bits.append(f"NDVI={rs.get('ndvi_mean')} ({rs.get('ndvi_date', 'بلا تاريخ')})")
        if fs.get("validity"):
            bits.append(f"صلاحية={fs.get('validity')}")
        if fs.get("farm_summary"):
            bits.append(str(fs.get("farm_summary"))[:300])
        if bits:
            lines.append("• حالة الحقل/المزرعة: " + "، ".join(bits))
        lines.extend(_ai_context_memory_lines(_extract_ai_context_pack(fs)))
    return "\n".join(lines) if lines else "لا تتوفّر أدلّة كافية من RAG/KG/حالة الحقل."


async def _build_evidence_response(
    req: AdvisorQuery,
    *,
    endpoint_mode: str,
    x_tenant_id: str | None,
    x_agent_token: str | None = None,
) -> dict[str, Any]:
    # SEC-3: the gateway-injected X-Tenant-Id is the ONLY tenant source of truth.
    # A body tenant_id may only echo it (never override); missing header or a body
    # mismatch fails closed with 403.
    try:
        tenant_id = resolve_trusted_tenant(x_tenant_id, req.tenant_id)
    except TrustedTenantError as exc:
        raise HTTPException(403, exc.code) from exc

    async with httpx.AsyncClient() as client:
        # C3: public clients must not be able to inject ``current_field_state`` and
        # make the AI answer appear grounded in canonical field evidence. A supplied
        # context pack is accepted only from an internal caller proving possession of
        # SAHOOL_AGENT_TOKEN; otherwise we fetch the canonical source-of-truth state
        # from sahool-platform. Without the token, a request carrying
        # ``current_field_state`` fails closed (403).
        field_state = None
        if req.current_field_state is not None:
            if not service_token_ok(x_agent_token, os.getenv("SAHOOL_AGENT_TOKEN", "")):
                raise HTTPException(403, "current_field_state_requires_service_token")
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
            # SEC-3: forward the trusted tenant so rag-retrieval enforces the same
            # X-Tenant-Id-source-of-truth guard on this internal service-to-service call.
            headers={"X-Tenant-Id": tenant_id},
            timeout=10.0,
        )
        if rag_resp.status_code >= 400:
            raise HTTPException(502, {"dependency": "rag-retrieval", "detail": rag_resp.text})
        kg_resp = await client.get(
            f"{KNOWLEDGE_GRAPH_URL.rstrip('/')}/edges",
            params={"subject_id": req.crop} if req.crop else {},
            # C2: forward the trusted tenant so knowledge-graph enforces its C5 read
            # guard (require_trusted_tenant) on this internal service-to-service call.
            headers={"X-Tenant-Id": tenant_id},
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

    ai_pack = _extract_ai_context_pack(field_state)
    # V52 — Tenant AI Policy Envelope: the platform is the policy authority; this consumer
    # enforces the envelope carried in the pack (it never opens the DB for policy). Absent/
    # invalid envelope ⇒ fail-closed refusal (no external LLM, envelope tool-gate closed).
    _envelope, _envelope_refusal = policy_envelope.enforce_request(ai_pack)
    _envelope_tool_gate = policy_envelope.allowed_tools_set(_envelope)
    policy_envelope_decision: dict[str, Any] = _envelope_refusal or {
        "decision": policy_envelope.DECISION_ALLOWED,
        "reason": "policy_envelope_valid",
        "policy_mode": (_envelope or {}).get("policy_mode"),
        "version": (_envelope or {}).get("version"),
    }
    evidence_ids = _extract_evidence_ids(rag_payload, kg_payload) + _field_memory_evidence_ids(
        ai_pack
    )
    # Keep order, remove duplicates, and cap the user-facing evidence list.
    evidence_ids = list(dict.fromkeys(evidence_ids))[:30]
    evidence_sources = _evidence_sources(rag_payload, kg_payload, field_state)
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
    provider_tool_calls: list[dict[str, Any]] = []
    provider_pending_approvals: list[dict[str, Any]] = []
    provider_tool_truncated = False
    provider_tool_rounds = 0
    if endpoint_mode == "chat" and _generation_allowed(tenant_id):
        context_text = _grounding_context_text(annotations)
        _policy_for_generation = normalize_policy(TENANT_POLICY.get_policy(tenant_id))
        # Resolve the provider up-front so the envelope can gate external calls fail-closed:
        # a missing/invalid envelope or a local_only policy blocks any external provider,
        # while local generation stays permitted (its data never leaves the tenant boundary).
        _cfg = ai_generation.resolve_generation(req.model)
        _external = _cfg is not None and ai_generation.provider_is_external(_cfg.provider)
        _gen_gate = policy_envelope.gate_generation(_envelope, external=_external)
        policy_envelope_decision = _gen_gate
        if _gen_gate["decision"] == policy_envelope.DECISION_BLOCKED:
            # Fail-closed: do not call an external provider; stay on the evidence-only answer.
            gen = None
        else:
            # Envelope is authoritative for data sharing: drive the existing redaction path
            # from the envelope's policy_mode (compose, don't duplicate).
            if _external and _gen_gate.get("policy_mode"):
                _policy_for_generation = dict(_policy_for_generation)
                _policy_for_generation["data_sharing_level"] = _gen_gate["policy_mode"]
            gen = await ai_generation.generate(
                req.question,
                context_text,
                req.model,
                policy=_policy_for_generation,
                allowed_capabilities=_policy_for_generation.get("allowed_capabilities"),
                tool_fetcher=_build_agent_tool_fetcher(
                    field_state=field_state, ai_pack=ai_pack, annotations=annotations
                ),
                tenant_id=tenant_id,
                actor="ai_agronomist",
                timestamp=_utc_timestamp(),
                max_tool_rounds=3,
                audit_saver=_save_agent_tool_audit,
                approval_saver=_save_pending_approval,
                allowed_tools=_envelope_tool_gate,
            )
        if gen is not None:
            answer_ar = gen.text
            mode = "generated_grounded"
            generation_model = gen.model
            generation_provider = gen.provider
            provider_tool_calls = list(gen.tool_calls or [])
            provider_pending_approvals = list(gen.pending_approvals or [])
            provider_tool_truncated = bool(gen.tool_calls_truncated)
            provider_tool_rounds = int(gen.tool_rounds or 0)

    audit_event = await _record_ai_advice_event(
        tenant_id=tenant_id,
        field_id=req.field_id,
        question=req.question,
        evidence_ids=evidence_ids,
        confidence=confidence,
        selected_imagery_date=req.selected_imagery_date,
        endpoint_mode=endpoint_mode,
    )

    # شفافيّة الـHarness (V55 المرحلة ٥): لقطة رصد صادقة يراها المستخدم — ماذا يرى
    # الوكيل، قدراته، ومستوى مشاركة البيانات. استدعاءات الأدوات فارغة هنا (حلقة
    # الأدوات المُوجَّهة بالنموذج تُوصَل لاحقاً)، لكنّ البنية والرصد حقيقيّان.
    _pack = ai_pack if isinstance(ai_pack, dict) else {}
    _readiness = _pack.get("readiness") or {}
    if _readiness.get("requires_imagery_backfill_24_months"):
        _raster_state = observation_context.RASTER_NOT_RENDERED
    elif _readiness.get("complete"):
        _raster_state = observation_context.RASTER_READY
    else:
        _raster_state = observation_context.RASTER_UNKNOWN
    _weather = _pack.get("weather_history") or {}
    _policy_raw = TENANT_POLICY.get_policy(tenant_id)
    _policy = normalize_policy(_policy_raw if isinstance(_policy_raw, dict) else {})
    observation = observation_context.build_observation(
        field_id=req.field_id,
        selected_date=req.selected_imagery_date,
        raster_state=_raster_state,
        weather_source="open-meteo" if _weather.get("available") else None,
        last_api_errors=_readiness.get("warnings"),
        policy=_policy,
    )

    # V57 — وصل حلقة الأدوات بالمسار الحيّ: النموذج/الواجهة قد يطلبان أدوات؛ الـHarness
    # يحكمها بالقدرات والمخاطر. القراءة تُنفّذ من سياق الحقل المتاح؛ الأفعال المؤثّرة
    # تُعاد كطلبات موافقة ولا تُنفَّذ داخل chat.
    tool_result = tool_loop.run_tool_calls(
        req.tool_calls,
        allowed_capabilities=_policy.get("allowed_capabilities"),
        fetcher=_build_agent_tool_fetcher(
            field_state=field_state, ai_pack=ai_pack, annotations=annotations
        ),
        tenant_id=tenant_id,
        actor="ai_agronomist",
        timestamp=_utc_timestamp(),
        audit_saver=_save_agent_tool_audit,
        approval_saver=_save_pending_approval,
        allowed_tools=_envelope_tool_gate,
    )
    all_tool_calls = list(provider_tool_calls) + list(tool_result.get("tool_calls") or [])
    all_pending_approvals = list(provider_pending_approvals) + list(
        tool_result.get("pending_approvals") or []
    )
    harness = harness_transparency.build_transparency(
        observation=observation,
        tool_calls=all_tool_calls,
        pending_approvals=all_pending_approvals,
    )

    response = {
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
        "evidence_sources": evidence_sources,
        "ai_context_pack_readiness": ai_pack.get("readiness")
        if isinstance(ai_pack, dict)
        else None,
        # V52 — surface the tenant AI policy envelope decision for transparency/audit.
        "policy_envelope_decision": policy_envelope_decision,
        "policy_envelope_present": _envelope is not None,
        "harness": harness,
        "tool_calls": all_tool_calls,
        "pending_approvals": all_pending_approvals,
        "tool_calls_truncated": bool(tool_result.get("truncated")) or provider_tool_truncated,
        "provider_tool_rounds": provider_tool_rounds,
        "confidence": confidence,
        "guardrail_result": {
            "status": "not_executed",
            "reason": "evidence-only endpoint; no decision emitted",
        },
        "audit_event": audit_event,
        "decision_authority": "field_intelligence_coordinator",
    }
    # M2 — مظروف استشاريّ مُهيكَل مُتحقَّق (مُشتقّ؛ القرار advisory_only — لا يخترعه النموذج).
    response["advisory"] = advisory_contract.build_advisory_envelope(response)
    return response


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
