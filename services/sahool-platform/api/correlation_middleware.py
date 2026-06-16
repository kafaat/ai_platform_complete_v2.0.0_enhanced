"""api/correlation_middleware.py — وسيط معرّف الربط (Correlation-ID) للتتبّع الموزّع.

يضمن أنّ كلّ طلب وارد يحمل/يولّد correlation_id، فيُضبَط في سياق الطلب (contextvars
عبر core.correlation) ويُعاد في رأس الاستجابة — فتتسلسل آثار الطلب عبر السجلّات
والخدمات (انتشار X-Correlation-Id). إن حمل الطلب معرّفاً من خدمة سابقة نواصله، وإلّا
نبدأ سلسلة جديدة.

دفاعيّ: فشل إعداد الربط لا يكسر الطلب (نُكمل بلا معرّف). يعتمد على starlette (تبعيّة
FastAPI القائمة) — لا تبعيّات جديدة.
"""

from __future__ import annotations

from core.correlation import correlation_headers, from_headers
from starlette.middleware.base import BaseHTTPMiddleware

# اسم الرأس المُعتمَد لانتشار المعرّف (يطابق core.correlation).
CORRELATION_HEADER = "X-Correlation-Id"


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """وسيط HTTP: يضبط سياق الربط من رؤوس الطلب الواردة ويُعيده في الاستجابة.

    التسجيل (في api.main): ``app.add_middleware(CorrelationIdMiddleware)``.
    """

    async def dispatch(self, request, call_next):
        # اضبط السياق من رؤوس الطلب (يُواصل معرّفاً وارداً أو يولّد جديداً). دفاعيّ:
        # أيّ خطأ هنا لا يكسر الطلب — نُكمل بلا ربط.
        try:
            from_headers(dict(request.headers))
        except Exception:  # noqa: BLE001 — التتبّع لا يكسر المسار
            pass
        response = await call_next(request)
        # أعِد رؤوس الربط في الاستجابة كي يتتبّعها العميل/الوسطاء.
        try:
            for name, value in correlation_headers().items():
                response.headers[name] = value
        except Exception:  # noqa: BLE001
            pass
        return response
