"""
مرجع: backend proxy لـ Claude API (نمط آمن).

المشكلة التي يحلّها (مراجعة أمنية 1.3):
  استدعاء Anthropic مباشرة من الواجهة (React) يكشف المفتاح في المتصفّح.
  أي مستخدم يفتح DevTools → Network → يستخرج المفتاح.

الحل: الواجهة تستدعي /api/chat (هنا)، وهذا الـproxy:
  • يقرأ المفتاح من البيئة (لا يصل المتصفّح إطلاقاً)
  • يطبّق rate-limiting لكل مزرعة
  • يتطلّب مصادقة (JWT/جلسة)
  • يحقن سياق المزرعة من جانب الخادم

هذا ملف مرجعي يوضّح النمط — يُدمج في طبقة API الفعلية عند بنائها
(FastAPI مقترح). النواة الحالية لا تتضمّن خادماً، لكن هذا يوثّق
العقد المطلوب بين الواجهة والخادم.

التشغيل (مثال FastAPI):
    pip install fastapi uvicorn httpx
    uvicorn api.chat_proxy_reference:app
"""

import os
import time
from collections import defaultdict

# المفتاح من البيئة فقط — لا يُكتب في الكود ولا يصل الواجهة
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"

# rate-limiting بسيط في الذاكرة (للإنتاج: Redis)
_RATE_LIMIT_PER_MIN = 10
_calls: dict[str, list[float]] = defaultdict(list)


def check_rate_limit(tenant_id: str) -> bool:
    """يسمح بـ10 طلبات/دقيقة لكل مزرعة. يمنع استنزاف رصيد API."""
    now = time.time()
    window = [t for t in _calls[tenant_id] if now - t < 60]
    _calls[tenant_id] = window
    if len(window) >= _RATE_LIMIT_PER_MIN:
        return False
    _calls[tenant_id].append(now)
    return True


def build_proxy_request(body: dict, farm_context: str) -> dict:
    """يبني طلب Anthropic من جانب الخادم. سياق المزرعة يُحقن هنا
    (لا يثق بما ترسله الواجهة كاملاً)."""
    return {
        "model": body.get("model", "claude-sonnet-4-20250514"),
        "max_tokens": min(body.get("max_tokens", 600), 1024),  # سقف وقائي
        "system": farm_context,  # من الخادم، لا من الواجهة
        "messages": body.get("messages", []),
    }


# ── مثال FastAPI (يُفعّل عند بناء طبقة API) ──
try:
    import httpx
    import jwt  # PyJWT
    from fastapi import FastAPI, HTTPException, Request

    app = FastAPI(title="SAHOOL Chat Proxy")

    # مفاتيح التحقّق من التوكن (نفس عقد auth-service): RS256 بمفتاح عامّ، أو HS256 بسرّ.
    _JWT_PUBLIC_KEY = os.environ.get("JWT_PUBLIC_KEY", "")
    _JWT_SECRET = os.environ.get("JWT_SECRET", "")

    def _tenant_from_jwt(request: Request) -> str:
        """يستخرج tenant_id من توكن JWT مُتحقَّق منه في ترويسة Authorization.

        أمان: المصدر الوحيد الموثوق للهويّة هو التوكن المُوقَّع — لا ترويسة
        X-Tenant-Id ولا جسم الطلب (كلاهما قابل للتزوير من المتصفّح).
        """
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            raise HTTPException(401, "توكن مصادقة مفقود")
        token = auth[len("Bearer ") :]
        try:
            if _JWT_PUBLIC_KEY:
                claims = jwt.decode(token, _JWT_PUBLIC_KEY, algorithms=["RS256"])
            elif _JWT_SECRET:
                claims = jwt.decode(token, _JWT_SECRET, algorithms=["HS256"])
            else:
                raise HTTPException(503, "تحقّق التوكن غير مُهيّأ")
        except jwt.PyJWTError as e:
            raise HTTPException(401, "توكن غير صالح") from e
        tenant_id = claims.get("tenant_id")
        if not tenant_id:
            raise HTTPException(401, "التوكن لا يحمل tenant_id")
        return str(tenant_id)

    @app.post("/api/chat")
    async def chat(request: Request):
        if not ANTHROPIC_API_KEY:
            raise HTTPException(503, "خدمة المحادثة غير مُهيّأة")

        # الهويّة من التوكن المُوقَّع حصراً (لا ترويسة/جسم قابلين للتزوير).
        tenant_id = _tenant_from_jwt(request)

        if not check_rate_limit(tenant_id):
            raise HTTPException(429, "تجاوزت الحدّ — حاول بعد دقيقة")

        body = await request.json()
        # سياق المزرعة يُجلب من قاعدة البيانات حسب tenant_id (مبسّط هنا)
        farm_context = body.get("system", "")
        payload = build_proxy_request(body, farm_context)

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                ANTHROPIC_URL,
                headers={
                    "x-api-key": ANTHROPIC_API_KEY,  # المفتاح هنا فقط، خادمياً
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json=payload,
            )
        return resp.json()

except ImportError:
    # FastAPI غير مثبّت — هذا ملف مرجعي، النواة لا تتطلّبه
    app = None
