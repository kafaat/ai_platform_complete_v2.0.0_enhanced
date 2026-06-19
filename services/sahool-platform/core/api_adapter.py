"""
sahool_core.api_adapter
========================
طبقة API محايدة عن الإطار — تعمل مع FastAPI/Flask/Starlette بلا تعديل.

الفكرة: لا نفترض uvicorn ولا dependency محدّدة. الـAPI Layer يأخذ
ApiRequest dict، يستدعي orchestrate_recommendation، يُرجع ApiResponse
dict. النواة تُختبر بـdicts عاديّة، الإطار الخارجي مجرّد wrapper.

النمط (Hexagonal Architecture):
  FastAPI route → ApiRequest dict → handle_request() → ApiResponse dict → JSON

المبادئ المحفوظة:
  • الحياد: لا framework imports في النواة
  • Auth: UserSchema يأتي من JWT (خارجي)، يمرّ كمعطى
  • Rate limiting (AI Workaholic): سجلّ in-memory بـwindow زمنية
  • Tenant isolation: مفروض في orchestrator، مُختبَر هنا
  • Error semantics: HTTP-like status codes + structured response

التكامل:
  HTTP request → JWT decode → UserSchema →
  handle_recommendation_request → orchestrate_recommendation →
  ApiResponse → JSON

ما لم يُبنَ هنا (مُؤجَّل بمبرّر):
  • FastAPI app الفعلي (يحتاج uvicorn + secrets)
  • JWT signing/verification (يحتاج RS256 keys)
  • Database integration (يحتاج SQLite/PostgreSQL adapter)
  → كلّها wrappers خفيفة فوق هذه الطبقة
"""

from __future__ import annotations

import time
from collections import defaultdict, deque
from dataclasses import asdict, dataclass, field

from core.canonical_schemas import UserSchema
from core.internal_orchestrator import orchestrate_recommendation

# ─── Request/Response Types ──────────────────────────────────────


@dataclass
class ApiRequest:
    """طلب HTTP-like محايد عن الإطار."""

    user: UserSchema
    payload: dict  # body المستخدم
    path: str = "/"
    method: str = "POST"
    headers: dict = field(default_factory=dict)


@dataclass
class ApiResponse:
    """استجابة HTTP-like محايدة."""

    status_code: int  # 200, 400, 401, 403, 404, 429, 500
    body: dict
    headers: dict = field(default_factory=dict)
    # الكائن المُغنّى الكامل (EnrichedRecommendation كـdict) للمستهلِك الذي يريد
    # التخزين/التدقيق — لا يُسلسَل في جسم HTTP (الجسم يبقى كما هو). يُملأ فقط حين
    # تُجرى توصية فعليّة (لا في رفض المعدّل/المستخدم غير النشط).
    enriched: dict | None = None


# ─── Rate Limiter (AI Workaholic Guard) ──────────────────────────


class RateLimiter:
    """حدّ التوصيات للمستخدم — يحرس ضدّ recommendation spam.

    المبدأ الجوهري من السلسلة: "لا تجعلوا سهول AI-heavy".
    20 توصية في الساعة لمستخدم واحد حدّ معقول للسياق الزراعي:
    - 20 حقل × 1 توصية = توصية كاملة لمزرعة
    - أكثر = إما اختبار أو سوء استخدام

    التخزين: in-memory deque بـwindow زمنية (يُستبدَل بـRedis لاحقاً)."""

    def __init__(self, max_requests: int = 20, window_seconds: int = 3600):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._user_requests: dict[str, deque] = defaultdict(deque)

    def check_and_record(self, user_id: str) -> tuple[bool, int]:
        """يفحص الحدّ. يُرجع (allowed, remaining).

        إن مرّ → يُسجّل الطلب. إن تجاوز → لا تسجيل، رفض."""
        now = time.time()
        cutoff = now - self.window_seconds
        requests = self._user_requests[user_id]

        # نظّف الطلبات القديمة (خارج النافذة)
        while requests and requests[0] < cutoff:
            requests.popleft()

        if len(requests) >= self.max_requests:
            return False, 0

        requests.append(now)
        return True, self.max_requests - len(requests)

    def reset(self, user_id: str | None = None) -> None:
        """إعادة تعيين (لاختبارات أو حالات خاصّة)."""
        if user_id:
            self._user_requests[user_id].clear()
        else:
            self._user_requests.clear()


# ─── Recommendation Endpoint ─────────────────────────────────────

# rate limiter مشترك (وحدة وحدة، Singleton في النواة)
_rate_limiter = RateLimiter(max_requests=20, window_seconds=3600)


