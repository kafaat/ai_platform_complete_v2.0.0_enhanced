"""Platform health/readiness/metrics routes extracted from api.main.

Behavior-preserving P1 decomposition: routes keep the same paths and response
contracts, while main.py keeps only bootstrap/shared state.
"""

from __future__ import annotations

import logging

from core.api_adapter import db_probe_ok, handle_healthz, handle_readyz
from fastapi import APIRouter
from fastapi.responses import JSONResponse, PlainTextResponse

from api import main
from shared.knowledge.source_registry import readiness_check as knowledge_registry_readiness

router = APIRouter()


# Runtime identity is read from a build-time generated, read-only image file.
# Mutable runtime environment values are deliberately not trusted. Operational
# provenance surface — classified infrastructure, excluded from the domain budget.
@router.get("/runtime-identity", include_in_schema=True)
def runtime_evidence_identity():
    from shared.runtime_identity import load_build_identity

    return load_build_identity("sahool-platform")


@router.get("/healthz")
def healthz():
    """Liveness — no dependency; only process availability."""
    resp = handle_healthz()
    return JSONResponse(status_code=resp.status_code, content=resp.body)


@router.get("/metrics")
async def metrics():
    """Minimal Prometheus-compatible platform metrics endpoint."""
    db_enabled = 1 if main._DB_POOL is not None else 0
    payload = "\n".join(
        [
            *await _w301_event_relay_gauges(),
            "# HELP sahool_platform_up Platform process is serving requests",
            "# TYPE sahool_platform_up gauge",
            "sahool_platform_up 1",
            "# HELP sahool_platform_db_pool_enabled Database pool configured",
            "# TYPE sahool_platform_db_pool_enabled gauge",
            f"sahool_platform_db_pool_enabled {db_enabled}",
            "# HELP sahool_platform_rate_limit_buckets In-process rate limit bucket count",
            "# TYPE sahool_platform_rate_limit_buckets gauge",
            f"sahool_platform_rate_limit_buckets {len(main._rate_buckets)}",
            "",
        ]
    )
    return PlainTextResponse(payload, media_type="text/plain; version=0.0.4")


@router.get("/readyz")
async def readyz():
    """Readiness — checks core, the packaged knowledge registry, plus actual DB dependency."""
    resp = handle_readyz()
    # G3: سجلّ مصادر الحقيقة جزءٌ من الصورة؛ غيابه يحجب كلّ توصية ريّ ساعيّة. يُعلَن هنا
    # (503 بسببٍ يسمّي الملفّ) لا صمتاً لكلّ طلب. Missing registry ⇒ not ready.
    knowledge = knowledge_registry_readiness()
    base = dict(resp.body)
    base["checks"] = {**base.get("checks", {}), "knowledge_source_registry": knowledge}
    if not knowledge["ok"]:
        logging.error("readyz: سجلّ مصادر الحقيقة غير مقروء — %s", knowledge.get("error"))
        base["status"] = "degraded"
        return JSONResponse(status_code=503, content=base)
    if resp.status_code != 200:
        return JSONResponse(status_code=resp.status_code, content=base)
    if not await db_probe_ok(main._DB_POOL):
        body = dict(base)
        body.update({"status": "not ready", "db": "down"})
        logging.warning("readyz: فحص القاعدة فشل — not ready (503)")
        return JSONResponse(status_code=503, content=body)

    # Existing readiness surface, additive operational evidence only: expose the *effective*
    # Decision-SoR mode so a post-cutover collector can prove that this deployed platform has
    # actually demoted itself to orchestrator/BFF.  Runtime identity remains immutable and
    # separate at /runtime-identity; mutable mode state belongs on /readyz.
    from api.decision_sor_mode import get_platform_decision_sor_mode

    body = dict(base)
    body["db"] = "up" if main._DB_POOL is not None else "disabled"
    body["decision_sor"] = get_platform_decision_sor_mode().as_dict()
    # R2: additive relay state (disabled|connecting|degraded|up|reconnecting).
    body["nats"] = main.NATS_RELAY.status
    # W3-01: the held backlog is a signal (never a 503): it says what enabling the flag replays.
    body["outbox"] = await _outbox_backlog()
    # W3-01: with FEATURE_NATS_PUBLISHERS on, readiness fails closed until the stream and its
    # required consumers exist — the relay itself is held until then (NATS_PREFLIGHT.gate).
    # Flag off ⇒ "disabled" and readiness is unchanged.
    # R2 still holds after that: a missing broker does not fail readiness. Once the relay has
    # started, a failed re-check (NATS restart, reconnect) reads "degraded" with its error
    # codes and stays 200 — events wait in event_outbox and drain when the broker returns.
    preflight = await _nats_preflight()
    body["nats_preflight"] = _public_preflight(preflight)
    if preflight["status"] == "degraded":
        logging.warning(
            "readyz: NATS preflight degraded after the relay started (%s) — still ready",
            ",".join(str(e) for e in preflight.get("errors", [])),
        )
    elif preflight["status"] not in ("disabled", "passed"):
        body["status"] = "not ready"
        logging.warning(
            "readyz: NATS preflight %s (%s) — not ready (503)",
            preflight["status"],
            ",".join(str(e) for e in preflight.get("errors", [])),
        )
        return JSONResponse(status_code=503, content=body)
    return JSONResponse(status_code=resp.status_code, content=body)


