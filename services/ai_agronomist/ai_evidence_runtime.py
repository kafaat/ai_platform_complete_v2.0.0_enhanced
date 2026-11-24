from __future__ import annotations

import asyncio
import json
import logging
import math
import os
import re
import uuid
from collections.abc import Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote

import httpx
from fastapi import HTTPException

from shared.ai.structured_advisory import (
    SCHEMA as ADVISORY_SCHEMA,
)
from shared.ai.structured_advisory import (
    AdvisoryRejected,
    model_selection_context,
    parse_model_output,
)
from shared.ai.structured_advisory import (
    digest as advisory_digest,
)
from shared.security.tenant_assertion_headers import (
    TenantAssertionError,
    tenant_assertion_headers,
)
from shared.security.trusted_tenant import (
    TrustedTenantError,
    resolve_trusted_tenant,
    service_token_ok,
)

from . import (
    advisory_contract,
    ai_generation,
    harness_transparency,
    observation_context,
    policy_envelope,
    runtime_evidence,
    tool_loop,
)
from .decision_contracts import (
    EvidenceItem,
    EvidenceStrength,
    assert_no_decision_keys,
    compose_confidence,
)
from .field_boundary_ai import propose_boundaries
from .productivity_zones import propose_productivity_zones
from .soil_sampling_planner import plan_copies_for_platform, plan_soil_sampling
from .tenant_policies import build_store_from_env, normalize_policy
from .vra_prescription_engine import generate_vra_prescription

# Runtime evidence/advisory policy is intentionally colocated with evidence execution.
TENANT_POLICY = build_store_from_env()

RAG_BASE_URL = os.getenv("RAG_BASE_URL", "http://sahool-rag-retrieval:8000")
KNOWLEDGE_GRAPH_URL = os.getenv("KNOWLEDGE_GRAPH_URL", "http://sahool-knowledge-graph:8000")
PLATFORM_URL = os.getenv("PLATFORM_URL", "http://sahool-platform:8000")

logger = logging.getLogger("ai_agronomist.evidence_runtime")

# S2 — صيغة معرّف الحقل القانونيّة (``fields.field_id VARCHAR(50)``: ``fld_<hex>`` أو UUID).
# كان المعرّف يُحقَن خاماً في مسارٍ داخليّ يحمل رمز الخدمة، فـ``../../x#`` يبلغ مسارات
# داخليّة أخرى. الفارغ مقبول = «بلا حقل». The canonical field-id shape; anything else is rejected.
FIELD_ID_PATTERN = r"^[A-Za-z0-9_-]{0,50}$"
_FIELD_ID_RE = re.compile(FIELD_ID_PATTERN)
# المقطع يُرمَّز دائماً (quote safe="") — دفاعٌ ثانٍ إن تجاوز معرّفٌ التحقّق.
_FIELD_STATE_PATH = "/internal/fields/{field_id}/state"


def is_canonical_field_id(value: Any) -> bool:
    return isinstance(value, str) and bool(value) and bool(_FIELD_ID_RE.fullmatch(value))


def _upstream_unavailable(reason: str, **log_fields: Any) -> dict[str, Any]:
    """Generic, caller-safe failure: neither the caller nor the log sees an upstream body.

    Lab receipt for #1471: the log carried ``resp.text`` and ``repr(exc)`` (a credentialed URL in
    a ConnectError). Only the reason, the HTTP status, the exception type and the correlation
    id are logged now, as ``_dependency_http_failure`` does for KG/RAG.

    S2 — كان جسم خطأ المنصّة (``resp.text``) ونصّ الاستثناء يُعادان للمتّصل عبر 502؛
    الآن يُسجَّلان خادميّاً مع معرّف ارتباط، والمتّصل يرى المعرّف وحده.
    """
    correlation_id = uuid.uuid4().hex
    logger.warning(
        "canonical field state unavailable reason=%s correlation_id=%s %s",
        reason,
        correlation_id,
        log_fields,
    )
    return {"status": "unavailable", "reason": reason, "correlation_id": correlation_id}


def _dependency_http_failure(dependency: str, upstream_status: int) -> HTTPException:
    """Return a caller-safe 502 without reflecting internal KG/RAG HTTP response bodies.

    A correlation ID ties the client error to the server's status-only log entry.
    Neither upstream payloads, credentials nor farmer questions are logged.
    """
    correlation_id = uuid.uuid4().hex
    logger.warning(
        "advisory upstream HTTP error dependency=%s upstream_status=%s correlation_id=%s",
        dependency,
        upstream_status,
        correlation_id,
    )
    return HTTPException(
        502,
        {
            "dependency": dependency,
            "reason_code": "advisory_dependency_unavailable",
            "message_ar": "تعذّر جلب أدلة المستشار؛ أعد المحاولة لاحقاً.",
            "correlation_id": correlation_id,
        },
    )


AGENT_TOKEN = os.getenv("SAHOOL_AGENT_TOKEN", "")
# W0-05: the platform's internal routes also need a tenant assertion signed with this key for
# the tenant this runtime verified (resolve_trusted_tenant), not only the shared service token.
PLATFORM_ASSERTION_SERVICE = "ai_agronomist"


def _platform_tenant_headers(tenant_id: str, method: str, path: str) -> dict[str, str] | None:
    """Signed tenant headers for a platform internal call, or None when no key is configured."""
    key = os.getenv("PLATFORM_TENANT_ASSERTION_KEY", "")
    if not key:
        return None
    try:
        return tenant_assertion_headers(
            key=key,
            key_id=os.getenv("PLATFORM_TENANT_ASSERTION_KEY_ID", "current"),
            service=PLATFORM_ASSERTION_SERVICE,
            tenant_id=tenant_id,
            method=method,
            path=path,
        )
    except TenantAssertionError:
        return None


