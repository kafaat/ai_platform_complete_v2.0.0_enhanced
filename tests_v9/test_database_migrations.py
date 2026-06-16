"""Database Migration Tests — SAHOOL v9.1.0"""

import os
import re

import pytest

IMP = os.path.join(os.path.dirname(__file__), "../../sahool_improvements")
BASE = os.path.dirname(os.path.dirname(__file__))


def read_sql(path):
    try:
        return open(path, encoding="utf-8").read()
    except Exception:
        return ""


class TestSQLSyntax:
    @pytest.mark.unit
    def test_no_syntax_errors_init_v8(self):
        import sqlparse

        # FIX: الملف يقع في migrations/ داخل المستودع (المسار القديم
        # ../../sahool_improvements لم يَعُد موجوداً ⇒ read_sql='' ⇒ فشل زائف).
        sql = read_sql(os.path.join(BASE, "migrations/init_v8.sql"))
        statements = sqlparse.parse(sql)
        assert len(statements) > 0

    @pytest.mark.unit
    def test_no_8quote_rls_bypass(self):
        """سياسات RLS يجب ألّا تحوي تهريباً مضاعفاً (over-escaping).

        النمط الخطير ("8-quote bypass") ينشأ من لفّ سياسة داخل سلسلة مفردة
        داخل أخرى فتتضاعف الاقتباسات (''''، 4+ متتالية) ويسهل أن تتحوّل
        خطأً إلى شرط دائم الصدق. الحلّ الصحيح: dollar-quoting ($ddl$...$ddl$).
        ملاحظة: السلسلة الفارغة '' (اقتباسان) شرعيّة (NULLIF(x, ''))، فلا تُحسب.
        """
        sql_files = [
            "migrations/v9_foundation.sql",
            "migrations/v9_new_tables.sql",
            "migrations/v9_market.sql",
            "migrations/v9_automation.sql",
            "migrations/v9_odoo_bridge.sql",
        ]
        for f in sql_files:
            sql = read_sql(os.path.join(BASE, f))
            # 4+ اقتباسات متتالية = تهريب مضاعف (وليس مجرّد '' فارغة شرعيّة)
            over_escaped = [
                line
                for line in sql.split("\n")
                if re.search(r"'{4,}", line) and not line.strip().startswith("--")
            ]
            assert len(over_escaped) == 0, (
                f"over-escaped quotes (bypass risk) in {f}: {over_escaped}"
            )

    @pytest.mark.unit
    def test_no_pg_has_role_bypass(self):
        """pg_has_role bypass must be removed from all migrations."""
        sql_files = [
            "migrations/v9_foundation.sql",
            "migrations/v9_new_tables.sql",
            "migrations/v9_market.sql",
            "migrations/v9_automation.sql",
            "migrations/v9_odoo_bridge.sql",
        ]
        for f in sql_files:
            sql = read_sql(os.path.join(BASE, f))
            active = [
                line.strip()
                for line in sql.split("\n")
                if "pg_has_role" in line and not line.strip().startswith("--")
            ]
            assert len(active) == 0, f"pg_has_role in {f}"

    @pytest.mark.unit
    def test_workflow_states_before_transitions(self):
        """workflow_states must be defined before workflow_transitions."""
        sql = read_sql(os.path.join(BASE, "migrations/v9_odoo_bridge.sql"))
        states_pos = sql.find("CREATE TABLE IF NOT EXISTS workflow_states")
        trans_pos = sql.find("CREATE TABLE IF NOT EXISTS workflow_transitions")
        assert states_pos >= 0, "workflow_states not found"
        assert trans_pos >= 0, "workflow_transitions not found"
        assert states_pos < trans_pos, "workflow_states must come before workflow_transitions"

    @pytest.mark.unit
    def test_no_fk_to_view(self):
        """Foreign keys must reference tables, not views."""
        sql = read_sql(os.path.join(BASE, "migrations/v9_new_tables.sql"))
        # Should reference field_boundaries, not fields (which was a view)
        bad_fk = re.findall(r"REFERENCES fields\(field_id\)", sql)
        assert len(bad_fk) == 0, "FK references the VIEW 'fields' directly"

    @pytest.mark.integration
    async def test_migrations_apply_cleanly(self, http_client):
        """Test that the DB is alive after migrations."""
        import asyncpg
        from conftest import TEST_DB_URL

        pool = await asyncpg.create_pool(TEST_DB_URL, min_size=1, max_size=2)
        try:
            result = await pool.fetchval("SELECT 1")
            assert result == 1
        finally:
            await pool.close()


