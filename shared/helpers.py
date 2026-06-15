"""
SAHOOL v9.0 — shared/helpers.py (v8 + v9 مدمج)
════════════════════════════════════════════════
v8 foundation + v9 security improvements:
  - init_db, get_pool, close_pool
  - init_redis, get_redis, close_redis
  - init_nats, get_nats, close_nats
  - enforce_tenant, query_with_tenant, execute_with_tenant (FIXED: no SQL injection)
  - service_lifespan, add_probes, setup_prometheus
  - cached, publish_event, dispatch, wrapped_send, get_data
  - validate_role (Literal), check_rate_limit, create_app
"""

from __future__ import annotations

import asyncio
import hashlib as _hashlib
import json as _json
import logging
import os
import re
import time
import uuid as _uuid
from collections import defaultdict
from collections.abc import Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from functools import wraps
from typing import Literal

import asyncpg
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from starlette.middleware.base import BaseHTTPMiddleware as _BaseHTTPMiddleware


# ── Logging ────────────────────────────────────────────────────
def setup_logging(service_name: str, level: str = "INFO") -> logging.Logger:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format=f'{{"time":"%(asctime)s","svc":"{service_name}","level":"%(levelname)s","msg":"%(message)s"}}',
    )
    return logging.getLogger(service_name)


# ── Database ───────────────────────────────────────────────────
_db_pool: asyncpg.Pool | None = None


async def init_db(dsn: str | None = None, min_size: int = 2, max_size: int = 10) -> asyncpg.Pool:
    global _db_pool
    if _db_pool is not None:
        return _db_pool
    url = dsn or os.getenv("DATABASE_URL", "")
    if not url:
        raise RuntimeError("DATABASE_URL not set")
    # FIX: statement_cache_size معامل عميل asyncpg لا إعداد خادم؛ تمريره في
    # server_settings يجعل asyncpg ينفّذ SET statement_cache_size فيفشل الاتصال
    # بـ"unrecognized configuration parameter" ضد أي Postgres. (=0 لتوافق pgbouncer.)
    # FIX (تسابق الإقلاع المتزامن): حزام أمان فوق depends_on:service_healthy —
    # عند تشغيل كل الحاويات معاً قد تتأخّر Postgres لحظةً؛ أعد المحاولة بتراجع
    # أسّي بدل تعطّل الخدمة فوراً. (URL خطأ/مرفوض دائماً ⇒ يرمي بعد المحاولات.)
    last_err: Exception | None = None
    for attempt in range(6):
        try:
            _db_pool = await asyncpg.create_pool(
                url, min_size=min_size, max_size=max_size,
                command_timeout=30, statement_cache_size=0,
            )
            return _db_pool
        except (OSError, asyncpg.PostgresError) as e:
            last_err = e
            delay = min(2**attempt, 20)
            logging.warning(
                "init_db: Postgres غير جاهز (محاولة %d/6): %s — إعادة بعد %ds",
                attempt + 1, e, delay,
            )
            await asyncio.sleep(delay)
    raise RuntimeError(f"init_db: تعذّر الاتصال بـPostgres بعد 6 محاولات: {last_err}")


async def get_pool() -> asyncpg.Pool:
    if _db_pool is None:
        return await init_db()
    return _db_pool


get_db_pool = get_pool


async def close_pool():
    global _db_pool
    if _db_pool:
        await _db_pool.close()
        _db_pool = None


# ── Redis ──────────────────────────────────────────────────────
_redis_client = None


async def init_redis(url: str | None = None):
    global _redis_client
    try:
        import redis.asyncio as aioredis

        redis_url = url or os.getenv("REDIS_URL", "redis://sahool-redis:6379/0")
        _redis_client = aioredis.from_url(redis_url, encoding="utf-8", decode_responses=True)
        await _redis_client.ping()
    except Exception as e:
        logging.warning(f"Redis unavailable: {e}")
        _redis_client = None
    return _redis_client


def get_redis():
    return _redis_client


