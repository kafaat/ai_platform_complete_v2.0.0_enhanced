#!/usr/bin/env python3
"""مفتاحٌ مكرَّر في وثيقة JSON يُسقِط ما قبله **صامتاً**.

``MUT-REGISTRY-DUPLICATE-KEY-SHADOWS-A-BLOCK-01``. مقيسٌ على ``a1f5da7f``:
``docs/architecture/guard_mutation_registry.json`` حمل مفتاحين مكرّرين تحت
``behavioural`` — ``.github/workflows/ci.yml`` و``docs/architecture/rag_authority_convergence.json``.

و``json.load`` **آخِريُّ الترجيح**: يأخذ القيمة الأخيرة ويطرح ما قبلها بلا كلمة. فكتلةٌ
ثانية لملفٍّ له كتلةٌ أصلاً تُعطِّل **كلَّ** طفرات الأولى — لا رسالةَ، ولا رمزَ خروج،
ولا شيءَ يحمرّ. وهو صنف «حارسٌ كفّ عن الحجب بلا أن يحمرّ» واقعاً في السجلّ المبنيّ
لقياس ذلك الصنف بعينه.

الأثرُ المقيس في تلك الحادثة صفر — الكتلتان الأوليان متطابقتان بتّاً، والثانية من
الزوج الآخر مجموعةٌ فائقة لسابقتها. **والصنفُ هو العطل لا الحادثة:** أوّلُ كتلةٍ ثانية
*أصغر* من سابقتها تُسقِط الفرقَ صامتاً.

**لِمَ لا مسحٌ معجميّ للنصّ الخام.** التكرارُ يُكشَف هنا عند **المحلّل** عبر
``object_pairs_hook`` — وهي الواجهة التي تُسلِّم كلّ زوجٍ رآه المحلّل *قبل* أن ينهار
إلى ``dict``. أمّا مسحُ النصّ بتعبيرٍ نمطيّ فيرى `"a": 1` داخل **قيمةٍ نصّيّة** مفتاحاً،
فيُدين وثائقَ سليمة — وهو ``GUARD-PINS-IMPLEMENTATION-NOT-PROPERTY-01`` بعينه: يُثبِّت
شكلَ النصّ بدل الخاصّيّة المقصودة. والخاصّيّةُ هي «ما رآه المحلّل مرّتين»، والهُوك يقولها
بالضبط. المرفوضُ هو ``json.load`` **الافتراضيّ** الذي يطوي التكرار، لا وحدةُ ``json``.

**النطاق: كلُّ ملفّ ``.json`` متعقَّب، بلا قائمة استثناءات وبلا أساسٍ مُجمَّد** — وهذا
مقيسٌ لا مُفترَض: ٢٣٣ ملفّاً، صفرُ تكرار، صفرُ متعذّرِ القراءة. ومفتاحٌ مكرَّر ليس له
حالةُ استعمالٍ مشروعة في وثيقة سياسة، فالاستثناءُ هنا يكون ثقباً لا مرونة.

يفشل **مغلقاً**: ملفٌّ لا يُقرَأ أو لا يُحلَّل أو جردٌ فارغ = فشلٌ بسببٍ مسمًّى. و«لم
يُنظَر» يُفصَل عن «لم يُوجَد» صراحةً — حارسٌ مسح صفرَ ملفّاتٍ يقول نجاحاً بلا أن يقيس.

يعمل بلا pytest — نفس نمط ``platform_route_placement_guard``.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

# GUARD-DIES-PRINTING-ITS-OWN-SUCCESS-UNDER-C-LOCALE-01: مخرَجُ هذا الحارس عربيّ،
# و`print` يُرمّز بلغة الآلة. فتحت `LC_ALL=C` يحسب صحيحاً ثمّ يموت وهو يطبع نجاحه
# (UnicodeEncodeError) ⇒ خروجٌ بـ1 يُقرَأ «الحارس يحجب» وهو قد مرّ.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[2]


class DuplicateAwareDict(dict):
    """``dict`` يتذكّر ما رآه المحلّل مكرّراً قبل أن ينهار إلى قيمةٍ واحدة."""

    duplicates: dict[str, int]


def _pairs_hook(pairs: list[tuple[str, Any]]) -> DuplicateAwareDict:
    counts: dict[str, int] = {}
    for key, _ in pairs:
        counts[key] = counts.get(key, 0) + 1
    obj = DuplicateAwareDict(pairs)
    obj.duplicates = {k: n for k, n in counts.items() if n > 1}
    return obj


def _walk(node: Any, path: str, out: list[tuple[str, str, int]]) -> None:
    """يمشي البنيةَ كلَّها — التكرارُ العميق تكرارٌ أيضاً.

    الحادثةُ الأصليّة كانت تحت ``behavioural`` لا في الجذر، فحارسٌ يفحص المستوى
    الأعلى وحده كان سيمرّ عليها.
    """
    if isinstance(node, DuplicateAwareDict):
        for key, count in sorted(node.duplicates.items()):
            out.append((path, key, count))
    if isinstance(node, dict):
        for key, value in node.items():
            _walk(value, f"{path}.{key}", out)
    elif isinstance(node, list):
        for index, value in enumerate(node):
            _walk(value, f"{path}[{index}]", out)


def duplicate_keys(text: str) -> list[tuple[str, str, int]]:
    """المسارُ والمفتاحُ وعددُ مرّاته — لكلّ تكرارٍ رآه المحلّل، على أيّ عمق."""
    found: list[tuple[str, str, int]] = []
    _walk(json.loads(text, object_pairs_hook=_pairs_hook), "$", found)
    return found


def tracked_json_files(root: Path = ROOT) -> list[Path]:
    """جردُ الملفّات من git — لا قائمةَ ثانية تبيت بصمت."""
    result = subprocess.run(
        ["git", "ls-files", "*.json"],
        cwd=root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
    )
    if result.returncode != 0:
        raise RuntimeError(f"git ls-files فشل: {result.stderr.strip()}")
    return [root / line for line in result.stdout.split("\n") if line.strip()]


def findings(root: Path = ROOT) -> tuple[list[str], int]:
    """يُعيد (الإخفاقات، عددَ ما مُسِح). العددُ يفصل «لم يُنظَر» عن «لم يُوجَد»."""
    problems: list[str] = []
    try:
        files = tracked_json_files(root)
    except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
        return [f"تعذّر جردُ ملفّات JSON: {exc}"], 0

    scanned = 0
    for path in sorted(files):
        try:
            text = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            # ملفٌّ متعقَّبٌ غيرُ موجودٍ على القرص حالةٌ شاذّة لا تُبتلَع.
            problems.append(f"{path.relative_to(root)}: متعقَّبٌ ولا يُقرَأ من القرص")
            continue
        except (OSError, UnicodeDecodeError) as exc:
            problems.append(f"{path.relative_to(root)}: تعذّرت القراءة — {exc}")
            continue
        scanned += 1
        try:
            duplicates = duplicate_keys(text)
        except ValueError as exc:
            problems.append(f"{path.relative_to(root)}: JSON غير صالح — {exc}")
            continue
        for location, key, count in duplicates:
            problems.append(
                f"{path.relative_to(root)}: مفتاحٌ مكرَّر {key!r} ×{count} عند {location} "
                "— القيمةُ الأخيرة تُسقِط ما قبلها صامتاً"
            )
    if not problems and scanned == 0:
        problems.append("لم يُمسَح أيُّ ملفّ JSON — «لم يُنظَر» ليس «سليم»")
    return problems, scanned


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=str(ROOT))
    args = parser.parse_args(argv)

    problems, scanned = findings(Path(args.root))
    if problems:
        for problem in problems:
            print("json_duplicate_key_fail", problem)
        return 1
    print(f"json_duplicate_key_guard_ok ({scanned} ملفّاً · لا مفتاحَ مكرَّراً على أيّ عمق)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
