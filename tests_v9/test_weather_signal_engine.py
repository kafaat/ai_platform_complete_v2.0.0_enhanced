"""حُرّاس ثابتة لـweather-signal-engine (P1) — تتحقّق من الأنماط المُلزَمة دون رفع خدمات.

تقرأ services/weather-signal-engine/src/main.py وتفحصه نصّيّاً + py_compile: يُصرَّف،
يستعمل دور sahool_jobs (JOBS_DATABASE_URL لا postgres superuser)، asyncpg لا SQLAlchemy،
CAST(...AS jsonb) وANY(...::text[]) لقوائم IN، ويُعيد استعمال النواة build_signal_records.
"""

import py_compile
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_MAIN = (
    Path(__file__).resolve().parents[1] / "services" / "weather-signal-engine" / "src" / "main.py"
)


def _src() -> str:
    return _MAIN.read_text(encoding="utf-8")


def test_main_compiles():
    """يُصرَّف main.py بلا أخطاء صياغة."""
    assert _MAIN.is_file(), "main.py مفقود"
    py_compile.compile(str(_MAIN), doraise=True)


def test_uses_jobs_role_not_superuser():
    """يتّصل بدور sahool_jobs عبر JOBS_DATABASE_URL، لا postgres superuser (تجنّب تجاوز RLS)."""
    src = _src()
    assert "JOBS_DATABASE_URL" in src
    assert "postgres://postgres:" not in src.lower()
    assert "superuser" not in src.lower()


def test_asyncpg_not_sqlalchemy():
    """asyncpg (لا SQLAlchemy) مطابقةً للمنصّة."""
    src = _src()
    assert "import asyncpg" in src
    # نتحقّق من الاستيراد/المحرّك لا مجرّد ورود الكلمة (قد ترد في تعليق).
    assert "import sqlalchemy" not in src.lower()
    assert "create_engine" not in src


def test_jsonb_and_in_list_patterns():
    """CAST(...AS jsonb) للحمولة وANY(...::text[]) لقوائم IN (لا ::jsonb)."""
    src = _src()
    assert "CAST(" in src and "AS jsonb)" in src
    assert "::jsonb" not in src
    assert "::text[])" in src


def test_reuses_pure_core():
    """يُعيد استعمال النواة النقيّة build_signal_records (لا يُعيد كتابة منطق الإشارات)."""
    src = _src()
    assert "build_signal_records" in src
    assert "from core.weather_overlay_pipeline import" in src


def test_scheduled_loop():
    """حلقة مجدولة: فترة قابلة للضبط + نوم بينها، ونقطة دخول asyncio.run(run())."""
    src = _src()
    assert "WEATHER_SIGNAL_INTERVAL_SEC" in src
    assert "asyncio.sleep" in src
    assert 'if __name__ == "__main__":' in src
    assert "asyncio.run(run())" in src