async def close_redis():
    global _redis_client
    if _redis_client:
        await _redis_client.close()
        _redis_client = None


# ── NATS ───────────────────────────────────────────────────────
_nats_conn = None


async def init_nats(url: str | None = None):
    global _nats_conn
    try:
        import nats

        nats_url = url or os.getenv("NATS_URL", "nats://sahool-nats:4222")
        _nats_conn = await nats.connect(nats_url)
    except Exception as e:
        logging.warning(f"NATS unavailable: {e}")
    return _nats_conn


def get_nats():
    return _nats_conn


async def close_nats():
    global _nats_conn
    if _nats_conn and not _nats_conn.is_closed:
        await _nats_conn.close()
        _nats_conn = None


# ── Tenant Isolation (FIXED: no SQL injection) ─────────────────
_TENANT_RE = re.compile(r"^[a-zA-Z0-9_\-]{1,64}$")


def _validate_tenant_id(tenant_id: str) -> str:
    if not tenant_id or not _TENANT_RE.match(tenant_id):
        raise ValueError(f"Invalid tenant_id: {tenant_id!r}")
    return tenant_id


@asynccontextmanager
async def tenant_context(conn: asyncpg.Connection, tenant_id: str):
    safe = _validate_tenant_id(tenant_id)
    await conn.execute("SELECT set_config('app.current_tenant', $1, true)", safe)
    try:
        yield conn
    finally:
        await conn.execute("SELECT set_config('app.current_tenant', '', true)")


async def enforce_tenant(conn: asyncpg.Connection, tenant_id: str):
    safe = _validate_tenant_id(tenant_id)
    await conn.execute("SELECT set_config('app.current_tenant', $1, true)", safe)


async def require_tenant(request: Request) -> str:
    payload = getattr(request.state, "jwt_payload", {})
    tid = payload.get("tenant_id", "")
    if not tid:
        raise HTTPException(400, "tenant_id missing")
    return _validate_tenant_id(tid)


async def query_with_tenant(conn, tenant_id: str, query: str, *args):
    async with tenant_context(conn, tenant_id):
        return await conn.fetch(query, *args)


async def execute_with_tenant(conn, tenant_id: str, query: str, *args):
    async with tenant_context(conn, tenant_id):
        return await conn.execute(query, *args)


# ── Role Validation (v9 NEW) ───────────────────────────────────
ValidRole = Literal["admin", "expert", "farmer", "viewer"]
VALID_ROLES = {"admin", "expert", "farmer", "viewer"}


def validate_role(role: str) -> str:
    if role not in VALID_ROLES:
        logging.warning(f"Invalid role: {role!r} -> farmer")
        return "farmer"
    return role


# ── Prometheus ─────────────────────────────────────────────────
_REQUEST_COUNT: Counter | None = None
_REQUEST_LATENCY: Histogram | None = None


def setup_prometheus(service_name: str):
    global _REQUEST_COUNT, _REQUEST_LATENCY
    _REQUEST_COUNT = Counter(
        "sahool_http_requests_total", "HTTP requests", ["service", "method", "path", "status"]
    )
    _REQUEST_LATENCY = Histogram(
        "sahool_http_request_duration_seconds", "Latency", ["service", "path"]
    )
    return _REQUEST_COUNT, _REQUEST_LATENCY


def metrics(service_name: str):
    async def _mw(request: Request, call_next) -> Response:
        if request.url.path in ("/metrics", "/healthz", "/readyz"):
            return await call_next(request)
        start = time.perf_counter()
        response = await call_next(request)
        elapsed = time.perf_counter() - start
        if _REQUEST_COUNT:
            _REQUEST_COUNT.labels(
                service=service_name,
                method=request.method,
                path=request.url.path,
                status=response.status_code,
            ).inc()
        if _REQUEST_LATENCY:
            _REQUEST_LATENCY.labels(service=service_name, path=request.url.path).observe(elapsed)
        response.headers["X-Response-Time"] = f"{elapsed * 1000:.1f}ms"
        return response

    return _mw


