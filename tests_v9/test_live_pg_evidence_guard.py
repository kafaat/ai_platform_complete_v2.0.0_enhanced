"""عقد وظيفة PG المخصّصة — يُختبَر بلا قاعدة، فيعمل في كلّ وظيفة.

هذه اختباراتُ **وحدة**: تُركّب تقارير `junit` اصطناعيّة وتُبدّل قارئ الكتالوج، فلا
تحتاج PostgreSQL. وهذا مقصود — حارسُ العقد نفسه يجب ألّا يكون رهينةَ وجود القاعدة،
وإلّا صار تكذيبه متخطًّى في كلّ وظيفة عامّة وهو صنف `STABLE_WRONG_TEST` الذي
يُصنّفه `guard_mutation_guard`.

والبنود الأربعة المُختبَرة هنا هي التي **لا** يفرضها `SAHOOL_REQUIRE_LIVE_PG`:
هو يحرس غياب القاعدة، وهذه تحرس ما سواه.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
_SCRIPT = ROOT / "scripts" / "ci" / "live_pg_evidence_guard.py"


def _load():
    spec = importlib.util.spec_from_file_location("_live_pg_evidence_guard", _SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


MOD = _load()


def _junit(tmp_path: Path, *, tests: int, failures: int = 0, skipped: int = 0) -> Path:
    path = tmp_path / "live.xml"
    path.write_text(
        f'<testsuites><testsuite name="live" tests="{tests}" failures="{failures}" '
        f'errors="0" skipped="{skipped}"/></testsuites>',
        encoding="utf-8",
    )
    return path


def _restricted() -> dict[str, str]:
    """الدور المقيَّد تماماً — كلّ خاصّيّة `false`، مهما بلغ عددها."""
    return dict.fromkeys(MOD.ROLE_ATTRIBUTES, "false")


def _stub(monkeypatch, *, role=None, drift=()):
    """يُبدّل كلّ ما يلمس القاعدة — العقد يُقاس، لا الاتّصال.

    **والقاعدة تُشتقّ من `ROLE_ATTRIBUTES` لا تُكتَب ثلاثيّةً حرفيّة:** الصياغة السابقة
    ثبّتت ثلاثة أسماء، فكانت إضافةُ خاصّيّة رابعة تُحمِّر كلّ اختبار بـ`zip(strict=True)`
    بدل أن تُحمِّر ما يخصّها. مُبدِّلٌ يَبيت مع أوّل توسيع للعقد.
    """
    monkeypatch.setattr(
        MOD, "server_identity", lambda *a, **k: {"postgresql": "16.13", "postgis": "3.4.2"}
    )
    properties = _restricted() if role is None else dict(role)
    monkeypatch.setattr(MOD, "role_properties", lambda *a, **k: properties)
    monkeypatch.setattr(MOD, "schema_drift", lambda *a, **k: list(drift))


def _granting(attribute: str) -> dict[str, str]:
    """دورٌ مقيَّدٌ في كلّ شيء **إلّا** الخاصّيّة المُسمّاة — فيعزلها التأكيد وحدها."""
    role = _restricted()
    role[attribute] = "true"
    return role


def _run(junit: Path) -> int:
    return MOD.main(["--junit", str(junit)])


def _catalogue(monkeypatch, answer: str, *, version: str = "160013"):
    """مُبدِّل `psql` يعي **أيّ** استعلامٍ يُسأل.

    الصياغة الأولى أجابت بالقيمة نفسها لكلّ استعلام، فلمّا أُضيف فحصُ الإصدار صار
    يقرأ `PRIMARY KEY (…)` إصداراً ويُنتِج انحرافاً ثالثاً — مُبدِّلٌ أعمى يُفسِد
    الاختبار عند أوّل سؤالٍ جديد.
    """
    monkeypatch.setattr(
        MOD, "psql", lambda sql, **k: version if "server_version_num" in sql else answer
    )


def test_a_clean_run_passes(tmp_path, monkeypatch):
    """المرساة المقابلة: بلا هذا قد تمرّ كلّ التكذيبات لأنّ الحارس يرفض دائماً."""
    _stub(monkeypatch)
    assert _run(_junit(tmp_path, tests=30)) == 0


def test_a_fully_skipped_run_is_a_failure_not_a_pass(tmp_path, monkeypatch):
    """الفجوة الأصليّة بثوبها الأخضر: ٣٠ اختباراً تُجمَع وتُتخطّى كلّها.

    الفحص الذي استبدلتُه كان يعدّ `--collect-only | grep -c '::'` — فيقيس **الجمع**
    لا التنفيذ، ويمرّ على هذا بالضبط.
    """
    _stub(monkeypatch)
    assert _run(_junit(tmp_path, tests=30, skipped=30)) == 1


def test_one_skipped_live_test_is_enough_to_fail(tmp_path, monkeypatch):
    """الحدّ عند صفر لا عند «أغلبها نُفِّذ» — تخطٍّ واحد ادّعاءٌ لم يُقَس.

    **والأرقام مختارة لتعزل الخاصّيّة، لا لتبدو معقولة:** `٣١` مجموعاً و`١` متخطًّى
    يعني `٣٠` مُنفَّذاً — أي أنّ شرط «مُنفَّذ ≥ ٣٠» **يمرّ**، فلا يبقى ما يُسقِط هذا
    الاختبار سوى شرط التخطّي وحده.

    صياغتي الأولى كتبت `٣٠/١` فصار المُنفَّذ ٢٩، فالتقطه شرطُ الحدّ الأدنى أيضاً
    وبقي الاختبار أحمر حتّى بعد تعطيل شرط التخطّي — أي أنّه توقّف عن قياس ما سُمّي
    باسمه. كشفَته الطفرة المُسجَّلة حين رفع الحدُّ من ٢٥ إلى ٣٠.
    """
    _stub(monkeypatch)
    assert _run(_junit(tmp_path, tests=31, skipped=1)) == 1


def test_zero_executed_is_a_failure(tmp_path, monkeypatch):
    _stub(monkeypatch)
    assert _run(_junit(tmp_path, tests=0)) == 1


# ─────────────────────────────────────────────────────────────────────────────
# خصائص الدور الأربع — **اختبارٌ مُسمًّى لكلٍّ منها على حدة**
#
# ولماذا أربعة اختبارات لا واحدٌ يمرّ بحلقة: `guard_mutation_guard` يزرع العطل ويطلب
# أن يحمرّ اختبارٌ **باسمه**. فحلقةٌ واحدة تُسقِط اسماً واحداً مهما كانت الخاصّيّة
# المنزوعة، فيُقرأ الأربعة مغطّاةً وثلاثةٌ منها بلا حارس مستقلّ. والفصل يمنع أن يستر
# مجموعٌ فردَه — وهو الدرس الذي أخرج هذه الشريحة أصلاً: `createdb` كان **يُقرأ ويُطبَع
# ولا يحكم**، وبدا محروساً لأنّه ظاهرٌ في الملخّص.
# ─────────────────────────────────────────────────────────────────────────────


def test_a_superuser_role_is_rejected(tmp_path, monkeypatch):
    """`NOSUPERUSER` — دورٌ خارقٌ يتخطّى RLS وكلّ صلاحيّة، فلا يُقاس تحته عزل."""
    _stub(monkeypatch, role=_granting("superuser"))
    assert _run(_junit(tmp_path, tests=30)) == 1


def test_a_bypassrls_role_is_rejected(tmp_path, monkeypatch):
    """`NOBYPASSRLS` — مقيسٌ في هذا المستودع: مالك الجداول كان يتخطّى RLS فمرّ زرعُ
    `NO FORCE ROW LEVEL SECURITY` بلا قتيل. الخاصّيّة هي ما يجعل ادّعاء العزل قابلاً
    للقياس أصلاً."""
    _stub(monkeypatch, role=_granting("bypassrls"))
    assert _run(_junit(tmp_path, tests=30)) == 1


def test_a_createdb_role_is_rejected(tmp_path, monkeypatch):
    """**الخاصّيّة التي كانت تُقرأ وتُطبَع ولا تحكم.**

    `role_properties` كانت تستعلم عن `rolcreatedb` والملخّص يعرضه، بينما شرط الرفض
    يقرأ `superuser` و`bypassrls` وحدهما. رقمٌ معروض لا حارس — وهو الصنف الأخطر لأنّ
    ظهورَه في المخرَج يُقرأ شهادةً على أنّه مفحوص.

    ودورٌ يملك `CREATEDB` ينشئ قاعدةً يملكها، فيصير فيها المالك — خارج كلّ سياسة
    مكتوبة في قاعدة الأدلّة.
    """
    _stub(monkeypatch, role=_granting("createdb"))
    assert _run(_junit(tmp_path, tests=30)) == 1


def test_a_createrole_role_is_rejected(tmp_path, monkeypatch):
    """**الخاصّيّة التي لم تكن تُسأل أصلاً** — لا في الاستعلام ولا في القرار.

    ومالكُها يبلغ **بخطوتين** ما مُنِع منه بخطوة: يُنشئ دوراً ويمنحه ما يشاء ثمّ
    يعمل تحته. فادّعاء «الدور مقيَّد» كان أضيق ممّا يُقرأ منه، وصمتُ الحارس عنه لم
    يكن حكماً بغيابها بل بأنّه لم ينظر.
    """
    _stub(monkeypatch, role=_granting("createrole"))
    assert _run(_junit(tmp_path, tests=30)) == 1


def test_the_catalogue_query_asks_for_every_gating_attribute(monkeypatch):
    """**الحلقة المفقودة بين القرار والقياس.**

    رفضٌ يعتمد خاصّيّةً **لا يقرؤها الاستعلام** ينهار عند `KeyError` أو — أسوأ —
    يقرأ قيمةً في خانةٍ ليست لها. فالتأكيد هنا على الاستعلام **الفعليّ**: كلّ اسمٍ
    يحجب يجب أن يقابله عمود كتالوج مطلوب.

    ويُقاس بالتقاط نصّ `psql` لا بقراءة ثابتٍ في المصدر: الأوّل يقيس ما يُرسَل إلى
    القاعدة، والثاني يقيس ما كُتِب — وبينهما بالضبط تقع الفجوة التي عولجت هنا.
    """
    asked: list[str] = []
    monkeypatch.setattr(
        MOD, "psql", lambda sql, **k: asked.append(sql) or "false|false|false|false"
    )
    MOD.role_properties("d", "o", "sahool_app")

    assert len(asked) == 1, asked
    sql = asked[0].lower()
    missing = [c for c in MOD._ROLE_CATALOGUE_COLUMNS if c not in sql]
    assert missing == [], f"أعمدة يُبنى عليها الحكم ولا يطلبها الاستعلام: {missing}"

    catalogue_of = {
        "superuser": "rolsuper",
        "bypassrls": "rolbypassrls",
        "createdb": "rolcreatedb",
        "createrole": "rolcreaterole",
    }
    unasked = [name for name in MOD._REJECT_IF_TRUE if catalogue_of[name] not in sql]
    assert unasked == [], f"خصائص تحجب ولا تُقرأ من الكتالوج: {unasked}"


@pytest.mark.parametrize(
    "row,label",
    [
        ("false|false|false", "حقولٌ أقلّ ممّا يُقرأ"),
        ("false|false|false|false|false", "حقولٌ أكثر"),
        ("false|false|false|", "حقلٌ فارغ في الذيل"),
        ("false|false|false|t", "‏`t` لا `true` — صيغةٌ أخرى للمنطقيّ"),
        ("false|false|false|NULL", "‏NULL نصّاً"),
    ],
)
def test_a_malformed_role_row_is_fail_closed(monkeypatch, row, label):
    """**صفٌّ لا يُفهَم فشلٌ، لا قيمٌ جزئيّة تُقرأ حكماً.**

    `split("|")` بلا تحقّق يُنتِج الصمت الخطر: عمودٌ يُضاف أو يُحذَف في استعلامٍ
    مستقبليّ فتنزلق القيم خانةً — يُقرأ `rolcreatedb` مكان `rolbypassrls` — والحكم
    يخرج **بثقة كاملة** على أسماء لا تقابل قيمها. وقيمةٌ ليست `true`/`false` تمرّ على
    مقارنة «ليست false»… أو لا تمرّ، بحسب ما كُتِب — وكلاهما حكمٌ على مجهول.

    فالفشل المغلق هنا ليس تشدّداً: هو رفضُ إصدار حكمٍ عن سؤالٍ لم يُجَب.
    """
    monkeypatch.setattr(MOD, "psql", lambda sql, **k: row)
    with pytest.raises(SystemExit):
        MOD.role_properties("d", "o", "sahool_app")


def test_a_restricted_role_row_is_read_exactly(monkeypatch):
    """المرساة المقابلة: الفشل المغلق يجب ألّا يبتلع الصفّ السليم."""
    monkeypatch.setattr(MOD, "psql", lambda sql, **k: "false|false|false|false")
    assert MOD.role_properties("d", "o", "sahool_app") == _restricted()


def test_a_missing_contract_object_is_drift(tmp_path, monkeypatch):
    """يمرّ بـ`schema_drift` الحقيقيّة — والمُبدَّل هو `psql` وحده.

    صياغتي الأولى أبدلت `schema_drift` نفسها بقائمةٍ جاهزة، فكان تعطيل المقارنة
    داخلها **لا يُسقِط هذا الاختبار**: يقرأ مصنوعةً ركّبتُها بدل أن يمرّ بالقاعدة.
    أمسكَته الطفرة المُسجَّلة وهي خضراء — وهو الصنف الذي بُني `guard_mutation_guard`
    لأجله بالحرف.
    """
    contract = tmp_path / "contract.json"
    contract.write_text(
        json.dumps(
            {
                "postgres_major": 16,
                "objects": {"water_ledger": {"primary_key": "PRIMARY KEY (field_id)"}},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(MOD, "CONTRACT", contract)

    _catalogue(monkeypatch, "PRIMARY KEY (field_id)")
    assert MOD.schema_drift("d", "o") == [], "المطابق يُدان — إيجابيّة كاذبة"

    _catalogue(monkeypatch, "PRIMARY KEY (something_else)")
    drift = MOD.schema_drift("d", "o")
    assert drift and "water_ledger.primary_key" in drift[0], drift


def test_a_wrong_major_version_is_drift_but_a_different_patch_is_not(tmp_path, monkeypatch):
    """الرئيسيّ عقدٌ والتفصيليّ ليس — والفرق مقيس لا موصوف.

    CI تعمل على `16.4` ومحلّيّاً `16.13`، وكلاهما يفي. تثبيتُ التفصيليّ يجعل ترقيةَ
    صورةٍ انحرافاً كاذباً فيُنزَع الحارس في أوّل يوم؛ وإهمالُ الرئيسيّ يجعل الأدلّة
    تعمل على نحوِ DDL لإصدارٍ آخر بلا إنذار.
    """
    contract = tmp_path / "contract.json"
    contract.write_text(json.dumps({"postgres_major": 16, "objects": {}}), encoding="utf-8")
    monkeypatch.setattr(MOD, "CONTRACT", contract)

    for num, expect_drift in (("160004", False), ("160013", False), ("150009", True)):
        monkeypatch.setattr(MOD, "psql", lambda *a, num=num, **k: num)
        drift = MOD.schema_drift("d", "o")
        assert bool(drift) is expect_drift, (num, drift)


def test_an_object_the_contract_does_not_name_is_not_drift(tmp_path, monkeypatch):
    """الزائد لا يُدان: العقد يصف ما تستند إليه الأدلّة لا كامل المخطّط.

    لولا هذا لصارت كلُّ هجرةٍ تُضيف قيداً «انحرافاً»، فيُدرَّب القارئ على تجاهل
    الحارس — وهو تعطيلٌ له بثوب تشدُّد.
    """
    contract = tmp_path / "contract.json"
    contract.write_text(
        json.dumps(
            {"postgres_major": 16, "objects": {"water_ledger": {"check": ["CHECK (etc_mm >= 0)"]}}}
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(MOD, "CONTRACT", contract)
    _catalogue(monkeypatch, "CHECK (etc_mm >= 0)\nCHECK (a_new_constraint > 1)")
    assert MOD.schema_drift("d", "o") == []


def test_a_missing_report_is_not_silently_treated_as_zero(tmp_path, monkeypatch):
    """تقريرٌ غائب ≠ صفر اختبار: الأوّل «لم يُشغَّل pytest»، والثاني نتيجة.

    خلطُهما يجعل خطوةً لم تُنفَّذ أصلاً تُبلَّغ كقياسٍ سالب.
    """
    _stub(monkeypatch)
    with pytest.raises(SystemExit) as err:
        _run(tmp_path / "does_not_exist.xml")
    assert "لم يُشغَّل pytest" in str(err.value)


def test_the_contract_covers_every_table_the_proofs_assert_on():
    """عقدٌ يغطّي بعض الجداول يترك الباقي بلا كشف انحراف — وهو أسوأ من غيابه."""
    contract = json.loads(
        (ROOT / "docs/architecture/live_pg_schema_contract.json").read_text(encoding="utf-8")
    )
    proofs = (ROOT / "tests_v9/test_live_pg_fake_connection_debt.py").read_text(encoding="utf-8")
    for table in contract["objects"]:
        assert table in proofs, f"{table} في العقد ولا تلمسه الأدلّة — مدخل بائت"
    for table in (
        "water_ledger",
        "soil_profile_projection_jobs",
        "offline_pending_ops",
        "scouting_pins",
        "workflow_state",
        "events",
        "canonical_nutrient_ledgers",
        "prescriptions",
    ):
        assert table in contract["objects"], f"{table} تُقاس ولا يحرسها العقد"


def test_a_missing_psql_client_is_a_contract_error_not_a_traceback(monkeypatch):
    """عطلُ بيئةٍ يجب أن يُقرأ عطلَ بيئة.

    بلا هذا يرمي `subprocess.run` خطأً خاماً فتظهر trace غير مُوجَّهة، ويُبحَث عن
    السبب في الكود بينما هو في تجهيز الوظيفة.
    """

    def _absent(*a, **k):
        raise FileNotFoundError("psql")

    monkeypatch.setattr(MOD.subprocess, "run", _absent)
    with pytest.raises(SystemExit) as err:
        MOD.psql("select 1", database="d", role="r")
    assert "لا عميل psql" in str(err.value)


# ───────────────────── عقد استدعاء `psql` نفسه (تصويب المالك) ─────────────────────


def test_psql_is_fail_closed_and_ignores_psqlrc(monkeypatch):
    r"""رايتان تُقرآن تجميلاً وهما عقد.

    `~/.psqlrc` يُقرأ افتراضيّاً: `\pset` أو `\timing` في بيئة المُشغِّل يُضيف سطراً
    إلى الخرج، فيُقرأ ذلك السطر **قيمةَ كتالوج** ويُقارَن بالعقد. و`ON_ERROR_STOP=1`
    يجعل خطأ SQL يُنهي بغير صفر — بدونه قد يعود psql بصفرٍ بعد خطأ فيُقرأ خرجٌ ناقص
    «نجاحاً»، وهو بالضبط الصنف الذي يوجد هذا الحارس ضدّه.
    """
    seen = {}

    def fake_run(argv, **kwargs):
        seen["argv"] = argv
        return SimpleNamespace(returncode=0, stdout="1\n", stderr="")

    monkeypatch.setattr(MOD.subprocess, "run", fake_run)
    assert MOD.psql("select 1", database="sahool", role="sahool_app") == "1"

    argv = seen["argv"]
    assert "-X" in argv, "‏`.psqlrc` يُقرأ — إعدادُ بيئةٍ يستطيع تلويث القياس"
    assert argv[argv.index("-v") + 1] == "ON_ERROR_STOP=1"


def test_psql_sql_failure_is_fatal(monkeypatch):
    """المرساة المقابلة: رمزُ خروجٍ غير صفريّ يُنهي بعقد لا يُبتلَع."""

    def fake_run(*args, **kwargs):
        return SimpleNamespace(returncode=1, stdout="", stderr="ERROR: broken query")

    monkeypatch.setattr(MOD.subprocess, "run", fake_run)
    with pytest.raises(SystemExit, match="تعذّر الاستعلام"):
        MOD.psql("select broken", database="sahool", role="sahool_app")


# ─────────────────────────────────────────────────────────────────────────────
# الدليل المكتوب — يوجد يوم الفشل، ويربط نفسه بما اختُبِر
# ─────────────────────────────────────────────────────────────────────────────


def _evidence(tmp_path: Path, monkeypatch, *, tests=30, skipped=0, role=None, drift=()) -> dict:
    _stub(monkeypatch, role=role, drift=drift)
    out = tmp_path / "live_pg_evidence.json"
    code = MOD.main(
        ["--junit", str(_junit(tmp_path, tests=tests, skipped=skipped)), "--evidence", str(out)]
    )
    assert out.is_file(), "لم يُكتَب الدليل أصلاً"
    return {"code": code, "doc": json.loads(out.read_text(encoding="utf-8"))}


def test_the_evidence_is_written_on_failure_not_only_on_success(tmp_path, monkeypatch):
    """**الشرط الذي يقلب معنى الكلمة إن سقط.**

    وثيقةٌ لا توجد إلّا حين ينجح كلّ شيء ليست دليلاً — الدليل يُطلَب يوم الفشل. فيُقاس
    الطرفان معاً: تشغيلٌ راسب يكتب `FAIL` **ويُعيد ١**، وتشغيلٌ ناجح يكتب `PASS`
    ويُعيد ٠. والترتيب جزءٌ من العقد: الكتابة **قبل** إعادة رمز الخروج.
    """
    failed = _evidence(tmp_path, monkeypatch, role=_granting("createrole"))
    assert failed["code"] == 1
    assert failed["doc"]["verdict"] == "FAIL"
    assert failed["doc"]["problems"], "حكمٌ FAIL بلا سببٍ مكتوب لا يُقرأ"

    passed = _evidence(tmp_path, monkeypatch)
    assert passed["code"] == 0
    assert passed["doc"]["verdict"] == "PASS"
    assert passed["doc"]["problems"] == []


def test_the_evidence_binds_the_tested_commit_and_tree(tmp_path, monkeypatch):
    """**الدليل يقول عن أيّ شجرةٍ يتكلّم — وإلّا فهو ادّعاءٌ بلا مرجع.**

    و`github_sha` **منفصل** عن `checkout_sha` عمداً: في أحداث `pull_request` تعمل
    الوظيفة على دمجٍ وهميّ، فيشير `GITHUB_SHA` إلى شيءٍ غير الشجرة المقيسة. توحيدُهما
    كان سيُنتِج وثيقةً تدّعي أنّ ما اختُبِر هو ما أطلق التشغيل — وهو غير صحيح بالبناء.
    فاختلافهما **معلومة** لا عطل، ولا يُقرأ إلّا إن كُتِبا معاً.

    والشجرة تُكتَب مع الالتزام لأنّ الالتزام قد يُعاد كتابته بمحتوى الشجرة نفسه:
    المحتوى هو ما قِيس.
    """
    monkeypatch.setenv("GITHUB_SHA", "0" * 40)
    binding = _evidence(tmp_path, monkeypatch)["doc"]["binding"]

    assert binding["checkout_sha"] != "unavailable" and len(binding["checkout_sha"]) == 40
    assert binding["checkout_tree"] != "unavailable" and len(binding["checkout_tree"]) == 40
    assert binding["checkout_sha"] != binding["checkout_tree"], (
        "الالتزام والشجرة كائنان مختلفان — تساويهما يعني أنّ أحدهما لم يُقرأ"
    )
    assert binding["github_sha"] == "0" * 40
    assert binding["github_sha"] != binding["checkout_sha"], (
        "‏github_sha لا يُشتقّ من checkout_sha — الفارق هو المعلومة"
    )


def test_the_evidence_names_its_scope_and_carries_all_four_attributes(tmp_path, monkeypatch):
    """**الاسم يقول مداه، وحدُّ الصدق داخل الوثيقة لا خارجها.**

    من يقرأ الـJSON وحده — بعد شهور، في تدقيق — يجب أن يعرف **ما لا يُثبِته**. فالحقل
    اسمه `direct_role_attributes` لا `role_isolation`، وفيه نصٌّ يقول صراحةً إنّه لا
    يُثبِت الإغلاق الانتقاليّ لعضويّات الأدوار ولا أثر `SET ROLE`.
    """
    doc = _evidence(tmp_path, monkeypatch)["doc"]
    section = doc["direct_role_attributes"]

    assert set(section["attributes"]) == set(MOD.ROLE_ATTRIBUTES)
    assert set(section["gating"]) == set(MOD._REJECT_IF_TRUE)
    assert "pg_auth_members" in section["$comment"] and "SET ROLE" in section["$comment"], (
        "حدُّ الصدق غير مكتوب داخل الوثيقة — فمن يقرؤها وحدها يقرأ أوسع ممّا قِيس"
    )


def test_the_evidence_carries_no_connection_variable(tmp_path, monkeypatch):
    """ما يُرفَع مصنوعةً يُقرأ لاحقاً — فلا يحمل بيانات اعتماد ولا عنوان خادم."""
    monkeypatch.setenv("PGPASSWORD", "test_password")
    monkeypatch.setenv("PGHOST", "localhost")
    raw = json.dumps(_evidence(tmp_path, monkeypatch)["doc"], ensure_ascii=False)
    for secret in ("test_password", "PGPASSWORD", "localhost", "5435"):
        assert secret not in raw, f"تسرّب «{secret}» إلى الدليل المرفوع"


def test_a_fail_closed_environment_error_still_leaves_evidence(tmp_path, monkeypatch):
    """**العطل الذي لا حكمَ فيه يترك أثراً مقروءاً بدل صمت.**

    غيابُ `psql` أو دورٌ غير موجود يُنهيان بـ`SystemExit` — وهو الصواب: عطلُ بيئةٍ
    ليس حكماً. لكنّ الخروج الصامت يترك الوظيفة بلا وثيقة، فيُقرأ لاحقاً «لم يُشغَّل
    شيء» وهو يعني «شُغِّل وانهار». فيُكتَب `FAIL` بسببه ثمّ تُعاد الرسالة كما هي.
    """
    monkeypatch.setattr(
        MOD, "server_identity", lambda *a, **k: {"postgresql": "16.13", "postgis": "3.4.2"}
    )
    monkeypatch.setattr(MOD, "schema_drift", lambda *a, **k: [])
    monkeypatch.setattr(MOD, "psql", lambda *a, **k: "")  # الدور غير موجود

    out = tmp_path / "live_pg_evidence.json"
    with pytest.raises(SystemExit):
        MOD.main(["--junit", str(_junit(tmp_path, tests=30)), "--evidence", str(out)])

    assert out.is_file(), "خروجٌ مغلق بلا دليل — الصمت يُقرأ «لم يُشغَّل»"
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert doc["verdict"] == "FAIL"
    assert doc["problems"] and "غير موجود" in doc["problems"][0]


def test_without_the_flag_no_file_is_written(tmp_path, monkeypatch):
    """‏`--evidence` اختياريّة: الفحوص المحلّيّة لا تُخلّف مصنوعات في شجرة العمل."""
    _stub(monkeypatch)
    assert MOD.main(["--junit", str(_junit(tmp_path, tests=30))]) == 0
    assert not (tmp_path / "live_pg_evidence.json").exists()
