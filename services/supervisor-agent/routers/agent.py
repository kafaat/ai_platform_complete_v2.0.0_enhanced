"""routers/agent.py — مسارات الوكيل (استعلام/تحسين/أدوات/سجلّ/تدقيق)
======================================================================
شريحة من تفكيك ``main.py`` إلى وحدات ``APIRouter`` (سلوك محفوظ).

نُقلت المُعالِجات حرفيّاً مع تغيير ``@app`` إلى ``@router``؛ المخرجات
والمصادقة مطابقة. التبعيّات المشتركة (الحالة/المساعِدات/النماذج/السجلّ) تبقى في
``main`` وتُشار إليها عبر ``main.X``. ``register_routers(app)`` يضمّ الراوتر بلا prefix.

إصدار المسارات (API-VERSIONING-GUARD-IS-A-MIRROR-01، شريحة 2026-07-30): المسارات
الخمسة كانت غير مُصدَّرة حرفيّاً (بلا prefix على الراوتر) — /agent/query·
/agent/optimize·/agent/tools·/agent/journal/{invocation_id}·/agent/actuator-audit
صارت /v1/agent/query·/v1/agent/optimize·/v1/agent/tools·
/v1/agent/journal/{invocation_id}·/v1/agent/actuator-audit. البوّابة الخارجيّة
(/api/agent/* عبر nginx) بقيت كما هي — فقط هدف proxy_pass الداخليّ تغيّر.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import main
from circuit_breaker import CircuitOpenError
from fastapi import APIRouter, Depends, HTTPException
from tool_contracts import SideEffectClass

router = APIRouter()


@router.post("/v1/agent/query", response_model=main.AgentResponse)
async def process_query(
    query: main.AgentQuery, user: dict = Depends(main._get_current_user)
) -> main.AgentResponse:
    start_time = datetime.now(UTC)
    domain, sub_intent, confidence = await main.router.classify_intent(query.query)
    skill = main.skill_libraries.get(domain)
    if not skill:
        elapsed = int((datetime.now(UTC) - start_time).total_seconds() * 1000)
        return main.AgentResponse(
            response_ar="عذراً، لا أستطيع معالجة هذا الطلب حالياً. يرجى التواصل مع الدعم الفني.",
            confidence=0.0,
            sources=[],
            processing_time_ms=elapsed,
        )
    # الهويّة من التوكن المُتحقَّق لا من جسم الطلب (منع انتحال المستأجر)
    trusted_user_id = user.get("sub") or user.get("user_id") or query.user_id
    trusted_tenant_id = user.get("tenant_id") or query.tenant_id
    # Advisor Context Binding: حين يتوفّر field_id نُرفِق الحالة القانونيّة للحقل
    # (grounding) في السياق قبل المهارة — best-effort، يحفظ العقد تماماً (غياب
    # field_id أو تعذّر الجلب ⇒ السياق كما ورد، بلا 500 ولا حجب).
    agro_context = query.context
    if query.field_id:
        import httpx

        async with httpx.AsyncClient(timeout=10.0) as client:
            _fs = await main._fetch_field_state(client, query.field_id, trusted_tenant_id)
        agro_context = main.bind_field_context(query.context, _fs)
    try:
        result = await skill.execute(
            intent=sub_intent,
            query=query.query,
            field_id=query.field_id,
            user_id=trusted_user_id,
            tenant_id=trusted_tenant_id,
            context=agro_context,
            objectives=query.preferred_objectives,
        )
    except CircuitOpenError as e:
        # خدمة MCP خلفيّة متعطّلة (القاطع مفتوح) — تدهور لطيف بدل 500.
        # القاطع المفتوح مرصود أصلاً (مقياس + سجلّ)؛ هنا نُبقي المنصّة مستجيبة.
        main.logger.warning("circuit.degraded_response domain=%s detail=%s", domain, e)
        return main._degraded_response(start_time, domain)
    response_ar = main._format_arabic_response(result)
    # حَوكمة موحّدة: إن أنتجت المهارة إجراءات قابلة للتنفيذ، تمرّ عبر البوّابة
    # (سدّ الباب الخلفي: لا مسار توصية→أمر يتجاوز /validate).
    actions = result.get("actions", [])
    governance = None
    if actions or result.get("actionable"):
        governance = await main._validate_actions_via_guardrails(
            result, query, trusted_user_id, trusted_tenant_id
        )
    elapsed = int((datetime.now(UTC) - start_time).total_seconds() * 1000)
    return main.AgentResponse(
        response_ar=response_ar,
        response_en=result.get("en_response"),
        structured_data=result.get("structured"),
        actions_triggered=actions,
        governance=governance,
        confidence=confidence,
        sources=result.get("sources", []),
        processing_time_ms=elapsed,
    )


@router.post("/v1/agent/optimize")
async def optimize_farm(query: main.AgentQuery, user: dict = Depends(main._get_current_user)):
    start_time = datetime.now(UTC)
    if not query.field_id:
        raise HTTPException(status_code=400, detail="field_id required for optimization")
    # الهويّة من التوكن المُتحقَّق لا من جسم الطلب (منع انتحال المستأجر)
    trusted_tenant_id = user.get("tenant_id") or query.tenant_id
    rs_task = main.skill_libraries["remote_sensing"].execute(
        intent="full_analysis", field_id=query.field_id, tenant_id=trusted_tenant_id
    )
    cm_task = main.skill_libraries["crop_model"].execute(
        intent="simulate_current", field_id=query.field_id, tenant_id=trusted_tenant_id
    )
    mk_task = main.skill_libraries["market"].execute(
        intent="price_forecast", field_id=query.field_id, tenant_id=trusted_tenant_id
    )
    rs_result, cm_result, mk_result = await asyncio.gather(rs_task, cm_task, mk_task)
    scenarios = main._generate_scenarios(rs_result, cm_result, mk_result)
    pareto_front = main._pareto_optimal(scenarios, query.preferred_objectives)
    recommended = main._select_balanced(pareto_front, query.preferred_objectives)
    # حَوكمة البوّابة (الإصلاح الأعلى قيمة): التوصية تمرّ عبر Guardrails /validate
    # قبل أن تصبح قابلة للتنفيذ — البوّابة حاكمة للمسار لا خطر محلّي فقط.
    governance = await main._validate_via_guardrails(
        recommended,
        rs_result,
        cm_result,
        query,
        x_user_id=user.get("sub"),
        trusted_tenant_id=trusted_tenant_id,
    )
    elapsed = int((datetime.now(UTC) - start_time).total_seconds() * 1000)
    return {
        "pareto_options": pareto_front,
        "recommended": recommended,
        "governance": governance,  # قرار البوّابة الموحّد (LOW/MEDIUM/HIGH/CRITICAL)
        "trade_off_explanation": main._generate_tradeoff_arabic(
            recommended, pareto_front, query.preferred_objectives
        ),
        "processing_time_ms": elapsed,
        "sources": ["RUE-Estimator (FAO-56)", "Sentinel-2", "Open-Meteo", "Market Data"],
    }


@router.get("/v1/agent/tools")
async def list_tools(user: dict = Depends(main._get_current_user)):
    """يرجع كل الـtools المسجّلة + contracts. يتطلّب مصادقة (كان يكشف السجلّ علناً)."""
    tools = []
    for tool_id in main._tool_registry.list_tools():
        contract = main._tool_registry.get_contract(tool_id)
        tools.append(
            {
                "tool_id": contract.tool_id,
                "version": contract.version,
                "description": contract.description,
                "side_effects": contract.side_effects.value,
                "timeout_ms": contract.timeout_ms,
                "deterministic": contract.deterministic,
                "required_capabilities": contract.required_capabilities,
                "idempotent": contract.idempotent,
                "max_retries": contract.max_retries,
            }
        )
    return {"total": len(tools), "tools": tools}


@router.get("/v1/agent/journal/{invocation_id}")
async def get_journal_replay(invocation_id: str, user: dict = Depends(main._get_current_user)):
    """Replay لـinvocation (debug/audit) — مقصور على مستأجِر التوكن (كان مكشوفاً للجميع)."""
    tenant = user.get("tenant_id")
    entries = await main._execution_journal.replay(invocation_id)
    # عزل المستأجِر: لا نكشف سجلّ invocation لمستأجِر آخر (404 لا 403 — لا تسريب وجود).
    entries = [e for e in entries if e.tenant_id == tenant]
    if not entries:
        raise HTTPException(404, "Invocation not found")
    return {
        "invocation_id": invocation_id,
        "entries": [
            {
                "event": e.event,
                "tool_id": e.tool_id,
                "timestamp": e.timestamp,
                "tenant_id": e.tenant_id,
                "payload": e.payload,
            }
            for e in entries
        ],
    }


@router.get("/v1/agent/actuator-audit")
async def get_actuator_audit(user: dict = Depends(main._get_current_user)):
    """Audit لكلّ actuator invocations (ريّ/مضخّات). حسّاس — admin + مستأجِر التوكن.

    كان مكشوفاً بلا مصادقة وبـtenant_id من query ⇒ أيّ زائر يقرأ سجلّ actuator لأيّ مستأجِر.
    """
    if user.get("role") != "admin":
        raise HTTPException(403, "Admin role required")
    tenant_id = user.get("tenant_id")  # من التوكن لا من query
    entries = await main._execution_journal.get_entries()
    actuator_tools = set(main._tool_registry.list_by_side_effect(SideEffectClass.ACTUATOR))
    audit = [
        {
            "invocation_id": e.invocation_id,
            "tool_id": e.tool_id,
            "event": e.event,
            "timestamp": e.timestamp,
            "tenant_id": e.tenant_id,
        }
        for e in entries
        if e.tool_id in actuator_tools and e.tenant_id == tenant_id
    ]
    return {"total": len(audit), "entries": audit}
