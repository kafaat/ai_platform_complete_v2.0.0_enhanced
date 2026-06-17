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


def _forced_tables(sql: str) -> set[str]:
    """الجداول التي يُطبَّق عليها FORCE ROW LEVEL SECURITY **استاتيكيّاً** (لا عبر الحلقة
    الديناميكيّة العمياء): صريحاً، أو عبر الدالّة المساعِدة (تُطبّق FORCE داخليّاً)، أو ضمن
    ARRAY[...] داخل بلوك DO يذكر FORCE."""
    forced: set[str] = set()
    # 1) صريح: ALTER TABLE name FORCE ROW LEVEL SECURITY
    for m in re.finditer(
        r"ALTER TABLE\s+(?:IF EXISTS\s+)?([A-Za-z_]\w*)\s+FORCE ROW LEVEL SECURITY", sql, re.I
    ):
        forced.add(m.group(1).lower())
    # 2) عبر الدالّة المساعِدة (تُطبّق ENABLE+FORCE+POLICY) بقيمة حرفيّة
    for m in re.finditer(r"_sahool_apply_tenant_rls\(\s*'([A-Za-z_]\w*)'\s*\)", sql, re.I):
        forced.add(m.group(1).lower())
    # 3) ARRAY[...] داخل بلوك DO يُطبّق FORCE (أو الدالّة المساعِدة)
    for do_block in re.finditer(r"DO\s*\$\$(.*?)\$\$", sql, re.S | re.I):
        block = do_block.group(1)
        if re.search(r"FORCE ROW LEVEL SECURITY|_sahool_apply_tenant_rls", block, re.I):
            for arr in re.finditer(r"ARRAY\s*\[(.*?)\]", block, re.S):
                for q in re.finditer(r"'([A-Za-z_]\w*)'", arr.group(1)):
                    forced.add(q.group(1).lower())
    return forced


# اسم ملفّ الهجرة الذي يطبّق FORCE شاملاً على كلّ جدول مُستأجَر قائم (حلقة ديناميكيّة).
_BLANKET_FORCE_MIGRATION = "v9_rls_force_all.sql"


def _manifest_order() -> list[str]:
    """ترتيب ملفّات الهجرة كما في MANIFEST.txt (يتجاهل التعليقات والفراغات)."""
    lines = (MIGRATIONS_DIR / "MANIFEST.txt").read_text(encoding="utf-8").splitlines()
    return [s for ln in lines if (s := ln.strip()) and not s.startswith("#")]


def _late_tenant_tables() -> set[str]:
    """جداول tenant_id المُنشأة في هجرات **تالية** لـv9_rls_force_all في MANIFEST.

    الحلقة الشاملة في v9_rls_force_all تغطّي الجداول الموجودة حين تشغيلها فقط؛ الجداول
    المُنشأة بعدها (في تمريرة تطبيق واحدة) لا تغطّيها، فيجب أن تُطبّق FORCE صراحةً/عبر
    الدالّة المساعِدة — وإلّا يتجاوزها مالك الجدول (FORCE وحده يُخضِع المالك للسياسة)."""
    order = _manifest_order()
    try:
        cut = order.index(_BLANKET_FORCE_MIGRATION)
    except ValueError:
        pytest.fail(f"{_BLANKET_FORCE_MIGRATION} غير موجود في MANIFEST — حلقة FORCE الشاملة مفقودة")
    late: set[str] = set()
    for fname in order[cut + 1 :]:
        path = MIGRATIONS_DIR / fname
        if not path.exists():
            continue
        late |= _tables_with_tenant_id(path.read_text(encoding="utf-8"))
    return late


@pytest.mark.unit
@pytest.mark.security
def test_blanket_force_migration_present():
    """حلقة FORCE الشاملة (v9_rls_force_all) موجودة وتطبّق FORCE ديناميكيّاً.

    إزالتها تكشف الجداول القديمة (التي تعتمد عليها لا على FORCE الصريح) لتجاوز المالك."""
    order = _manifest_order()
    assert _BLANKET_FORCE_MIGRATION in order, "حلقة FORCE الشاملة غير مُدرَجة في MANIFEST"
    text = (MIGRATIONS_DIR / _BLANKET_FORCE_MIGRATION).read_text(encoding="utf-8")
    assert re.search(r"FORCE ROW LEVEL SECURITY", text, re.I), "v9_rls_force_all لا يطبّق FORCE"


@pytest.mark.unit
@pytest.mark.security
def test_late_tenant_tables_have_explicit_force():
    """كلّ جدول مُستأجَر مُنشأ بعد حلقة FORCE الشاملة يجب أن يطبّق FORCE صراحةً/عبر الدالّة.

    يحوّل «انضباط FORCE» إلى بوّابة CI: جدول جديد يُفعّل RLS لكن ينسى FORCE (ولا يستعمل
    _sahool_apply_tenant_rls) ⇒ يتجاوزه مالك الجدول رغم RLS (دفاع عمق ناقص) — يُكتشَف هنا."""
    sql = _forward_sql_text()
    forced = _forced_tables(sql)
    late = _late_tenant_tables()

    missing = sorted(late - forced - INTENTIONAL_GLOBAL)
    assert not missing, (
        "جداول مُستأجَرة مُنشأة بعد v9_rls_force_all بلا FORCE صريح (خطر تجاوز المالك):\n  "
        + "\n  ".join(missing)
        + "\n\nالإصلاح: استعمل _sahool_apply_tenant_rls('<table>') (يطبّق ENABLE+FORCE+POLICY) "
        "أو أضِف ALTER TABLE <table> FORCE ROW LEVEL SECURITY في الـmigration."
    )


@pytest.mark.unit
@pytest.mark.security
def test_force_guard_detects_unforced_late_table():
    """سلامة حارس FORCE: جدول يُفعّل RLS بسياسة لكن دون FORCE ⇒ يُرصَد كثغرة."""
    fake_sql = (
        "CREATE TABLE late_unforced (\n"
        "  id UUID PRIMARY KEY,\n"
        "  tenant_id UUID NOT NULL\n"
        ");\n"
        "ALTER TABLE late_unforced ENABLE ROW LEVEL SECURITY;\n"
        "CREATE POLICY tenant_isolation ON late_unforced USING (true);\n"
    )
    assert "late_unforced" in _tables_with_tenant_id(fake_sql)
    assert "late_unforced" not in _forced_tables(fake_sql)  # بلا FORCE/helper ⇒ يُرصَد


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
