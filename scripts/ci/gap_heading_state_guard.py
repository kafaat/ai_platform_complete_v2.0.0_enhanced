#!/usr/bin/env python3
"""راتشِتُ العناوين اليتيمة — `GAP-HEADING-WITHOUT-A-STATE-RECORD-IS-INVISIBLE-01`.

**العطلُ مقيسٌ على مصنوعَتَي تشغيلٍ حقيقيَّتين، لا مفترَض.** أُضيفت فجوةٌ جديدة بعنوان
``## <معرِّف> — مفتوحة (P2 حوكمة، 2026-09-19)`` — والحالةُ **عربيّةٌ في العنوان**. و
``gap_registry_measure`` لا يقرأ الحالةَ إلّا من سطر ``- **الحالة:**`` أو
``- **status:**``، و``classify()`` لا يقبل إلّا ``open``/``fixed``/``verified``. فكانت
النتيجةُ على الأساسَين:

====================  ==========  ==========
المقيس                 #1033       #1035
====================  ==========  ==========
heading_count          263         **264**
section_state_count    42          42
unclassified_*         []          []
====================  ==========  ==========

أي أنّ الفجوةَ لم تظهر ``open`` ولا حتّى ``unclassified`` — **اختفت من كلّ عدٍّ يُقرأ،
ووظيفةُ القياس خضراء**. كشفه المالكُ بمقارنة المصنوعتين مباشرةً.

**والسببُ بنيويٌّ لا إملائيّ:** حقولُ ``unclassified_*`` تصف ما **رآه** القارئُ ولم
يفهمه. وما لم يُرَ أصلاً لا يقع في أيٍّ منها — فكلُّ حقول الشذوذ القائمة كانت عمياءَ
عنه **بالتصميم**، لا بإغفال. وهذا الصنفُ مُسجَّلٌ في هذا المستودع بصيغته الأخرى:
«الغيابُ يُقرأ قياساً».

**ولماذا راتشِتٌ لا صفرٌ مفروض:** المقيسُ **٢١١ من ٢٦٤**. أكثرُ عناوين السجلّ سردٌ
تاريخيٌّ لا مدخلُ حالة، فحقلٌ يُحمِّر على الكلّ يُطفَأ في أوّل أسبوع — وحمايةٌ تُوقِف
العملَ كلَّه تُطفَأ فتُنتِج حمايةً صفراً. فالمنعُ منعُ **النموّ**، والخفضُ يقع بإضافة
سطر حالةٍ قانونيٍّ تحت العنوان أو بتصحيح عنوانٍ ليس فجوةً أصلاً.

**وحدُّ صدقٍ مكتوب:** هذا يقيس **الرؤية** لا الصحّة. مدخلةٌ مرئيّةٌ بحالةٍ خاطئة تمرّ
من هنا — ويُمسِكها ``unclassified_section_states`` أو ``contradictory_sections``.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "sahool-brain" / "gaps" / "registry.md"
BASELINE = ROOT / "docs" / "architecture" / "gap_heading_state_baseline.json"


def _measure_module():
    spec = importlib.util.spec_from_file_location(
        "gap_registry_measure", ROOT / "scripts" / "ci" / "gap_registry_measure.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["gap_registry_measure"] = module
    spec.loader.exec_module(module)
    return module


def evaluate(measured: int, baseline: int, orphans: list[dict]) -> list[str]:
    """أسبابُ الحجب. الفارغةُ تعني أنّ الأساس لم ينمُ."""
    if measured <= baseline:
        return []
    added = measured - baseline
    names = ", ".join(sorted({item["id"] for item in orphans})[:5])
    return [
        f"عناوينُ فجواتٍ بلا سجلِّ حالة: {measured} > الأساس {baseline} (+{added}). "
        "عنوانٌ بلا سطر حالةٍ قانونيّ **لا يظهر في أيّ عدٍّ يُقرأ** — لا `open` ولا "
        "`unclassified` — والقياسُ يبقى أخضر. أضِف تحته "
        "`- **الحالة:** open — …` (`open`/`fixed`/`verified` حصراً؛ «مفتوحة» في "
        f"العنوان لا تُقرأ). من اليتامى: {names}."
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="راتشِتُ العناوين اليتيمة في سجلّ الفجوات")
    parser.add_argument("--registry", default=str(REGISTRY))
    parser.add_argument("--baseline", default=str(BASELINE))
    args = parser.parse_args(argv)

    module = _measure_module()
    report = module.measure(Path(args.registry).read_text(encoding="utf-8"))
    # أساسٌ مفقودٌ أو لا يُحلَّل ليس «صفرَ ديْن» — الاستثناءُ يفشل مغلقاً.
    baseline = json.loads(Path(args.baseline).read_text(encoding="utf-8"))["baseline"]

    measured = report["orphan_gap_heading_count"]
    errors = evaluate(measured, baseline, report["orphan_gap_headings"])
    if errors:
        print("gap_heading_state_guard_failed")
        for line in errors:
            print(f"- {line}")
        return 1
    # الخضرةُ تُصرِّح بما قِيس: خضرةٌ بلا عدٍّ لا يفرّق قارئُها بين «قِيس فمرّ» و«لم يُقَس».
    print(
        f"gap_heading_state_guard_ok ({measured} يتيماً من {report['heading_count']} عنوان، "
        f"الأساس {baseline} — راتشِتٌ ينزل ولا يصعد)"
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
