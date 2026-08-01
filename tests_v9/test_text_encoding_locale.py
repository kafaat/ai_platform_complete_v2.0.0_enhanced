"""TEXT-DECODED-WITH-THE-MACHINES-LOCALE-01 — النصّ يُفكّ بترميز الآلة لا بـUTF-8.

تقرير فحص خارجيّ أبلغ عن **١٢ فشلاً** على Windows ونسبها إلى «بيئة Windows» — أي إلى
شيء لا يخصّ الشيفرة. لم يُصدَّق ولم يُرفَض: أُعيد إنتاج العطل **على Linux** بفرض لغة C
(`LC_ALL=C PYTHONUTF8=0` ⇒ الترميز الافتراضيّ ANSI_X3.4-1968) فظهرت **١٢** بالضبط،
كلّها UnicodeDecodeError. فالتصنيف الصحيح ليس «عطل Windows» بل **اعتماد على ترميز
الآلة**؛ وWindows يكشفه فقط لأنّ افتراضيّه ليس UTF-8.

الفارق ليس لفظيّاً: «عطل بيئة» يُغلَق بتغيير الجهاز، و«اعتماد على ترميز الآلة» يُغلَق
بإصلاح الشيفرة. الأوّل يجعل CI الأخضر شهادةً على أنّ Linux افتراضيّه UTF-8، لا على أنّ
الحارس يقرأ ما يدّعي قراءته.

**والمتّجهان اثنان لا واحد:**
  ① قراءة مباشرة — `read_text()`/`open()` بلا `encoding`.
  ② فكّ ترميز مخرَج عمليّة — `subprocess.run(..., text=True)` يفكّ بترميز اللغة أيضاً،
     فاختبارٌ يُشغّل حارساً يطبع عربيّة ينهار في **الأب** لا في الابن. هذا المتّجه لا
     يظهر لأيّ فحص يبحث عن `open(` وحده، وهو سبب ثلاثة من الاثني عشر.

الأساس يمنع النموّ **ولا يدّعي** أنّ ما فيه سليم: أُثبِت انهيار ثمانية ملفّات (أُصلِحت)،
والبقيّة تقرأ ASCII اليوم — حظّ لا تصميم، فتوثيق هذا المستودع عربيّ.

فحص صرف — ``pytest -m unit``.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parents[1]
_ROOTS = ("scripts", "tests", "tests_v9")
_BASELINE = _ROOT / "docs" / "architecture" / "text_encoding_locale_baseline.json"

_TEXT_IO = {"open", "read_text", "write_text"}
_SUBPROCESS = {"run", "check_output", "Popen"}


def _call_name(node: ast.Call) -> str | None:
    fn = node.func
    if isinstance(fn, ast.Attribute):
        return fn.attr
    if isinstance(fn, ast.Name):
        return fn.id
    return None


def _offenders_in(src: str) -> dict[str, int]:
    """المواضع التي تعتمد ترميز الآلة، مفصولةً بمتّجهها."""
    reads = subprocesses = 0
    for node in ast.walk(ast.parse(src)):
        if not isinstance(node, ast.Call):
            continue
        if any(k.arg == "encoding" for k in node.keywords):
            continue
        name = _call_name(node)
        if name in _TEXT_IO:
            # الوضع الثنائيّ لا يفكّ ترميزاً فلا يعنيه هذا الحارس.
            mode = [
                a.value
                for a in node.args[1:2]
                if isinstance(a, ast.Constant) and isinstance(a.value, str)
            ]
            if mode and "b" in mode[0]:
                continue
            reads += 1
        elif name in _SUBPROCESS:
            if {"text", "universal_newlines"} & {k.arg for k in node.keywords}:
                subprocesses += 1
    return {"reads": reads, "subprocess": subprocesses}


def _scan() -> dict[str, dict[str, int]]:
    found: dict[str, dict[str, int]] = {}
    for root in _ROOTS:
        for path in sorted((_ROOT / root).rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            try:
                counts = _offenders_in(path.read_text(encoding="utf-8"))
            except SyntaxError:
                continue
            if counts["reads"] or counts["subprocess"]:
                found[path.relative_to(_ROOT).as_posix()] = counts
    return found


def _baseline() -> dict[str, dict[str, int]]:
    return json.loads(_BASELINE.read_text(encoding="utf-8"))["files"]


def test_no_new_file_decodes_text_with_the_machines_locale():
    """الأساس يتقلّص ولا ينمو — والرسالة تسمّي الملفّ ومتّجهه.

    ملفّ جديد يقرأ نصّاً بلا `encoding` يُسقِط هذا الاختبار. الإصلاح سطرٌ واحد
    (`encoding="utf-8"`)، لا إضافة مدخل إلى الأساس.
    """
    new = sorted(set(_scan()) - set(_baseline()))
    assert not new, (
        "ملفّات جديدة تفكّ ترميز النصّ بترميز الآلة: "
        + " · ".join(new)
        + '\nأضِف encoding="utf-8" إلى القراءة أو إلى subprocess — لا تُضِف المدخل إلى الأساس.'
    )


def test_the_baseline_never_grows_and_holds_no_dead_entries():
    """مدخل بائت خطر بقدر المدخل الناقص: يُقرأ دَيناً قائماً وقد أُصلِح.

    وهو إنفاذ عكسيّ كعقد #735 — الأساس يُوصَف بأنّه يتقلّص، فليُثبَت تقلّصه.
    """
    current, baseline = _scan(), _baseline()
    stale = sorted(set(baseline) - set(current))
    assert not stale, "مداخل في الأساس لم تعد منحرفة — احذفها: " + " · ".join(stale)
    assert len(baseline) <= 188, f"الأساس نما إلى {len(baseline)}؛ يتقلّص ولا ينمو"


def test_the_eight_files_proven_to_break_are_fixed_and_stay_fixed():
    """الثمانية التي انهارت فعلاً تحت لغة C — لا يعود أيّها إلى الأساس.

    هذه ليست تكراراً للاختبار السابق: ذاك يمنع **النموّ**، وهذا يُثبّت **الإصلاح**.
    ملفّ منها يفقد ترميزه الصريح يمرّ من الأوّل (لأنّه في الأساس أصلاً لو أُعيد) ويسقط هنا.
    """
    proven = {
        "scripts/ci/execution_delivery_receipt_boundary_gate.py",
        "tests_v9/test_api_versioning_policy_guard.py",
        "tests_v9/test_field_forms_mobile_runtime_wiring.py",
        "tests_v9/test_mobile_backend_contract.py",
        "tests_v9/test_simulation_single_truth_guard.py",
        "tests_v9/test_unified_production_readiness_gate.py",
        "tests_v9/test_water_ledger_identity_guard_v21.py",
        "tests_v9/test_wx10_11b_execution_delivery_receipt_contract.py",
    }
    regressed = sorted(proven & set(_scan()))
    assert not regressed, "ملفّات مُثبَت انهيارها عادت بلا ترميز صريح: " + " · ".join(regressed)
    assert not (proven & set(_baseline())), "المُصلَح لا يُسجَّل في الأساس"


def test_the_subprocess_vector_is_actually_covered():
    """تكذيب مُدمَج: لو نسي الماسح متّجه العمليّات لَبقي ثلث الفشل غير مرئيّ.

    فحصٌ يبحث عن `open(` وحده يمرّ على `subprocess.run(..., text=True)` — وهو سبب
    ثلاثة من الاثني عشر. هذا يُثبِت أنّ الماسح يراه، لا أنّني قصدتُ أن يراه.
    """
    assert _offenders_in("subprocess.run(cmd, text=True)")["subprocess"] == 1
    assert _offenders_in("subprocess.run(cmd, text=True, encoding='utf-8')")["subprocess"] == 0
    assert _offenders_in("p.read_text()")["reads"] == 1
    assert _offenders_in("p.read_text(encoding='utf-8')")["reads"] == 0
    assert _offenders_in("open(p, 'rb')")["reads"] == 0, "الوضع الثنائيّ لا يفكّ ترميزاً"


def test_this_repository_actually_contains_the_bytes_that_trigger_it():
    """العطل مشروط بوجود بايت غير ASCII في ملفّ مقروء — فليُقَس وجوده لا يُفترَض.

    لو كانت الشجرة ASCII بالكامل لكان هذا الحارس احتياطاً نظريّاً. وهي ليست كذلك:
    التوثيق والتعليقات عربيّة، وهو ما جعل الاثني عشر تنهار.
    """
    probe = _ROOT / "services" / "decision-service" / "main.py"
    raw = probe.read_bytes()
    assert any(b > 0x7F for b in raw), f"{probe} صار ASCII — أعد اختيار المسبار"
    with pytest.raises(UnicodeDecodeError):
        raw.decode("ascii")
