"""تغطية RLS لكلّ جدول مُستأجَر — حارس CI (عزل المستأجرين).

السبب: عزل المستأجرين في المنصّة مفروضٌ على مستوى قاعدة البيانات عبر
Row-Level Security (سياسة `tenant_isolation` على `current_setting('app.current_tenant')`،
fail-closed). لكنّ تفعيل RLS في الـmigrations يتمّ عبر **قوائم جداول يدويّة**
(`v9_rls_tenant_isolation.sql` و`v9_new_tables.sql` …) لا عبر التقاط آليّ لكلّ
جدول. الخطر: جدول جديد يُضاف لاحقاً بعمود `tenant_id` لكن يُنسى إدراجه في قائمة
RLS ⇒ يصبح مكشوفاً عبر المستأجرين (IDOR صامت) دون أيّ خطأ ظاهر.

هذا الاختبار يحوّل «انضباط المطوّر» إلى **بوّابة CI**: يجمع كلّ جدول يحوي عمود
`tenant_id` من الـmigrations، ويتأكّد أنّ لكلٍّ منه تفعيلَ RLS (صريحاً، أو عبر
الدالّة المساعِدة `_sahool_apply_tenant_rls`, أو ضمن حلقة `ARRAY[...]` تُفعّل RLS).
أيّ جدول مُستأجَر بلا RLS يُفشِل الاختبار مع رسالة تشرح الإصلاح.

ملاحظة: عند وجود جدول يحوي `tenant_id` لكنّه عالميّ عمداً (لا يحتاج عزلاً)،
يُضاف اسمه إلى `INTENTIONAL_GLOBAL` مع تعليق يبرّر — فيبقى الحارس صادقاً صريحاً.
"""

import glob
import pathlib
import re

import pytest

# جذر المستودع = أب مجلّد tests_v9/ (هذا الملفّ في tests_v9/).
REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
MIGRATIONS_DIR = REPO_ROOT / "migrations"

# جداول تحوي tenant_id لكنّها عالميّة عمداً (لا تخضع لعزل المستأجِر). فارغة الآن:
# كلّ جدول مُستأجَر في المنصّة محميّ بـRLS. تُضاف هنا أيّ استثناءات مبرّرة مستقبلاً.
INTENTIONAL_GLOBAL: set[str] = set()


def _forward_sql_text() -> str:
    """نصّ كلّ ملفّات migrations/*.sql الأماميّة (عدا .down.sql) مدموجاً."""
    chunks = []
    for path in sorted(glob.glob(str(MIGRATIONS_DIR / "*.sql"))):
        if path.endswith(".down.sql"):
            continue
        chunks.append(pathlib.Path(path).read_text(encoding="utf-8"))
    return "\n".join(chunks)


def _tables_with_tenant_id(sql: str) -> set[str]:
    """الجداول التي تملك عمود tenant_id (عبر CREATE TABLE أو ADD COLUMN)."""
    tables: set[str] = set()
    # CREATE TABLE [IF NOT EXISTS] name ( ... tenant_id ... ) ;
    for m in re.finditer(
        r"CREATE TABLE(?:\s+IF NOT EXISTS)?\s+([A-Za-z_]\w*)\s*\((.*?)\n\)\s*;",
        sql,
        re.S | re.I,
    ):
        name, body = m.group(1), m.group(2)
        if re.search(r"\btenant_id\b", body, re.I):
            tables.add(name.lower())
    # ALTER TABLE [IF EXISTS] name ADD COLUMN [IF NOT EXISTS] tenant_id ...
    for m in re.finditer(
        r"ALTER TABLE\s+(?:IF EXISTS\s+)?([A-Za-z_]\w*)\s+ADD COLUMN"
        r"(?:\s+IF NOT EXISTS)?\s+tenant_id\b",
        sql,
        re.I,
    ):
        tables.add(m.group(1).lower())
    return tables


