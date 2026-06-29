"""routers/health.py — مسارات الصحّة والجاهزيّة والمقاييس (Health/Readiness/Metrics)
======================================================================
شريحة من تفكيك ``main.py`` إلى وحدات ``APIRouter`` (سلوك محفوظ).

نُقلت المُعالِجات حرفيّاً مع تغيير ``@app`` إلى ``@router``؛ المسارات/المخرجات
مطابقة. التبعيّات المشتركة تبقى في ``main`` وتُشار إليها عبر ``main.X``.
``register_routers(app)`` يضمّ الراوتر بلا prefix.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Response

router = APIRouter()


@router.get("/healthz")
@router.get("/health")
async def healthz():
    return {"status": "alive", "service": "supervisor-agent"}


@router.get("/readyz")
async def readyz():
    # بلا تبعيّة صلبة قصداً: مُنسِّق بلا قاعدة؛ خدمات MCP الخلفيّة تُعالَج بتدهور
    # لطيف عبر قواطع الدائرة (لا تُعطِّل الجاهزيّة). صحّة تلك التبعيّات تُكشَف في
    # /health (يردّ 503 عند فتح قاطع). لا شيء صلب ننتظره هنا ⇒ جاهز بصدق.
    return {"status": "ready", "version": "9.1.0"}


@router.get("/metrics")
async def metrics():
    """مقاييس Prometheus (تتضمّن حالة قواطع MCP). Prometheus يسحب هذه النقطة
    أصلاً (scrape config: job supervisor-agent، metrics_path /metrics)."""
    from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@router.get("/healthz/deps")
async def healthz_deps():
    """صحّة التبعيّات الخلفيّة عبر حالة قواطع MCP.

    تشغيليّاً: يردّ 503 (degraded) إن كان أيّ قاطع مفتوحاً — أيّ خدمة MCP
    تُعتبر متعطّلة الآن — فيلتقطه الـreadiness/Alertmanager بدل العمى. القاطع
    المفتوح يعني أنّ المنصّة تردّ fail-fast لتلك الخدمة وقد تكون متدهورة جزئيّاً.
    """
    from circuit_breaker import CircuitState, mcp_breakers

    breakers = mcp_breakers.status_all()
    open_services = [b["name"] for b in breakers if b["state"] == CircuitState.OPEN.value]
    degraded = bool(open_services)
    body = {
        "status": "degraded" if degraded else "ok",
        "service": "supervisor-agent",
        "open_circuits": open_services,
        "breakers": breakers,
    }
    return Response(
        content=json.dumps(body, ensure_ascii=False),
        media_type="application/json",
        status_code=503 if degraded else 200,
    )
