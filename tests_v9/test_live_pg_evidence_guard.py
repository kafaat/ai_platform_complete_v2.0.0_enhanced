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


def _stub(monkeypatch, *, role=None, drift=()):
    """يُبدّل كلّ ما يلمس القاعدة — العقد يُقاس، لا الاتّصال."""
    monkeypatch.setattr(
        MOD, "server_identity", lambda *a, **k: {"postgresql": "16.13", "postgis": "3.4.2"}
    )
    clean = dict.fromkeys(MOD._FORBIDDEN_ROLE_ATTRS, "false")
    monkeypatch.setattr(MOD, "role_properties", lambda *a, **k: {**clean, **(role or {})})
    monkeypatch.setattr(MOD, "schema_drift", lambda *a, **k: list(drift))


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


def test_every_forbidden_role_attribute_is_rejected_on_its_own(tmp_path, monkeypatch):
    """**اختبارٌ سالب لكلّ خاصّيّة على حدة** — لا شرطٌ مركَّب يُخفي ثقباً.

    الصياغة السابقة فحصت `superuser` و`bypassrls` وحدهما، بينما تقرأ الدالّة
    `createdb` أيضاً: خاصّيّةٌ **تُطبَع ولا تُدان**، وهي «خضرةٌ لا تقول شيئاً» بعينها.
    و`createrole` لم تكن تُقرأ أصلاً — وهي أخطرها: تمنح حاملها عضويّة أدوارٍ أخرى
    فيصل إلى مستأجِرين آخرين بلا superuser وبلا BYPASSRLS.

    والحلقة تشتقّ حالاتها من العقد نفسه، فخاصّيّةٌ تُضاف إليه بلا إدانة تُسقِط هذا
    الاختبار فوراً — بدل أن تنضمّ صامتةً إلى المطبوع غير المفحوص.
    """
    for attr in MOD._FORBIDDEN_ROLE_ATTRS:
        _stub(monkeypatch, role={attr: "true"})
        assert _run(_junit(tmp_path, tests=30)) == 1, f"{attr} لم يُدَن وحده"


def test_the_forbidden_set_covers_the_four_escalation_paths():
    """العقد يُسمّي الأربعة — ونقصانُه ثقبٌ لا تفصيل."""
    assert set(MOD._FORBIDDEN_ROLE_ATTRS) == {
        "rolsuper",
        "rolbypassrls",
        "rolcreatedb",
        "rolcreaterole",
    }, sorted(MOD._FORBIDDEN_ROLE_ATTRS)
    for attr, why in MOD._FORBIDDEN_ROLE_ATTRS.items():
        assert len(why.strip()) >= 30, f"{attr}: مَنعٌ بلا سببٍ مكتوب"


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


def test_the_attestation_is_written_even_when_the_verdict_is_failure(tmp_path, monkeypatch):
    """أدلّةٌ لا تُحفَظ إلّا عند النجاح تجعل الفشل بلا أثرٍ يُراجَع — وهو عكس الغرض.

    وسجلّ التشغيل يفنى مع الرَّنَر، فادّعاء «قِيس على هذا الالتزام» بلا مصنوعة
    محفوظة لا يُراجَع لاحقاً — وهو شرط المالك لإغلاق النقطة.
    """
    _stub(monkeypatch, role={"rolcreaterole": "true"})
    out = tmp_path / "attest.json"
    assert MOD.main(["--junit", str(_junit(tmp_path, tests=30)), "--attest", str(out)]) == 1

    doc = json.loads(out.read_text(encoding="utf-8"))
    assert doc["verdict"] == "fail"
    assert doc["role"]["rolcreaterole"] == "true"
    assert doc["commit_sha"] and doc["commit_sha"] != "unknown", "الأدلّة غير مربوطة بالـSHA"
    assert any("rolcreaterole" in p for p in doc["problems"])