# W0-02 (knowledge-1/x-4): rag-retrieval answers 424 TENANT_CORPUS_EMPTY when the tenant
# has no readable corpus, and 503 when retrieval is unavailable. Neither is a reason to
# fail the whole advisory request: like the KG path, the answer degrades to field-state
# evidence and *declares* ``rag_available: false`` so "RAG absent" never reads as "RAG
# found nothing". Every other status (auth/tenant refusals, 500, 502...) still fails as 502.
_RAG_DEGRADABLE_STATUSES = frozenset({424, 503})
# Only these upstream codes are echoed; anything else (raw bodies, stack text) is never
# reflected and is replaced by a status-derived code.
_RAG_UNAVAILABLE_REASON_CODES = frozenset({"TENANT_CORPUS_EMPTY", "rag_retrieval_unavailable"})


def _rag_unavailable(resp: httpx.Response) -> dict[str, Any]:
    """Caller-safe degradation record for a degradable rag-retrieval status."""
    try:
        detail = resp.json().get("detail")
    except Exception:  # noqa: BLE001 — non-JSON upstream body is never reflected
        detail = None
    code = detail.get("code") if isinstance(detail, dict) else detail
    reason_code = (
        code
        if isinstance(code, str) and code in _RAG_UNAVAILABLE_REASON_CODES
        else f"rag_upstream_http_{resp.status_code}"
    )
    correlation_id = uuid.uuid4().hex
    logger.warning(
        "advisory rag-retrieval degraded upstream_status=%s reason_code=%s correlation_id=%s",
        resp.status_code,
        reason_code,
        correlation_id,
    )
    return {
        "available": False,
        "reason_code": reason_code,
        "upstream_status": resp.status_code,
        "correlation_id": correlation_id,
    }


@asynccontextmanager
async def _dependency_boundary(dependency: str, timeout_s: float):
    """Bound the whole retrieval hop and retain its identity on transport failure."""
    try:
        async with asyncio.timeout(timeout_s):
            yield
    except (TimeoutError, httpx.TimeoutException) as exc:
        raise HTTPException(
            504,
            {
                "dependency": dependency,
                "reason_code": "advisory_dependency_timeout",
                "message_ar": "انتهت مهلة جلب أدلة المستشار؛ أعد المحاولة لاحقاً.",
            },
        ) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(
            502,
            {
                "dependency": dependency,
                "reason_code": "advisory_dependency_unavailable",
                "message_ar": "تعذّر جلب أدلة المستشار؛ أعد المحاولة لاحقاً.",
            },
        ) from exc


async def _fetch_canonical_field_state(
    client: httpx.AsyncClient, *, tenant_id: str, field_id: str | None
) -> dict[str, Any] | None:
    """Fetch CanonicalFieldState from sahool-platform through the internal S2S endpoint.

    This runtime is evidence-only. The field state is included as context and evidence; final decision
    authority remains with field_intelligence_coordinator and guardrails.
    """
    if not field_id:
        return None
    # S2 — دفاعٌ في العمق: لا يُرسَل رمز الخدمة إلى مسارٍ بُني من معرّفٍ غير قانونيّ.
    if not is_canonical_field_id(field_id):
        return {"status": "unavailable", "reason": "invalid_field_id"}
    if not AGENT_TOKEN:
        return {"status": "unavailable", "reason": "SAHOOL_AGENT_TOKEN not configured"}
    path = _FIELD_STATE_PATH.format(field_id=quote(field_id, safe=""))
    signed = _platform_tenant_headers(tenant_id, "GET", path)
    if signed is None:
        return {"status": "unavailable", "reason": "PLATFORM_TENANT_ASSERTION_KEY not configured"}
    try:
        resp = await client.get(
            PLATFORM_URL.rstrip("/") + path,
            params={"tenant_id": tenant_id, "canonical": "true", "ai_context": "true"},
            headers={"X-Agent-Token": AGENT_TOKEN, **signed},
            timeout=30.0,
        )
        if resp.status_code == 404:
            return {"status": "not_found", "field_id": field_id}
        if resp.status_code >= 400:
            return _upstream_unavailable("platform_http_error", http_status=resp.status_code)
        payload = resp.json()
        canonical = payload.get("canonical_field_state")
        pack = payload.get("ai_context_pack")
        if (
            not isinstance(canonical, dict)
            or canonical.get("schema_version") != "canonical_field_state.v1"
            or canonical.get("field_id") != field_id
            or not isinstance(pack, dict)
            or pack.get("field_id") != field_id
            or str(pack.get("tenant_id")) != tenant_id
        ):
            return {"status": "unavailable", "reason": "canonical_context_identity_mismatch"}
        return {**canonical, "ai_context_pack": pack}
    except Exception as exc:  # noqa: BLE001
        return _upstream_unavailable("platform_request_failed", error_type=type(exc).__name__)


# العلاقات المحكومة التي **دورها البيانيّ مرجعيّ ودلالتها الدليليّة سياقُ استرجاع
# فقط**، مأخوذةً بالاسم من `docs/architecture/knowledge_relation_registry.json`.
# يفرض التطابقَ `knowledge_relation_registry_guard.py`، فلا تنزلق علاقةٌ إلى هنا
# بلا تسجيل ولا يبقى الاسمان مستقلَّين يتباعدان بصمت.
RETRIEVAL_CONTEXT_RELATIONS = frozenset(
    {
        "historically_susceptible_to",
        "historically_favored_by",
        "historically_limits",
        "historically_used_for",
    }
)