make_metrics_middleware = metrics


def add_probes(app: FastAPI, pool_getter=None, service_name: str = "service"):
    @app.get("/healthz")
    @app.get("/health")
    async def _health():
        return {"status": "alive", "service": service_name}

    @app.get("/readyz")
    async def _ready():
        if pool_getter:
            try:
                p = (
                    await pool_getter()
                    if asyncio.iscoroutinefunction(pool_getter)
                    else pool_getter()
                )
                async with p.acquire() as c:
                    await c.fetchval("SELECT 1")
            except Exception as e:
                raise HTTPException(503, f"Not ready: {e}") from e
        return {"status": "ready", "service": service_name}

    @app.get("/metrics")
    async def _metrics():
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


# ── Lifespan ───────────────────────────────────────────────────
def service_lifespan(
    app_or_db=None,
    *args,
    with_db: bool = True,
    with_redis: bool = True,
    with_nats: bool = False,
    **kwargs,
):
    @asynccontextmanager
    async def lifespan(_app_inner=None):
        if with_db:
            await init_db()
        if with_redis:
            await init_redis()
        if with_nats:
            await init_nats()
        yield
        if with_db:
            await close_pool()
        if with_redis:
            await close_redis()
        if with_nats:
            await close_nats()

    return lifespan


# ── NATS Events ────────────────────────────────────────────────
async def publish_event(subject: str, data: dict, service: str = "unknown") -> bool:
    nc = get_nats()
    if not nc or nc.is_closed:
        return False
    try:
        js = nc.jetstream()
        await js.publish(subject, _json.dumps(data, ensure_ascii=False).encode())
        return True
    except Exception as e:
        logging.warning(f"[{service}] NATS {subject}: {e}")
        return False


async def dispatch(
    event_type: str, data: dict, tenant_id: str = "", service: str = "unknown"
) -> bool:
    subject = f"sahool.tenant.{tenant_id or 'default'}.{event_type}"
    return await publish_event(
        subject,
        {
            "event_type": event_type,
            "tenant_id": tenant_id,
            "data": data,
            "timestamp": datetime.now(UTC).isoformat(),
        },
        service=service,
    )


async def wrapped_send(method: str, url: str, payload: dict, headers: dict | None = None) -> dict:
    import httpx

    async with httpx.AsyncClient(timeout=30) as c:
        r = await getattr(c, method.lower())(url, json=payload, headers=headers or {})
        r.raise_for_status()
        return r.json()


# ── Caching ────────────────────────────────────────────────────
def cached(ttl_seconds: int = 300, prefix: str = "cache"):
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            rc = get_redis()
            if not rc:
                return await func(*args, **kwargs)
            # M5 FIX: hash() المدمج مُعشّى لكلّ عمليّة (PYTHONHASHSEED) ⇒ مفاتيح
            # مختلفة لنفس المدخل عبر العمّال (كاش لا يُشارَك) + تصادمات. نستخدم
            # بصمة sha256 مستقرّة عبر العمليّات.
            _raw = (str(args) + str(sorted(kwargs.items()))).encode("utf-8")
            key = f"{prefix}:{func.__name__}:{_hashlib.sha256(_raw).hexdigest()[:16]}"
            try:
                v = await rc.get(key)
                if v:
                    return _json.loads(v)
            except Exception as e:  # noqa: BLE001 — كاش best-effort: الفشل ⇒ إعادة الحساب
                logging.getLogger("sahool.cache").debug("cache get فشل (%s) — إعادة حساب", e)
            result = await func(*args, **kwargs)
            try:
                await rc.setex(key, ttl_seconds, _json.dumps(result, ensure_ascii=False))
            except Exception as e:  # noqa: BLE001 — كاش best-effort: فشل الكتابة لا يكسر النتيجة
                logging.getLogger("sahool.cache").debug("cache set فشل (%s)", e)
            return result

        return wrapper

    return decorator


async def get_data(key: str, default=None):
    rc = get_redis()
    if not rc:
        return default
    try:
        v = await rc.get(key)
        return _json.loads(v) if v else default
    except Exception:
        return default


