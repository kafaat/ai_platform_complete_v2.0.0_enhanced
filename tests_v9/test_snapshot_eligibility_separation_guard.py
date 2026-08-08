"""`CANONICAL-SNAPSHOT-ELIGIBILITY-POLICY-01`: اللقطة لا تكتسب أهليّة.

الحارس يعمل خطوةً حاجبة في `ci.yml`، فهذه الاختبارات لا تُعيد فحص ما يفحصه — تحرس
**دلالته**: أنّ الطريقين إلى العطل مسدودان معاً، وأنّه لا يُبلِغ خضرةً حين يفقد موضوعه.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
_SCRIPT = ROOT / "scripts" / "ci" / "snapshot_eligibility_separation_guard.py"


def _load():
    spec = importlib.util.spec_from_file_location("snapshot_eligibility_separation_guard", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


MOD = _load()


def test_the_tree_is_clean_right_now():
    assert MOD.violations() == []


def _repo(tmp_path: Path, *, model_body: str, migration: str) -> Path:
    service = tmp_path / "services" / "decision-service"
    (service / "migrations").mkdir(parents=True, exist_ok=True)
    (service / "main.py").write_text(
        "from pydantic import BaseModel\n\n\n"
        f"class VegetationSnapshotIn(BaseModel):\n{model_body}\n\n\ndef unrelated():\n    pass\n",
        encoding="utf-8",
    )
    (service / "migrations" / "019_x.sql").write_text(migration, encoding="utf-8")
    return tmp_path


_CLEAN_MODEL = "    field_id: str\n    snapshot_hash: str\n"
_CLEAN_TABLE = (
    "CREATE TABLE IF NOT EXISTS decision_vegetation_snapshots (\n"
    "  snapshot_id text PRIMARY KEY, tenant_id uuid NOT NULL,\n"
    "  snapshot_hash text NOT NULL, payload jsonb NOT NULL\n"
    ");\n"
)


def _violations_in(monkeypatch, root: Path) -> list[str]:
    service = root / "services" / "decision-service"
    monkeypatch.setattr(MOD, "ROOT", root)
    monkeypatch.setattr(MOD, "SERVICE", service)
    monkeypatch.setattr(MOD, "MIGRATIONS", service / "migrations")
    monkeypatch.setattr(MOD, "MODEL_FILE", service / "main.py")
    return MOD.violations()


def test_a_clean_tree_is_not_denounced(tmp_path, monkeypatch):
    """حارسٌ يُطلِق على الشجرة السليمة يُنزَع في أوّل يوم."""
    root = _repo(tmp_path, model_body=_CLEAN_MODEL, migration=_CLEAN_TABLE)
    assert _violations_in(monkeypatch, root) == []


def test_an_eligibility_field_on_the_model_is_caught(tmp_path, monkeypatch):
    """الطريق الأوّل: حقلٌ يُضاف إلى النموذج لأنّ واجهةً احتاجته."""
    root = _repo(
        tmp_path,
        model_body=_CLEAN_MODEL + "    policy_version: str | None = None\n",
        migration=_CLEAN_TABLE,
    )
    found = _violations_in(monkeypatch, root)
    assert len(found) == 1 and "policy_version" in found[0]


def test_an_eligibility_column_in_the_create_table_is_caught(tmp_path, monkeypatch):
    """الطريق الثاني: عمودٌ في تعريف الجدول."""
    root = _repo(
        tmp_path,
        model_body=_CLEAN_MODEL,
        migration=_CLEAN_TABLE.replace(
            "  snapshot_hash text NOT NULL,",
            "  snapshot_hash text NOT NULL, decision_eligible boolean,",
        ),
    )
    found = _violations_in(monkeypatch, root)
    assert len(found) == 1 and "decision_eligible" in found[0]


def test_an_alter_table_add_column_is_caught_too(tmp_path, monkeypatch):
    """الطريق الثالث — والأرجح عمليّاً: هجرةٌ لاحقة تُضيف العمود «للسرعة».

    حارسٌ يقرأ `CREATE TABLE` وحده يمرّ على هذه، وهي المسار الطبيعيّ لأنّ أحداً لا
    يُعيد كتابة تعريف جدول قائم.
    """
    root = _repo(
        tmp_path,
        model_body=_CLEAN_MODEL,
        migration=_CLEAN_TABLE
        + "\nALTER TABLE decision_vegetation_snapshots ADD COLUMN eligibility_assessment_id text;\n",
    )
    found = _violations_in(monkeypatch, root)
    assert len(found) == 1 and "eligibility_assessment_id" in found[0]


def test_an_unrelated_column_is_not_denounced(tmp_path, monkeypatch):
    """النطاق ضيّق عمداً: الحارس يمنع **حكم الأهليّة** لا كلّ تطوّر للمخطَّط."""
    root = _repo(
        tmp_path,
        model_body=_CLEAN_MODEL,
        migration=_CLEAN_TABLE
        + "\nALTER TABLE decision_vegetation_snapshots ADD COLUMN cloud_pct real;\n",
    )
    assert _violations_in(monkeypatch, root) == []


def test_losing_its_subject_is_a_failure_not_a_pass(tmp_path, monkeypatch):
    """**أهمّ اختبار هنا.**

    لو أُعيد تسمية الجدول أو النموذج، فحارسٌ ساكت يُقرأ «لا مخالفة» وهو يعني «لم
    أنظر». وهذا الصنف بعينه مُسجَّل في هذا المستودع: `runtime_contract_generator`
    كان أخضر لأنّه لا يرى، لا لأنّه لا يجد.
    """
    service = tmp_path / "services" / "decision-service"
    (service / "migrations").mkdir(parents=True, exist_ok=True)
    (service / "main.py").write_text("class SomethingElse:\n    pass\n", encoding="utf-8")
    (service / "migrations" / "019_x.sql").write_text(
        "CREATE TABLE IF NOT EXISTS renamed_snapshots (id text);\n", encoding="utf-8"
    )
    found = _violations_in(monkeypatch, tmp_path)
    assert len(found) == 2, found
    assert any("VegetationSnapshotIn" in line for line in found)
    assert any("decision_vegetation_snapshots" in line for line in found)


def test_the_message_names_the_file_and_the_remedy():
    """رسالة الحارس جزءٌ منه: من يقرأها يجب أن يعرف أين يذهب."""
    body = _SCRIPT.read_text(encoding="utf-8")
    assert "decision_eligibility_assessments" in body
    assert "eligibility_policy.py" in body


def test_add_column_if_not_exists_does_not_slip_through(tmp_path, monkeypatch):
    """**السلبيّة الكاذبة التي كشفَتها مراجعة #810.**

    أوّل صياغة التقطت `IF` بوصفها اسم العمود، فمرّ الاسم المحظور. وهي ليست صيغةً
    نادرة: تظهر **٢١ مرّة** في هجرات هذه الخدمة نفسها — أي أنّ أرجح طريقٍ إلى
    العطل كانت الطريق الوحيد الذي لا يراه الحارس.
    """
    root = _repo(
        tmp_path,
        model_body=_CLEAN_MODEL,
        migration=_CLEAN_TABLE + "\nALTER TABLE decision_vegetation_snapshots"
        " ADD COLUMN IF NOT EXISTS policy_version text;\n",
    )
    found = _violations_in(monkeypatch, root)
    assert len(found) == 1 and "policy_version" in found[0]


def test_the_full_postgresql_grammar_is_caught(tmp_path, monkeypatch):
    """كلّ الاختياريّات مجتمعةً **بترتيب القواعد**: `[IF EXISTS] [ONLY]` ثمّ `[IF NOT EXISTS]`.

    صياغتي الثانية عكسَت `ONLY` و`IF EXISTS`، فأفلتت هذه الصيغة القانونيّة **تماماً**
    — صفر التقاط، لا اسمٌ خاطئ. **ثقبان متتاليان في نحوٍ واحد**، وكلاهما صيغةٌ
    مشروعة: حارس DDL يُكتَب من القواعد المنشورة لا من الصيغة التي صادفتُها.
    """
    root = _repo(
        tmp_path,
        model_body=_CLEAN_MODEL,
        migration=_CLEAN_TABLE + "\nALTER TABLE IF EXISTS ONLY public.decision_vegetation_snapshots"
        " ADD COLUMN IF NOT EXISTS decision_eligible boolean;\n",
    )
    found = _violations_in(monkeypatch, root)
    assert len(found) == 1 and "decision_eligible" in found[0]


def test_each_optional_clause_alone_is_caught_too(tmp_path, monkeypatch):
    """المجتمعة لا تُغني عن المفردة: نمطٌ ناقص قد يمرّ التركيبة الكاملة صدفةً."""
    for index, clause in enumerate(("ONLY ", "IF EXISTS ", "")):
        root = _repo(
            tmp_path / f"case{index}",
            model_body=_CLEAN_MODEL,
            migration=_CLEAN_TABLE + f"\nALTER TABLE {clause}decision_vegetation_snapshots"
            " ADD COLUMN policy_version text;\n",
        )
        found = _violations_in(monkeypatch, root)
        assert len(found) == 1 and "policy_version" in found[0], clause


@pytest.mark.parametrize(
    "prefix,suffix,label",
    [
        ("", " *", "النجمة الوراثيّة `<t> *` — بقيت خارج النمط بعد تصحيح الترتيب"),
        ("IF EXISTS ", " *", "`IF EXISTS` مع النجمة"),
        ("IF EXISTS ONLY ", " *", "القواعد كاملةً: `[IF EXISTS] [ONLY] name [ * ]`"),
        ("ONLY IF EXISTS ", "", "المعكوسة — تُقبَل عمداً (كاشف لا مُحلِّل نحويّ)"),
    ],
)
def test_every_legal_alter_prefix_is_caught(tmp_path, monkeypatch, prefix, suffix, label):
    """القواعد كاملةً — `ALTER TABLE [ IF EXISTS ] [ ONLY ] name [ * ]`.

    تصحيحُ ترتيب الكلمتين أغلق ثقباً وترك ثالثاً: **النجمة الوراثيّة** جزءٌ من
    القواعد نفسها، و`ALTER TABLE <t> * ADD COLUMN decision_eligible` صيغةٌ مشروعة
    كانت تمرّ. ثلاثة ثقوب في نحوٍ واحد، وكلّ مرّة يُقاس ما نُظِر إليه لا ما صُودِف.

    **والمعكوسة تُقبَل عمداً:** الإفراط في الالتقاط لا يكلّف شيئاً لأنّ SQL غير
    القانونيّة تفشل في الترحيل أصلاً — أمّا التقصير فهو العطل بعينه.
    """
    root = _repo(
        tmp_path,
        model_body=_CLEAN_MODEL,
        migration=_CLEAN_TABLE + f"\nALTER TABLE {prefix}decision_vegetation_snapshots{suffix}"
        " ADD COLUMN decision_eligible boolean;\n",
    )
    found = _violations_in(monkeypatch, root)
    assert len(found) == 1 and "decision_eligible" in found[0], label


def test_an_unrelated_column_under_a_composite_prefix_is_still_clean(tmp_path, monkeypatch):
    """توسيع الالتقاط يجب ألّا يُنتج إنذاراً كاذباً — عمودٌ بريء يبقى بريئاً."""
    root = _repo(
        tmp_path,
        model_body=_CLEAN_MODEL,
        migration=_CLEAN_TABLE + "\nALTER TABLE IF EXISTS ONLY decision_vegetation_snapshots *"
        " ADD COLUMN cloud_pct real;\n",
    )
    assert _violations_in(monkeypatch, root) == []


@pytest.mark.parametrize(
    "table,column,label",
    [
        ('public."decision_vegetation_snapshots"', "decision_eligible", "جدول مقتبس مؤهَّل"),
        ('"decision_vegetation_snapshots"', "decision_eligible", "جدول مقتبس عارٍ من المخطَّط"),
        ("decision_vegetation_snapshots", '"decision_eligible"', "عمود مقتبس"),
        ('"decision_vegetation_snapshots"', '"decision_eligible"', "الاثنان مقتبسان"),
        ("public . decision_vegetation_snapshots", "decision_eligible", "مسافات حول النقطة"),
        ('"public".decision_vegetation_snapshots', "decision_eligible", "مخطَّط مقتبس"),
    ],
)
def test_a_quoted_identifier_is_the_same_identifier(tmp_path, monkeypatch, table, column, label):
    """`"decision_vegetation_snapshots"` هو الجدول نفسه، و`"decision_eligible"` العمود نفسه.

    الاقتباس في PostgreSQL يحفظ حالة الأحرف ولا يُنشئ كياناً آخر. وكان النمط يقرأ
    الاسم **عارياً فقط**، فتمرّ هجرةٌ مشروعة تماماً من أمامه بصفر التقاط. وهو الثقب
    **الرابع** في النحو نفسه بعد `IF NOT EXISTS` وترتيب `IF EXISTS`/`ONLY` والنجمة.
    """
    root = _repo(
        tmp_path,
        model_body=_CLEAN_MODEL,
        migration=_CLEAN_TABLE + f"\nALTER TABLE {table}\n  ADD COLUMN {column} boolean;\n",
    )
    found = _violations_in(monkeypatch, root)
    assert len(found) == 1 and "decision_eligible" in found[0], label


def test_the_word_column_is_never_captured_as_a_column_name(tmp_path, monkeypatch):
    """`ADD COLUMN "x"` كان يُنتِج **التقاطاً خاطئاً** لا صفراً — وهذا أخطر.

    `(\\w+)` يفشل عند `"`، فيتراجع المُطابِق عن `(?:column\\s+)?` **ويلتقط `COLUMN`**
    بوصفه اسم العمود. اسمٌ ليس في `FORBIDDEN` ⇒ الحارس يمرّ خضراء وهو **قد نظر ورأى
    الشيء الخطأ**. الصنف نفسه الذي أفلتت به `IF NOT EXISTS` أوّل مرّة، وهو ما يجعل
    دعمَ الاقتباس وحده غير كافٍ: بلا لَجم التراجع يعود العطل من بابه.
    """
    root = _repo(
        tmp_path,
        model_body=_CLEAN_MODEL,
        migration=_CLEAN_TABLE
        + '\nALTER TABLE decision_vegetation_snapshots ADD COLUMN "policy_version" text;\n',
    )
    captured = MOD._ALTER_ADD.findall(
        'ALTER TABLE decision_vegetation_snapshots ADD COLUMN "policy_version" text;'
    )
    assert [c.lower() for c in captured] == ["policy_version"], captured
    found = _violations_in(monkeypatch, root)
    assert len(found) == 1 and "policy_version" in found[0]


def test_a_quoted_table_in_create_table_is_still_found(tmp_path, monkeypatch):
    """اسمٌ مقتبس في `CREATE TABLE` — والعمود المحظور داخله يُمسَك."""
    root = _repo(
        tmp_path,
        model_body=_CLEAN_MODEL,
        migration=(
            'CREATE TABLE public."decision_vegetation_snapshots" (\n'
            "  snapshot_id text PRIMARY KEY, snapshot_hash text NOT NULL,\n"
            "  decision_eligible boolean\n);\n"
        ),
    )
    found = _violations_in(monkeypatch, root)
    assert len(found) == 1 and "decision_eligible" in found[0], found


def test_a_quoted_column_inside_create_table_is_caught(tmp_path, monkeypatch):
    """والعمود المقتبس داخل تعريفٍ غير مقتبس كان **تجاوزاً صامتاً مؤكَّداً**."""
    root = _repo(
        tmp_path,
        model_body=_CLEAN_MODEL,
        migration=(
            "CREATE TABLE decision_vegetation_snapshots (\n"
            "  snapshot_id text PRIMARY KEY, snapshot_hash text NOT NULL,\n"
            '  "policy_version" text\n);\n'
        ),
    )
    found = _violations_in(monkeypatch, root)
    assert len(found) == 1 and "policy_version" in found[0], found


@pytest.mark.parametrize(
    "migration,label",
    [
        (
            '\nALTER TABLE "decision_vegetation_snapshots" ADD COLUMN "cloud_pct" real;\n',
            "عمودٌ بريء مقتبس على جدولٍ مقتبس",
        ),
        (
            '\nALTER TABLE public."decision_other_table" ADD COLUMN decision_eligible boolean;\n',
            "جدولٌ آخر مقتبس — ليس موضوع الحارس",
        ),
    ],
)
def test_quoting_support_does_not_manufacture_false_alarms(tmp_path, monkeypatch, migration, label):
    """توسيع الالتقاط يجب ألّا يُنتج إنذاراً كاذباً — ولا أن يبتلع جدولاً غير موضوعه."""
    root = _repo(tmp_path, model_body=_CLEAN_MODEL, migration=_CLEAN_TABLE + migration)
    assert _violations_in(monkeypatch, root) == [], label
