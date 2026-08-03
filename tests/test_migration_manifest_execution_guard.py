"""حارس: كلّ ترحيل مُعلَن في MANIFEST يجب أن يكون موصولاً في `run_migrations.sql`.

الأصل مقيس لا مفترض. موجة `v217`→`v231` أضافت خمسة عشر ترحيلاً إلى
`migrations/MANIFEST.txt` **بلا** سطر `\\i` مقابل في `scripts_v9/run_migrations.sql`،
فلم تُشغَّل على PostgreSQL قطّ رغم مرورها بكلّ بوّابة. ولمّا وُصِلت انكشف في أوّل
تشغيل عيبٌ حقيقيّ: `v219_machinery_delivery_consumption.sql` يستشهد بـ
`machinery_export_artifacts(tenant_id, id)` والعمود الحقيقيّ في
`v216_machinery_export.sql:57` هو `artifact_id` ⇒
``column "id" referenced in foreign key constraint does not exist``.

الإعلان بلا وصل هو **قدرة موجودة لا تجري**: الملفّ يبدو مُعتمَداً لأنّه مذكور في
البيان، وجميع الحرّاس الساكنة تراه، ولا شيء ينفّذه. الاتّجاه الآخر يُفحَص أيضاً —
سطر `\\i` لملفّ خارج البيان يعني ترحيلاً يعمل بلا سجلّ يُعلنه.

وموضع `v206_rls_final_hardening.sql` **آخِراً** ثابتٌ متعمَّد: يُعيد تغطية RLS على
كلّ ما سبقه، فالترحيل الجديد يُدرَج **قبله** لا بعده.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "migrations" / "MANIFEST.txt"
RUNNER = ROOT / "scripts_v9" / "run_migrations.sql"

_INCLUDE = re.compile(r"^\\i\s+migrations/(\S+\.sql)\s*$", re.M)

pytestmark = pytest.mark.unit


def _declared() -> list[str]:
    return [
        line.strip()
        for line in MANIFEST.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


def _executed() -> list[str]:
    return _INCLUDE.findall(RUNNER.read_text(encoding="utf-8"))


def test_every_declared_migration_is_wired_into_the_runner() -> None:
    declared, executed = _declared(), set(_executed())
    unwired = [name for name in declared if name not in executed]
    assert not unwired, (
        "ترحيلات مُعلَنة في migrations/MANIFEST.txt وغير موصولة في "
        f"scripts_v9/run_migrations.sql — لن تُنفَّذ على أيّ قاعدة: {unwired}. "
        "أضِف سطر `\\\\i migrations/<name>` قبل v206_rls_final_hardening.sql."
    )


def test_every_wired_migration_is_declared_in_the_manifest() -> None:
    declared, executed = set(_declared()), _executed()
    undeclared = [name for name in executed if name not in declared]
    assert not undeclared, (
        "ترحيلات تعمل في scripts_v9/run_migrations.sql وغير مُعلَنة في "
        f"migrations/MANIFEST.txt: {undeclared}"
    )


def test_every_wired_migration_file_exists() -> None:
    missing = [name for name in _executed() if not (ROOT / "migrations" / name).exists()]
    assert not missing, f"سطر \\i يشير إلى ملفّ غير موجود: {missing}"


def test_the_runner_executes_each_migration_once() -> None:
    executed = _executed()
    duplicated = sorted({name for name in executed if executed.count(name) > 1})
    assert not duplicated, f"ترحيل موصول أكثر من مرّة: {duplicated}"


def test_rls_final_hardening_stays_last_in_both_records() -> None:
    # v206 يُعيد تغطية RLS على كلّ ما سبقه؛ إدراج ترحيل بعده يترك جداوله بلا تغطية.
    assert _declared()[-1] == "v206_rls_final_hardening.sql"
    assert _executed()[-1] == "v206_rls_final_hardening.sql"
