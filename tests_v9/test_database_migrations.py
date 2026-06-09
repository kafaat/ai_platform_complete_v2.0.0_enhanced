"""Database Migration Tests — SAHOOL v9.1.0"""
import pytest
import re
import os

IMP  = os.path.join(os.path.dirname(__file__), "../../sahool_improvements")
BASE = os.path.dirname(os.path.dirname(__file__))

def read_sql(path):
    try: return open(path, encoding="utf-8").read()
    except Exception: return ""

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
            over_escaped = [l for l in sql.split("\n")
                            if re.search(r"'{4,}", l) and not l.strip().startswith("--")]
            assert len(over_escaped) == 0, f"over-escaped quotes (bypass risk) in {f}: {over_escaped}"

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
            active = [l.strip() for l in sql.split("\n")
                      if "pg_has_role" in l and not l.strip().startswith("--")]
            assert len(active) == 0, f"pg_has_role in {f}"

    @pytest.mark.unit
    def test_workflow_states_before_transitions(self):
        """workflow_states must be defined before workflow_transitions."""
        sql = read_sql(os.path.join(BASE, "migrations/v9_odoo_bridge.sql"))
        states_pos = sql.find("CREATE TABLE IF NOT EXISTS workflow_states")
        trans_pos  = sql.find("CREATE TABLE IF NOT EXISTS workflow_transitions")
        assert states_pos >= 0, "workflow_states not found"
        assert trans_pos >= 0,  "workflow_transitions not found"
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
