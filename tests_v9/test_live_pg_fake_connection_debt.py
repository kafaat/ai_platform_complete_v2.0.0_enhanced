"""أدلّة حيّة على PG16 لِما يدّعي الاختبارُ أنّ **القاعدة** تفرضه.

`FAKE-CONNECTION-ENFORCES-NOTHING-01` — الشطر الذي لا يُسدَّد إلّا بقاعدة حقيقيّة.

**لماذا لا يكفي الوهميّ، مقيساً:** بعد ٢٢٦ هجرة على PG16 نظيفة تعطّلت الرحلة القانونيّة
**أربع مرّات بأربعة أسباب مختلفة**، وكلّها كانت خضراء سنةً على اتّصال وهميّ. والوهميّ
لا يفرض `CHECK` ولا `TRIGGER` ولا `UNIQUE`، ولا يُعيد أنواع `jsonb` كما يُعيدها asyncpg.

**والعقد هنا أضيق من «شغّله على قاعدة»:** لكلّ ادّعاء **حالة قبول وحالة رفض فعليّة**،
والرفض بـ`SQLSTATE` أو بأثر القيد/المشغّل. لأنّ حالة القبول وحدها تمرّ على جدولٍ بلا
قيدٍ أصلاً — فتُثبِت أنّ الإدراج يعمل، لا أنّ القاعدة تمنع شيئاً.

**واللاتماثل مقصود:**

  · وظيفة عامّة بلا قاعدة  ⇒ **تخطٍّ مُعلَن** (لا تُعطَّل بوّابات لا علاقة لها بالقاعدة)
  · وظيفة PG المخصّصة      ⇒ **فشل** إن لم تُنفَّذ — `SAHOOL_REQUIRE_LIVE_PG=1`

بلا هذا اللاتماثل يصير «تخطٍّ» في الوظيفة المخصّصة خضرةً تعني «لم يُقَس»، وهو الصنف
الذي أوجب الفجوة كلّها.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import uuid

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.slow]

_DB = os.environ.get("SAHOOL_TEST_PGDATABASE", "sahool")
# مقبس Unix محليّاً، ومضيف TCP في CI حيث تعمل القاعدة في حاوية. القيمة تصلح
# لـpsql (`-h`) ولـasyncpg (`host=`) معاً: كلاهما يقرأ المسار المطلق كمقبس.
_HOST = os.environ.get("SAHOOL_TEST_PGHOST", "/var/run/postgresql")
_PORT = os.environ.get("SAHOOL_TEST_PGPORT", "5432")
_APP_ROLE = os.environ.get("SAHOOL_TEST_PGROLE", "sahool_app")
_OWNER_ROLE = os.environ.get("SAHOOL_TEST_PGOWNER", "sahool_user")
_REQUIRE = os.environ.get("SAHOOL_REQUIRE_LIVE_PG") == "1"

TENANT_A = "11111111-1111-1111-1111-111111111111"
TENANT_B = "22222222-2222-2222-2222-222222222222"


def psql(sql: str, *, role: str) -> tuple[int, str, str]:
    """‏(rc, stdout, stderr) — بلا ابتلاع، فالفشل جزء من القياس.

    `shutil.which` أوّلاً: بلا عميل psql يرمي `subprocess.run` خطأً **وقت الاستيراد**
    فينهار جمع الملفّ — خطأُ تجميع يُخفي الملفّ كلّه بدل تخطٍّ مُعلَن.
    """
    if shutil.which("psql") is None:
        raise FileNotFoundError("psql")
    proc = subprocess.run(  # noqa: S603
        [
            "psql",
            "-h",
            _HOST,
            "-p",
            _PORT,
            "-d",
            _DB,
            "-U",
            role,
            "-v",
            "ON_ERROR_STOP=1",
            "-Atc",
            sql,
        ],
        capture_output=True,
        encoding="utf-8",
        check=False,
    )
    return proc.returncode, proc.stdout.strip(), proc.stderr.strip()


def sqlstate(sql: str, *, role: str) -> str:
    """`SQLSTATE` الفعليّ للرفض — لا نصّ الرسالة.

    نصّ الرسالة يتغيّر بإصدار الخادم وبلغته؛ و`SQLSTATE` عقدٌ ثابت في المعيار. تأكيدٌ
    على النصّ يمرّ اليوم ويُكذَب بترقية، وهو `GUARD-PINS-IMPLEMENTATION-NOT-PROPERTY-01`
    في ثوب آخر.

    **و`VERBOSITY verbose` ليست تجميلاً:** بدونها لا يطبع psql الرمز أصلاً. أوّل صياغة
    عندي حاولت انتزاعه من رسالة عاديّة فالتقطت `DO` — أي أنّ «الرفض بـSQLSTATE» كان
    سيمرّ بقيمةٍ ليست SQLSTATE لولا أنّ التأكيد يقارن رمزاً بعينه.
    """
    if shutil.which("psql") is None:
        raise FileNotFoundError("psql")
    proc = subprocess.run(  # noqa: S603
        [
            "psql",
            "-h",
            _HOST,
            "-p",
            _PORT,
            "-d",
            _DB,
            "-U",
            role,
            "-qAt",
            "-c",
            r"\set VERBOSITY verbose",
            "-c",
            f"do $$ begin {sql}; end $$;",
        ],
        capture_output=True,
        encoding="utf-8",
        check=False,
    )
    assert proc.returncode != 0, "العبارة نجحت بينما الاختبار يتوقّع رفضاً من القاعدة"
    # الصيغة المطوَّلة تضع الرمز **داخل** سطر الخطأ: `ERROR:  42501: …` — لا في سطر
    # مستقلّ. أوّل صياغة بحثت عن سطرٍ يبدأ بـ`SQLSTATE:` فلم تجده، وكانت سترفع
    # AssertionError عن غياب الرمز بينما الرمز حاضر أمامها.
    match = re.search(r"^ERROR:\s+([0-9A-Z]{5}):", proc.stderr, re.MULTILINE)
    if match:
        return match.group(1)
    raise AssertionError(f"لم يطبع الخادم SQLSTATE:\n{proc.stderr}")


def _live() -> tuple[bool, str]:
    if shutil.which("psql") is None:
        return False, "لا عميل psql"
    try:
        rc, out, err = psql("select 1", role=_OWNER_ROLE)
    except OSError as exc:  # pragma: no cover - بيئة بلا psql رغم which
        return False, f"psql غير قابل للتشغيل: {exc}"
    return (rc == 0 and out == "1"), (err or "لا اتّصال بالقاعدة")


_LIVE, _WHY = _live()

if _REQUIRE and not _LIVE:
    raise RuntimeError(
        "SAHOOL_REQUIRE_LIVE_PG=1 والقاعدة غير متاحة: " + _WHY + "\n"
        "هذه وظيفة PG المخصّصة — التخطّي فيها خضرةٌ تعني «لم يُقَس»، وهو الصنف الذي "
        "أوجب FAKE-CONNECTION-ENFORCES-NOTHING-01. تُشغَّل القاعدة أو تُسقَط الوظيفة."
    )

pytestmark.append(pytest.mark.skipif(not _LIVE, reason=f"تخطٍّ مُعلَن (ليس نجاحاً): {_WHY}"))


def as_tenant(tenant: str, sql: str) -> str:
    return f"set local app.current_tenant = '{tenant}'; {sql}"


# ═══════════════════ الدور المقيَّد — قبل أيّ ادّعاء عزل ═══════════════════


def test_the_app_role_is_provably_restricted():
    """بلا هذا، كلّ ادّعاء عزلٍ تحته يقيس دوراً يتخطّى RLS فيمرّ مجّاناً.

    `NOSUPERUSER` **و**`NOBYPASSRLS` معاً: الأولى وحدها لا تكفي — دورٌ عاديّ بـ
    `BYPASSRLS` يقرأ كلّ المستأجِرين وهو ليس superuser.
    """
    rc, out, _ = psql(
        f"select rolsuper::text||'/'||rolbypassrls::text from pg_roles where rolname='{_APP_ROLE}'",
        role=_OWNER_ROLE,
    )
    assert rc == 0, "الدور غير موجود"
    assert out == "false/false", f"{_APP_ROLE} ليس مقيَّداً: super/bypassrls = {out}"


# ═════════ tests_v9/test_water_ledger.py — الادّعاء: UNIQUE (upsert) ═════════
#
# الوهميّ يؤكّد أنّ نصّ SQL **يحوي** `ON CONFLICT (field_id, ledger_date) DO UPDATE`.
# وهذا لا يُثبِت شيئاً عن القاعدة: لا أنّ الهدف قيدٌ قائم، ولا أنّ التكرار يُمنَع،
# ولا أنّ الـupsert مُتماثِل. الثلاثة تُقاس هنا.


def _insert_ledger(field: str, date: str, etc: float, *, conflict: str, tenant: str = TENANT_A):
    return as_tenant(
        tenant,
        "insert into water_ledger (tenant_id, field_id, ledger_date, etc_mm) values "
        f"('{tenant}', '{field}', date '{date}', {etc}) "
        f"on conflict ({conflict}) do update set etc_mm = excluded.etc_mm",
    )


@pytest.fixture
def field_id():
    return f"fld-{uuid.uuid4().hex[:12]}"


def test_the_upsert_target_is_a_real_constraint_accept(field_id):
    """**القبول:** إدراجان بنفس المفتاح ⇒ صفٌّ واحد، والقيمة الثانية تسود.

    وهذا يُثبِت ثلاثة أشياء لا يراها الوهميّ: أنّ `(field_id, ledger_date)` هدفٌ صالح
    لـ`ON CONFLICT`، وأنّ التكرار **لا يُنشئ صفّاً ثانياً**، وأنّ `DO UPDATE` يكتب.
    """
    rc, _, err = psql(
        _insert_ledger(field_id, "2026-06-22", 4.0, conflict="field_id, ledger_date"),
        role=_APP_ROLE,
    )
    assert rc == 0, err
    rc, _, err = psql(
        _insert_ledger(field_id, "2026-06-22", 9.5, conflict="field_id, ledger_date"),
        role=_APP_ROLE,
    )
    assert rc == 0, err

    rc, out, _ = psql(
        as_tenant(
            TENANT_A,
            f"select count(*)::text||'/'||max(etc_mm)::text from water_ledger "
            f"where field_id='{field_id}'",
        ),
        role=_APP_ROLE,
    )
    assert rc == 0
    assert out.splitlines()[-1] == "1/9.5", f"الـupsert ليس مُتماثِلاً: {out}"


def test_a_wrong_conflict_target_is_refused_by_the_database_reject(field_id):
    """**الرفض:** هدفُ تعارضٍ لا يقابله قيدٌ فريد ⇒ `42P10` من الخادم.

    وهذا ما يجعل الادّعاء **عن القاعدة** لا عن النصّ: لو كان `(field_id, ledger_date)`
    مجرّد عبارة في سلسلة، لَقبِلت القاعدة أيّ هدفٍ آخر بالسهولة نفسها. و`42P10`
    (`invalid_column_reference`) يُسمّي بالضبط «لا قيد فريد يطابق مواصفة ON CONFLICT».
    """
    state = sqlstate(
        _insert_ledger(field_id, "2026-06-23", 1.0, conflict="field_id"),
        role=_APP_ROLE,
    )
    assert state == "42P10", f"رُفِض بسببٍ آخر: SQLSTATE={state}"


def test_the_primary_key_is_the_upsert_target_measured_on_the_database(field_id):
    """هويّة القيد تُقرأ من الكتالوج لا من الهجرة — الهجرة نيّة، والكتالوج واقع."""
    rc, out, _ = psql(
        "select pg_get_constraintdef(oid) from pg_constraint "
        "where conrelid='water_ledger'::regclass and contype='p'",
        role=_OWNER_ROLE,
    )
    assert rc == 0
    assert out == "PRIMARY KEY (field_id, ledger_date)", out


def test_rls_isolates_the_ledger_under_the_restricted_role(field_id):
    """العزل يُقاس بالقراءة الفعليّة تحت الدور المقيَّد، لا بوجود السياسة في الكتالوج."""
    rc, _, err = psql(
        _insert_ledger(field_id, "2026-06-24", 2.0, conflict="field_id, ledger_date"),
        role=_APP_ROLE,
    )
    assert rc == 0, err

    for tenant, expected in ((TENANT_A, "1"), (TENANT_B, "0")):
        rc, out, _ = psql(
            as_tenant(tenant, f"select count(*) from water_ledger where field_id='{field_id}'"),
            role=_APP_ROLE,
        )
        assert rc == 0 and out.splitlines()[-1] == expected, f"{tenant} ⇒ {out}"


def test_row_level_security_is_enabled_and_forced_in_the_catalog():
    """**حدٌّ مُعلَن: هذا تأكيدٌ كتالوجيّ لا سلوكيّ** — والفرق مقيس هنا.

    زرعتُ `NO FORCE ROW LEVEL SECURITY` على نسخةٍ من القاعدة فلم يسقط شيء من هذا
    الملفّ: كلّ ما تحته يقيس الدور المقيَّد، و`FORCE` لا يمسّ إلّا **مالك الجدول**.
    فإمّا أن يُقاس أو يُحذف الادّعاء؛ وهذا التأكيد يجعل للزرع قاتلاً.

    ولمَ كتالوجيّاً لا سلوكيّاً: المالك هنا `sahool_user` وهو superuser، و`superuser`
    يتخطّى RLS **مهما كان `FORCE`**. مقيس: `select count(*) from water_ledger` تحته
    بلا `app.current_tenant` يُعيد كلّ الصفوف. فأثر `FORCE` غير قابل للرصد في هذا
    التشكيل، وادّعاء سلوكيٍّ هنا سيكون `GUARD-PINS-IMPLEMENTATION-NOT-PROPERTY-01`.

    **وهذه ليست ملاحظةً بل نتيجة:** `FORCE` خامدٌ ما دام المالك superuser، فأيّ اتّصال
    تطبيقيّ بدور المالك يقرأ كلّ المستأجِرين وRLS قائمةٌ في الكتالوج. سُجِّلت في
    `docs/architecture/live_pg_findings.md` ولا تُصلَح داخل هذه الشريحة.
    """
    rc, out, _ = psql(
        "select relrowsecurity::text||'/'||relforcerowsecurity::text "
        "from pg_class where oid='water_ledger'::regclass",
        role=_OWNER_ROLE,
    )
    assert rc == 0
    assert out == "true/true", f"RLS ليست مُفعَّلة ومفروضة: enabled/forced = {out}"


def test_writing_under_another_tenant_is_refused_by_with_check(field_id):
    """`WITH CHECK` يمنع الكتابة **باسم** مستأجِر آخر — لا التطبيق وحده."""
    sql = (
        "insert into water_ledger (tenant_id, field_id, ledger_date, etc_mm) values "
        f"('{TENANT_B}', '{field_id}', date '2026-06-25', 3.0)"
    )
    state = sqlstate(as_tenant(TENANT_A, sql), role=_APP_ROLE)
    assert state == "42501", f"لم يُرفَض بـinsufficient_privilege: SQLSTATE={state}"


# ═══ services/soil-service/test_soil_projection_jobs.py — الادّعاء: UNIQUE ═══
#
# الوهميّ يؤكّد سلسلتين منفصلتين في نصّ SQL: `ON CONFLICT (tenant_id, field_id)`
# و`pending','running','retry`. **ولا شيء يربطهما** — تأكيدان يمرّان لو حُذف أحدهما
# من موضعه ووُضع في تعليق. وارتباطهما ليس تجميلاً بل شرط صحّة: الفهرس الفريد هنا
# **جزئيّ**، وPostgreSQL لا يختار فهرساً جزئيّاً لـ`ON CONFLICT` إلّا إذا كرّرت
# العبارةُ مُسنِدَه. فالنصّ الذي يحمل السلسلة الأولى وحدها يُرفَض على قاعدة حقيقيّة.


def _enqueue_job(field: str, reason: str, *, predicate: bool) -> str:
    where = "where status in ('pending','running','retry')" if predicate else ""
    return (
        "insert into soil_profile_projection_jobs (tenant_id, field_id, reason) values "
        f"('{TENANT_A}', '{field}', '{reason}') "
        f"on conflict (tenant_id, field_id) {where} "
        "do update set reason = excluded.reason"
    )


def test_the_active_field_coalescing_is_a_real_partial_index_accept(field_id):
    """**القبول:** إدراجان بنفس (tenant, field) ⇒ صفٌّ واحد والسبب الأخير يسود."""
    for reason in ("first", "second"):
        rc, _, err = psql(_enqueue_job(field_id, reason, predicate=True), role=_OWNER_ROLE)
        assert rc == 0, err

    rc, out, _ = psql(
        "select count(*)::text||'/'||max(reason) from soil_profile_projection_jobs "
        f"where field_id='{field_id}'",
        role=_OWNER_ROLE,
    )
    assert rc == 0 and out == "1/second", f"لم يُدمَج العمل النشِط: {out}"


def test_dropping_the_predicate_is_refused_because_the_index_is_partial_reject(field_id):
    """**الرفض:** العبارة ذاتها بلا المُسنِد ⇒ `42P10`.

    هذا هو القياس الذي يربط تأكيدَي الوهميّ: لو كان المُسنِد زينةً لَقبِلته القاعدة.
    """
    state = sqlstate(_enqueue_job(field_id, "no-predicate", predicate=False), role=_OWNER_ROLE)
    assert state == "42P10", f"رُفِض بسببٍ آخر: SQLSTATE={state}"


def test_a_completed_job_does_not_block_new_work_because_the_index_is_partial(field_id):
    """«completed history remains immutable» — الجزئيّة **سلوك** لا تعليق في الهجرة.

    فهرسٌ كامل على (tenant, field) كان سيجعل الحقلَ غيرَ قابل لإعادة الجدولة أبداً
    بعد أوّل اكتمال. مقيس هنا: بعد `completed` يُنشئ الإدراج التالي صفّاً **ثانياً**.
    """
    rc, _, err = psql(_enqueue_job(field_id, "run-1", predicate=True), role=_OWNER_ROLE)
    assert rc == 0, err
    rc, _, err = psql(
        f"update soil_profile_projection_jobs set status='completed' where field_id='{field_id}'",
        role=_OWNER_ROLE,
    )
    assert rc == 0, err
    rc, _, err = psql(_enqueue_job(field_id, "run-2", predicate=True), role=_OWNER_ROLE)
    assert rc == 0, err

    rc, out, _ = psql(
        f"select count(*) from soil_profile_projection_jobs where field_id='{field_id}'",
        role=_OWNER_ROLE,
    )
    assert rc == 0 and out == "2", f"المكتمِل يحجب عملاً جديداً: {out} صفّاً"


def test_the_job_status_domain_is_enforced_by_the_database_reject(field_id):
    """`CHECK` على `status` — الوهميّ يقبل أيّ سلسلة."""
    state = sqlstate(
        "insert into soil_profile_projection_jobs (tenant_id, field_id, status) values "
        f"('{TENANT_A}', '{field_id}', 'bogus')",
        role=_OWNER_ROLE,
    )
    assert state == "23514", f"قُبِلت حالة خارج المجال أو رُفِضت بسببٍ آخر: {state}"


# ══ tests_v9/test_offline_pending_queue.py — الادّعاء: UNIQUE (DO NOTHING) ══


def _insert_op(op_id: str, kind: str, *, conflict: str = "op_id") -> str:
    return (
        "insert into offline_pending_ops (op_id, tenant_id, user_id, op_kind, created_at) "
        f"values ('{op_id}', '{TENANT_A}', 'u1', '{kind}', now()) "
        f"on conflict ({conflict}) do nothing"
    )


@pytest.fixture
def op_id():
    return str(uuid.uuid4())


def test_the_offline_queue_insert_is_idempotent_on_the_database_accept(op_id):
    """**القبول:** `DO NOTHING` ⇒ الثاني لا يكتب، و**القيمة الأولى تبقى**.

    الوهميّ يُحاكي هذا في بايثون (`if s.startswith("INSERT INTO offline_pending_ops")`)
    فيُثبِت أنّ محاكاته تعمل. المقيس هنا أنّ **القاعدة** تفعله.
    """
    for kind in ("first", "second"):
        rc, _, err = psql(_insert_op(op_id, kind), role=_OWNER_ROLE)
        assert rc == 0, err

    rc, out, _ = psql(
        f"select count(*)::text||'/'||max(op_kind) from offline_pending_ops where op_id='{op_id}'",
        role=_OWNER_ROLE,
    )
    assert rc == 0 and out == "1/first", f"‏DO NOTHING لم يحفظ الأوّل: {out}"


def test_a_conflict_target_without_a_unique_constraint_is_refused_reject(op_id):
    """**الرفض:** `on conflict (op_kind)` ⇒ `42P10` — لا قيد فريد يقابله."""
    state = sqlstate(_insert_op(op_id, "x", conflict="op_kind"), role=_OWNER_ROLE)
    assert state == "42P10", f"رُفِض بسببٍ آخر: SQLSTATE={state}"


def test_the_offline_queue_status_domain_is_enforced_reject(op_id):
    state = sqlstate(
        "insert into offline_pending_ops "
        "(op_id, tenant_id, user_id, op_kind, created_at, status) values "
        f"('{op_id}', '{TENANT_A}', 'u1', 'k', now(), 'bogus')",
        role=_OWNER_ROLE,
    )
    assert state == "23514", f"قُبِلت حالة خارج المجال أو رُفِضت بسببٍ آخر: {state}"


# ═══ tests_v9/test_scouting_pins_persistence.py — الادّعاء: UNIQUE (pin_id) ═══


def _insert_pin(pin: str, category: str, *, conflict: str = "pin_id") -> str:
    return (
        "insert into scouting_pins (pin_id, tenant_id, field_id, lat, lng, issue_category) "
        f"values ('{pin}', '{TENANT_A}', 'F1', 24.7, 46.7, '{category}') "
        f"on conflict ({conflict}) do nothing"
    )


def test_scouting_pin_persistence_is_idempotent_on_the_database_accept(field_id):
    pin = f"pin-{field_id}"
    for category in ("pest", "disease"):
        rc, _, err = psql(_insert_pin(pin, category), role=_OWNER_ROLE)
        assert rc == 0, err

    rc, out, _ = psql(
        f"select count(*)::text||'/'||max(issue_category) from scouting_pins where pin_id='{pin}'",
        role=_OWNER_ROLE,
    )
    assert rc == 0 and out == "1/pest", f"ليس idempotent على القاعدة: {out}"


def test_a_scouting_pin_conflict_target_that_is_not_unique_is_refused_reject(field_id):
    state = sqlstate(_insert_pin(f"pin2-{field_id}", "pest", conflict="field_id"), role=_OWNER_ROLE)
    assert state == "42P10", f"رُفِض بسببٍ آخر: SQLSTATE={state}"


# ═══ tests_v9/test_workflow_store_hardening.py — الادّعاء: TRIGGER ═══


def test_the_workflow_updated_at_trigger_fires_on_the_database_accept(field_id):
    """**القبول:** `UPDATE` لا يمسّ `updated_at` ⇒ المشغّل يكتبها رغم ذلك.

    ولا يكفي أن تتغيّر: العبارة تُسنِد `updated_at` صراحةً إلى ماضٍ بعيد، فلو كان
    المشغّل غائباً لَبقيت القيمة المُسنَدة. البقاء والتغيّر يفترقان هنا، وهذا ما
    يجعل القياس عن **المشغّل** لا عن `DEFAULT now()`.
    """
    wf = f"wf-{field_id}"
    rc, _, err = psql(
        f"insert into workflow_state (workflow_id, tenant_id) values ('{wf}', '{TENANT_A}')",
        role=_OWNER_ROLE,
    )
    assert rc == 0, err
    rc, _, err = psql(
        f"update workflow_state set updated_at = timestamptz '2001-01-01' where workflow_id='{wf}'",
        role=_OWNER_ROLE,
    )
    assert rc == 0, err

    rc, out, _ = psql(
        f"select (updated_at > now() - interval '1 minute')::text from workflow_state "
        f"where workflow_id='{wf}'",
        role=_OWNER_ROLE,
    )
    assert rc == 0
    assert out == "true", "المشغّل لم يدهس القيمة المُسنَدة — `touch_workflow_updated_at` خامد"


def test_the_trigger_is_registered_before_update_for_each_row(field_id):
    """التوقيت جزء من الادّعاء: `AFTER` أو `FOR EACH STATEMENT` لا يكتب `NEW`."""
    rc, out, _ = psql(
        "select tgname from pg_trigger where tgrelid='workflow_state'::regclass "
        "and not tgisinternal and (tgtype & 2) = 2 and (tgtype & 1) = 1 "
        "and (tgtype & 16) = 16",
        role=_OWNER_ROLE,
    )
    assert rc == 0
    assert out == "trg_workflow_updated", f"ليس BEFORE UPDATE FOR EACH ROW: {out!r}"


# ═ tests_v9/test_canonical_event_emission_contracts.py — CHECK · TRIGGER · jsonb ═
#
# الوهميّ يقرأ `CHECK (source IN (...))` من نصّ الهجرة بتعبير نمطيّ ويقارنه بتعداد
# بايثون. هذا يحرس **الانحراف** بين نصّين ولا يمسّ القاعدة: لو لم تُطبَّق الهجرة
# أصلاً لَبقي أخضر.


def _insert_event(source: str, *, command_id: str = "null", payload: str = "'{}'::jsonb") -> str:
    return (
        "insert into events (event_type, entity_type, entity_id, tenant_id, source, "
        "command_id, payload) values "
        f"('t.e', 'field', 'F1', '{TENANT_A}', '{source}', {command_id}, {payload})"
    )


def test_the_event_source_domain_is_enforced_by_the_database(field_id):
    """قبولٌ ورفض على المحور نفسه: `mobile` تمرّ و`bogus` تُرفَض بـ`23514`."""
    rc, _, err = psql(_insert_event("mobile"), role=_OWNER_ROLE)
    assert rc == 0, err
    state = sqlstate(_insert_event("bogus"), role=_OWNER_ROLE)
    assert state == "23514", f"قُبِل مصدر خارج المجال أو رُفِض بسببٍ آخر: {state}"


def test_the_events_command_fk_is_enforced_by_the_database(field_id):
    """`events.command_id REFERENCES commands(command_id)` — الوهميّ يقبل أيّ UUID.

    والمحور واحد: أمرٌ **قائم** يمرّ، وأمرٌ غير موجود يُرفَض بـ`23503`. الرفض وحده
    كان سيمرّ على عمودٍ `NOT NULL` بلا مرجع أصلاً؛ والقبول وحده يمرّ بلا قيد. معاً
    يُسمّيان القيد.
    """
    command = str(uuid.uuid4())
    rc, _, err = psql(
        "insert into commands (command_id, command_type, actor_id, tenant_id, payload, source) "
        f"values ('{command}', 'c.t', 'a1', '{TENANT_A}', '{{}}'::jsonb, 'web')",
        role=_OWNER_ROLE,
    )
    assert rc == 0, err
    rc, _, err = psql(_insert_event("mobile", command_id=f"'{command}'::uuid"), role=_OWNER_ROLE)
    assert rc == 0, f"رُفِض أمرٌ قائم — المرجع ليس المقيس: {err}"

    state = sqlstate(
        _insert_event("mobile", command_id=f"'{uuid.uuid4()}'::uuid"), role=_OWNER_ROLE
    )
    assert state == "23503", f"قُبِل أمرٌ غير موجود أو رُفِض بسببٍ آخر: {state}"


def test_the_events_table_is_append_only_by_trigger_reject(field_id):
    """`UPDATE` و`DELETE` كلاهما مرفوض — والمشغّل يرفع `check_violation` (23514)."""
    rc, _, err = psql(_insert_event("web"), role=_OWNER_ROLE)
    assert rc == 0, err
    for verb in (
        "update events set entity_id='X' where entity_id='F1'",
        "delete from events where entity_id='F1'",
    ):
        state = sqlstate(verb, role=_OWNER_ROLE)
        assert state == "23514", f"«{verb.split()[0]}» لم يُرفَض بالمشغّل: SQLSTATE={state}"


def test_jsonb_is_validated_by_the_database_not_by_the_writer_reject(field_id):
    """`22P02` — نصٌّ ليس JSON يُرفَض عند التحويل، والوهميّ يخزّنه كسلسلة."""
    state = sqlstate(_insert_event("web", payload="'{not json'::jsonb"), role=_OWNER_ROLE)
    assert state == "22P02", f"قُبِل jsonb غير صالح أو رُفِض بسببٍ آخر: {state}"


def test_asyncpg_really_returns_jsonb_as_str_without_a_codec(field_id):
    """الادّعاء الوحيد هنا الذي **لا يقيسه psql**: سلوك المُشغِّل، لا القاعدة.

    الاختبار الوهميّ يبني صفّاً «كما يُعيده asyncpg» — أي يفترض الجواب الذي يدّعي
    قياسه. وهو افتراض صحيح، لكنّه غير مقيس: لو سجّل الإصدار التالي مُرمِّزاً افتراضيّاً
    لَبقي الوهميّ أخضر بينما ينكسر `decode_jsonb` في الإنتاج.

    فيُقاس هنا باتّصال asyncpg حقيقيّ: `jsonb` يصل **نصّاً** ما لم يُسجَّل مُرمِّز،
    و`json.loads` عليه يُعيد البنية. والقبول والرفض على المحور نفسه: بعد
    `set_type_codec` يصل **مفكوكاً** — فالسلسلة ليست خاصّية أبديّة بل نتيجة غياب
    المُرمِّز، وهو بالضبط ما يعتمد عليه `decode_jsonb`.
    """
    asyncpg = pytest.importorskip("asyncpg", reason="المُشغِّل غير مثبَّت — لا يُقاس هنا")
    import asyncio
    import json

    async def measure():
        conn = await asyncpg.connect(host=_HOST, port=int(_PORT), user=_OWNER_ROLE, database=_DB)
        try:
            raw = await conn.fetchval("select '{\"a\": [1, 2]}'::jsonb")
            await conn.set_type_codec(
                "jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog"
            )
            decoded = await conn.fetchval("select '{\"a\": [1, 2]}'::jsonb")
            return raw, decoded
        finally:
            await conn.close()

    raw, decoded = asyncio.run(measure())
    assert isinstance(raw, str), (
        f"asyncpg أعاد {type(raw).__name__} لا str — `decode_jsonb` مبنيّ على العكس"
    )
    assert json.loads(raw) == {"a": [1, 2]}
    assert decoded == {"a": [1, 2]}, "تسجيل المُرمِّز لم يغيّر النتيجة — القياس لا يفرّق الحالتين"


# ═ services/sahool-platform/tests/test_persisted_canonical_writers.py — FK · UNIQUE ═


def _insert_nutrient_ledger(digest: str, status: str, *, conflict: str | None = None) -> str:
    tail = f"on conflict ({conflict}) do nothing" if conflict else ""
    return (
        "insert into canonical_nutrient_ledgers "
        "(tenant_id, field_id, season_id, crop_id, phenology_stage, as_of, status, "
        "balances, ledger_digest) values "
        f"('{TENANT_A}', 'F1', 'S1', 'C1', 'mid', now(), '{status}', "
        f"'{{\"nutrient\": \"N\"}}'::jsonb, '{digest}') {tail}"
    )


@pytest.fixture
def digest():
    return uuid.uuid4().hex + uuid.uuid4().hex


def test_the_nutrient_ledger_conflict_target_is_a_real_unique_constraint_accept(digest):
    """**القبول:** الرباعيّ `(tenant, field, season, ledger_digest)` هدفٌ صالح ومُسكِت."""
    target = "tenant_id, field_id, season_id, ledger_digest"
    for status in ("managed", "blocked"):
        rc, _, err = psql(
            _insert_nutrient_ledger(digest, status, conflict=target), role=_OWNER_ROLE
        )
        assert rc == 0, err

    rc, out, _ = psql(
        f"select count(*)::text||'/'||max(status) from canonical_nutrient_ledgers "
        f"where ledger_digest='{digest}'",
        role=_OWNER_ROLE,
    )
    assert rc == 0 and out == "1/managed", f"‏DO NOTHING لم يحفظ الأوّل: {out}"


def test_the_nutrient_ledger_rejects_a_duplicate_without_a_conflict_clause_reject(digest):
    """**الرفض:** بلا `ON CONFLICT` ⇒ `23505` — القيد قائم لا العبارة."""
    rc, _, err = psql(_insert_nutrient_ledger(digest, "managed"), role=_OWNER_ROLE)
    assert rc == 0, err
    state = sqlstate(_insert_nutrient_ledger(digest, "managed"), role=_OWNER_ROLE)
    assert state == "23505", f"قُبِل التكرار أو رُفِض بسببٍ آخر: SQLSTATE={state}"


def test_the_ledger_digest_shape_is_enforced_by_the_database_reject():
    """`CHECK (ledger_digest ~ '^[0-9a-f]{64}$')` — الوهميّ يقبل `'e' * 64` وأيّ شيء."""
    state = sqlstate(_insert_nutrient_ledger("NOT-A-DIGEST", "managed"), role=_OWNER_ROLE)
    assert state == "23514", f"قُبِل بصمة غير صالحة أو رُفِض بسببٍ آخر: {state}"


def test_the_phenology_state_conflict_target_is_the_primary_key_measured(digest):
    """`ON CONFLICT (tenant_id, state_digest)` — هويّة القيد من الكتالوج لا من الهجرة."""
    rc, out, _ = psql(
        "select pg_get_constraintdef(oid) from pg_constraint "
        "where conrelid='canonical_phenology_states'::regclass and contype='p'",
        role=_OWNER_ROLE,
    )
    assert rc == 0
    assert out == "PRIMARY KEY (tenant_id, state_digest)", out


# ═ services/sahool-platform/tests/test_prescriptions_router.py — UNIQUE · jsonb ═


def _insert_prescription(pid: str, name: str, zones: str = '[{"z": 1, "rate": 12.5}]') -> str:
    return (
        "insert into prescriptions "
        "(prescription_id, tenant_id, field_id, name, product_type, zones) values "
        f"('{pid}', '{TENANT_A}', 'F1', '{name}', 'fertilizer', '{zones}'::jsonb) "
        "on conflict (prescription_id) do nothing"
    )


def test_prescription_insert_is_idempotent_on_the_database_accept(field_id):
    pid = f"rx-{field_id}"
    for name in ("first", "second"):
        rc, _, err = psql(_insert_prescription(pid, name), role=_OWNER_ROLE)
        assert rc == 0, err

    rc, out, _ = psql(
        f"select count(*)::text||'/'||max(name) from prescriptions where prescription_id='{pid}'",
        role=_OWNER_ROLE,
    )
    assert rc == 0 and out == "1/first", f"‏DO NOTHING لم يحفظ الأوّل: {out}"


def test_prescription_zones_round_trip_as_jsonb_not_as_text_accept(field_id):
    """`zones` عمود `jsonb` — يُستعلَم بنيويّاً، والأرقام تعود أرقاماً.

    الوهميّ يمرّر السلسلة ويستعيدها، فيمرّ على عمود `text` بالسهولة نفسها.
    """
    pid = f"rx2-{field_id}"
    rc, _, err = psql(_insert_prescription(pid, "zones"), role=_OWNER_ROLE)
    assert rc == 0, err

    rc, out, _ = psql(
        "select jsonb_typeof(zones)||'/'||jsonb_typeof(zones->0->'rate')||'/'||"
        f"(zones->0->>'rate') from prescriptions where prescription_id='{pid}'",
        role=_OWNER_ROLE,
    )
    assert rc == 0
    assert out == "array/number/12.5", f"العمود لا يتصرّف كـjsonb: {out}"


def test_prescription_zones_reject_invalid_json(field_id):
    state = sqlstate(
        _insert_prescription(f"rx3-{field_id}", "bad", zones="{not json"), role=_OWNER_ROLE
    )
    assert state == "22P02", f"قُبِل jsonb غير صالح أو رُفِض بسببٍ آخر: {state}"