def _safe_graph_expansion_terms(kg_payload: dict[str, Any], *, limit: int = 6) -> list[str]:
    """Return governed reference-relation terms for retrieval expansion only.

    An edge expands the query only when its ``relation`` is a **registered**
    retrieval-context relation.  Unknown or unregistered relations are ignored
    fail-closed, together with anything not explicitly ``confidence=reference`` and
    ``prescriptive=false``.  The terms improve recall; they never become decision
    authority, and their influence is surfaced in annotations for auditability.
    """
    terms: list[str] = []
    for row in kg_payload.get("edges", []) or []:
        if not isinstance(row, dict):
            continue
        # ── الحقلان وحدهما لا يُرشِّحان شيئاً ────────────────────────────────────
        # رفعه المالك وأصاب: `kg_store` يفرض بقيدٍ في الجدول `confidence='reference'`
        # و`prescriptive=0`، فشرطٌ عليهما يقبل **كلّ حافّةٍ يمكن للمخزن أن يحملها** —
        # حشوٌ لا مُرشِّح. و`/v1/edges` لا يُلحِق `graph_role` من السجلّ، فعلاقةٌ
        # جديدة غير مُسجَّلة كانت تدخل توسعة الاستدعاء بمجرّد كونها غير آمرة، وهي
        # الحالة الافتراضيّة للمخزن. فالتقييد صار بالاسم المُسجَّل نفسه.
        if row.get("relation") not in RETRIEVAL_CONTEXT_RELATIONS:
            continue
        if row.get("confidence") != "reference" or row.get("prescriptive") not in (False, 0):
            continue
        for key in ("object_name", "object_id"):
            value = row.get(key)
            if not isinstance(value, str):
                continue
            value = " ".join(value.replace("_", " ").split()).strip()
            if not value or len(value) > 96 or value in terms:
                continue
            terms.append(value)
            break
        if len(terms) >= limit:
            break
    return terms


def _graph_conditioned_retrieval_query(
    question: str, kg_payload: dict[str, Any]
) -> tuple[str, list[str]]:
    terms = _safe_graph_expansion_terms(kg_payload)
    if not terms:
        return question, []
    # Deliberately retrieval-only: no imperative/prescriptive wording is introduced.
    return f"{question}\nReference graph context: {'; '.join(terms)}", terms


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
    # Retrieval ranking scores (including RRF) and KG edges are not calibrated
    # confidence. Only owner-declared, usable canonical products contribute.
    items: list[EvidenceItem] = []
    if (
        not isinstance(field_state, dict)
        or field_state.get("schema_version") != "canonical_field_state.v1"
    ):
        return 0.0
    for name, strength in (
        ("soil", EvidenceStrength.LAB),
        ("weather", EvidenceStrength.WEATHER),
        ("spectral", EvidenceStrength.SATELLITE),
    ):
        product = field_state.get(name)
        if not isinstance(product, dict):
            continue
        if product.get("quality_status") not in {"validated", "verified"}:
            continue
        if product.get("operational_eligible") is False or product.get("limitations"):
            continue
        # Preserve an explicit zero. Availability alone never supplies a score.
        value = product.get("confidence")
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        if math.isfinite(value) and 0 <= value <= 1:
            items.append(EvidenceItem(strength, value, verified=True))
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
    model_output: str | None = None,
    soil_sampling_plans: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Best-effort audit event for the AI advice runtime.

    This deliberately records an AI_SUGGESTION event only. It does not create
    prescriptions, tasks, actuator commands, or recommendations. Event failure
    must not hide the advisory answer, but the status is returned for runtime
    visibility and E2E verification.
    """
    if not AGENT_TOKEN:
        return {"status": "skipped", "reason": "SAHOOL_AGENT_TOKEN not configured"}
    signed = _platform_tenant_headers(tenant_id, "POST", "/internal/events/ai-advice")
    if signed is None:
        return {"status": "skipped", "reason": "PLATFORM_TENANT_ASSERTION_KEY not configured"}
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
                    **({"model_output": model_output} if model_output is not None else {}),
                    **({"soil_sampling_plans": soil_sampling_plans} if soil_sampling_plans else {}),
                },
                headers={"X-Agent-Token": AGENT_TOKEN, **signed},
                # Plans are handed on to soil-service inside this request, so they get the
                # longer budget too.
                timeout=35.0 if model_output is not None or soil_sampling_plans else 3.0,
            )
        if resp.status_code >= 400:
            # ``audit_event`` is returned to the client: no platform body in it (review of #1471).
            return {"status": "failed", "http_status": resp.status_code}
        payload = resp.json()
        # AI-GENERATION-ATTRIBUTED-TO-SUPPRESSED-OUTPUT-01 (الصنفُ نفسُه: صمتٌ يُقرأ نجاحاً):
        # ردٌّ بلا ``persisted`` كان يُقرأ «recorded» — منصّةٌ أقدم، أو ردٌّ مُشوَّه، يصير
        # إيصالَ حفظٍ لم يُرَ. كلُّ فروع المنصّة المنشورة تُعيده اليوم (main وdeploy/*)،
        # فالغيابُ لا يصف منصّةً قائمة: يُسمّى ``unconfirmed`` لا نجاحاً ولا فشلاً.
        # والحكمُ يُكتَب **بعد** الحمولة كي لا يَغلِبه مفتاحُ ``status`` في الردّ.
        persisted = payload.get("persisted")
        if persisted is True:
            status = "recorded"
        elif persisted is False:
            status = "not_persisted"
        else:
            status = "unconfirmed"
        return {**payload, "status": status}
    except Exception as exc:  # noqa: BLE001
        # The exception text can hold a credentialed URL; the client sees only its type.
        return {"status": "failed", "reason": type(exc).__name__}


def _generation_allowed(tenant_id: str) -> bool:
    """بوّابة مزدوجة: الراية العامّة + سياسة المستأجِر (المنع الصريح يُحترَم)."""
    if not ai_generation.generation_enabled():
        return False
    return ai_generation.tenant_allows_generation(TENANT_POLICY.get_policy(tenant_id))


def _utc_timestamp() -> str:
    """وقت UTC موحّد لسجلات الأدوات (حتميّ في الاختبارات عبر حقنه خارجياً عند الحاجة)."""
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _trusted_crop_for_retrieval(
    requested_crop: str | None,
    field_state: dict[str, Any] | None,
    field_id: str | None,
) -> str | None:
    """Field queries use the owner-read crop card, not the client's claim."""
    if not field_id:
        if isinstance(requested_crop, str) and requested_crop.strip():
            return requested_crop.strip()
        return None
    pack = _extract_ai_context_pack(field_state)
    reference = (pack or {}).get("crop_knowledge") or {}
    if isinstance(reference, dict) and reference.get("status") == "reference_only":
        crop_id = reference.get("crop_id")
        if isinstance(crop_id, str) and crop_id.strip():
            return crop_id
    return None