def _rls_protected_tables(sql: str) -> set[str]:
    """الجداول التي يُفعَّل عليها RLS — صريحاً أو عبر الدالّة المساعِدة أو ضمن
    حلقة ARRAY[...] تُفعّل RLS."""
    protected: set[str] = set()
    # 1) صريح: ALTER TABLE name ENABLE ROW LEVEL SECURITY
    for m in re.finditer(
        r"ALTER TABLE\s+(?:IF EXISTS\s+)?([A-Za-z_]\w*)\s+ENABLE ROW LEVEL SECURITY",
        sql,
        re.I,
    ):
        protected.add(m.group(1).lower())
    # 2) صريح: CREATE POLICY ... ON name  (وجود سياسة ⇒ RLS مقصود على الجدول)
    for m in re.finditer(r"CREATE POLICY\s+\w+\s+ON\s+([A-Za-z_]\w*)", sql, re.I):
        protected.add(m.group(1).lower())
    # 3) عبر الدالّة المساعِدة بقيمة حرفيّة: _sahool_apply_tenant_rls('name')
    for m in re.finditer(r"_sahool_apply_tenant_rls\(\s*'([A-Za-z_]\w*)'\s*\)", sql, re.I):
        protected.add(m.group(1).lower())
    # 4) ديناميكيّ: أسماء داخل ARRAY[...] ضمن بلوك DO يُفعّل RLS (حلقة FOREACH).
    #    نلتقط كلّ ARRAY[...] يسبقه/يتبعه في نفس بلوك DO ذكرُ تفعيل RLS.
    for do_block in re.finditer(r"DO\s*\$\$(.*?)\$\$", sql, re.S | re.I):
        block = do_block.group(1)
        if re.search(r"ROW LEVEL SECURITY|_sahool_apply_tenant_rls", block, re.I):
            for arr in re.finditer(r"ARRAY\s*\[(.*?)\]", block, re.S):
                for q in re.finditer(r"'([A-Za-z_]\w*)'", arr.group(1)):
                    protected.add(q.group(1).lower())
    return protected


@pytest.mark.unit
@pytest.mark.security
def test_every_tenant_table_has_rls():
    """كلّ جدول يحوي tenant_id يجب أن يكون محميّاً بـRLS (أو مُستثنى عمداً)."""
    sql = _forward_sql_text()
    tenant_tables = _tables_with_tenant_id(sql)
    protected = _rls_protected_tables(sql)

    # سلامة الحارس: لا بدّ أن يجد جداول مُستأجَرة (وإلّا فالتحليل مكسور).
    assert tenant_tables, "لم يُكتشف أيّ جدول بعمود tenant_id — تحليل الـmigrations مكسور"

    unprotected = sorted(tenant_tables - protected - INTENTIONAL_GLOBAL)
    assert not unprotected, (
        "جداول تحوي tenant_id بلا تفعيل RLS مكتشَف (خطر تسرّب عبر المستأجرين):\n  "
        + "\n  ".join(unprotected)
        + "\n\nالإصلاح: فعّل RLS في migration (مثل v9_rls_tenant_isolation.sql) عبر "
        "_sahool_apply_tenant_rls('<table>') أو ENABLE ROW LEVEL SECURITY + "
        "CREATE POLICY tenant_isolation. إن كان الجدول عالميّاً عمداً، أضِفه إلى "
        "INTENTIONAL_GLOBAL في هذا الملفّ مع تبرير."
    )


@pytest.mark.unit
@pytest.mark.security
def test_rls_guard_detects_unprotected_table():
    """سلامة الحارس نفسه: لو ظهر جدول مُستأجَر خارج مجموعة RLS، يُكتشف."""
    fake_sql = (
        "CREATE TABLE leaky_table (\n"
        "  id UUID PRIMARY KEY,\n"
        "  tenant_id UUID NOT NULL,\n"
        "  payload TEXT\n"
        ");\n"
    )
    tenant_tables = _tables_with_tenant_id(fake_sql)
    protected = _rls_protected_tables(fake_sql)
    assert "leaky_table" in tenant_tables
    assert "leaky_table" not in protected  # بلا ENABLE/POLICY ⇒ يُرصَد كثغرة