async def _outbox_backlog() -> dict:
    """W3-01: event_outbox backlog signal (held / oldest age / dead letter) — read-only.

    The pool choice (jobs pool, cross-tenant like the relay) lives in ``api.event_bus``:
    routers serve tenant requests and never touch the jobs pool themselves.
    """
    from api.event_bus import probe_outbox_backlog

    return await probe_outbox_backlog()


async def _nats_preflight() -> dict:
    """W3-01: flag off ⇒ ``disabled``; flag on ⇒ the (TTL-cached) preflight result."""
    import os

    from api.event_bus import nats_publishers_enabled
    from shared.nats_stream_contract import NATS_PREFLIGHT

    flag = nats_publishers_enabled()
    if not flag:
        return NATS_PREFLIGHT.snapshot(flag=False)
    return await NATS_PREFLIGHT.refresh(
        main.NATS_RELAY.conn, flag=True, url=os.getenv("NATS_URL", "nats://sahool-nats:4222")
    )


def _public_preflight(preflight: dict) -> dict:
    """/readyz is unauthenticated: publish the verdict and error codes, not the broker topology
    (consumer names, drift values, credential facts). The full result is in the platform log
    and in ``python -m shared.nats_stream_contract preflight`` run by an operator."""
    keep = ("status", "flag", "connected", "relay", "age_seconds")
    out = {k: preflight[k] for k in keep if k in preflight}
    if "stream" in preflight:
        out["stream_exists"] = bool(preflight["stream"].get("exists"))
    if "consumers" in preflight:
        consumers = preflight["consumers"]
        out["consumers_present"] = sum(1 for v in consumers.values() if v)
        out["consumers_checked"] = len(consumers)
    if "learning_worker" in preflight:
        out["learning_worker_mode"] = preflight["learning_worker"].get("mode")
    if "errors" in preflight:
        out["errors"] = sorted({str(e).split(":", 1)[0] for e in preflight["errors"]})
    return out


def _gauge(name: str, help_text: str, value) -> list[str]:
    return [f"# HELP {name} {help_text}", f"# TYPE {name} gauge", f"{name} {value}"]


async def _w301_event_relay_gauges() -> list[str]:
    """W3-01: backlog and DLQ as gauges so a staging enablement can be watched over time
    (held should fall to ~0 after the flag flips; dead_letter should stay 0)."""
    from api.event_bus import nats_publishers_enabled
    from shared.nats_stream_contract import NATS_PREFLIGHT

    flag = nats_publishers_enabled()
    backlog = await _outbox_backlog()
    preflight = NATS_PREFLIGHT.snapshot(flag=flag)
    lines = [
        *_gauge(
            "sahool_platform_nats_publishers_enabled",
            "FEATURE_NATS_PUBLISHERS effective value",
            1 if flag else 0,
        ),
        *_gauge(
            "sahool_platform_nats_preflight_passed",
            "1 when the last NATS stream/consumer preflight passed (0 when off or failed)",
            1 if preflight.get("status") == "passed" else 0,
        ),
        *_gauge(
            "sahool_platform_outbox_backlog_probe_ok",
            "1 when the event_outbox backlog probe succeeded",
            1 if backlog.get("status") == "ok" else 0,
        ),
    ]
    if backlog.get("status") != "ok":
        return lines
    age = backlog["oldest_held_age_seconds"]
    return [
        *lines,
        *_gauge(
            "sahool_platform_outbox_held",
            "Unpublished replayable event_outbox rows",
            backlog["held"],
        ),
        *_gauge(
            "sahool_platform_outbox_dead_letter",
            "event_outbox rows that exhausted their attempts",
            backlog["dead_letter"],
        ),
        *_gauge(
            "sahool_platform_outbox_oldest_held_age_seconds",
            "Age of the oldest held event_outbox row (0 when none)",
            0 if age is None else age,
        ),
        *_gauge(
            "sahool_platform_outbox_backlog_all_tenants",
            "1 when the backlog probe sees every tenant (jobs role), 0 when RLS-scoped",
            1 if backlog["scope"] == "all_tenants" else 0,
        ),
    ]
