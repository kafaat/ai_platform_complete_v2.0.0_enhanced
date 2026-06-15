"""اكتمال MANIFEST للـmigrations — حارس CI.

السبب: كلّ migration أماميّ (forward) يجب أن يُدرَج في
migrations/MANIFEST.txt لأنّ الإقلاع (bootstrap) و CI يطبّقان الملفّات
بالترتيب المذكور فيه حصراً. ملفّ ترحيل يُنشأ ثمّ يُنسى من MANIFEST لن
يُطبَّق أبداً — فجوة صامتة (الجدول/العمود/السياسة لا يُنشأ، فينكسر الإنتاج
دون أيّ خطأ ظاهر وقت الإقلاع). هذا الاختبار يكشف الإغفال آليّاً.

ملفّات التراجع (.down.sql) مستثناة عمداً — تُطبَّق يدويّاً عند الحاجة فقط
ولا تُدرَج في MANIFEST.
"""

import glob
import pathlib

import pytest

# جذر المستودع = أب مجلّد tests_v9/ (هذا الملفّ في tests_v9/).
REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
MIGRATIONS_DIR = REPO_ROOT / "migrations"
MANIFEST_PATH = MIGRATIONS_DIR / "MANIFEST.txt"


def _forward_migration_files() -> set[str]:
    """أسماء (basename) ملفّات migrations/*.sql عدا ملفّات .down.sql."""
    files = set()
    for path in glob.glob(str(MIGRATIONS_DIR / "*.sql")):
        name = pathlib.Path(path).name
        if name.endswith(".down.sql"):
            continue
        files.add(name)
    return files


def _manifest_entries() -> set[str]:
    """الأسماء المُدرَجة في MANIFEST.txt (تجاهُل الفارغ والتعليقات #)."""
    entries = set()
    for raw in MANIFEST_PATH.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        entries.add(pathlib.Path(line).name)
    return entries


@pytest.mark.unit
def test_every_forward_migration_is_in_manifest():
    """كلّ ملفّ ترحيل أماميّ يجب أن يكون مُدرَجاً في MANIFEST."""
    on_disk = _forward_migration_files()
    listed = _manifest_entries()
    missing = sorted(on_disk - listed)
    assert not missing, (
        "ملفّات ترحيل غائبة عن MANIFEST: " + ", ".join(missing)
    )


@pytest.mark.unit
def test_every_manifest_entry_exists_on_disk():
    """كلّ مُدخَل في MANIFEST يجب أن يقابله ملفّ موجود (يكشف الأخطاء الكتابيّة/الحذف)."""
    listed = _manifest_entries()
    on_disk = _forward_migration_files()
    orphans = sorted(listed - on_disk)
    assert not orphans, (
        "مُدخَلات في MANIFEST لا ملفّ لها على القرص: " + ", ".join(orphans)
    )
