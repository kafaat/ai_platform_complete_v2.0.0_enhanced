"""عقد الواجهة الرفيعة لنصيحة الحقل (WS-D.2e) — تُستهلَك، لا تُحسَب.

قرار المستخدم: WeatherAdvicePage (وطبقة weather_advice) واجهة **رفيعة** لا تملك منطقاً
حسابيّاً مستقلّاً — لا ET0/GDD/Water-Balance مستقلّ، بل تستهلك القيَم الكنسيّة. حارس
راتشِت يمنع إعادة إدخال الحساب المستقلّ (الازدواجيّة) مستقبلاً، تمهيداً لإعادة التسمية
التدريجيّة إلى Field Advisory ثمّ Field Advisory BFF (مرحلة مستقلّة لاحقة).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parent.parent
_ADVICE_PY = _ROOT / "services" / "sahool-platform" / "api" / "weather_advice.py"
_ADVICE_TSX = _ROOT / "frontend" / "src" / "sections" / "WeatherAdvicePage.tsx"


def test_backend_advice_consumes_et0_does_not_compute_it():
    src = _ADVICE_PY.read_text(encoding="utf-8")
    # لا يستدعي نواة ET0 (يستقبل et0_mm مُدخَلاً) ولا يُعرّف نوى الطقس.
    assert "compute_et0(" not in src, "weather_advice must consume et0, not call compute_et0"
    assert "def _svp" not in src, "advice facade must not define an SVP kernel"
    assert "def penman_monteith" not in src, "advice facade must not define an ET0 kernel"
    assert "def gdd_daily" not in src and "def daily_gdd" not in src, (
        "advice facade must not define a GDD kernel"
    )
    # يستقبل ET0 مُدخَلاً (عقد الواجهة الرفيعة: تُستهلَك القيمة، لا تُشتقّ).
    assert "et0_mm" in src, "advice facade must take et0 as an input parameter"


def test_frontend_advice_page_is_render_only():
    src = _ADVICE_TSX.read_text(encoding="utf-8")
    # يستهلك عبر hook/جلب — لا يحسب توصية محلّيّاً.
    assert "useIrrigationAdvice" in src, "page must consume the advice via the hook (server value)"
    # لا حساب ETc/ET0 محلّيّ في الواجهة (يعرض a.et0 كما يأتي من الخادم).
    forbidden = [r"et0\s*\*", r"\*\s*kc\b", r"\bpenman", r"\bhargreaves", r"gdd\s*\+="]
    for pat in forbidden:
        assert not re.search(pat, src, re.IGNORECASE), (
            f"WeatherAdvicePage must not compute irrigation locally (matched {pat!r})"
        )
