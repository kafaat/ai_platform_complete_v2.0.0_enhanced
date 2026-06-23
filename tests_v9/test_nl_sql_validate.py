"""اختبارات نقيّة لتحقّق NL→SQL (api.nl_sql_validate).

التحقّق دفاع متعمّق فوق sandbox العميل: يقبل SELECT/WITH المفردة، ويرفض DML/DDL/تعدّد
العبارات (لا تمرير شيء غير قراءة). نقيّ — بلا خدمات/شبكة.
"""

from __future__ import annotations

import os
import sys

import pytest

pytestmark = pytest.mark.unit

CORE = os.path.join(os.path.dirname(__file__), "..", "services/sahool-platform")
if CORE not in sys.path:
    sys.path.insert(0, CORE)

from api.nl_sql_validate import extract_sql, validate_select  # noqa: E402


# ── extract_sql: تنظيف ردّ النموذج ──
def test_extract_strips_code_fence():
    assert extract_sql("```sql\nSELECT * FROM fields\n```") == "SELECT * FROM fields"


def test_extract_strips_plain_fence_and_semicolon():
    assert extract_sql("```\nSELECT crop FROM fields;\n```") == "SELECT crop FROM fields"


def test_extract_trims_whitespace_and_trailing_semicolon():
    assert extract_sql("  SELECT 1 FROM fields ;  ") == "SELECT 1 FROM fields"


# ── validate_select: يقبل القراءة ──
@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM fields",
        "select crop, count(*) AS n FROM fields GROUP BY crop ORDER BY n DESC",
        "SELECT id, name, area_ha FROM fields WHERE area_ha > 50",
        "WITH big AS (SELECT * FROM fields WHERE area_ha > 10) SELECT crop FROM big",
        "(SELECT 1 FROM fields)",
    ],
)
def test_validate_accepts_read_only(sql):
    assert validate_select(sql) == sql.strip().rstrip(";").strip()


# ── validate_select: يرفض الكتابة/الإدارة/التعدّد ──
@pytest.mark.parametrize(
    "sql",
    [
        "",
        "   ",
        "DELETE FROM fields",
        "INSERT INTO fields VALUES (1)",
        "UPDATE fields SET crop='x'",
        "DROP TABLE fields",
        "CREATE TABLE x (a INT)",
        "ALTER TABLE fields ADD COLUMN z INT",
        "ATTACH 'x.db'",
        "COPY fields TO 'x.csv'",
        "PRAGMA database_list",
        "INSTALL spatial",
        "LOAD spatial",
        "SELECT 1 FROM fields; DROP TABLE fields",  # تعدّد عبارات
    ],
)
def test_validate_rejects_non_read_only(sql):
    with pytest.raises(ValueError):
        validate_select(sql)
