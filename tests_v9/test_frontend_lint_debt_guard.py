"""`FRONTEND-LINT-DEBT-UNGUARDED-01` — الدَّين يُحرَس، ولا يُدَّعى أنّه أُصلِح.

**ولماذا هذا الحارس أصلاً:** `eslint` هنا يُبلِّغ **تحذيراً** لا خطأً على `no-explicit-any`
و`no-unused-vars`. فوظيفة *Frontend Typecheck* تخرج خضراء وفيها ٨٢ تحذيراً، وGitHub
يعرض **عشرة** منها في التعليقات — فيقرأ المالك «عشرة» والواقع ثمانون. العدّاد غير مرئيّ
وغير محجوب معاً، وهذا أسوأ من دَينٍ مُعلَن.

**والاختبارات بمعطياتٍ مُركَّبة عمداً:** حارسٌ لا يُختبَر إلّا بتشغيل `npx eslint` يصير
تكذيبُه معتمداً على `node_modules` — فيُتخطّى في كلّ بيئةٍ بلا تثبيت، وهو صنف
`STABLE_WRONG_TEST` الذي يُصنّفه `guard_mutation_guard`. فالحُكم يُختبَر على تقريرٍ
مُجسَّد، والتشغيل الفعليّ يبقى مساراً ثانياً.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
_SCRIPT = ROOT / "scripts" / "ci" / "frontend_lint_debt_guard.py"


def _load():
    spec = importlib.util.spec_from_file_location("_frontend_lint_debt_guard", _SCRIPT)
    assert spec is not None and spec.loader is not None, f"تعذّر تحميل {_SCRIPT} — صحّح المسار"
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


MOD = _load()

ANY_RULE = "@typescript-eslint/no-explicit-any"
UNUSED_RULE = "@typescript-eslint/no-unused-vars"


def _report(counts: dict[str, int], *, path: str = "/repo/frontend/src/x.tsx") -> list:
    """تقرير `eslint -f json` مُركَّب بعددٍ مطلوب لكلّ قاعدة."""
    messages = []
    for rule, total in counts.items():
        messages.extend({"ruleId": rule, "line": index + 1} for index in range(total))
    return [{"filePath": path, "messages": messages}]


def _at_baseline() -> list:
    return _report(dict(MOD.BASELINE))


def test_the_measured_baseline_passes():
    """المرساة المقابلة: بلا هذا قد تمرّ كلّ التكذيبات لأنّ الحارس يرفض دائماً."""
    assert MOD.violations(_at_baseline()) == []


def test_the_repository_itself_sits_at_its_baseline():
    """**والأساس يُقاس على الشجرة الحقيقيّة لا على معطياتٍ مُركَّبة وحدها.**

    حارسٌ يعمل على نصوصٍ مُصطنَعة فقط يبقى أخضر بينما الواجهة انزلقت — وهو بعينه
    «أخضرُ لأنّه لا ينظر إلى ما وُجِد له». ويُتخطّى بصدق حين تغيب `node_modules`،
    لأنّ «لم يُقَس» يُقال ولا يُقرأ نجاحاً.
    """
    if not (ROOT / "frontend" / "node_modules" / ".bin" / "eslint").exists():
        pytest.skip("eslint غير مثبَّت — القياس الحيّ غير متاح، ولا يُدَّعى أنّه مرّ")
    assert MOD.main([]) == 0


def test_one_more_warning_is_blocked():
    """**البند الأوّل: الزيادة حاجزة — عند إدخالها لا بعد شهور.**"""
    counts = dict(MOD.BASELINE)
    counts[ANY_RULE] += 1
    problems = MOD.violations(_report(counts))
    assert problems, "زيادةٌ عن السقف مرّت — الراتشِت لا يحجب"
    assert any("دَينٌ جديد" in line for line in problems)


def test_paying_debt_without_lowering_the_ceiling_is_blocked():
    """**البند الثاني: النقصان مخالفةٌ كالزيادة — وهذا هو غير البديهيّ.**

    سقفٌ يبقى ٤٦ بعد سداد خمسة يبتلع **عودتها** صامتاً: تُصلَح خمس ثمّ تُضاف خمس
    فيبقى العدّاد ٤٦ والحارس أخضر. راتشِتٌ لا يُخفَّض ليس راتشِتاً بل سقفٌ مُرتخٍ.
    """
    counts = dict(MOD.BASELINE)
    counts[ANY_RULE] -= 5
    problems = MOD.violations(_report(counts))
    assert problems, "نقصانٌ بلا خفض السقف مرّ — السقف مُرتخٍ"
    assert any("اخفِض" in line for line in problems)


def test_a_rule_outside_the_baseline_is_blocked():
    """**البند الثالث: سقفٌ إجماليّ وحده يسمح باستبدال دَينٍ بأسوأ منه.**

    لو كان المفروض مجموعاً، لَمرّ تحويلُ عشرة `any` إلى عشرة `no-unsafe-assignment`
    بلا أثر. فالسقف **لكلّ قاعدة**، والقاعدة الجديدة تُحمِر حتى لو ثبت المجموع.
    """
    counts = dict(MOD.BASELINE)
    counts[ANY_RULE] -= 3
    counts["@typescript-eslint/no-unsafe-assignment"] = 3
    problems = MOD.violations(_report(counts))
    assert any("خارج الأساس" in line for line in problems), (
        "قاعدةٌ جديدة مرّت بمجموعٍ ثابت — الحارس يعدّ ولا يُصنّف"
    )


def test_the_failure_names_the_files_to_look_at():
    """رسالةٌ تقول «زاد العدد» تترك قارئها يبحث في ثلاثين ملفّاً.

    فالفشل يحمل أسماء الملفّات الحاملة للقاعدة — من يقرأ الأحمر يجب أن يعرف أين ينظر.
    """
    counts = {ANY_RULE: MOD.BASELINE[ANY_RULE] + 1, UNUSED_RULE: MOD.BASELINE[UNUSED_RULE]}
    problems = MOD.violations(_report(counts, path="/repo/frontend/src/sections/Dash.tsx"))
    assert any("src/sections/Dash.tsx" in line for line in problems)


def test_every_ceiling_carries_a_written_reason():
    """عددٌ بلا سببٍ يُنقَل بين الأجيال بلا معنى — «٤٦» لا تقول لماذا ولا متى تُسدَّد."""
    assert set(MOD.BASELINE) == set(MOD.WHY), "كلّ قاعدة في الأساس يلزمها سببٌ مكتوب في WHY، والعكس"
    for rule, reason in MOD.WHY.items():
        assert len(reason) > 40, f"{rule}: سببٌ أقصر من أن يكون سبباً"


def test_an_unreadable_report_fails_closed(tmp_path):
    """**«لم يُقَس» ليس «لم ينمُ».**

    تقريرٌ غائب أو غير قابل للتحليل يعني أنّ الدَّين **لم يُعَدّ** — وقبولُه يجعل
    الحارس أخضرَ بالضبط حين لا يُقاس شيء.
    """
    # الاسم ASCII عمداً: التأكيد عن **ملفّ غائب**، وخطوة ١٠ تُشغّل الجناح تحت
    # `LC_ALL=C PYTHONUTF8=0` فيصير ترميز نظام الملفّات ASCII — واسمٌ عربيّ يرفع
    # `UnicodeEncodeError` **قبل** أن يبلغ الحارس، فيسقط الاختبار على تجهيزته لا على
    # ما يقيسه. (المحتوى العربيّ أدناه سليم: `write_text` يُثبّت الترميز صراحةً.)
    # CI-GUARDS-CRASH-ON-NON-UTF8-CONSOLE-01
    with pytest.raises(SystemExit):
        MOD.main(["--report-file", str(tmp_path / "absent-report.json")])

    broken = tmp_path / "report.json"
    broken.write_text("{ليس JSON", encoding="utf-8")
    with pytest.raises(SystemExit):
        MOD.main(["--report-file", str(broken)])


def test_a_non_list_report_is_rejected(tmp_path):
    """`eslint -f json` يُعيد مصفوفةً؛ كائنُ خطأٍ في موضعها لا يُقرأ «صفر تحذير»."""
    path = tmp_path / "report.json"
    path.write_text(json.dumps({"error": "boom"}), encoding="utf-8")
    with pytest.raises(SystemExit):
        MOD.main(["--report-file", str(path)])


def test_the_honesty_limit_is_written_down():
    """حدُّ المدى مكتوبٌ في الحارس نفسه لا في مراجعةٍ تُنسى.

    من يقرأ خضرته يجب أن يعرف أنّها تعني «لم يتراكم»، لا «أُصلِح الدَّين».
    """
    body = _SCRIPT.read_text(encoding="utf-8")
    assert "لا يُصلحه" in body
    assert "تصميم أنواع" in body


def test_every_printed_failure_line_keeps_its_prefix(tmp_path, capsys):
    """**رسالةٌ متعدّدة الأسطر تفقد بادئتها في السطر الثاني — فيبدو تتمّةً غريبة.**

    الحالة تقع على المخالفة الوحيدة التي تحمل سطرَ ملفّات: طباعةُ النصّ كتلةً واحدة
    تُخرِج `الملفّات: …` بلا `✗` ولا إزاحة، فلا يعرف قارئ سجلّ CI أهو مخالفةٌ أخرى أم
    تتمّة — وتنكسر أيّ قراءةٍ سطريّة للسجلّ.

    فيُقاس **كلّ** سطرٍ مطبوع لا السطر الأوّل: إمّا `✗` وإمّا إزاحة التتمّة.
    """
    counts = dict(MOD.BASELINE)
    counts[ANY_RULE] += 1
    path = tmp_path / "report.json"
    path.write_text(json.dumps(_report(counts)), encoding="utf-8")

    assert MOD.main(["--report-file", str(path)]) == 1
    printed = capsys.readouterr().out.splitlines()

    body = [
        line
        for line in printed
        if line.strip() and not line.startswith("frontend_lint_debt_guard:") and "الدَّين" not in line
    ]
    assert body, "لا سطر مخالفةٍ مطبوع أصلاً"
    for line in body:
        assert line.startswith("  ✗ ") or line.startswith("      "), (
            f"سطرٌ بلا بادئة ولا إزاحة: {line!r} — التتمّة تُقرأ مخالفةً مستقلّة"
        )
    assert any("الملفّات:" in line for line in body), "سطر الملفّات ضاع من المخرَج"
