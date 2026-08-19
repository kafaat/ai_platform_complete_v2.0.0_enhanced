from __future__ import annotations

import os
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import httpx
from fastapi import HTTPException

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
from .soil_sampling_planner import plan_soil_sampling
from .tenant_policies import build_store_from_env, normalize_policy
from .vra_prescription_engine import generate_vra_prescription

# Runtime evidence/advisory policy is intentionally colocated with evidence execution.
TENANT_POLICY = build_store_from_env()

RAG_BASE_URL = os.getenv("RAG_BASE_URL", "http://sahool-rag-retrieval:8000")
KNOWLEDGE_GRAPH_URL = os.getenv("KNOWLEDGE_GRAPH_URL", "http://sahool-knowledge-graph:8000")
PLATFORM_URL = os.getenv("PLATFORM_URL", "http://sahool-platform:8000")
AGENT_TOKEN = os.getenv("SAHOOL_AGENT_TOKEN", "")


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

        # SEMANTIC-CONVERGENCE-01: resolve reference KG context first, then use it only
        # to expand RAG retrieval. KG remains reference-only and never becomes decision evidence.
        kg_resp = await client.get(
            f"{KNOWLEDGE_GRAPH_URL.rstrip('/')}/v1/edges",
            params={"subject_id": req.crop} if req.crop else {},
            # C2: forward the trusted tenant so knowledge-graph enforces its C5 read
            # guard (require_trusted_tenant) on this internal service-to-service call.
            headers={"X-Tenant-Id": tenant_id},
            timeout=5.0,
        )
        if kg_resp.status_code >= 500:
            raise HTTPException(502, {"dependency": "knowledge-graph", "detail": kg_resp.text})
        # ٤xx من KG (رفض حارس المستأجر مثلاً) يُهبَط به فاشلاً-مغلقاً إلى «لا حواف»،
        # لكنّ الهبوط **يُعلَن**: بدونه يصير «KG لم يُجِب» مطابقاً حرفيّاً لـ«KG لم يجد
        # شيئاً» في الاستجابة، وكلاهما `edges: []`. وهو تدهورُ توافريّةٍ يجب أن يكون
        # صريحاً لا مُلفَّقاً دلاليّاً — فالمستهلك يقرأ ثقةً محسوبةً بلا دليل رسمٍ بيانيّ
        # ولا شيء يقول له إنّ المصدر كان غائباً.
        kg_available = kg_resp.status_code < 400
        kg_payload = kg_resp.json() if kg_available else {"edges": []}
        retrieval_query, graph_terms = _graph_conditioned_retrieval_query(req.question, kg_payload)

        rag_resp = await client.post(
            f"{RAG_BASE_URL.rstrip('/')}/v1/search",
            json={
                "tenant_id": tenant_id,
                "query": retrieval_query,
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

    rag_payload = rag_resp.json()
    annotations = {
        "rag": rag_payload.get("annotations", []),
        "knowledge_graph": kg_payload.get("edges", []),
        # ── وسمُ السلطة يقول ما يقع، لا ما نتمنّاه ──────────────────────────────
        # كُتِب أوّلاً `evidence_authority: "none"` وهو **غير صحيح من طرفٍ إلى طرف**،
        # رفعه المالك بقياسٍ لا رأي: `_extract_evidence_ids` تُدرِج كلّ حافّة KG في
        # معرّفات الأدلّة، و`_confidence_from_payloads` تمنح كلّ حافّة
        # `EvidenceStrength.KG` بوزن 0.65 — وكلاهما سابقٌ لهذه الشريحة. وأضافت هذه
        # الشريحة أثراً ثالثاً: عبارات التوسعة تُغيّر استعلام RAG، فتُغيّر الوثائق
        # المُسترجَعة ⇒ التوصيفات ⇒ معرّفات الأدلّة ⇒ الثقة.
        #
        # فالتمييز الصحيح: **سلطةُ القرار** غائبة فعلاً (لا مسار من حافّةٍ إلى مُشغِّل
        # ولا إلى اعتماد قرار)، أمّا **التأثير في اختيار الدليل** فقائم. وكتابة
        # «none» عليه كانت تُعمي قارئ الاستجابة عن أثرٍ حقيقيّ. وإسقاط KG من حساب
        # الثقة قرارٌ يسبق هذه الشريحة ويخصّ سلوكاً على `main`، فيُحكَّم مستقلّاً؛
        # والواجب هنا ألّا نصف القائم وصفاً كاذباً.
        "graph_retrieval_expansion": {
            "mode": "reference_only",
            "terms": graph_terms,
            "decision_authority": "none",
            "evidence_authority": "indirect_unverified_evidence_influence",
            "evidence_influence_paths": [
                "expansion_terms_change_rag_query_selection",
                "kg_edges_enter_evidence_ids",
                "kg_edges_contribute_to_confidence",
            ],
            "governed_relations_only": sorted(RETRIEVAL_CONTEXT_RELATIONS),
            # يفرّق «KG غاب» عن «KG لم يجد»: كلاهما `edges: []` ولا يُميَّزان بغيره.
            "knowledge_graph_available": kg_available,
        },
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
    # P1-8: يميّز «evidence-only لأنّ التوليد لم يُحاوَل» عن «حُوصِر بالسياسة» عن «حُوول وفشل» —
    # حتّى لا يبدو الجواب المُدهوَر (فشل مزوّد) كأنّه evidence-only بالتصميم. شفافيّة، لا تغيير سلوك.
    generation_status = "not_attempted"
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
                max_tool_rounds=3,
                audit_saver=save_agent_tool_audit,
                approval_saver=save_pending_approval,
                allowed_tools=_envelope_tool_gate,
            )
            # حُوول التوليد فعلاً: None ⇒ فشل مزوّد/إجابة فارغة (مُدهوَر)، لا تصميم.
            generation_status = "succeeded" if gen is not None else "attempted_failed"
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
        audit_saver=save_agent_tool_audit,
        approval_saver=save_pending_approval,
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
        # P1-8: تمييز صريح لسبب evidence-only (لم يُحاوَل/حُوصِر بالسياسة/حُوول وفشل/نجح).
        "generation_status": generation_status,
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
