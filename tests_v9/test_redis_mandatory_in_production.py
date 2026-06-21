"""حوكمة #408 — Redis إلزاميّ (fail-closed) للإبطال في الإنتاج.

الفجوة: عند غياب Redis كانت خدمة auth والمنصّة تُكملان الإقلاع بإبطال JWT معطّلاً
(fail-open): توكن مُبطَل/مُسجَّل خروجه يمرّ، وقفل الحساب/أرضيّة التوكن تتعطّل. الإصلاح:
في الإنتاج (SAHOOL_ENV=production) ترفض الخدمتان الإقلاع بدل التشغيل صامتاً.

(A) اختبارات نقيّة لمنطق _is_production (محاكاة os.getenv — لا استيراد للخدمة الثقيلة).
(B) حُرّاس مصدر — يتأكّدان من وجود بوّابة الإنتاج التي ترفع RuntimeError. تُنفَّذ في CI
    دائماً دون استيراد الخدمة (لا fastapi/asyncpg/redis مطلوبة).

لا اختبار هنا يتطلّب Redis حيّاً — السلوك يُتحقَّق منه عبر المصدر والمنطق النقيّ.
"""

from __future__ import annotations

import os
import re

import pytest

pytestmark = pytest.mark.unit

ROOT = os.path.join(os.path.dirname(__file__), "..")
AUTH = os.path.join(ROOT, "services/auth/main.py")
PLATFORM = os.path.join(ROOT, "services/sahool-platform/api/main.py")


def _read(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


# دالّة مرجعيّة تطابق منطق _is_production في الخدمتين — تُختبَر نقيّةً دون استيراد
# الوحدات الثقيلة (fastapi/asyncpg). أيّ انحراف في المصدر يُكشَف عبر حُرّاس (B).
def _is_production_ref(env: dict) -> bool:
    return (env.get("SAHOOL_ENV", "development") or "").strip().lower() == "production"


# ── (A) منطق _is_production النقيّ ──
@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("production", True),
        ("PRODUCTION", True),  # غير حسّاس لحالة الأحرف
        ("  production  ", True),  # يتجاهل المسافات المحيطة
        ("development", False),
        ("dev", False),
        ("staging", False),
        ("", False),
    ],
)
def test_is_production_logic(value, expected):
    assert _is_production_ref({"SAHOOL_ENV": value}) is expected


def test_is_production_defaults_to_development():
    """غياب SAHOOL_ENV ⇒ development (False) — CI/dev يبقى أخضر بلا ضبط البيئة."""
    assert _is_production_ref({}) is False


# ── (B) حُرّاس المصدر: بوّابة الإنتاج fail-closed موجودة ──
def test_auth_has_is_production_helper():
    src = _read(AUTH)
    assert "def _is_production()" in src, "auth: مساعد _is_production مفقود"
    # يقرأ SAHOOL_ENV بافتراض development.
    assert re.search(r'os\.getenv\(\s*"SAHOOL_ENV"\s*,\s*"development"\s*\)', src), (
        "auth: _is_production يجب أن يقرأ SAHOOL_ENV (افتراض development)"
    )


def test_auth_redis_failure_raises_in_production():
    """lifespan في auth: عند فشل Redis والإنتاج يرفع RuntimeError (لا تنازل صامت)."""
    src = _read(AUTH)
    # داخل معالج فشل Redis: فرع إنتاج يرفع RuntimeError.
    assert re.search(
        r"if _is_production\(\):\s*\n\s*raise RuntimeError\(",
        src,
    ), "auth: لا بوّابة fail-closed (if _is_production(): raise RuntimeError) عند فشل Redis"
    assert "Redis مطلوب في الإنتاج" in src, "auth: رسالة الرفض المتوقّعة مفقودة"
    # التطوير ما زال يتنازل (تحذير + _redis = None) كي لا ينكسر dev/CI.
    assert "refresh tokens disabled" in src, "auth: مسار التطوير (تحذير + تنازل) أُزيل بالخطأ"


def test_platform_has_is_production_helper():
    src = _read(PLATFORM)
    assert "def _is_production()" in src, "platform: مساعد _is_production مفقود"


def test_platform_denylist_raises_in_production():
    """بنّاء denylist في المنصّة: في الإنتاج بلا Redis يرفع RuntimeError بدل InMemoryDenylist."""
    src = _read(PLATFORM)
    builder = src[src.index("def _build_denylist(") :]
    builder = builder[: builder.index("\n_DENYLIST")]
    assert "if _is_production():" in builder, "platform: بنّاء denylist بلا بوّابة _is_production()"
    assert "raise RuntimeError(" in builder, (
        "platform: بنّاء denylist لا يرفع RuntimeError في الإنتاج عند غياب Redis"
    )
    assert "Redis مطلوب في الإنتاج" in builder, "platform: رسالة الرفض المتوقّعة مفقودة"
    # التطوير ما زال يتنازل إلى الذاكرة.
    assert "InMemoryDenylist()" in builder, "platform: fallback ذاكرة التطوير أُزيل بالخطأ"
