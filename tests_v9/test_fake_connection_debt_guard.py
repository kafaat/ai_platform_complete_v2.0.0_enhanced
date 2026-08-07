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


def test_the_baseline_says_what_it_does_not_claim(guard):
    """أساسٌ يُقرأ «هذه سليمة» أسوأ من غيابه — النصّ جزءٌ من العقد."""
    declared = json.loads(BASELINE.read_text(encoding="utf-8"))
    note = declared.get("$comment", "")
    assert "يمنع النموّ" in note and "لا يدّعي" in note, note
    assert "قاعدة حيّة" in note, "طريق الخروج من الدَّين يجب أن يكون مكتوباً"