def _trusted_region_for_generation(
    field_state: dict[str, Any] | None, field_id: str | None, tenant_id: str | None
) -> str | None:
    """A field question's region, read from the owner's field record.

    The platform's AI context pack carries the field row as ``field_profile``
    (``to_jsonb(f.*)`` in ``field_ai_context._fetch_field_profile``), so ``fields.region``
    (v33/v104) arrives with the same owner read that supplies the crop card. A general
    question has no owner record, so this returns None for it.

    The pack must name this field and this tenant. The owner read already checks that, but a
    service caller may supply ``current_field_state`` itself, and another field's region must
    not decide which approved references this question may use. ``fields.region`` is what the
    tenant saved for its own field (client value or reverse geocoding at creation), not a
    verified location; it is trusted per question only in that it is not sent with the question.
    """
    if not field_id:
        return None
    pack = _extract_ai_context_pack(field_state)
    if not isinstance(pack, dict) or pack.get("field_id") != field_id:
        return None
    if tenant_id is None or str(pack.get("tenant_id")) != str(tenant_id):
        return None
    profile = (pack or {}).get("field_profile")
    region = profile.get("region") if isinstance(profile, dict) else None
    if isinstance(region, str) and region.strip():
        return region.strip()
    return None


def _generation_scope(
    req: Any, retrieval_crop: str | None, owner_region: str | None = None
) -> dict[str, str | None]:
    """The crop and region the reference-approval gate matches an excerpt against.

    Same trust rule as retrieval: a field question takes the crop from the owner's crop card
    (``retrieval_crop``) and the region from the owner's field record (``owner_region``, from
    ``_trusted_region_for_generation``). A client-sent ``req.region`` is ignored for a field
    question, so it cannot admit an excerpt for that field; a field whose record has no region
    keeps the region unknown. A general question has no owner record, so the client's crop and
    region are its only scope.
    """
    if req.field_id:
        return {"crop": retrieval_crop, "region": owner_region or None}
    region = req.region.strip() if isinstance(req.region, str) else ""
    return {"crop": retrieval_crop, "region": region or None}


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
    from . import tool_executor

    pack = ai_pack if isinstance(ai_pack, dict) else {}
    fs = field_state if isinstance(field_state, dict) else {}

    canonical_field_id = fs.get("field_id")
    pack_field_id = pack.get("field_id")
    bound_field_id = canonical_field_id or pack_field_id

    def fetcher(tool_name: str, params: dict[str, Any]) -> Any:
        # The fetcher serves one already-authorized field snapshot. The model chooses the
        # tool, but cannot redirect field A's evidence to field B by passing another
        # field_id. A refusal raises, so tool_executor records the call as failed
        # (``fetcher_error``) with no data, instead of an executed call.
        if canonical_field_id and pack_field_id and str(canonical_field_id) != str(pack_field_id):
            raise ValueError("field_context_identity_mismatch")
        requested = params.get("field_id")
        if requested is not None and (
            not isinstance(requested, str) or not bound_field_id or requested != str(bound_field_id)
        ):
            raise ValueError("field_context_identity_mismatch")
        field_id = bound_field_id
        if tool_name == "get_field_state":
            return {
                "field_id": field_id,
                "canonical_field_state": fs,
                "crop_knowledge": pack.get("crop_knowledge") or {},
                "ai_context_readiness": pack.get("readiness") if pack else None,
            }
        if tool_name == "get_truecolor_scene":
            return tool_executor.truecolor_scene(
                pack, field_id, params.get("date"), pack.get("readiness") if pack else None
            )
        if tool_name == "get_index_timeline":
            return tool_executor.index_timeline(
                pack, field_id, params.get("index"), params.get("days")
            )
        if tool_name == "get_weather_history":
            return tool_executor.weather_history(pack, field_id, params.get("days"))
        if tool_name == "get_operation_windows":
            return tool_executor.operation_windows(pack, field_id)
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
            canonical = fs.get("canonical_field_state") if isinstance(fs, dict) else None
            # The real internal field endpoint returns {**canonical, "ai_context_pack": ...};
            # the nested form is also accepted for internal compatibility callers.
            if (
                not isinstance(canonical, dict)
                and fs.get("schema_version") == "canonical_field_state.v1"
            ):
                canonical = fs
            water_owner = canonical.get("water") if isinstance(canonical, dict) else None
            if isinstance(water_owner, dict):
                if field_id and water_owner.get("field_id") not in (None, field_id):
                    raise ValueError("canonical_water_field_identity_mismatch")
                # Read the actual owner product; do not calculate fictitious water productivity.
                for key in (
                    "depletion_mm",
                    "taw_mm",
                    "raw_mm",
                    "root_depth_m",
                    "quality_status",
                    "water_state_digest",
                    "season_id",
                    "water_productivity",
                    "water_use_efficiency",
                ):
                    if water_owner.get(key) is not None:
                        water[key] = water_owner[key]
            for key in (
                "water_balance",
                "water_deficit_mm",
                "water_deficit",
                "water_use_efficiency",
                "irrigation_mm",
                "et0_mm",
                "water_productivity",
            ):
                if key not in water:
                    for src in (fs, pack):
                        if isinstance(src, dict) and src.get(key) is not None:
                            water[key] = src[key]
                            break
            return {
                "field_id": field_id,
                "days": params.get("days"),
                "water_productivity": water,
                "available": bool(water),
                "productivity_measured": (
                    "water_productivity" in water or "water_use_efficiency" in water
                ),
                "canonical_water_owner_present": isinstance(water_owner, dict),
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
    crop_ref = pack.get("crop_knowledge") or {}
    if isinstance(crop_ref, dict) and crop_ref.get("status") == "reference_only":
        crop_label = str(crop_ref.get("crop_id"))[:80]
        digest = str(crop_ref.get("knowledge_digest"))[:24]
        lines.append(
            f"  - مرجع المحصول: {crop_label}؛ بصمة المعرفة: {digest} (مرجع عام، ليس قرارًا)."
        )
    summary = pack.get("ai_context_summary_ar")
    if summary:
        lines.append(f"  - الملخص: {str(summary)[:700]}")

    imagery = pack.get("imagery_timeline") or {}
    if isinstance(imagery, dict):
        # Older accepted packs have total_dates but not unique_scene_dates.
        # A missing unique count is unknown, not zero indicator acquisitions.
        unique = imagery.get("unique_scene_dates")
        unique_text = (
            str(unique)
            if isinstance(unique, int) and not isinstance(unique, bool) and unique >= 0
            else "غير معروف"
        )
        lines.append(
            "  - المشاهد/المؤشرات التاريخية: "
            f"{unique_text} تاريخ التقاط فريد "
            f"و{_source_count(imagery.get('total_dates'))} سجل مؤشر."
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
            # W1-22: مجموعٌ ناقص يصل `None` من الحزمة (يومٌ بلا قراءة لا يُحسَب جافّاً) — يُقال
            # «غير مكتمل» للنموذج لا «None مم».
            def _mm(value: Any) -> str:
                return f"{value} مم" if value is not None else "غير مكتمل"

            lines.append(
                "  - الطقس التاريخي: "
                f"{ws.get('days', '—')} يوم، مطر {_mm(ws.get('total_precipitation_mm'))}، "
                f"ET0 {_mm(ws.get('total_et0_mm'))}، متوسط حرارة {ws.get('avg_temp_c', '—')}°م."
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
        if readiness.get("imagery_history_absent"):
            _win = readiness.get("imagery_observed_window_days")
            _win_ar = f" خلال {_win} يوماً" if isinstance(_win, int) else ""
            lines.append(
                f"  - جاهزية الصور: لا مشهد واحد{_win_ar}؛ شغّل backfill قبل أيّ تحليل بصريّ."
            )
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


def _generation_is_grounded(annotations: dict[str, Any]) -> bool:
    """Check retrieval presence only; this does not validate any generated claim.

    حوافُّ KG وحالةُ الحقل سياقٌ مفيد لكنّها ليست شاهداً نصّيّاً يُسنَد إليه ادّعاءٌ مولَّد؛
    نصٌّ مولَّد فوق صفر مقتطفات هو توليدٌ حرّ يحمل وسمَ التأريض زوراً (RAG-10).
    """
    rag = annotations.get("rag") if isinstance(annotations, dict) else None
    if not rag:
        return False
    # مقتطفٌ بلا نصّ (بيانات وصفيّة فقط) ليس شاهداً — `_grounding_context_text` لا يُخرِج إلّا
    # text/content/snippet، فالتأريضُ يشترط أحدَها غيرَ فارغ (Copilot على #1001).
    for item in rag:
        if not isinstance(item, dict):
            continue
        text = item.get("text") or item.get("content") or item.get("snippet")
        if isinstance(text, str) and text.strip():
            return True
    return False


def _guardrail_result(mode: str, generation_status: str) -> dict[str, Any]:
    """نتيجة حواجز صادقة: لا حاجزَ يُنفَّذ في هذا المسار على أيّ نصّ.

    الفرق المعلَن: جوابُ أدلّة بلا نصّ مولَّد (لا شيء ليُحجَز) مقابل نصٍّ مولَّد أُعيد
    للمستخدم **بلا** فحص حاجز — الثانية تُسمّى باسمها بدل عبارة «لا قرار» الثابتة.
    """
    if generation_status == "validated_structured_facts":
        return {
            "status": "validated_field_facts",
            "generated_text_checked": False,
            "claim_validation": "numeric_equality_to_current_owner_snapshot",
            "decision_validation": "not_requested",
            "generation_status": generation_status,
            "executes_action": False,
        }
    if generation_status == "suppressed_unvalidated_output":
        return {
            "status": "blocked",
            "reason": "unstructured_output_has_no_claim_or_action_validation",
            "generated_text_checked": False,
            "generation_status": generation_status,
            "decision_validation": "not_executed",
        }
    if mode == "generated_grounded":
        return {
            "status": "not_executed",
            "reason": "generated text returned without guardrail evaluation",
            "generated_text_checked": False,
            "generation_status": generation_status,
        }
    return {
        "status": "not_executed",
        "reason": "evidence-only endpoint; no decision emitted",
        "generated_text_checked": None,
        "generation_status": generation_status,
    }


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


async def build_evidence_response(
    req: Any,
    *,
    endpoint_mode: str,
    x_tenant_id: str | None,
    x_agent_token: str | None = None,
    save_agent_tool_audit: Callable[[dict[str, Any]], None],
    save_pending_approval: Callable[[dict[str, Any]], None],
) -> dict[str, Any]:
    # SEC-3: the gateway-injected X-Tenant-Id is the ONLY tenant source of truth.
    # A body tenant_id may only echo it (never override); missing header or a body
    # mismatch fails closed with 403.
    try:
        tenant_id = resolve_trusted_tenant(x_tenant_id, req.tenant_id)
    except TrustedTenantError as exc:
        raise HTTPException(403, exc.code) from exc

    voice_read_only = getattr(req, "voice_read_only", False) is True
    # Establish the zero-tool voice budget before any evidence dependency runs.
    _envelope_tool_gate: set[str] = set()
    max_tool_rounds = 0 if voice_read_only else 3
    if voice_read_only and (
        not req.field_id or req.tool_calls or req.current_field_state is not None
    ):
        raise HTTPException(403, "voice_read_only_request_invalid")

    # S2 — يُرفَض المعرّف غير القانونيّ قبل أيّ نداءٍ تابع (الموديل يفرضه أيضاً).
    if req.field_id and not is_canonical_field_id(req.field_id):
        raise HTTPException(422, "invalid_field_id")

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

        # Check the current owner-fetched policy BEFORE KG/RAG or generation.
        # Voice's local-only boundary is independent of a tenant's tool grants.
        if voice_read_only:
            envelope, refusal = policy_envelope.enforce_request(
                _extract_ai_context_pack(field_state)
            )
            if (
                refusal is not None
                or envelope is None
                or envelope.get("tenant_id") != tenant_id
                or envelope.get("contract") != "sahool.ai_policy_envelope"
                or type(envelope.get("contract_version")) is not int
                or envelope["contract_version"] != 2
                or envelope.get("version") != "v52"
                or envelope.get("policy_mode") != "local_only"
                or envelope.get("external_llm_allowed") is not False
                or envelope.get("external_tts_allowed") is not False
            ):
                raise HTTPException(403, "voice_local_policy_required")

        # The tenant's active season, not the request body, selects the crop.
        retrieval_crop = _trusted_crop_for_retrieval(req.crop, field_state, req.field_id)
        # The same owner read gives a field question its region (never the client's).
        retrieval_region = _trusted_region_for_generation(field_state, req.field_id, tenant_id)
        kg_available = False
        kg_payload = {"edges": []}
        kg_failure = {}
        if retrieval_crop:
            try:
                async with _dependency_boundary("knowledge-graph", 5.0):
                    kg_resp = await client.get(
                        f"{KNOWLEDGE_GRAPH_URL.rstrip('/')}/v1/edges",
                        params={"subject_id": retrieval_crop},
                        # C2: forward the verified tenant to knowledge-graph's C5 read guard;
                        # the owner-canonical crop scopes reference retrieval, never the client crop.
                        headers={"X-Tenant-Id": tenant_id},
                        timeout=5.0,
                    )
            except HTTPException as exc:
                # Only field-grounded advice can continue without the reference graph.
                if (
                    not req.field_id
                    or not field_state
                    or not isinstance(
                        exc.__cause__, (TimeoutError, httpx.NetworkError, httpx.TimeoutException)
                    )
                ):
                    raise
                correlation_id = uuid.uuid4().hex
                kg_failure = {
                    "reason_code": exc.detail["reason_code"],
                    "correlation_id": correlation_id,
                    "upstream_status": None,
                }
                logger.warning("KG transport unavailable correlation_id=%s", correlation_id)
            else:
                if kg_resp.status_code in (401, 403) or kg_resp.status_code >= 500:
                    raise _dependency_http_failure("knowledge-graph", kg_resp.status_code)
                kg_available = kg_resp.status_code < 400
                kg_payload = kg_resp.json() if kg_available else {"edges": []}
        retrieval_query, graph_terms = _graph_conditioned_retrieval_query(req.question, kg_payload)

        rag_resp: httpx.Response | None = None
        rag_retrieval: dict[str, Any] = {"available": True}
        try:
            async with _dependency_boundary("rag-retrieval", 10.0):
                rag_resp = await client.post(
                    f"{RAG_BASE_URL.rstrip('/')}/v1/search",
                    json={
                        "tenant_id": tenant_id,
                        "query": retrieval_query,
                        "crop": retrieval_crop,
                        "field_id": req.field_id,
                        # A field question filters by the owner's region, not the client's.
                        "region": retrieval_region if req.field_id else req.region,
                        "source_type": None,
                        "final_k": req.final_k,
                    },
                    # SEC-3: forward the trusted tenant so rag-retrieval enforces the same
                    # X-Tenant-Id-source-of-truth guard on this internal service-to-service call.
                    headers={"X-Tenant-Id": tenant_id, "X-Agent-Token": AGENT_TOKEN},
                    timeout=10.0,
                )
        except HTTPException as exc:
            detail = exc.detail
            if (
                exc.status_code not in (502, 504)
                or not isinstance(detail, dict)
                or detail.get("dependency") != "rag-retrieval"
                or detail.get("reason_code")
                not in ("advisory_dependency_unavailable", "advisory_dependency_timeout")
            ):
                raise
            # Transport errors have no HTTP response. An absent optional RAG host must
            # not prevent field-state advice. Never degrade an upstream HTTP 401/403:
            # those are processed below and remain fail-closed.
            correlation_id = uuid.uuid4().hex
            transport_reason = detail["reason_code"]
            logger.warning(
                "advisory rag-retrieval degraded transport_reason=%s correlation_id=%s",
                transport_reason,
                correlation_id,
            )
            rag_retrieval = {
                "available": False,
                "reason_code": "rag_transport_unavailable",
                "upstream_status": None,
                "transport_reason": transport_reason,
                "correlation_id": correlation_id,
            }
        if rag_resp is not None:
            if rag_resp.status_code in _RAG_DEGRADABLE_STATUSES:
                rag_retrieval = _rag_unavailable(rag_resp)
            elif rag_resp.status_code >= 400:
                raise _dependency_http_failure("rag-retrieval", rag_resp.status_code)

    from shared.ai.seed_claims import partition_generation_references

    rag_available = rag_retrieval["available"] is True
    rag_payload = rag_resp.json() if rag_available else {"annotations": []}
    # Keep unreviewed seed pointers auditable while excluding their claim text from generation.
    usable, unreviewed = partition_generation_references(
        rag_payload.get("annotations") or [],
        **_generation_scope(req, retrieval_crop, retrieval_region),
    )
    rag_payload = {**rag_payload, "annotations": usable}
    annotations = {
        "rag": rag_payload.get("annotations", []),
        "unverified_seed_references": unreviewed,
        "knowledge_graph": kg_payload.get("edges", []),
        # KG can change retrieval selection and reference IDs, but contributes
        # no measurement confidence and holds no decision authority.
        "graph_retrieval_expansion": {
            "mode": "reference_only",
            "terms": graph_terms,
            "decision_authority": "none",
            "evidence_authority": "indirect_unverified_evidence_influence",
            "evidence_influence_paths": [
                "expansion_terms_change_rag_query_selection",
                "kg_edges_enter_evidence_ids",
                "kg_edges_are_reference_only",
            ],
            "governed_relations_only": sorted(RETRIEVAL_CONTEXT_RELATIONS),
            # يفرّق «KG غاب» عن «KG لم يجد»: كلاهما `edges: []` ولا يُميَّزان بغيره.
            "knowledge_graph_available": kg_available,
            **kg_failure,
        },
        # W0-02: "RAG absent" is declared, never disguised as "RAG found nothing".
        "rag_retrieval": rag_retrieval,
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
    # Missing/malformed tenant envelope must never become allowed_tools=None:
    # tool_loop treats None as a backwards-compatible unrestricted envelope gate.
    if not voice_read_only:
        _envelope_tool_gate = policy_envelope.enforced_allowed_tools(_envelope)
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
    available_sources = [s["label_ar"] for s in evidence_sources if s.get("available")]
    answer_ar = (
        "المصادر المتاحة: " + "، ".join(available_sources) + "."
        if available_sources
        else "لم تتوفر أدلة كافية للإجابة عن السؤال."
    )
    answer_ar += " أي توصية تنفيذية تحتاج تقييماً من منسّق ذكاء الحقل والحواجز."

    # توليد اختياريّ مؤرَّض فوق الأدلّة (مسار OpenRouter/سحابيّ) — خلف راية عامّة +
    # سياسة المستأجِر، بمفتاح من البيئة، مع سقوط آمن إلى جواب الأدلّة أعلاه عند أيّ
    # غياب/فشل. RAG+KG تبقى طبقة التأصيل الأساسيّة (تُمرَّر كأدلّة للنموذج).
    mode = "evidence_only"
    # P1-8: يميّز «evidence-only لأنّ التوليد لم يُحاوَل» عن «حُوصِر بالسياسة» عن «حُوول وفشل» —
    # حتّى لا يبدو الجواب المُدهوَر (فشل مزوّد) كأنّه evidence-only بالتصميم. شفافيّة، لا تغيير سلوك.
    generation_status = "not_attempted"
    # AI-GENERATION-ATTRIBUTED-TO-SUPPRESSED-OUTPUT-01: ما **حُووِل** (قياس) منفصلٌ عمّا **عُرِض**
    # (نسبة). النموذجُ الذي أُخمِد خرجُه لا يُنسَب إليه الجوابُ الظاهر — الواجهةُ ترسم
    # «المزوّد · النموذج» على كلّ جوابٍ يحمل ``generation_provider``.
    generation_attempted_model: str | None = None
    generation_attempted_provider: str | None = None
    provider_tool_calls: list[dict[str, Any]] = []
    provider_pending_approvals: list[dict[str, Any]] = []
    provider_tool_truncated = False
    provider_tool_rounds = 0
    model_output = None
    # F8 — stored owner-engine proposals, shown for specialist review only (flag OFF by
    # default). Read from the platform; never computed here, never given to the model below
    # (its candidate list stays empty), never approved, executed or written.
    from .engine_proposal_client import fetch_engine_proposals

    engine_proposals = await fetch_engine_proposals(
        tenant_id=tenant_id,
        field_id=req.field_id,
        endpoint_mode=endpoint_mode,
        platform_url=PLATFORM_URL,
        agent_token=AGENT_TOKEN,
        sign=_platform_tenant_headers,
        voice_read_only=voice_read_only,
    )
    if endpoint_mode == "chat" and _generation_allowed(tenant_id):
        context_text = _grounding_context_text(annotations)
        selection = None
        if req.field_id and isinstance(field_state, dict):
            try:
                selection = model_selection_context(
                    tenant_id=tenant_id, field_id=req.field_id, state=field_state, candidates=[]
                )
                if selection["available_claims"]:
                    context_text += "\n\n" + json.dumps(selection, ensure_ascii=False)
                else:
                    selection = None
            except AdvisoryRejected:
                selection = None
        _policy_for_generation = normalize_policy(TENANT_POLICY.get_policy(tenant_id))
        # Resolve the provider up-front so the envelope gates generation fail-closed:
        # a missing/invalid envelope blocks local and external providers; a valid
        # local_only envelope permits local generation while blocking external calls.
        _cfg = ai_generation.resolve_generation(req.model)
        _external = _cfg is not None and ai_generation.provider_is_external(_cfg.provider)
        _gen_gate = policy_envelope.gate_generation(_envelope, external=_external)
        policy_envelope_decision = _gen_gate
        if voice_read_only and _external:
            raise HTTPException(403, "voice_external_generation_forbidden")
        if _gen_gate["decision"] == policy_envelope.DECISION_BLOCKED:
            # Fail-closed: do not call a generation provider; stay on the evidence-only answer.
            gen = None
            generation_status = "blocked_by_policy"
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
                max_tool_rounds=max_tool_rounds,
                audit_saver=save_agent_tool_audit,
                approval_saver=save_pending_approval,
                allowed_tools=_envelope_tool_gate,
            )
            # حُوول التوليد فعلاً: None ⇒ فشل مزوّد/إجابة فارغة (مُدهوَر)، لا تصميم.
            generation_status = "succeeded" if gen is not None else "attempted_failed"
            if _cfg is not None:
                # المحاولةُ تُقاس ولو فشلت (مراجعةٌ مستقلّة): المُهيَّأ هنا، وما أجاب فعلاً يَغلِبه أدناه.
                generation_attempted_provider = _cfg.provider
                generation_attempted_model = _cfg.model
        if gen is not None:
            # Guardrails accepts typed proposals from the decision owner. A
            # retrieved paragraph does not prove that arbitrary model prose is
            # entailed or safe. Keep tool receipts, but never publish unchecked
            # free text as a grounded recommendation.
            generation_status = (
                "suppressed_unvalidated_output"
                if _generation_is_grounded(annotations)
                else "suppressed_ungrounded"
            )
            generation_attempted_model = gen.model
            if selection is not None:
                try:
                    parsed = parse_model_output(gen.text)
                    if (
                        parsed["field_id"] == req.field_id
                        and parsed["evidence_fingerprint"] == selection["evidence_fingerprint"]
                        and not parsed["candidate_ids"]
                    ):
                        model_output = gen.text
                except AdvisoryRejected:
                    pass  # Unstructured or malformed output stays suppressed.
            generation_attempted_provider = gen.provider
            provider_tool_calls = list(gen.tool_calls or [])
            provider_pending_approvals = list(gen.pending_approvals or [])
            provider_tool_truncated = bool(gen.tool_calls_truncated)
            provider_tool_rounds = int(gen.tool_rounds or 0)

    # V57 — وصل حلقة الأدوات بالمسار الحيّ: النموذج/الواجهة قد يطلبان أدوات؛ الـHarness
    # يحكمها بالقدرات والمخاطر. القراءة تُنفّذ من سياق الحقل المتاح؛ الأفعال المؤثّرة
    # تُعاد كطلبات موافقة ولا تُنفَّذ داخل chat.
    # Read tools may run CPU-bound work (k-means zoning, sampling plans), so the loop runs
    # in a worker thread and never blocks the event loop serving other requests.
    _policy_raw = TENANT_POLICY.get_policy(tenant_id)
    _policy = normalize_policy(_policy_raw if isinstance(_policy_raw, dict) else {})
    tool_result = await asyncio.to_thread(
        tool_loop.run_tool_calls,
        req.tool_calls,
        allowed_capabilities=_policy.get("allowed_capabilities"),
        fetcher=_build_agent_tool_fetcher(
            field_state=field_state, ai_pack=ai_pack, annotations=annotations
        ),
        tenant_id=tenant_id,
        actor="ai_agronomist",
        timestamp=_utc_timestamp(),
        audit_saver=save_agent_tool_audit,
        approval_saver=save_pending_approval,
        allowed_tools=_envelope_tool_gate,
    )
    # The planner's plans travel with the advice event; the platform hands them to soil-service,
    # which stores the copy before the client can name one of their points on a lab sample.
    sampling_plans = plan_copies_for_platform(
        list(provider_tool_calls) + list(tool_result.get("tool_calls") or []), req.field_id
    )
    audit_event = await _record_ai_advice_event(
        tenant_id=tenant_id,
        field_id=req.field_id,
        question=req.question,
        evidence_ids=evidence_ids,
        confidence=confidence,
        selected_imagery_date=req.selected_imagery_date,
        endpoint_mode=endpoint_mode,
        **({"model_output": model_output} if model_output is not None else {}),
        **({"soil_sampling_plans": sampling_plans} if sampling_plans else {}),
    )
    validation = audit_event.get("advisory_validation")
    if model_output is not None and isinstance(validation, dict):
        if (
            audit_event.get("persisted") is True
            and validation.get("status") == "verified"
            and validation.get("schema_version") == ADVISORY_SCHEMA
            and validation.get("model_output_digest") == advisory_digest(model_output)
            and validation.get("tenant_id") == tenant_id
            and validation.get("field_id") == req.field_id
            and validation.get("executes_action") is False
            and validation.get("creates_decision") is False
            and validation.get("candidate_previews") == []
            and isinstance(validation.get("claims"), list)
            and validation["claims"]
            and isinstance(validation.get("answer_ar"), str)
            and validation["answer_ar"].strip()
        ):
            answer_ar = validation["answer_ar"]
            mode = "validated_field_facts"
            generation_status = "validated_structured_facts"
    if validation is not None and generation_status != "validated_structured_facts":
        # The receipt is public too: withheld claims must not leak through metadata.
        validation = {"status": "blocked", "reason": "advisory_receipt_not_accepted"}
        audit_event = {**audit_event, "advisory_validation": validation}

    # شفافيّة الـHarness (V55 المرحلة ٥): لقطة رصد صادقة يراها المستخدم — ماذا يرى
    # الوكيل، قدراته، ومستوى مشاركة البيانات. استدعاءات الأدوات فارغة هنا (حلقة
    # الأدوات المُوجَّهة بالنموذج تُوصَل لاحقاً)، لكنّ البنية والرصد حقيقيّان.
    _pack = ai_pack if isinstance(ai_pack, dict) else {}
    _readiness = _pack.get("readiness") or {}
    if _readiness.get("imagery_history_absent"):
        _raster_state = observation_context.RASTER_NOT_RENDERED
    elif _readiness.get("complete"):
        _raster_state = observation_context.RASTER_READY
    else:
        _raster_state = observation_context.RASTER_UNKNOWN
    _weather = _pack.get("weather_history") or {}
    observation = observation_context.build_observation(
        field_id=req.field_id,
        selected_date=req.selected_imagery_date,
        raster_state=_raster_state,
        # مصدرُ الطقس كما أعلنته الحزمة (weather-service منذ W1-22) لا اسمُ مزوّدٍ ثابت.
        weather_source=(
            (_weather.get("source") or "weather-service") if _weather.get("available") else None
        ),
        last_api_errors=_readiness.get("warnings"),
        policy=_policy,
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

    generation_surfaced = generation_status == "validated_structured_facts"
    response = {
        "status": "ok",
        "mode": mode,
        # P1-8: تمييز صريح لسبب evidence-only (لم يُحاوَل/حُوصِر بالسياسة/حُوول وفشل/نجح).
        "generation_status": generation_status,
        "endpoint_mode": endpoint_mode,
        "answer_ar": answer_ar,
        "message": answer_ar,
        "tenant_id": tenant_id,
        "field_id": req.field_id,
        "retrieval_crop": retrieval_crop,
        "selected_imagery_date": req.selected_imagery_date,
        "selected_model": req.model,
        # النسبةُ للجواب الظاهر فقط؛ المحاولةُ تبقى مقيسةً في ``generation_attempted_*``.
        "generation_surfaced": generation_surfaced,
        "generation_model": generation_attempted_model if generation_surfaced else None,
        "generation_provider": generation_attempted_provider if generation_surfaced else None,
        "generation_attempted_model": generation_attempted_model,
        "generation_attempted_provider": generation_attempted_provider,
        "language": req.language,
        "annotations": annotations,
        "evidence_ids": evidence_ids,
        "evidence_sources": evidence_sources,
        "rag_available": rag_available,
        "rag_unavailable_reason": None if rag_available else rag_retrieval["reason_code"],
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
        "confidence_basis": "owner_reported_evidence_quality",
        "confidence_calibrated": False,
        # The publication boundary is separate from typed decision validation.
        "guardrail_result": _guardrail_result(mode, generation_status),
        "advisory_validation": validation,
        "audit_event": audit_event,
        "decision_authority": "field_intelligence_coordinator",
        "engine_proposals": engine_proposals,
    }
    # M2 — مظروف استشاريّ مُهيكَل مُتحقَّق (مُشتقّ؛ القرار advisory_only — لا يخترعه النموذج).
    response["advisory"] = advisory_contract.build_advisory_envelope(response)
    return response
