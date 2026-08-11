"""TEXT-DECODED-WITH-THE-MACHINES-LOCALE-01 — النصّ يُفكّ بترميز الآلة لا بـUTF-8.

تقرير فحص خارجيّ أبلغ عن **١٢ فشلاً** على Windows ونسبها إلى «بيئة Windows» — أي إلى
شيء لا يخصّ الشيفرة. لم يُصدَّق ولم يُرفَض: أُعيد إنتاج العطل **على Linux** بفرض لغة C
(`LC_ALL=C PYTHONUTF8=0` ⇒ الترميز الافتراضيّ ANSI_X3.4-1968) فظهرت **١٢** بالضبط،
كلّها UnicodeDecodeError. فالتصنيف الصحيح ليس «عطل Windows» بل **اعتماد على ترميز
الآلة**؛ وWindows يكشفه فقط لأنّ افتراضيّه ليس UTF-8.

الفارق ليس لفظيّاً: «عطل بيئة» يُغلَق بتغيير الجهاز، و«اعتماد على ترميز الآلة» يُغلَق
بإصلاح الشيفرة. الأوّل يجعل CI الأخضر شهادةً على أنّ Linux افتراضيّه UTF-8، لا على أنّ
الحارس يقرأ ما يدّعي قراءته.

**والمتّجهات ثلاثة لا واحد** — والعلاج الشائع (إضافة `encoding` إلى القراءات) يُغلق
ثمانية من الاثني عشر لا كلّها، مقيساً بتطبيقه وحده:
  ① قراءة مباشرة — `read_text()`/`open()` بلا `encoding`.
  ② فكّ ترميز مخرَج عمليّة — `subprocess.run(..., text=True)` يفكّ بترميز اللغة أيضاً،
     فاختبارٌ يُشغّل حارساً يطبع عربيّة ينهار في **الأب** لا في الابن. هذا المتّجه لا
     يظهر لأيّ فحص يبحث عن `open(` وحده.
  ③ **مخرَج الابن نفسه** — `encoding` على الأب لا يُملي على الابن بماذا يكتب، فرسالة
     تحوي «—» أو حرفاً عربيّاً تُسقِطه بـ`UnicodeEncodeError`؛ يُغلَق بـ
     `PYTHONIOENCODING=utf-8` في بيئته. هذا وحده سبب أربعة من الاثني عشر.

الأساس يمنع النموّ **ولا يدّعي** أنّ ما فيه سليم: أُثبِت انهيار ثمانية ملفّات (أُصلِحت)،
والبقيّة تقرأ ASCII اليوم — حظّ لا تصميم، فتوثيق هذا المستودع عربيّ.

**ودقّة الماسح نفسها قابلة للخطأ:** نسخته الأولى أدرجت أربعة ملفّات دَيناً وهي نظيفة،
لأنّها قرأت وسيط الوضع من الموضع الثاني دائماً — وموضعه في `path.open("rb")` هو الأوّل.
أمسك بها فحصٌ خارجيّ لا أنا. الأساس المُبالِغ في الدَّين يُدرَّب قارئه على تجاهله، وهو
عطل الحارس الأكثر شيوعاً؛ فصارت حالات الشكلين مُقفَلة باختبار صريح أدناه.

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


def _path_like_names(tree: ast.AST) -> set[str]:
    """أسماء يُثبِت التحليل المحلّيّ أنّها Path — لا تخميناً من الاسم.

    ثلاثة مصادر إثبات فقط، وكلّها ساكنة: إسنادٌ من `Path(...)`، أو من تعبير مسار
    (`base / "x"`)، أو تعليقُ نوعٍ `: Path`. وما عداها **لا يُثبَت**، فلا يُدان.
    """
    names: set[str] = set()

    def _is_path_expr(node: ast.AST) -> bool:
        if isinstance(node, ast.Call):
            fn = node.func
            if isinstance(fn, ast.Name) and fn.id == "Path":
                return True
            if isinstance(fn, ast.Attribute) and fn.attr == "Path":
                return True
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
            return _is_path_expr(node.left) or (
                isinstance(node.left, ast.Name) and node.left.id in names
            )
        if isinstance(node, ast.Name):
            return node.id in names
        if isinstance(node, ast.Attribute) and node.attr in {"parent", "resolve"}:
            return _is_path_expr(node.value)
        return False

    for _ in range(2):  # تمريرتان: إسنادٌ يعتمد على اسمٍ عُرِف بعده
        for node in ast.walk(tree):
            if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                ann = node.annotation
                text = ann.id if isinstance(ann, ast.Name) else getattr(ann, "attr", "")
                if text == "Path":
                    names.add(node.target.id)
            elif isinstance(node, ast.Assign) and _is_path_expr(node.value):
                for tgt in node.targets:
                    if isinstance(tgt, ast.Name):
                        names.add(tgt.id)
    return names


def _receiver_is_path(node: ast.Call, path_names: set[str]) -> bool:
    """أهذا فتحُ ملفٍّ محلّيّ يعتمد ترميز الآلة، أم `open` لشيء آخر تماماً؟

    **الإيجابيّة الكاذبة الموثَّقة:** `opener.open(request, timeout=…)` من `urllib`
    يُعيد بايتات، ولا يفكّ ترميزاً، **ولا يقبل `encoding=` أصلاً** — فإدانته تطلب
    إصلاحاً مستحيلاً، ولا مخرج منها إلّا إضافةُ الملفّ إلى أساسٍ يقول عن نفسه إنّه
    يتقلّص ولا ينمو. أي أنّ الكاشف غير المُرسى يدفع نحو إفساد الرَّاتشِت.

    والقاعدة **محافظة عمداً**: تُدين ما يُثبَت أنّه مسار، وتصمت عمّا لا يُثبَت.
    فسكوتها عن `client.open(x)` مجهول النوع أرخص من إدانةٍ لا علاج لها.
    """
    fn = node.func
    if isinstance(fn, ast.Name):  # `open(...)` المدمَجة
        return True
    if not isinstance(fn, ast.Attribute):
        return False
    recv = fn.value
    if isinstance(recv, ast.Call):  # `Path("x").open()`
        rf = recv.func
        return (isinstance(rf, ast.Name) and rf.id == "Path") or (
            isinstance(rf, ast.Attribute) and rf.attr == "Path"
        )
    if isinstance(recv, ast.Name):  # اسمٌ أُثبِت محلّيّاً أنّه Path
        return recv.id in path_names
    if isinstance(recv, ast.BinOp) and isinstance(recv.op, ast.Div):  # `base / "x"`
        return True
    return False


def _offenders_in(src: str) -> dict[str, int]:
    """المواضع التي تعتمد ترميز الآلة، مفصولةً بمتّجهها."""
    reads = subprocesses = 0
    tree = ast.parse(src)
    path_names = _path_like_names(tree)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if any(k.arg == "encoding" for k in node.keywords):
            continue
        is_method = isinstance(node.func, ast.Attribute)
        name = _call_name(node)
        if name in _TEXT_IO:
            # `read_text` كاسم عارٍ ليست طريقة مسار بل دالّة محلّيّة يعرّفها الملفّ
            # (`runtime_contract_generator.py` مثالها) — وهي تتولّى ترميزها بنفسها.
            # المدمَجة الوحيدة التي تُستدعى باسم عارٍ هي `open`.
            if not is_method and name != "open":
                continue
            # موضع وسيط الوضع يختلف بين الشكلين: `open(path, "rb")` وسيطه الثاني،
            # و`path.open("rb")` وسيطه **الأوّل**. قراءة الثاني دائماً تجعل كلّ فتح
            # ثنائيّ على كائن مسار يُحسَب عيباً — أربعة ملفّات في هذه الشجرة كانت
            # مُدرَجة دَيناً وهي نظيفة، وأمسك بها فحصٌ خارجيّ لا أنا.
            # **الإرساء على نوع المتلقّي** — `.open` اسمٌ تتقاسمه مكتبات لا تفكّ
            # ترميزاً ولا تقبل `encoding=` أصلاً (`opener.open` من urllib مثالها
            # المقيس). فإدانتها تطلب إصلاحاً مستحيلاً، ومخرجها الوحيد إضافةُ الملفّ
            # إلى أساسٍ يتقلّص ولا ينمو — أي أنّ الإيجابيّة الكاذبة تُفسِد الرَّاتشِت.
            if name == "open" and not _receiver_is_path(node, path_names):
                continue
            mode_args = node.args[0:1] if (is_method and name == "open") else node.args[1:2]
            mode = [
                a.value
                for a in mode_args
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
    assert len(baseline) <= 179, f"الأساس نما إلى {len(baseline)}؛ يتقلّص ولا ينمو"


def test_no_baselined_file_adds_a_new_offender_under_its_entry():
    """الأساس يُقاس بالاسم، والاسمُ لا يقول **كم**.

    **ثغرةٌ قِيست لا فُرِضت:** الاختبار أعلاه يمنع مدخلاً جديداً ويمنع مدخلاً
    بائتاً، والذي قبله يمنع ملفّاً جديداً — وثلاثتها تقارن **مجموعات أسماء**.
    فملفٌّ مُدرَجٌ بقراءتين تُضاف إليه ثالثة ولا شيء يحمرّ: اسمُه في الأساس على
    الحالين. وقد وقع فعلاً — شريحةٌ أضافت `read_text()` ثالثة إلى
    ``irrigation_runtime_orchestrator_guard`` فمرّت صامتة.

    والأساس يقول عن نفسه إنّه **يتقلّص**؛ فالعدد جزءٌ من العقد لا زينةٌ فيه.
    """
    current, baseline = _scan(), _baseline()
    grown = {
        path: (baseline[path], current[path])
        for path in sorted(set(baseline) & set(current))
        if current[path]["reads"] > baseline[path]["reads"]
        or current[path]["subprocess"] > baseline[path]["subprocess"]
    }
    assert not grown, (
        "ملفّات في الأساس زاد انحرافُها: "
        + " · ".join(f"{p} {was} ⇒ {now}" for p, (was, now) in grown.items())
        + '\nأضِف encoding="utf-8" إلى الموضع الجديد — الأساس يُغطّي القائم لا الزائد.'
    )


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
    # موضع وسيط الوضع يختلف بين الشكلين — والخلط بينهما يجعل كلّ فتح ثنائيّ عيباً.
    assert _offenders_in('p = Path("x")\np.open("rb")')["reads"] == 0, "الوضع الأوّل في طريقة المسار"
    assert _offenders_in('p = Path("x")\np.open("r")')["reads"] == 1, (
        "نصّيّ صريح بلا ترميز يبقى عيباً — و`p` مربوطة بـPath فالمتلقّي مُثبَت"
    )
    assert _offenders_in('p = Path("x")\np.open()')["reads"] == 1, "الافتراضيّ نصّيّ"
    # `read_text` باسم عارٍ دالّة محلّيّة لا طريقة مسار — إدراجها يضخّم الدَّين بالباطل.
    assert _offenders_in("content = read_text(path)")["reads"] == 0
    assert _offenders_in("p.read_text()")["reads"] == 1


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


# ── إرساء الكاشف على نوع المتلقّي (قرار المالك، 2026-08-03) ────────────────────
#
# `.open` اسمٌ تتقاسمه مكتبات لا علاقة لها بترميز الملفّات. وإدانتها به تطلب إصلاحاً
# **مستحيلاً** (لا تقبل `encoding=`)، ولا مخرج منها إلّا إضافة الملفّ إلى أساسٍ
# يتقلّص ولا ينمو — أي أنّ الإيجابيّة الكاذبة تُفسِد الرَّاتشِت لا تُزعِج فقط.

_NOT_FILE_OPENS = [
    ("opener.open(request, timeout=5)", "urllib: يُعيد بايتات ولا يقبل encoding"),
    ("urllib.request.build_opener().open(request)", "بانٍ مباشر"),
    ("archive.open(member)", "zipfile.ZipFile.open"),
    ("client.open(resource)", "متلقٍّ مجهول النوع"),
    ("rasterio.open(path)", "وحدة خارجيّة"),
    ("tar.extractfile(member)", "tarfile"),
]

_REAL_TEXT_OPENS = [
    ('open("file.txt")', "المدمَجة، وضع افتراضيّ"),
    ('open("file.txt", "r")', "المدمَجة، نصّيّ صريح"),
    ('Path("file.txt").open()', "بانٍ Path مباشر"),
    ('path = Path("file.txt")\npath.open()', "اسم مُثبَت محلّيّاً"),
    ('base = Path("d")\n(base / "f").open()', "تعبير مسار"),
    ("p: Path = get()\np.open()", "تعليق نوع"),
]

_ALREADY_SAFE = [
    ('open("file.txt", encoding="utf-8")', "ترميز صريح"),
    ('Path("file.txt").open(encoding="utf-8")', "ترميز صريح على Path"),
    ('open("f", "rb")', "ثنائيّ لا يحتاج ترميزاً"),
    ('Path("f").open("wb")', "كتابة ثنائيّة"),
]


@pytest.mark.parametrize(("src", "why"), _NOT_FILE_OPENS)
def test_a_non_file_open_is_not_condemned(src: str, why: str) -> None:
    """**الإيجابيّة الكاذبة الموثَّقة** — `opener.open` ليس فتحَ ملفّ نصّيّ."""
    assert _offenders_in(src)["reads"] == 0, f"إيجابيّة كاذبة ({why}): {src}"


@pytest.mark.parametrize(("src", "why"), _REAL_TEXT_OPENS)
def test_a_real_text_open_is_still_condemned(src: str, why: str) -> None:
    """**الحدّ الذي يمنع الإرساء من فتح ثغرة:** ما بُني الحارس له يبقى مُداناً."""
    assert _offenders_in(src)["reads"] == 1, f"فتحٌ نصّيّ أفلت ({why}): {src}"


@pytest.mark.parametrize(("src", "why"), _ALREADY_SAFE)
def test_an_encoded_or_binary_open_passes(src: str, why: str) -> None:
    assert _offenders_in(src)["reads"] == 0, f"سليم أُدين ({why}): {src}"


def test_errors_or_newline_alone_do_not_substitute_for_encoding() -> None:
    """`errors=` و`newline=` يضبطان سلوك الفكّ لا **ترميزه** — فلا يُغنيان عنه."""
    assert _offenders_in('open("f", errors="ignore")')["reads"] == 1
    assert _offenders_in('open("f", newline="")')["reads"] == 1
    assert _offenders_in('open("f", errors="ignore", encoding="utf-8")')["reads"] == 0