# ── Rate Limiting (v9) ─────────────────────────────────────────
_rate_store: dict[str, list] = defaultdict(list)


def check_rate_limit(key: str, max_requests: int = 5, window_seconds: int = 60) -> bool:
    now = datetime.now(UTC)
    window = now - timedelta(seconds=window_seconds)
    _rate_store[key] = [t for t in _rate_store[key] if t > window]
    if len(_rate_store[key]) >= max_requests:
        return False
    _rate_store[key].append(now)
    return True


# ── App factory ────────────────────────────────────────────────
def create_app(
    service_name: str,
    version: str = "9.0.0",
    with_db: bool = True,
    with_redis: bool = True,
    with_nats: bool = False,
) -> FastAPI:
    cors_origins = os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
    app = FastAPI(
        title=f"SAHOOL {service_name}",
        version=version,
        lifespan=service_lifespan(with_db=with_db, with_redis=with_redis, with_nats=with_nats),
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Tenant-ID"],
        allow_credentials=True,
    )
    setup_prometheus(service_name)
    from fastapi.middleware.gzip import GZipMiddleware
    from fastapi.middleware.trustedhost import TrustedHostMiddleware
    from starlette.middleware.base import BaseHTTPMiddleware

    # ✅ Middleware stack (order: outermost first)
    app.add_middleware(GlobalExceptionMiddleware)
    app.add_middleware(RequestIDMiddleware)
    app.add_middleware(GZipMiddleware, minimum_size=1000)

    allowed_hosts = os.getenv("ALLOWED_HOSTS", "*").split(",")
    if allowed_hosts != ["*"]:
        app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts)

    app.add_middleware(BaseHTTPMiddleware, dispatch=metrics(service_name))
    add_probes(app, pool_getter=get_pool if with_db else None, service_name=service_name)

    # ✅ OpenTelemetry auto-instrumentation
    try:
        from opentelemetry.instrumentation.asyncpg import AsyncPGInstrumentor
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        FastAPIInstrumentor.instrument_app(app)
        AsyncPGInstrumentor().instrument()
    except ImportError:
        pass  # opentelemetry optional — install opentelemetry-instrumentation-fastapi
    return app


# ── HTTP Retry (circuit breaker pattern) ──────────────────────
async def retry_request(
    coro_fn,
    *args,
    max_attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 10.0,
    exceptions: tuple = (Exception,),
    **kwargs,
):
    """Retry async function with exponential backoff.
    Usage:
        result = await retry_request(client.get, url, max_attempts=3)
    """
    last_exc = None
    for attempt in range(max_attempts):
        try:
            return await coro_fn(*args, **kwargs)
        except exceptions as e:
            last_exc = e
            if attempt == max_attempts - 1:
                raise
            delay = min(base_delay * (2**attempt), max_delay)
            logging.warning(
                f"retry_request: attempt {attempt + 1}/{max_attempts} failed: {e} — retrying in {delay:.1f}s"
            )
            await asyncio.sleep(delay)
    raise last_exc


# ── Request ID Middleware ──────────────────────────────────────
class RequestIDMiddleware(_BaseHTTPMiddleware):
    """Add X-Request-ID to every request for distributed tracing."""

    async def dispatch(self, request, call_next):
        req_id = request.headers.get("X-Request-ID") or str(_uuid.uuid4())
        request.state.request_id = req_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = req_id
        return response


class GlobalExceptionMiddleware(_BaseHTTPMiddleware):
    """Catch unhandled exceptions and return 500 without stack trace."""

    async def dispatch(self, request, call_next):
        try:
            return await call_next(request)
        except Exception as e:
            req_id = getattr(request.state, "request_id", "?")
            logging.error(f"Unhandled exception [{req_id}]: {e}", exc_info=True)
            from fastapi.responses import JSONResponse

            return JSONResponse(
                status_code=500, content={"error": "Internal server error", "request_id": req_id}
            )
