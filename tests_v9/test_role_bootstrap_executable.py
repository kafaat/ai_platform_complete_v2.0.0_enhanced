"""تكامليّ: تشغيل كتلة تهيئة الدور من apply_in_compose.sh **فعليّاً** على Postgres حيّ.

درس عطب staging (2026-07-20): الحارس الساكن تحقّق من وجود نصّ REVOKE فقط، لا من **قابليّة
تنفيذه** — فمرّ خطأ صياغة (`:'app_role'` داخل `DO $$`) عبر CI أخضر حتى فشل على بيئة نظيفة.
هذا الاختبار يستخرج heredoc تهيئة الدور من السكربت الحقيقيّ ويشغّله عبر psql مع
`-v app_role=…` (كما تفعل الحاوية)، ثمّ يؤكّد مصفوفة الصلاحيات الفعليّة.

يتطلّب psql حيّاً + Postgres — مُعلَّم ``integration`` ويُتخطّى إن غابا (لا يُخفِق صامتاً:
يُتخطّى بوضوح). يشغّله CI في وظيفة Integration Tests على Postgres حيّ.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import uuid
from pathlib import Path

import pytest

pytestmark = [pytest.mark.integration]

_ROOT = Path(__file__).resolve().parents[1]
_SCRIPT = _ROOT / "migrations" / "apply_in_compose.sh"

# مصدر الرابط الإداريّ (دور بامتياز CREATE DATABASE). في CI (وظيفة Integration Tests) يُصدَّر
# ``TEST_DATABASE_ADMIN_URL``/``TEST_DATABASE_URL`` كدور superuser ``sahool_test`` على TCP؛ نُفضّلهما
# على ``DATABASE_URL`` العامّ (قد يكون رابط socket ``?host=/…`` لا يعمل في هذه الوظيفة).
_ADMIN_URL = (
    os.getenv("TEST_DATABASE_ADMIN_URL")
    or os.getenv("TEST_ADMIN_URL")
    or os.getenv("TEST_DATABASE_URL")
    or os.getenv("DATABASE_URL")
)


def _extract_role_heredoc(text: str) -> str:
    """يستخرج جسم أوّل heredoc ``<<'SQL' … SQL`` يحوي CREATE ROLE (كتلة تهيئة الدور)."""
    for m in re.finditer(r"<<'SQL'\n(.*?)\nSQL\b", text, re.DOTALL):
        body = m.group(1)
        if "CREATE ROLE" in body and "app_role" in body:
            return body
    raise AssertionError("role-bootstrap heredoc (CREATE ROLE + app_role) not found in script")


def _psql(url: str, *args: str, sql: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["psql", url, "-v", "ON_ERROR_STOP=1", *args],
        input=sql,
        capture_output=True,
        text=True,
    )


def _split_conn(url: str) -> tuple[str, str, str]:
    """يعيد (admin_url_to_postgres_db, base_without_db, query_suffix) لإنشاء/حذف قاعدة اختبار.

    يعزل سلسلة الاستعلام (مثل ``?host=/tmp/postgres`` أو ``?sslmode=…``) **قبل** التقسيم على '/'
    كي لا تُخلَط شرطة مسار socket داخل الاستعلام مع فاصل اسم القاعدة (كانت تكسر rpartition).
    """
    head, sep, query = url.partition("?")
    base, _, _db = head.rpartition("/")
    suffix = f"?{query}" if sep else ""
    return f"{base}/postgres{suffix}", base, suffix


@pytest.mark.skipif(shutil.which("psql") is None, reason="psql client not available")
@pytest.mark.skipif(not _ADMIN_URL, reason="TEST_DATABASE_ADMIN_URL/TEST_DATABASE_URL not set")
def test_role_bootstrap_block_executes_and_sets_privileges():
    body = _extract_role_heredoc(_SCRIPT.read_text(encoding="utf-8"))
    admin_pg, base, query = _split_conn(_ADMIN_URL)
    dbname = f"roletest_{uuid.uuid4().hex[:10]}"
    test_url = f"{base}/{dbname}{query}"
    role = f"sahool_app_t_{uuid.uuid4().hex[:6]}"

    created = _psql(admin_pg, "-tA", sql=f"CREATE DATABASE {dbname}")
    assert created.returncode == 0, created.stderr
    try:
        # جداول الهدف موجودة كي تُطبَّق REVOKEs (الحقيقيّة محميّة بـto_regclass).
        setup = (
            "CREATE TABLE admin_boundaries(id int); CREATE TABLE admin_boundaries_source(id int); "
            "CREATE TABLE season_records(id int); CREATE TABLE season_crop(id int); "
            "CREATE TABLE season_events(id int); CREATE TABLE season_harvest(id int); "
            "CREATE TABLE season_cost_items(id int);"
            # T3: دوالّ DEFINER لمستوى تحكّم الإدخال (أجسام وهميّة؛ ما يهمّ التوقيع وACL).
            " CREATE FUNCTION claim_submissions_for_projection(int, int) RETURNS int"
            " LANGUAGE sql SECURITY DEFINER AS 'SELECT 1';"
            " CREATE FUNCTION complete_submission_projection(bigint, text, text) RETURNS int"
            " LANGUAGE sql SECURITY DEFINER AS 'SELECT 1';"
            " CREATE FUNCTION resolve_ingest_source(text) RETURNS int"
            " LANGUAGE sql SECURITY DEFINER AS 'SELECT 1';"
            " CREATE FUNCTION t3_control_fn() RETURNS int LANGUAGE sql AS 'SELECT 1';"
            # كما في v198/v199: مسحوبة من PUBLIC، فلا يبقى EXECUTE إلّا ما يمنحه السكربت.
            " REVOKE ALL ON FUNCTION claim_submissions_for_projection(int, int) FROM PUBLIC;"
            " REVOKE ALL ON FUNCTION complete_submission_projection(bigint, text, text) FROM PUBLIC;"
            " REVOKE ALL ON FUNCTION resolve_ingest_source(text) FROM PUBLIC;"
            " REVOKE ALL ON FUNCTION t3_control_fn() FROM PUBLIC;"
        )
        assert _psql(test_url, sql=setup).returncode == 0

        # نشغّل جسم السكربت الحقيقيّ (CREATE ROLE + GRANTs + \gexec REVOKEs) مرّتين — idempotent.
        for _ in range(2):
            res = _psql(
                test_url, "-v", f"app_role={role}", "-v", "app_pw=throwaway_pw_123456", sql=body
            )
            assert res.returncode == 0, f"role bootstrap failed to EXECUTE:\n{res.stderr}"

        # مصفوفة الصلاحيات الفعليّة (البرهان الذي لا يعطيه grep النصّيّ).
        def priv(table: str, p: str) -> bool:
            out = _psql(
                test_url, "-tA", sql=f"SELECT has_table_privilege('{role}','{table}','{p}')"
            )
            return out.stdout.strip() == "t"

        assert priv("admin_boundaries", "SELECT") is True
        for p in ("INSERT", "UPDATE", "DELETE"):
            assert priv("admin_boundaries", p) is False, f"admin_boundaries {p} should be revoked"
        for t in (
            "season_records",
            "season_crop",
            "season_events",
            "season_harvest",
            "season_cost_items",
        ):
            assert (
                priv(t, "SELECT") is True
                and priv(t, "INSERT") is True
                and priv(t, "UPDATE") is True
            )
            assert priv(t, "DELETE") is False, f"{t} DELETE should be revoked (append-only)"

        # T3: المنح الشامل يبقى للدوالّ العاديّة، ويُسحَب بعده EXECUTE على دوالّ تحكّم الإدخال.
        def fexec(sig: str) -> bool:
            out = _psql(
                test_url, "-tA", sql=f"SELECT has_function_privilege('{role}','{sig}','EXECUTE')"
            )
            return out.stdout.strip() == "t"

        assert fexec("t3_control_fn()") is True
        for sig in (
            "claim_submissions_for_projection(integer,integer)",
            "complete_submission_projection(bigint,text,text)",
            "resolve_ingest_source(text)",
        ):
            assert fexec(sig) is False, f"{sig} EXECUTE must be revoked from app role (T3)"
    finally:
        _psql(admin_pg, "-tA", sql=f"DROP DATABASE IF EXISTS {dbname} WITH (FORCE)")
