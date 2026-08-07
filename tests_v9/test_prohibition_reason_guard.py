"""‏`GUARD-PINS-IMPLEMENTATION-NOT-PROPERTY-01`: مَنعٌ بلا سببٍ مُعلَن.

الحارس يعمل خطوةً حاجبة في `ci.yml`، فهذه الاختبارات لا تُعيد فحص ما يفحصه — تحرس
**دلالته**: أنّ الكشف بنيويّ لا نصّيّ، وأنّ حدوده المُعلَنة حقيقيّة لا مجاملة،
وأنّ الجرد يقول ما لا يدّعيه.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
_SCRIPT = ROOT / "scripts" / "ci" / "prohibition_reason_guard.py"
_INVENTORY = ROOT / "docs" / "architecture" / "source_text_assertion_inventory.json"

# سقف راتشِت لا هدف: يُخفَض بكتابة سببٍ حقيقيّ، ولا يُرفَع لتمرير بوّابة.
_MAX_UNREASONED = 100


def _load():
    spec = importlib.util.spec_from_file_location("prohibition_reason_guard", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


MOD = _load()


def _inventory() -> dict:
    return json.loads(_INVENTORY.read_text(encoding="utf-8"))


def _frozen() -> dict:
    return _inventory()["prohibitions_without_a_stated_reason"]


def _count(mapping: dict) -> int:
    return sum(n for needles in mapping.values() for n in needles.values())


def test_the_tree_matches_the_inventory():
    assert MOD.check() == 0


def test_the_baseline_never_silently_grows():
    assert _count(_frozen()) <= _MAX_UNREASONED, f"نما الأساس: {_count(_frozen())}"


def test_the_inventory_says_what_it_does_not_claim():
    """أساسٌ يُقرأ «هذه أعطال» أسوأ من غيابه — المَعدود ليس محكوماً عليه.

    ولا يكفي أن أعرف ذلك: النصّ نفسه يجب أن يقوله، فمن يقرأه بعد سنة لا يقرأ نيّتي.
    """
    comment = _inventory()["$comment"]
    assert "مَعدودة لا" in comment and "محكومٌ عليها" in comment
    assert "لم يُثبَت أنّ أيّاً منها خاطئ" in comment
    assert "يُنشَر ولا يُحرَس" in comment, "الحدّ على التصنيف الاستدلاليّ غير مُعلَن"


def test_the_heuristic_class_is_published_but_never_gates():
    """‏٢٨٩ تأكيداً موجباً تثبّت نداءً — تُنشَر ولا تُحجَب.

    معيار الفجوة («هل يبقى التأكيد صحيحاً بعد إعادة صياغة صحيحة؟») غير قابل للحسم
    آليّاً. لو حجَبَ الحارسُ عليها لَصار هو نفسه الصنفَ الذي يعالجه: يثبّت ما طابق
    نمطاً ويُسمّيه ديناً.
    """
    assert _inventory()["totals"]["positive_pinning_a_call"] > 0
    body = _SCRIPT.read_text(encoding="utf-8")
    gate = body.split("def check(")[1].split("def generate(")[0]
    assert "positive_pinning_a_call" not in gate, "الصنف الاستدلاليّ صار حاجباً"


# ─────────────────────────────────────────────────────────────────────────────
# مستودع اصطناعيّ — لا يُكتَب شيء في الشجرة الحيّة (درس `probe_leak_guard`).
# ─────────────────────────────────────────────────────────────────────────────


def _repo(tmp_path: Path, body: str) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    target = tmp_path / "tests_v9" / "test_probe.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(body, encoding="utf-8")
    for cmd in (["init", "-q"], ["add", "-A"]):
        subprocess.run(["git", *cmd], cwd=tmp_path, check=True, capture_output=True)
    return tmp_path


def _found(monkeypatch, tmp_path: Path, body: str) -> dict:
    monkeypatch.setattr(MOD, "ROOT", _repo(tmp_path, body))
    return MOD.survey()["prohibitions_without_a_stated_reason"]


_READ = 'from pathlib import Path\n\nsrc = Path("x.py").read_text()\n\n\n'


def test_a_prohibition_without_a_reason_is_caught(tmp_path, monkeypatch):
    found = _found(monkeypatch, tmp_path, _READ + 'def test_x():\n    assert "boom" not in src\n')
    assert found == {"tests_v9/test_probe.py": {"boom": 1}}


def test_a_prohibition_that_states_its_reason_is_not_caught(tmp_path, monkeypatch):
    body = _READ + 'def test_x():\n    assert "boom" not in src, "الشهر ليس ٣١ يوماً"\n'
    assert _found(monkeypatch, tmp_path, body) == {}


def test_the_other_spelling_of_a_prohibition_is_caught_too(tmp_path, monkeypatch):
    """‏`not ("x" in y)` يمنع ما يمنعه `not in` بالضبط.

    حارسٌ يرى صيغةً واحدة يُلتَفّ عليه بإعادة صياغة لا تُغيّر شيئاً — وهو التفاف
    لا يحتاج نيّةً سيّئة، يكفي أن يكتبها أحدٌ هكذا.
    """
    body = _READ + 'def test_x():\n    assert not ("boom" in src)\n'
    assert _found(monkeypatch, tmp_path, body) == {"tests_v9/test_probe.py": {"boom": 1}}


def test_a_prohibition_on_something_that_is_not_source_text_is_out_of_scope(tmp_path, monkeypatch):
    """الحدّ المُعلَن حقيقيّ: ما يُمنَع في جسم استجابة هناك التأكيد **هو** العقد.

    لو شمله الحارس لَطالب برسالة على كلّ تأكيد سالب في المستودع — فيُنزَع في أوّل
    يوم، ويسقط معه ما بُني له.

    **والملفّ يحمل قارئاً حقيقيّاً عمداً.** أوّل صياغة عندي لم تحمله، فكان
    `survey()` يتخطّى الملفّ كلّه لخلوّه من القارئات — فمرّ التأكيد **بسببٍ آخر**
    غير الذي يدّعيه، وبقيت خاصّيّة النطاق بلا حارس. كشفَته طفرة مزروعة (تعطيل فحص
    الحاوية) بقيت خضراء.
    """
    body = _READ + (
        'def test_x():\n    payload = {"a": 1}\n'
        '    assert "keep" in src\n'
        '    assert "boom" not in payload\n'
    )
    assert _found(monkeypatch, tmp_path, body) == {}


def test_the_container_is_derived_from_the_assignment_not_from_its_name(tmp_path, monkeypatch):
    """‏`src` اصطلاحٌ لا عقد: متغيّرٌ بالاسم نفسه لم يُقرأ من ملفّ ليس نصّ مصدر.

    والقارئ حاضر في الملفّ تحت اسم آخر، وإلّا تخطّاه المسح فمرّ التأكيد مجّاناً.
    """
    body = _READ.replace("src =", "other =") + (
        'def test_x():\n    src = compute()\n    assert "boom" not in src\n'
    )
    assert _found(monkeypatch, tmp_path, body) == {}


def test_the_guard_reproduces_the_incident_that_created_the_gap():
    """التصديق: الحادثة المُثبِتة يجب أن تظهر **مُسدَّدة**، لا أن تغيب.

    ‏`timedelta(days=months` كان تأكيداً **موجباً** يحمي حساباً خاطئاً (الشهر ليس
    ٣١ يوماً: عند `months=24` تدخل أربعةَ عشرَ يوماً بصمت)، فصار مَنعاً **يُسمّي
    سببه** في #780. فإن لم يكن الملفّ حاضراً بالصيغة المُصحَّحة، فالمسح يقيس شيئاً
    آخر — أو أنّ العلاج تراجع.
    """
    incident = ROOT / "tests_v9" / "test_imagery_timeline_endpoint_v31_4.py"
    text = incident.read_text(encoding="utf-8")
    assert '"timedelta(days=months" not in' in text, "المَنع اختفى — العلاج تراجع"
    line = next(ln for ln in text.splitlines() if '"timedelta(days=months" not in' in ln)
    assert line.rstrip().endswith('"') and "," in line, "المَنع بلا سبب مُعلَن"
    assert incident.relative_to(ROOT).as_posix() not in _frozen(), "الحادثة تُعَدّ دَيناً وقد سُدِّدت"
