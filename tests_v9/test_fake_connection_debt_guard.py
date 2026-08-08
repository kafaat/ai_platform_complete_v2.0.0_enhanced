#!/usr/bin/env python3
"""عقد ``FAKE-CONNECTION-ENFORCES-NOTHING-01`` — وهميٌّ لا يفرض ما تفرضه القاعدة.

**الحادثة المقيسة:** بعد ٢٢٦ هجرة على PG16 نظيفة، تعطّلت الرحلة القانونيّة **أربع
مرّات متتالية بأربعة أسباب مختلفة**، كلّ إصلاح يكشف الذي بعده. وكلّها كانت خضراء
سنةً على وهميّ. والسجلّ سمّى ما لم يُقَس: «**السطح غير ممسوح**».

وهذا الملفّ يُثبّت **الخاصّيّة** لا الأرقام: أنّ الماسح يرى، وأنّ الراتشِت يُدين
النموّ، وأنّه لا يخضرّ بصفر مفحوص.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "scripts" / "ci" / "fake_connection_debt_guard.py"
BASELINE = ROOT / "docs" / "architecture" / "fake_connection_debt.json"
_PROOF = "tests_v9/test_live_pg_fake_connection_debt.py"


@pytest.fixture(scope="module")
def guard():
    spec = importlib.util.spec_from_file_location("_fake_conn_debt_guard", TOOL)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_the_committed_tree_matches_its_declared_baseline(guard):
    assert guard.check() == [], "\n".join(guard.check())


def test_the_scanner_actually_sees_something(guard):
    """أخضرٌ بصفر مفحوص هو الصفر الصامت الذي يوجد هذا الحارس ليمنعه."""
    found = guard.survey()
    assert len(found["fake"]) >= 20, f"انهار المسح إلى {len(found['fake'])} — تضييق صامت"
    assert found["claiming"], "صفر ادّعاء؟ الماسح فقد عينه لدلالات القاعدة"


def test_the_incident_file_is_named_by_the_survey_not_by_hand(guard):
    """**التصديق:** الملفّ الذي سقط أربع مرّات حيّاً يجب أن يُشتقّ، لا يُكتَب بيد.

    ``test_canonical_event_emission_contracts.py`` هو مصدر الحادثة، وسببها الأخطر
    ``jsonb`` — asyncpg يُعيده نصّاً والوهميّ يُعيد ``dict``. فإن لم يُسمِّه المسح،
    فالمسح لا يقيس ما وقع فعلاً.
    """
    claiming = guard.survey()["claiming"]
    key = "tests_v9/test_canonical_event_emission_contracts.py"
    assert key in claiming, sorted(claiming)
    assert "jsonb" in claiming[key], claiming[key]


def test_a_new_fake_that_claims_database_semantics_is_denied(guard, tmp_path, monkeypatch):
    """التكذيب: ملفّ جديد يجمع «وهميّ + دلالة قاعدة» يجب أن يُدان **باسمه**."""
    repo = tmp_path / "r"
    (repo / "tests_v9").mkdir(parents=True)
    subprocess.run(["git", "init", "-q", "."], cwd=repo, check=True, capture_output=True)
    (repo / "tests_v9" / "test_new.py").write_text(
        "class _FakeConn:\n    pass\n\n# يؤكّد ON CONFLICT بلا قاعدة\n", encoding="utf-8"
    )
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True, capture_output=True)

    found = guard.survey(root=repo)
    assert found["claiming"] == {"tests_v9/test_new.py": ["UNIQUE"]}, found


def test_a_fake_that_claims_nothing_about_the_database_is_not_denied(guard, tmp_path):
    """**الحدّ الذي يُبقي الحارس حيّاً.** وهميٌّ لمنطق صرف ليس ديناً.

    حارسٌ يتّهم كلّ وهميّ يُنزَع في أوّل يوم — أكثر الاختبارات لا تلمس القاعدة أصلاً.
    """
    repo = tmp_path / "r"
    (repo / "tests_v9").mkdir(parents=True)
    subprocess.run(["git", "init", "-q", "."], cwd=repo, check=True, capture_output=True)
    (repo / "tests_v9" / "test_pure.py").write_text(
        "class _FakeConn:\n    pass\n\n# منطق صرف، لا دلالة قاعدة\n", encoding="utf-8"
    )
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True, capture_output=True)

    found = guard.survey(root=repo)
    assert found["fake"] == ["tests_v9/test_pure.py"]
    assert found["claiming"] == {}, found


def test_the_baseline_is_derived_not_hand_maintained(guard):
    """‏`--generate` يُنتِج ما يقرؤه `--check` بالضبط — فلا أساس يُصان بيد ويَبيت."""
    declared = json.loads(BASELINE.read_text(encoding="utf-8"))
    found = guard.survey()
    assert declared["fake_connection_tests"] == found["fake"]
    assert declared["claiming_db_enforced"] == found["claiming"]


def test_the_guard_does_not_denounce_its_own_subject_matter(guard):
    """**الحدّ الذي وقعتُ فيه عند أوّل تشغيل.**

    هذا الملفّ يحوي ``class _FakeConn`` و``ON CONFLICT`` و``jsonb`` **بوصفها موضوعه**
    — زرعاتٌ في مستودعات مؤقّتة وشرحٌ للحادثة. فأدرجه الأساسُ ديناً عند أوّل مكنسة.
    وحارسٌ يُطلِق على توثيق ما يمنعه يُعطَّل في أوّل يوم؛ وقع فيه ``probe_leak_guard``
    بعد ``#802``، ووقعتُ فيه هنا بعد ساعة من إصلاحه.
    """
    found = guard.survey()
    mine = "tests_v9/test_fake_connection_debt_guard.py"
    assert mine not in found["fake"], "الحارس يُدين اختباره"
    assert mine not in found["claiming"], "الحارس يُدين اختباره"


def test_the_self_exemption_does_not_blind_the_guard(guard, tmp_path):
    """تكذيب الاستثناء نفسه: ملفٌّ آخر بالرموز ذاتها **يُدان** في الشجرة ذاتها."""
    repo = tmp_path / "r"
    (repo / "tests_v9").mkdir(parents=True)
    subprocess.run(["git", "init", "-q", "."], cwd=repo, check=True, capture_output=True)
    for name in ("test_fake_connection_debt_guard.py", "test_other.py"):
        (repo / "tests_v9" / name).write_text(
            "class _FakeConn:\n    pass\n# ON CONFLICT\n", encoding="utf-8"
        )
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True, capture_output=True)

    found = guard.survey(root=repo)
    assert found["claiming"] == {"tests_v9/test_other.py": ["UNIQUE"]}, found


def test_the_baseline_says_what_it_does_not_claim(guard):
    """أساسٌ يُقرأ «هذه سليمة» أسوأ من غيابه — النصّ جزءٌ من العقد."""
    declared = json.loads(BASELINE.read_text(encoding="utf-8"))
    note = declared.get("$comment", "")
    assert "يمنع النموّ" in note and "لا يدّعي" in note, note
    assert "قاعدة حيّة" in note, "طريق الخروج من الدَّين يجب أن يكون مكتوباً"


# ────────────────────────── السداد الحيّ (`proven_live`) ──────────────────────────
#
# طريق الخروج كان **مكتوباً وغير موجود**: `claiming_db_enforced` مُشتقّ من نصّ الملفّ،
# والإثبات على قاعدة حيّة لا يغيّر النصّ — فلا سبيل للخروج منه مهما أُثبِت. توثيقٌ
# صادقٌ يوم كُتِب صار ادّعاءً يوم جاء من يسلكه. القسم أدناه يجعله ممكناً **ومقيساً**.


def test_a_settlement_must_name_a_proof_file_that_exists(guard):
    entry = {"claims": ["UNIQUE"], "proof": "tests_v9/no_such_proof.py", "evidence": "x" * 40}
    bad = guard._proof_covers("tests_v9/test_x.py", entry, ["UNIQUE"])
    assert any("لا يُسمّي ملفّاً قائماً" in p for p in bad), bad


def test_a_settlement_whose_proof_never_mentions_the_source_is_refused(guard):
    """أخطر صنف: مدخلٌ يشير إلى ملفّ إثبات **قائم** لا علاقة له بمصدره.

    الملفّ موجود والاختبارات خضراء، فيمرّ الفحصان السهلان — ويبقى الدَّين غير مسدَّد.

    وملفّ «الإثبات» هنا هو الحارس نفسه، اختير لأنّه **لا يذكر** المصدر. وأوّل صياغة
    عندي اختارت هذا الملفَّ الذي تقرأه، فمرّ الفحص لأنّ السطر أعلاه يذكر المصدر —
    الاختبارُ يُبطِل نفسه بذكره ما يبحث عنه.
    """
    entry = {
        "claims": ["UNIQUE"],
        "proof": "scripts/ci/fake_connection_debt_guard.py",
        "evidence": "x" * 40,
    }
    bad = guard._proof_covers("tests_v9/test_water_ledger.py", entry, ["UNIQUE"])
    assert any("لا يذكره" in p for p in bad), bad


def test_a_partial_settlement_does_not_close_the_debt(guard):
    """ادّعاءٌ واحد مُثبَت من ثلاثة لا يُخرِج الملفّ — «كلّ ادّعاءاته» شرطٌ لا شعار."""
    entry = {"claims": ["CHECK"], "proof": _PROOF, "evidence": "x" * 40}
    bad = guard._proof_covers("tests_v9/test_x.py", entry, ["CHECK", "TRIGGER", "jsonb"])
    assert any("يُعيد فتح الدَّين" in p for p in bad), bad


def test_the_outstanding_debt_is_the_survey_minus_the_settlements(guard):
    """الرقم المُراقَب مشتقّ لا مكتوب — ولا يُخلَط بالخام الذي لا ينزل أبداً."""
    found = guard.survey()
    declared = json.loads(BASELINE.read_text(encoding="utf-8"))
    left = guard.outstanding(found=found, declared=declared)
    assert set(left) == set(found["claiming"]) - set(declared["proven_live"]), left


def test_regenerating_the_baseline_does_not_erase_the_settlements(guard, tmp_path, monkeypatch):
    """«المصنوع يدهس المكتوب» — صنفٌ أسقط بناءً في هذه الشجرة أكثر من مرّة.

    `proven_live` قرارٌ مقيس لا مُشتقّ، فأوّل `--generate` كان سيمحوه ويُعيد الدَّين
    المُسدَّد صامتاً. والقياس هنا تفاضليّ: يُعاد التوليد فعلاً ثمّ يُقرأ الملفّ.
    """
    target = tmp_path / "debt.json"
    original = json.loads(BASELINE.read_text(encoding="utf-8"))
    target.write_text(json.dumps(original, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(guard, "BASELINE", target)

    guard._generate()

    after = json.loads(target.read_text(encoding="utf-8"))
    assert after["proven_live"] == original["proven_live"], "أُبيد السداد بإعادة التوليد"
    assert after["claiming_db_enforced"] == guard.survey()["claiming"]