def handle_recommendation_request(
    req: ApiRequest,
    *,
    recommendation_history: list | None = None,
) -> ApiResponse:
    """نقطة الدخول الـHTTP لطلب توصية.

    يفحص:
      1. payload صحيح (الحقول الإلزامية)
      2. rate limit (AI Workaholic)
      3. يستدعي المايسترو الداخلي (الذي يفحص auth + cross_ref + provenance)
      4. يحوّل النتيجة لـApiResponse

    HTTP codes:
      200: مُسلَّمة
      400: payload ناقص
      401: user.is_active=False (auth context fail)
      403: صلاحية مرفوضة (RBAC أو tenant)
      429: rate limit
      500: خطأ داخلي"""

    # 1. validate payload
    required = {"tenant_id", "field_id", "farm_id", "crop", "validation"}
    missing = required - set(req.payload.keys())
    if missing:
        return ApiResponse(
            status_code=400,
            body={
                "error": "payload incomplete",
                "missing_fields": sorted(missing),
                "ar": f"الحقول الإلزامية الناقصة: {sorted(missing)}",
            },
        )

    # 2. rate limit (قبل أيّ حساب)
    allowed, remaining = _rate_limiter.check_and_record(req.user.user_id)
    if not allowed:
        return ApiResponse(
            status_code=429,
            body={
                "error": "rate_limit_exceeded",
                "ar": "تجاوزت حدّ التوصيات في الساعة (20). هذا يحرس ضدّ الإفراط في الطلب.",
                "retry_after_seconds": _rate_limiter.window_seconds,
            },
            headers={"X-RateLimit-Remaining": "0"},
        )

    # 3. user inactive (auth context)
    if not req.user.is_active:
        return ApiResponse(
            status_code=401,
            body={"error": "user_inactive", "ar": f"المستخدم {req.user.user_id} غير نشط"},
        )

    # 4. delegate to المايسترو الداخلي
    try:
        result = orchestrate_recommendation(
            user=req.user,
            tenant_id=req.payload["tenant_id"],
            farm_id=req.payload["farm_id"],
            field_id=req.payload["field_id"],
            crop=req.payload["crop"],
            validation=req.payload["validation"],
            irrigation=req.payload.get("irrigation"),
            suitability=req.payload.get("suitability"),
            zone_factor=req.payload.get("zone_factor"),
            zone_factor_status=req.payload.get("zone_factor_status", "pending"),
            local_knowledge=req.payload.get("local_knowledge"),
            field_state=req.payload.get("field_state"),
            recommendation_history=recommendation_history or [],
            current_indicators=req.payload.get("current_indicators"),
            growth_stage=req.payload.get("growth_stage"),
            issue_type=req.payload.get("issue_type"),
            district_id=req.payload.get("district_id"),
            engines_used=req.payload.get("engines_used"),
            weather_source=req.payload.get("weather_source", "open-meteo"),
            is_pesticide=req.payload.get("is_pesticide", False),
        )
    except Exception as e:
        return ApiResponse(
            status_code=500,
            body={
                "error": "internal_error",
                "detail": str(e)[:200],
                "ar": "خطأ داخلي — تواصل مع الدعم",
            },
        )

    # 5. حوّل النتيجة لـHTTP response
    if not result.delivered:
        # 403 لرفض الصلاحية، 422 لفشل الـpipeline
        is_auth_fail = "صلاحية" in result.reason_ar or "عزل tenant" in result.reason_ar
        status = 403 if is_auth_fail else 422
        return ApiResponse(
            status_code=status,
            body={
                "delivered": False,
                "reason_ar": result.reason_ar,
                "rec_id": result.rec_id,
            },
            headers={"X-RateLimit-Remaining": str(remaining)},
            enriched=asdict(result),
        )

    # 200 — مُسلَّمة
    return ApiResponse(
        status_code=200,
        body={
            "delivered": True,
            "rec_id": result.rec_id,
            "recommendation": result.base_recommendation,
            "cross_reference_count": result.cross_reference.get("count", 0),
            "cross_reference_note_ar": result.cross_reference.get("note_ar", ""),
            "model_versions_count": len(result.provenance.get("model_versions", {})),
            "timestamp": result.timestamp,
        },
        headers={"X-RateLimit-Remaining": str(remaining)},
        enriched=asdict(result),
    )


# ─── Health Endpoints ────────────────────────────────────────────


def handle_healthz() -> ApiResponse:
    """فحص حياة بسيط (Kubernetes liveness probe)."""
    return ApiResponse(
        status_code=200,
        body={"status": "alive", "service": "sahool-core", "timestamp": time.time()},
    )


def handle_readyz() -> ApiResponse:
    """فحص الجاهزية — يتأكّد من توفّر المكوّنات الجوهرية."""
    checks = {}
    try:
        from core.skills_registry import all_skills

        checks["skills_registry"] = {"ok": True, "count": len(all_skills())}
    except Exception as e:
        checks["skills_registry"] = {"ok": False, "error": str(e)}

    try:
        from core.canonical_schemas import entities_catalog

        checks["schemas"] = {"ok": True, "count": len(entities_catalog())}
    except Exception as e:
        checks["schemas"] = {"ok": False, "error": str(e)}

    all_ok = all(c.get("ok") for c in checks.values())
    return ApiResponse(
        status_code=200 if all_ok else 503,
        body={"status": "ready" if all_ok else "degraded", "checks": checks},
    )


async def db_probe_ok(pool) -> bool:
    """فحص اعتماديّة القاعدة الفعليّ للجاهزيّة (MED-001، شهادة P12).

    handle_readyz يفحص النواة (in-memory) فقط، فكان readyz يُرجِع ready رغم سقوط
    Postgres (إيجابيّة كاذبة توجّه المنظّم حركةً لنسخة لا تخدم القاعدة). هذه الدالّة
    تُجري SELECT 1 فعليّاً. pool=None ⇒ True (تشغيل بلا قاعدة مقصود — endpoints
    القاعدة تُرجِع 503 صراحةً)؛ pool قائم لكن الفحص يفشل ⇒ False (سقوط أثناء التشغيل)."""
    if pool is None:
        return True
    try:
        async with pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        return True
    except Exception:  # noqa: BLE001 — أيّ تعذّر اتّصال = ليست جاهزة
        return False


# ─── Reset (لاختبارات؛ لا للإنتاج) ────────────────────────────────


def _reset_rate_limiter() -> None:
    """إعادة تعيين الـrate limiter — للاختبارات فقط."""
    _rate_limiter.reset()
