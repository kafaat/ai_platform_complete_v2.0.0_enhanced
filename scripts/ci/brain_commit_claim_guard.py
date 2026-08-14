#!/usr/bin/env python3
"""يمنع رسالة التزام من ادّعاء تسجيل فجوة لم تُسجَّل.

`BRAIN-CLAIM-UNVERIFIED-01`. المستودع يفرض تطابق الأرقام وموضع المسارات واستهلاك النوى،
لكنّ **رسالة الالتزام نفسها** كانت خارج كلّ إنفاذ: يكفي أن تقول «سُجِّلت الفجوات» لتُقرأ
كأنّها سُجِّلت.

الدليل الذي أوجب هذا الحارس: رسالة #683 أعلنت تسجيل أربع فجوات؛ اثنتان فقط وصلتا الشجرة،
وإحدى الغائبتين كانت **حاجب** الشرائح الباقية. السبب الميكانيكيّ أنّ سكربت إعادة البناء
طبع `-1` (لم يُعثَر على القسم) ومُضِيَ فوقه.

القاعدة: كلّ معرّف فجوة يُذكَر في رسالة التزام داخل نطاق الـPR يجب أن يوجد **عنوان قسم
`## `** يحمله في `sahool-brain/gaps/registry.md`. ذكر معرّف = ادّعاء وجوده.

يعمل بلا pytest — نفس نمط `platform_route_placement_guard`.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

# GUARD-DIES-PRINTING-ITS-OWN-SUCCESS-UNDER-C-LOCALE-01: كان يموت في القراءة، فلمّا
# ثُبِّتت ظهر أنّه يموت في الكتابة — عطلان في ملفٍّ واحد، والثاني كان مستوراً بالأوّل.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "sahool-brain" / "gaps" / "registry.md"
ADJUDICATIONS = ROOT / "docs" / "architecture" / "gates" / "adjudications"

# معرّف فجوة: ثلاثة مقاطع كبيرة فأكثر بشرطات. يستبعد المختصرات القصيرة (WX-10) وأسماء
# الملفّات والثوابت العاديّة.
# الحدّ ليس `\b`: معرّف ملتصق بنصّ عربيّ (`لـAUTH-E2E-…`) لا حدّ كلمة قبله لأنّ الحرف
# العربيّ حرف كلمة، فيبدأ التطابق بعد أوّل شرطة ⇒ **معرّف وهميّ** (`E2E-UNDER-…`) يُطالَب
# بتسجيله، و**المعرّف الحقيقيّ يفوت** في آنٍ واحد. الحدّ الصحيح: ما يسبق/يلحق ليس شرطة
# ولا حرف ASCII — فتُقبل العربيّة حدّاً وتُرفض الشرطة. التقطه الحارس على رسالة التزام
# تذكر `لـAUTH-E2E-UNDER-RESTRICTED-ROLE`.
_GAP_ID = re.compile(r"(?<![-A-Za-z0-9_])[A-Z][A-Z0-9]*(?:-[A-Z0-9]+){2,}(?![-A-Za-z0-9_])")

# رموز كبيرة شائعة ليست معرّفات فجوات — تُستبعد صراحةً بدل توسيع النمط وإضعافه.
_NOT_GAP_IDS = {
    "SAHOOL-ALLOW-RLS-BYPASS-ROLE",
    "NOSUPERUSER-NOBYPASSRLS",
    "CO-AUTHORED-BY",
}

# معرّفات استشارات أمنيّة (CVE-…/GHSA-…/PYSEC-…/OSV-…). تُطابِق نمط المعرّف شكلاً
# — ثلاثة مقاطع كبيرة بشرطات — لكنّها **صنف مختلف**: تُصدرها جهة خارجيّة ولا تُسجَّل
# قطّ كأقسام في `gaps/registry.md`. استبعادها بالبادئة لا بالحالة الواحدة، لأنّ
# البديل أن يُسقِط الحارس كلّ التزام يذكر ثغرة باسمها — وهو ما يدفع نحو **كتمان**
# رقم الاستشارة في رسالة الالتزام، أي عكس ما بُني الحارس له.
# الدليل: رسالة `UNIT-TEST-DORMANCY-01` تذكر `PYSEC-2026-1325` توثيقاً لنتيجة
# pip-audit قبل/بعد ⇒ أسقطها الحارس. ما يبقى مرفوضاً: أيّ معرّف خارج هذه الأشكال.
#
# الاستثناء على **الشكل الكامل** لا على البادئة وحدها: `startswith("CVE-")` كان
# سيبتلع معرّف فجوة اسمه `CVE-LIKE-BUT-NOT` — التقطه اختبار التكذيب قبل الدفع.
# البادئة تُتبَع بمقاطع رقميّة/محدَّدة الطول، وهو ما يميّز الاستشارة عن أيّ معرّف
# داخليّ قد نختاره.
_ADVISORY = re.compile(
    r"^(?:(?:CVE|PYSEC|OSV)-[0-9]{4}-[0-9]+|GHSA-[A-Za-z0-9]{4}-[A-Za-z0-9]{4}-[A-Za-z0-9]{4})$"
)


def is_advisory(gid: str) -> bool:
    """معرّف استشارة أمنيّة خارجيّ — لا يُسجَّل في السجلّ ولا يُطالَب به."""
    return bool(_ADVISORY.match(gid))


# معرّف تفويض GATE — صنفٌ ثالث: ليس فجوةً ولا استشارةً خارجيّة، بل **مصنوعٌ في هذه
# الشجرة** تحت `docs/architecture/gates/adjudications/`. يُطابِق شكل معرّف الفجوة
# (مقاطع كبيرة بشرطات) فكان يُطالَب بقسمٍ في سجلّ الفجوات — وتسجيلُه هناك **كذب**:
# التفويض إذنُ مالكٍ لا عطلٌ مرصود، وحالته `ISSUED`/`CONSUMED` لا `open`/`fixed`.
#
# **ولا يُستثنى كالاستشارة، بل يُتحقَّق منه في سجلّه:** مبدأ الحارس أنّ الذكر ادّعاء —
# والاستشارة تُستثنى اضطراراً لأنّ مصدرها خارج الشجرة، أمّا التفويض فمِلفٌّ هنا، فيُقاس
# وجوده. هذا **أقوى** من الاستثناء: معرّف تفويضٍ ملفَّق يبقى ساقطاً.
#
# الدليل: التزام ختمِ `GATE01-ADJ-2026-08-13-001` بـ`CONSUMED` أسقطه الحارس مطالباً
# بتسجيله فجوةً. والبديل — حذفُ المعرّف من الرسالة — يُخفي **أيّ تفويضٍ خُتِم**، أي
# يدفع نحو الكتمان كما كان سيفعل مع أرقام الاستشارات.
_ADJUDICATION = re.compile(r"^GATE[0-9]{2}-ADJ-[0-9]{4}-[0-9]{2}-[0-9]{2}-[0-9]{3}$")


def is_adjudication(gid: str) -> bool:
    """معرّف تفويض بوّابة — يُتحقَّق منه في مجلَّد التفويضات لا في سجلّ الفجوات."""
    return bool(_ADJUDICATION.match(gid))


def adjudication_exists(gid: str, directory: Path = ADJUDICATIONS) -> bool:
    return (directory / f"{gid}.json").is_file()


def registry_ids() -> set[str]:
    """المعرّفات المُعلَنة رسميّاً — عنواناً أو **عمود معرّف في الجدول**.

    السجلّ يستعمل شكلين للتسجيل: قسم `## ` وصفّ جدول يبدأ عموده الأوّل بالمعرّف. قصر
    الفحص على العناوين وحدها أنتج **إيجابيّة كاذبة**: ٢٢ فجوة مسجَّلة كصفوف تُعامَل كغير
    مسجَّلة، فتسقط أيّ PR تذكرها برسالة تطالب بتسجيل ما هو مسجَّل سلفاً. مُثبَت على تاريخ
    مدموج (`37c3b56` يذكر `CAP-INT-004-INTEGRATION`).

    ما يبقى مرفوضاً: الذكر العابر في النثر — لأنّه لا يُنشئ مدخلاً ولا حالة.
    """
    ids: set[str] = set()
    for line in REGISTRY.read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            ids.update(_GAP_ID.findall(line))
        elif line.startswith("|"):
            # عمود المعرّف الأوّل فقط — لا بقيّة خلايا الصفّ (وصف/مصدر/حالة).
            first_cell = line.split("|")[1] if line.count("|") >= 2 else ""
            ids.update(_GAP_ID.findall(first_cell))
    return ids


def commit_messages(base: str, head: str) -> list[tuple[str, str]]:
    out = subprocess.run(
        ["git", "log", "--format=%H%x00%B%x1e", f"{base}..{head}"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        # المتّجه ② من `TEXT-DECODED-WITH-THE-MACHINES-LOCALE-01`: `text=True` وحدها
        # تفكّ بترميز **اللغة**، ورسائل الالتزام هنا عربيّة — فتحت `LC_ALL=C` ينهار
        # الأب قبل أن يقرأ ادّعاءً واحداً. وهذا آخر ما بقي من الصنف في `scripts/ci/`
        # بعد مسحٍ أشعل الحرّاس الـ١٤٦ عمليّاتٍ فرعيّة تحت تلك اللغة.
        encoding="utf-8",
        check=True,
    ).stdout
    result: list[tuple[str, str]] = []
    for record in out.split("\x1e"):
        if "\x00" not in record:
            continue
        sha, body = record.split("\x00", 1)
        result.append((sha.strip()[:7], body))
    return result


def check(base: str, head: str) -> int:
    known = registry_ids()
    violations: list[str] = []
    adjudication_violations: list[str] = []
    claimed = 0
    for sha, body in commit_messages(base, head):
        for gid in sorted(set(_GAP_ID.findall(body))):
            if gid in _NOT_GAP_IDS or is_advisory(gid):
                continue
            claimed += 1
            if is_adjudication(gid):
                if not adjudication_exists(gid):
                    adjudication_violations.append(
                        f"{sha}: يذكر {gid} — لا ملفّ "
                        f"docs/architecture/gates/adjudications/{gid}.json"
                    )
                continue
            if gid not in known:
                violations.append(f"{sha}: يذكر {gid} — لا قسم '## {gid}' ولا صفّ جدول يبدأ به")
    if violations or adjudication_violations:
        print("brain commit claim guard: FAIL")
        for v in sorted(set(violations + adjudication_violations)):
            print(f"  ✗ {v}")
        if violations:
            print(
                "\nذكر معرّف فجوة في رسالة التزام ادّعاءُ وجودها. سجّلها في "
                "sahool-brain/gaps/registry.md **بأحد الشكلين المقبولين** — قسم '## المعرّف' "
                "أو صفّ جدول يبدأ عموده الأوّل بالمعرّف — بمصدرها وحالتها، أو احذف الذكر."
            )
        if adjudication_violations:
            print(
                "\nوذكر معرّف تفويض ادّعاءُ صدوره. التفويض مصنوعٌ في هذه الشجرة — أضِف "
                "ملفّه في docs/architecture/gates/adjudications/ أو احذف الذكر. "
                "ولا يُسجَّل في سجلّ الفجوات: إذنُ مالكٍ لا عطلٌ مرصود."
            )
        return 1
    print(f"brain commit claim guard: PASS ({claimed} ادّعاء معرّف مُتحقَّق منه)")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="origin/main")
    parser.add_argument("--head", default="HEAD")
    args = parser.parse_args()
    return check(args.base, args.head)


if __name__ == "__main__":
    raise SystemExit(main())
