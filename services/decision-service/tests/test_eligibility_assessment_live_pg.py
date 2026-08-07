"""الدليل الحيّ لـ`CANONICAL-SNAPSHOT-ELIGIBILITY-POLICY-01` — قاعدة حقيقيّة، دورٌ مقيَّد.

**لماذا لا يكفي الوهميّ هنا، مقيساً لا مُرجَّحاً:** `FAKE-CONNECTION-ENFORCES-NOTHING-01`
سجّل في هذا المستودع أنّ اتّصالاً وهميّاً لا يفرض `CHECK` ولا `TRIGGER` ولا `UNIQUE`
ولا يُعيد أنواع `jsonb` كما يُعيدها asyncpg. وكلّ ما تحته **قاعدةٌ تفرضه**:

* عزل المستأجِر (RLS) — **لا يُقاس إلّا بدورٍ لا يتخطّاه**. الدور هنا `sahool_app`
  بـ`rolsuper=false` و`rolbypassrls=false`، وسياسة الجدول `FORCE`.
* الإلحاق فقط (مُشغِّل يمنع `UPDATE`/`DELETE`).
* التفرّد على `(tenant_id, snapshot_hash, policy_version, as_of)`.
* قيود `CHECK` على شكل البصمات وعلى حضور المراحل الأربع.
* والمعاملة: فشلٌ داخلها لا يترك نصف تقييم.

يتخطّى **مُعلِناً** إن لم تتوفّر قاعدة — التخطّي المُعلَن ليس نجاحاً، والخضرة الصامتة
هي ما يجعل «مُسجَّل» يُقرأ «يعمل».
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.slow]

_SERVICE = Path(__file__).resolve().parents[1]
_TABLE = "decision_eligibility_assessments"
TENANT_A = "11111111-1111-1111-1111-111111111111"
TENANT_B = "22222222-2222-2222-2222-222222222222"
AS_OF = datetime(2026, 8, 7, 12, 0, tzinfo=UTC)


def _load():
    spec = importlib.util.spec_from_file_location(
        "eligibility_policy", _SERVICE / "eligibility_policy.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules["eligibility_policy"] = module
    spec.loader.exec_module(module)
    return module


EP = _load()


def _psql(sql: str, *, role: str, database: str = "sahool", port: str | None = None):
    """يُشغّل SQL ويُعيد ‏(rc, stdout, stderr) — بلا ابتلاع، فالفشل جزء من القياس."""
    port = port or os.environ.get("SAHOOL_TEST_PGPORT", "5432")
    proc = subprocess.run(  # noqa: S603
        [
            "psql",
            "-p",
            port,
            "-d",
            database,
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


def _live() -> bool:
    rc, out, _ = _psql(f"select to_regclass('public.{_TABLE}')", role="sahool_user")
    return rc == 0 and out == _TABLE


pytestmark.append(
    pytest.mark.skipif(
        not _live(),
        reason=(
            "لا قاعدة حيّة تحمل الجدول — التخطّي مُعلَن ولا يُحسَب نجاحاً. "
            "طبّق services/decision-service/migrations/031_eligibility_assessment.sql"
        ),
    )
)


@pytest.fixture
def assessment():
    """يُدخِل **اللقطة أوّلاً** ثمّ يُعيد تقييمها.

    أوّل صياغة عندي أدخلت التقييم وحده، فسقط بـ`violates foreign key constraint` —
    والمرجع المُركَّب `(tenant_id, snapshot_hash)` يفعل ما وُضِع له: لا تقييم لِلقطةٍ
    لا وجود لها، ولا لِلقطة مستأجِرٍ آخر. الفشل كان القيد يعمل لا عيباً فيه.
    """
    snap = {
        "snapshot_hash": uuid.uuid4().hex + uuid.uuid4().hex,
        "tenant_id": TENANT_A,
        "acquisition_at": (AS_OF - timedelta(hours=2)).isoformat(),
        "data_available_at": (AS_OF - timedelta(hours=1)).isoformat(),
        "quality_gate": {
            "weather_observed_at": (AS_OF - timedelta(hours=1)).isoformat(),
            "soil_observed_at": (AS_OF - timedelta(hours=10)).isoformat(),
            "valid_pixel_pct": 95.0,
        },
        "feature_manifest": {"spectral_bands": ["ndvi", "ndmi"]},
    }
    rc, _, err = _psql(
        "insert into decision_vegetation_snapshots (snapshot_id, tenant_id, field_id,"
        " season_id, contract_version, snapshot_hash, acquisition_at, data_available_at,"
        " quality_gate, feature_manifest, payload) values ("
        f"'snap_{uuid.uuid4().hex}', '{TENANT_A}', 'field-1', 'season-1',"
        f" 'vegetation-snapshot.v2', '{snap['snapshot_hash']}',"
        f" '{snap['acquisition_at']}', '{snap['data_available_at']}',"
        f" '{json.dumps(snap['quality_gate'])}'::jsonb,"
        f" '{json.dumps(snap['feature_manifest'])}'::jsonb, '{{}}'::jsonb)",
        role="sahool_app",
    )
    assert rc == 0, f"تعذّر إدخال اللقطة المرجعيّة: {err}"
    return EP.assess(snapshot=snap, policy_version="v1", as_of=AS_OF, tenant_id=TENANT_A)


def _insert_sql(a, *, tenant: str, assessment_id: str, as_of: str | None = None) -> str:
    row = a.as_row()
    return (
        f"insert into {_TABLE} (assessment_id, tenant_id, snapshot_hash, policy_version,"
        " policy_digest, contract_version, as_of, inputs_digest, assessment_digest,"
        " stages, reasons) values ("
        f"'{assessment_id}', '{tenant}', '{row['snapshot_digest']}', '{row['policy_version']}',"
        f" '{row['policy_digest']}', '{row['contract_version']}', '{as_of or row['as_of']}',"
        f" '{row['inputs_digest']}', '{row['assessment_digest']}',"
        f" '{json.dumps(row['stages'])}'::jsonb, '{json.dumps(row['reasons'])}'::jsonb)"
    )


def _as_tenant(tenant: str, sql: str) -> str:
    return f"set local app.current_tenant = '{tenant}'; {sql}"


def test_the_restricted_role_really_is_restricted():
    """بلا هذا، كلّ ما تحته يقيس دوراً يتخطّى RLS فيمرّ مجّاناً."""
    rc, out, _ = _psql(
        "select rolsuper::text || '/' || rolbypassrls::text from pg_roles"
        " where rolname = 'sahool_app'",
        role="sahool_user",
    )
    assert rc == 0 and out == "false/false", f"الدور ليس مقيَّداً: {out}"


def test_rls_hides_another_tenants_assessment(assessment):
    """العزل يُقاس بالقراءة الفعليّة تحت الدور المقيَّد، لا بوجود السياسة في الكتالوج."""
    aid = f"elg_{uuid.uuid4().hex}"
    rc, _, err = _psql(
        f"begin; {_as_tenant(TENANT_A, _insert_sql(assessment, tenant=TENANT_A, assessment_id=aid))}; commit;",
        role="sahool_app",
    )
    assert rc == 0, err

    rc, out, _ = _psql(
        _as_tenant(TENANT_A, f"select count(*) from {_TABLE} where assessment_id='{aid}'"),
        role="sahool_app",
    )
    assert rc == 0 and out.splitlines()[-1] == "1", "المالك لا يرى صفّه"

    rc, out, _ = _psql(
        _as_tenant(TENANT_B, f"select count(*) from {_TABLE} where assessment_id='{aid}'"),
        role="sahool_app",
    )
    assert rc == 0 and out.splitlines()[-1] == "0", "مستأجِر آخر يرى تقييماً ليس له"


def test_writing_under_the_wrong_tenant_is_refused_by_the_database(assessment):
    """`WITH CHECK` يمنع الكتابة **باسم** مستأجِر آخر — لا التطبيق وحده."""
    aid = f"elg_{uuid.uuid4().hex}"
    rc, _, err = _psql(
        _as_tenant(TENANT_A, _insert_sql(assessment, tenant=TENANT_B, assessment_id=aid)),
        role="sahool_app",
    )
    assert rc != 0, "القاعدة قبلت كتابة عبر المستأجِرين"
    assert "row-level security" in err.lower() or "policy" in err.lower(), err


def test_the_assessment_is_append_only(assessment):
    """مصنوعٌ مشتقّ لكنّه دليل: يُعاد اشتقاقه ولا يُحرَّر في مكانه."""
    aid = f"elg_{uuid.uuid4().hex}"
    _psql(
        f"begin; {_as_tenant(TENANT_A, _insert_sql(assessment, tenant=TENANT_A, assessment_id=aid))}; commit;",
        role="sahool_app",
    )
    rc, _, err = _psql(
        _as_tenant(
            TENANT_A,
            f"update {_TABLE} set policy_version='v2' where assessment_id='{aid}'",
        ),
        role="sahool_app",
    )
    assert rc != 0, "التقييم قابل للتحرير — فتاريخُه لا يُصدَّق"
    assert "append" in err.lower() or "permission" in err.lower() or "immutab" in err.lower(), err


def test_a_replayed_assessment_does_not_duplicate(assessment):
    """التفرّد على (لقطة، سياسة، لحظة): إعادة التشغيل لا تُنتِج صفّاً ثانياً."""
    first, second = f"elg_{uuid.uuid4().hex}", f"elg_{uuid.uuid4().hex}"
    rc, _, err = _psql(
        f"begin; {_as_tenant(TENANT_A, _insert_sql(assessment, tenant=TENANT_A, assessment_id=first))}; commit;",
        role="sahool_app",
    )
    assert rc == 0, err
    rc, _, err = _psql(
        _as_tenant(TENANT_A, _insert_sql(assessment, tenant=TENANT_A, assessment_id=second)),
        role="sahool_app",
    )
    assert rc != 0 and "duplicate key" in err.lower(), err


def test_the_database_refuses_an_assessment_that_folds_the_stages(assessment):
    """«صالحة/غير صالحة» هو الخلط الذي أوجب الفجوة — والقاعدة ترفضه، لا التطبيق وحده."""
    aid = f"elg_{uuid.uuid4().hex}"
    sql = _insert_sql(assessment, tenant=TENANT_A, assessment_id=aid).replace(
        json.dumps(assessment.as_row()["stages"]), json.dumps({"eligible": True})
    )
    rc, _, err = _psql(_as_tenant(TENANT_A, sql), role="sahool_app")
    assert rc != 0 and "check constraint" in err.lower(), err


def test_a_failed_statement_leaves_no_half_assessment(assessment):
    """المعاملة: ما يفشل لا يترك أثراً نصفيّاً يُقرأ لاحقاً تقييماً قائماً."""
    good, bad = f"elg_{uuid.uuid4().hex}", f"elg_{uuid.uuid4().hex}"
    sql = (
        f"begin; {_as_tenant(TENANT_A, _insert_sql(assessment, tenant=TENANT_A, assessment_id=good))};"
        f" {_insert_sql(assessment, tenant=TENANT_A, assessment_id=bad)}; commit;"
    )
    rc, _, _ = _psql(sql, role="sahool_app")
    assert rc != 0

    rc, out, _ = _psql(
        _as_tenant(
            TENANT_A, f"select count(*) from {_TABLE} where assessment_id in ('{good}','{bad}')"
        ),
        role="sahool_app",
    )
    assert rc == 0 and out.splitlines()[-1] == "0", "المعاملة تركت نصف تقييم"


def test_the_snapshot_table_gained_no_eligibility_column():
    """**العقد المعماريّ، مقيساً على القاعدة الحيّة لا على النصّ.**

    لو ظهر عمود أهليّة في جدول اللقطات لتغيّر معنى الصفّ المعنون بمحتواه — وهو ما
    بُنيت هذه الشريحة كلّها لمنعه.
    """
    rc, out, _ = _psql(
        "select string_agg(column_name, ',' order by column_name) from information_schema.columns"
        " where table_name = 'decision_vegetation_snapshots'",
        role="sahool_user",
    )
    assert rc == 0
    columns = set(out.split(","))
    forbidden = {"policy_version", "eligibility", "eligibility_assessment_id", "decision_eligible"}
    assert not (columns & forbidden), f"جدول اللقطات اكتسب عمود أهليّة: {columns & forbidden}"
