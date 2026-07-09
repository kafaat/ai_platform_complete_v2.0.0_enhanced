"""حارس تحصين: الخدمات الثانويّة ترفض HS256 في الإنتاج (تماثُل مع auth/المنصّة).

كلّ خدمة تتحقّق من JWT (actuator/guardrails/odoo/tts/video/supervisor/local-ai-rag)
كانت تقبل HS256 (سرّ متماثل مشترَك) في الإنتاج عند غياب JWT_PUBLIC_KEY — وهو لا يُنهي
shared trust domain (أيّ خدمة تحمل السرّ تُزوّر توكناً). أُضيف حارس إقلاع fail-closed:
في الإنتاج بلا RS256 وبلا مهرب صريح (SAHOOL_ALLOW_HS256_IN_PROD) يُرفَض الإقلاع.

فحص مصدريّ (لا استيراد — تبعيّات الخدمات قد تغيب محلّيّاً): يتأكّد أنّ كلّ خدمة تحمل
الشروط الثلاثة للحارس. يمنع انحدار إزالة الحماية صامتاً عن أيّ خدمة.
"""

from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.unit

_ROOT = os.path.join(os.path.dirname(__file__), "..")
_SERVICES = (
    "actuator-service",
    "guardrails-engine",
    "local-ai-rag",
    "odoo-bridge",
    "tts-service",
    "video-processor",
    "supervisor-agent",
    "vegetation-analysis-service",
)


@pytest.mark.parametrize("svc", _SERVICES)
def test_service_refuses_hs256_in_production(svc):
    """مصدر كلّ خدمة يحمل حارس رفض HS256 في الإنتاج (الشروط الثلاثة + الرفض)."""
    path = os.path.join(_ROOT, "services", svc, "main.py")
    with open(path, encoding="utf-8") as f:
        src = f.read()
    # P1 decomposition: بعض الخدمات نقلت الحارس إلى وحدة *_runtime.py شقيقة —
    # نوسّع المسح إلى main.py + الشقيقات (توسيع نطاق فقط، لا إضعاف للتأكيدات).
    svc_dir = os.path.join(_ROOT, "services", svc)
    for fn in sorted(os.listdir(svc_dir)):
        if fn.endswith("_runtime.py"):
            with open(os.path.join(svc_dir, fn), encoding="utf-8") as f:
                src += "\n" + f.read()
    assert 'os.getenv("JWT_PUBLIC_KEY"' in src, f"{svc}: لا يقرأ JWT_PUBLIC_KEY (RS256)"
    assert '"SAHOOL_ENV"' in src, f"{svc}: لا يفحص بيئة الإنتاج"
    assert "SAHOOL_ALLOW_HS256_IN_PROD" in src, f"{svc}: لا مهرب ترحيل موثَّق"
    assert "RS256 مطلوب في الإنتاج" in src, f"{svc}: لا رفض fail-closed للإقلاع على HS256"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
