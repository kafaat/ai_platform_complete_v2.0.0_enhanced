"""حارس عامل تراكب الطقس (weather-polygon-worker) — يُجمّد الأنماط الصحيحة التي رصدتها
تقارير v05 كأخطاء في البرومبت المرجعيّ (بادئة NATS، CAST jsonb، ANY، دور الوظائف)."""

from __future__ import annotations

import os
import py_compile

import pytest

pytestmark = pytest.mark.unit

BASE = os.path.dirname(os.path.dirname(__file__))
_MAIN = os.path.join(BASE, "services", "weather-polygon-worker", "src", "main.py")


def _src():
    with open(_MAIN, encoding="utf-8") as f:
        return f.read()


def test_worker_compiles():
    py_compile.compile(_MAIN, doraise=True)


def test_uses_jobs_role_not_superuser():
    """يتّصل بدور sahool_jobs (JOBS_DATABASE_URL) — لا postgres superuser (تجاوز RLS)."""
    src = _src()
    assert "JOBS_DATABASE_URL" in src
    assert "postgres:password" not in src and "postgres:postgres" not in src


def test_nats_subjects_have_sahool_prefix():
    """مواضيع NATS ببادئة sahool. (لا weather.* المجرّدة التي تكسر الـstream)."""
    src = _src()
    assert "sahool.weather.forecast.updated" in src
    assert "sahool.weather.field.overlay.completed" in src
    # لا اشتراك على الموضوع بلا بادئة.
    assert '"weather.forecast.updated"' not in src


def test_uses_asyncpg_patterns_not_sqlalchemy():
    """asyncpg (لا SQLAlchemy)، ANY($1::text[]) للقوائم، CAST(... AS jsonb) للحمولة."""
    src = _src()
    # SQLAlchemy غير مستعمَل فعليّاً (لا استيراد ولا create_engine) — مطابقةً للمنصّة.
    assert "import asyncpg" in src
    assert "import sqlalchemy" not in src.lower() and "create_engine" not in src
    assert "ANY($1::text[])" in src
    assert "CAST($6 AS jsonb)" in src


def test_publishes_after_db_commit_outbox():
    """النشر بعد إتمام القاعدة (نمط outbox) — الكتابة ثمّ js.publish."""
    src = _src()
    # ترتيب: معالجة الحقول (قاعدة) قبل js.publish لاكتمال التراكب.
    assert src.index("process_field") < src.index("overlay.completed")
