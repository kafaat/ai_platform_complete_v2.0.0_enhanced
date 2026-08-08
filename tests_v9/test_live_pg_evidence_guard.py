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


def _stub(monkeypatch, *, role=("false", "false", "false"), drift=()):
    """يُبدّل كلّ ما يلمس القاعدة — العقد يُقاس، لا الاتّصال."""
    monkeypatch.setattr(
        MOD, "server_identity", lambda *a, **k: {"postgresql": "16.13", "postgis": "3.4.2"}
    )
    monkeypatch.setattr(
        MOD,
        "role_properties",
        lambda *a, **k: dict(zip(("superuser", "bypassrls", "createdb"), role, strict=True)),
    )
    monkeypatch.setattr(MOD, "schema_drift", lambda *a, **k: list(drift))


def _run(junit: Path) -> int:
    return MOD.main(["--junit", str(junit)])


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
    """الحدّ عند صفر لا عند «أغلبها نُفِّذ» — تخطٍّ واحد ادّعاءٌ لم يُقَس."""
    _stub(monkeypatch)
    assert _run(_junit(tmp_path, tests=30, skipped=1)) == 1


def test_zero_executed_is_a_failure(tmp_path, monkeypatch):
    _stub(monkeypatch)
    assert _run(_junit(tmp_path, tests=0)) == 1


def test_an_unrestricted_role_is_a_failure(tmp_path, monkeypatch):
    """`NOBYPASSRLS` وحده لا يكفي ولا `NOSUPERUSER` وحده — الاثنان معاً."""
    for role in (("true", "false", "false"), ("false", "true", "false")):
        _stub(monkeypatch, role=role)
        assert _run(_junit(tmp_path, tests=30)) == 1, role


def test_a_missing_contract_object_is_drift(tmp_path, monkeypatch):
    """يمرّ بـ`schema_drift` الحقيقيّة — والمُبدَّل هو `psql` وحده.

    صياغتي الأولى أبدلت `schema_drift` نفسها بقائمةٍ جاهزة، فكان تعطيل المقارنة
    داخلها **لا يُسقِط هذا الاختبار**: يقرأ مصنوعةً ركّبتُها بدل أن يمرّ بالقاعدة.
    أمسكَته الطفرة المُسجَّلة وهي خضراء — وهو الصنف الذي بُني `guard_mutation_guard`
    لأجله بالحرف.
    """
    contract = tmp_path / "contract.json"
    contract.write_text(
        json.dumps({"objects": {"water_ledger": {"primary_key": "PRIMARY KEY (field_id)"}}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(MOD, "CONTRACT", contract)

    monkeypatch.setattr(MOD, "psql", lambda *a, **k: "PRIMARY KEY (field_id)")
    assert MOD.schema_drift("d", "o") == [], "المطابق يُدان — إيجابيّة كاذبة"

    monkeypatch.setattr(MOD, "psql", lambda *a, **k: "PRIMARY KEY (something_else)")
    drift = MOD.schema_drift("d", "o")
    assert drift and "water_ledger.primary_key" in drift[0], drift


def test_an_object_the_contract_does_not_name_is_not_drift(tmp_path, monkeypatch):
    """الزائد لا يُدان: العقد يصف ما تستند إليه الأدلّة لا كامل المخطّط.

    لولا هذا لصارت كلُّ هجرةٍ تُضيف قيداً «انحرافاً»، فيُدرَّب القارئ على تجاهل
    الحارس — وهو تعطيلٌ له بثوب تشدُّد.
    """
    contract = tmp_path / "contract.json"
    contract.write_text(
        json.dumps({"objects": {"water_ledger": {"check": ["CHECK (etc_mm >= 0)"]}}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(MOD, "CONTRACT", contract)
    monkeypatch.setattr(
        MOD, "psql", lambda *a, **k: "CHECK (etc_mm >= 0)\nCHECK (a_new_constraint > 1)"
    )
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
