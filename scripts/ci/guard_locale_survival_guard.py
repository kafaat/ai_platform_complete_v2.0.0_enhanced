#!/usr/bin/env python3
"""حارسٌ يموت وهو يطبع نجاحه — GUARD-DIES-PRINTING-ITS-OWN-SUCCESS-UNDER-C-LOCALE-01.

**الانقلاب:** حارسٌ يحسب **صحيحاً** ثمّ ينهار وهو يطبع نتيجته، فيخرج بـ1 — أي يُبلِغ
حجباً على شجرةٍ سليمة، ورسالتُه traceback يسمّي الترميز لا الموضوع. وهو أسوأ من الصمت:
الصامت يُرى غيابُه، وهذا يُرى **ضدّ** ما قاس.

**ولماذا لم يكفِ الأساس الساكن القائم:** `text_encoding_locale_baseline.json` يقرأ
**الشيفرة** ويقول «هذا السطر قد ينهار»، وكان يُقرّ بحدّه صراحةً — «المُدرَج هنا لم
يُثبَت أنّه ينهار». وهذا يُشغّل **العمليّة** ويقول «هذا انهار». والفرق قِيس ولم يُقدَّر:
أوّل إشعالٍ لكلّ حارسٍ في ``scripts/ci`` تحت ``LC_ALL=C PYTHONUTF8=0`` أعطى **٣٥**
انهياراً في الكتابة و**٢٣** في القراءة — وكلّها كانت خضراء في CI، لأنّ عدّاء Linux
افتراضيّه UTF-8. فخضرة CI كانت شهادةً على لغة العدّاء لا على الحرّاس.

**وما يقيسه هذا بالضبط:** يُشعِل كلّ حارس عمليّةً فرعيّة تحت لغة C ويسأل سؤالاً واحداً:
هل مات **لسببٍ ترميزيّ**؟ لا يسأل عن رمز الخروج — حارسٌ يخرج بـ2 لأنّه يحتاج وسيطاً أو
قاعدةً ليس عطلاً في نطاق هذا الملفّ، وإدانتُه هنا كانت ستُنتِج أساساً مُبالِغاً يُدرَّب
قارئه على تجاهله. القياس سلوكيّ لا نصّيّ: لا يبحث عن ``reconfigure`` في المصدر — فوجودُ
السطر لا يعني أنّه يسبق أوّل طباعة، وغيابُه لا يعني عطلاً في حارسٍ لا يطبع إلّا ASCII.

**حدّ صدق مكتوب:** يُشغَّل كلّ حارس **بلا وسائط**. فالمسارات التي لا تُبلَغ إلّا خلف
راية (``--check`` · ``--fix``) غير مقيسة هنا، وقد تحمل الصنف نفسه. وما يُثبِته الأخضر:
«لا حارس ينهار ترميزيّاً على مساره الافتراضيّ تحت لغة C» — لا أكثر.

    python scripts/ci/guard_locale_survival_guard.py            # بوّابة
    python scripts/ci/guard_locale_survival_guard.py --list     # الجرد وحده
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

# GUARD-DIES-PRINTING-ITS-OWN-SUCCESS-UNDER-C-LOCALE-01: هذا الحارس أوّل من يخضع لقاعدته.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[2]
CI = ROOT / "scripts" / "ci"

# لغةُ الاختبار: ``LC_ALL=C`` وحدها لا تكفي — ``PYTHONUTF8`` قد تكون مضبوطة في البيئة
# فتُبطِل التجربة بصمت، و``PYTHONIOENCODING`` تفعل الشيء نفسه من الجهة الأخرى. فتُنزَع
# صراحةً: تجربةٌ يُبطِلها متغيّرٌ موروث تُبلِغ نجاحاً لم يقع.
C_LOCALE = {"LC_ALL": "C", "LANG": "C", "PYTHONUTF8": "0"}
STRIP = ("PYTHONIOENCODING",)

ENCODING_DEATHS = ("UnicodeEncodeError", "UnicodeDecodeError")


def guard_scripts(ci: Path = CI) -> list[Path]:
    """كلّ حارسٍ **عداه هو** — وإلّا أشعل نفسه فأشعلت نسختُه نفسها، بلا قاع.

    وقعت فعلاً في أوّل تشغيل: ثلاث دقائق لجولةٍ تستغرق دقيقة، والسبب تعشيشٌ لا بطء.
    وإعفاؤه من قاعدته ليس امتيازاً — قاعدتُه مفروضة عليه في ``tests_v9`` بمسبارٍ
    يُشعِله مباشرةً، فيبقى **مقيساً** بلا أن يُشعِل نفسه من داخل جولته.
    """
    return [p for p in sorted(ci.glob("*_guard.py")) if p.name != Path(__file__).name]


def c_locale_env() -> dict[str, str]:
    env = dict(os.environ)
    for key in STRIP:
        env.pop(key, None)
    env.update(C_LOCALE)
    return env


def encoding_death(output: str) -> str | None:
    """اسمُ الاستثناء الترميزيّ إن مات به، وإلّا ``None``.

    يُقرأ من المخرَج لا من رمز الخروج: الرمز يقول «فشل» ولا يقول **لماذا**، والفرق
    هو كلّ ما يفصل «حارسٌ وجد عطلاً» عن «حارسٌ عجز عن طباعة نتيجته».
    """
    for name in ENCODING_DEATHS:
        if name in output:
            return name
    return None


def probe(script: Path, env: dict[str, str], timeout: int = 120) -> str | None:
    """مخرَجُ الحارس مُشعَلاً تحت لغة C، أو ``None`` إن تجاوز المهلة.

    يُفكّ بـ``errors="replace"`` عمداً: الأب يقرأ بايتاتِ ابنٍ قد يكون كتب بترميزٍ
    مكسور، فانهيارُ الأب هنا كان سيُخفي نتيجة الابن — وهو المتّجه ② من الصنف نفسه.
    """
    try:
        proc = subprocess.run(
            [sys.executable, str(script)],
            capture_output=True,
            cwd=ROOT,
            env=env,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        # مهلةٌ ليست انهياراً ترميزيّاً — ولا تُدان هنا.
        return None
    return (proc.stdout + proc.stderr).decode("utf-8", "replace")


def unmeasured(output: str) -> bool:
    """مات قبل أوّل طباعة — فمرورُه **لم يُقَس**، ولا يُقرأ سلامةً.

    `ImportError` يقع قبل أيّ إخراج، فيعود المسبار فارغاً. ويقع فعلاً حين تُوضَع
    البوّابة في وظيفةٍ بلا تبعيّات الجناح — وهو الصنف الذي جعل `guard_mutation_guard
    --run` يُبلِغ مرّةً ثمانية عشر «إخفاقاً» صحيحاً بسببٍ خاطئ. فيُعَدّ ويُطبَع:
    خضرةٌ تُعلِن كم لم تقِس ليست خضرةً تُقرأ شهادةً.
    """
    return "ModuleNotFoundError" in output or "ImportError" in output


def sweep(scripts: list[Path], env: dict[str, str]) -> tuple[list[tuple[str, str]], list[str]]:
    """جولةٌ واحدة تُعيد (الموتى ترميزيّاً، من لم يُقَس). جولتان كانتا تُضاعِف الزمن."""
    deaths: list[tuple[str, str]] = []
    blind: list[str] = []
    for script in scripts:
        output = probe(script, env)
        if output is None:
            continue
        death = encoding_death(output)
        if death:
            deaths.append((script.name, death))
        elif unmeasured(output):
            blind.append(script.name)
    return deaths, blind


def evaluate(scripts: list[Path], env: dict[str, str]) -> list[tuple[str, str]]:
    """(اسم الحارس، الاستثناء) لكلّ من مات ترميزيّاً. الفارغة تعني مروراً."""
    return sweep(scripts, env)[0]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="إشعالُ كلّ حارسٍ تحت لغة C")
    parser.add_argument("--list", action="store_true", help="اطبع الجرد ولا تُشعِل")
    args = parser.parse_args(argv)

    scripts = guard_scripts()
    if args.list:
        for script in scripts:
            print(script.name)
        return 0

    deaths, blind = sweep(scripts, c_locale_env())
    if deaths:
        print("guard_locale_survival_guard_failed")
        for name, exc in deaths:
            print(f"- {name}: {exc} تحت LC_ALL=C — يحسب صحيحاً ثمّ يموت وهو يُبلِغ")
        print(
            "\nالعلاج عند التحميل لا داخل main(): بعض الحرّاس بلا main وتطبع من جسدها.\n"
            "    for _stream in (sys.stdout, sys.stderr):\n"
            '        if hasattr(_stream, "reconfigure"):\n'
            '            _stream.reconfigure(encoding="utf-8")\n'
            'وللقراءة: `encoding="utf-8"` على read_text/open و**على subprocess(text=True)**.'
        )
        return 1
    measured = len(scripts) - len(blind)
    print(f"guard_locale_survival_guard_ok ({measured}/{len(scripts)} حارساً قِيس تحت لغة C)")
    if blind:
        print(f"⊘ {len(blind)} لم يُقَس — مات باستيرادٍ ناقص قبل أوّل طباعة، فمرورُه ليس دليلاً:")
        for name in blind:
            print(f"  - {name}")
        print("  الأرجح وظيفةٌ بلا تبعيّات الجناح. ثبِّتها أو انقل البوّابة إلى وظيفةٍ تملكها.")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