class TestConcurrencyDeterminismMigrations:
    """حُرّاس ثابتة (static) لهجرات التزامن/الحتميّة v62/v63/v64 — تمنع انحدار
    البُنى الأمنيّة الحرجة فيها (الفهرس الجزئيّ، عمود seq، عمّاد row_version)."""

    @pytest.mark.unit
    def test_v62_partial_unique_index_guards_null_season(self):
        """v62: فهرس فريد جزئيّ على (field_id) حيث season_id IS NULL — يسدّ ثغرة
        NULL≠NULL في UNIQUE(field_id, season_id) فيمنع تكرار دورة الحياة قبل-البذر."""
        sql = read_sql(os.path.join(BASE, "migrations/v62_field_lifecycle_null_season_guard.sql"))
        assert "CREATE UNIQUE INDEX" in sql
        assert "ux_field_lifecycle_field_null_season" in sql
        # الشرطيّة الجزئيّة WHERE season_id IS NULL هي جوهر الإصلاح — لا تُسقَط.
        assert re.search(r"ON\s+field_lifecycle\s*\(\s*field_id\s*\)", sql)
        assert re.search(r"WHERE\s+season_id\s+IS\s+NULL", sql)

    @pytest.mark.unit
    def test_v63_events_seq_identity_and_order_index(self):
        """v63: عمود seq (IDENTITY) كاسر تعادل occurred_at + فهرس ترتيب إعادة البناء."""
        sql = read_sql(os.path.join(BASE, "migrations/v63_events_seq_deterministic_order.sql"))
        assert re.search(r"ADD COLUMN IF NOT EXISTS\s+seq\s+BIGINT", sql)
        assert "GENERATED ALWAYS AS IDENTITY" in sql  # لا كتابة يدويّة للـseq
        # فهرس يخدم (occurred_at, seq) لإعادة بناء حتميّة بلا فرز إضافيّ.
        assert re.search(r"occurred_at\s+ASC,\s*seq\s+ASC", sql)

    @pytest.mark.unit
    def test_v64_seasons_row_version_column_and_bump_trigger(self):
        """v64: عمّاد row_version + trigger يرفعه على كلّ UPDATE (يغطّي كلّ مسارات الكتابة)."""
        sql = read_sql(os.path.join(BASE, "migrations/v64_seasons_row_version.sql"))
        assert re.search(r"ADD COLUMN IF NOT EXISTS\s+row_version\s+INTEGER", sql)
        assert "bump_row_version" in sql
        assert re.search(r"BEFORE\s+UPDATE\s+ON\s+seasons", sql)
        # الرفع = OLD.row_version + 1 (لا تثبيت/إعادة تعيين).
        assert re.search(r"row_version\s*:=\s*OLD\.row_version\s*\+\s*1", sql)

    @pytest.mark.integration
    async def test_concurrency_schema_objects_exist_after_migration(self, http_client):
        """تحقّق حيّ (للقراءة فقط) أنّ بُنى v62/v63/v64 موجودة فعلاً في المخطّط بعد
        تطبيق الهجرات — استعلامات كتالوج بلا كتابة (لا RLS/FK)، حتميّة."""
        import asyncpg
        from conftest import TEST_DB_URL

        pool = await asyncpg.create_pool(TEST_DB_URL, min_size=1, max_size=2)
        try:
            # v62: الفهرس الجزئيّ موجود.
            idx = await pool.fetchval(
                "SELECT 1 FROM pg_indexes WHERE indexname = $1",
                "ux_field_lifecycle_field_null_season",
            )
            assert idx == 1, "v62: ux_field_lifecycle_field_null_season مفقود"
            # v63: عمود events.seq موجود (IDENTITY).
            seq_col = await pool.fetchval(
                "SELECT is_identity FROM information_schema.columns "
                "WHERE table_name = 'events' AND column_name = 'seq'"
            )
            assert seq_col == "YES", f"v63: events.seq ليس IDENTITY (={seq_col})"
            # v64: عمود seasons.row_version + trigger الرفع.
            rv_col = await pool.fetchval(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_name = 'seasons' AND column_name = 'row_version'"
            )
            assert rv_col == 1, "v64: seasons.row_version مفقود"
            trg = await pool.fetchval(
                "SELECT 1 FROM pg_trigger WHERE tgname = $1", "trg_seasons_row_version"
            )
            assert trg == 1, "v64: trigger trg_seasons_row_version مفقود"
        finally:
            await pool.close()


class TestHarvestTraceabilityMigration:
    """حُرّاس v65 (تتبّع سلسلة الإمداد): الجدولان + RLS لكلّ مستأجِر."""

    @pytest.mark.unit
    def test_v65_creates_tables_with_rls(self):
        """v65 ينشئ harvest_lots + custody_chain_events مع RLS صريح (ENABLE+FORCE+policy)."""
        sql = read_sql(os.path.join(BASE, "migrations/v65_harvest_traceability.sql"))
        assert "CREATE TABLE IF NOT EXISTS harvest_lots" in sql
        assert "CREATE TABLE IF NOT EXISTS custody_chain_events" in sql
        # ربط بالكيانات القائمة (لا تكرار).
        assert "REFERENCES fields(field_id)" in sql
        assert "REFERENCES seasons(season_id)" in sql
        assert "REFERENCES harvest_lots(harvest_lot_id)" in sql
        # RLS صريح لكلّ مستأجِر على الجدولين (يطابق حارس تغطية RLS).
        for tbl in ("harvest_lots", "custody_chain_events"):
            assert re.search(rf"ALTER TABLE {tbl} ENABLE ROW LEVEL SECURITY", sql)
            assert re.search(rf"ALTER TABLE {tbl} FORCE\s+ROW LEVEL SECURITY", sql)
            assert re.search(rf"CREATE POLICY tenant_isolation ON {tbl}", sql)

    @pytest.mark.integration
    async def test_v65_tables_exist_after_migration(self, http_client):
        """تحقّق حيّ (للقراءة فقط): الجدولان موجودان ولهما سياسة RLS بعد الهجرة."""
        import asyncpg
        from conftest import TEST_DB_URL

        pool = await asyncpg.create_pool(TEST_DB_URL, min_size=1, max_size=2)
        try:
            for tbl in ("harvest_lots", "custody_chain_events"):
                exists = await pool.fetchval(
                    "SELECT 1 FROM information_schema.tables "
                    "WHERE table_schema = 'public' AND table_name = $1",
                    tbl,
                )
                assert exists == 1, f"v65: جدول {tbl} مفقود"
                pol = await pool.fetchval(
                    "SELECT 1 FROM pg_policies WHERE tablename = $1 AND policyname = 'tenant_isolation'",
                    tbl,
                )
                assert pol == 1, f"v65: سياسة RLS على {tbl} مفقودة"
        finally:
            await pool.close()
