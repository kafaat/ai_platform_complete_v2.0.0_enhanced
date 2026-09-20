#!/usr/bin/env python3
"""`A-RATCHET-CLEARED-BY-DELETING-WHAT-IT-MEASURES-01` — علاجٌ يُنزِل العدّاد ويهدم الهدف.

**العطلُ ليس فرضيّاً: نصُّ الأساس نفسُه يدعو إليه.** `db_writer_ownership_baseline.json`
يقول عن مخالفاته: «الأساسُ راتشِتٌ ينزل ولا يصعد: يُخفَّض **بنقل الكتابة إلى مالكها أو
بتصحيح العقد** بأساسٍ مُعلَن». والعلاجُ الثاني بابٌ مفتوح: من أراد إنزالَ العدّاد بلا
نقلِ سطرٍ واحد، أضاف الخدمةَ المخالِفةَ إلى `writers` فصارت الكتابةُ «مأذوناً بها»
واختفت المخالفة.

**ولماذا هذا هدمٌ لا تصحيح — مقيسٌ لا مُفترَض:** كلُّ مخالفةٍ من الأربع والسبعين
مالكُها المُعلَن **هدفُ استخراجٍ حيّ** في `platform_extraction_map.json` (٧٤/٧٤).
فـ`field-management-service` يملك ٢١ منها وله ١٣٥ مساراً هدفاً في الخريطة. أي أنّ
العدّادَ لا يقيس «أخطاءً» بل **المسافةَ إلى البنية المقصودة**؛ و«تصحيحُ» العقد ليطابق
شيفرةَ اليوم يُنزِله إلى الصفر **بينما البنيةُ تنحدر** — ويمحو الهدفَ الذي كان يقيسه.

**والقاعدةُ المفروضة هنا واحدةٌ وضيّقة:** جدولٌ مالكُه هدفُ استخراجٍ حيّ لا يكتسب
كاتباً إضافيّاً مُعلَناً. لا يُمنَع تصحيحُ العقد مطلقاً — يُمنَع أن يقع **صامتاً**:
فإن تقاعد الهدفُ فعلاً، تُحدَّث الخريطةُ في التغيير نفسِه فيسقط الجدولُ من نطاق هذا
الحارس ويصير التصحيحُ مشروعاً. **القرارُ يبقى ممكناً، والصمتُ يصير مستحيلاً.**

**وأرضيّةُ صفرٍ لا راتشِت، والفرقُ مقيس:** الشجرةُ اليوم تحمل ٣٨٢ جدولاً في هذا
النطاق و**صفرَ** كاتبٍ إضافيّ. فالأرضيّةُ لا تُحمِّر على عملٍ قائم ولا تُطفأ — بخلاف
راتشِتٍ يبدأ بدَينٍ فيُدرَّب قارئُه على تجاوزه.

**وما لا يدّعيه هذا الحارس:** لا يحكم على المخالفات الأربع والسبعين ولا يُنقِصها —
إنقاصُها يحتاج **نقلَ الكتابة** أي الاستخراجَ نفسَه. وهو لا يمنع تقاعدَ هدفٍ، ولا
يقول إنّ العقدَ صحيح. يمنع طريقاً واحداً بعينه: أن يُقرأ العدّادُ منخفضاً وقد هُدِم
ما كان يقيسه.

    python scripts/ci/ownership_extraction_alignment_guard.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import yaml

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = ROOT / "docs" / "architecture" / "db_ownership.yml"
EXTRACTION_MAP = ROOT / "docs" / "architecture" / "platform_extraction_map.json"


def load_contract(path: Path | None = None) -> dict[str, Any]:
    """جداولُ العقد — ويفشل صراحةً على عقدٍ غيرِ مقروء.

    نفسُ حجّة `db_writer_ownership_guard.load_contract`: قراءةُ الجذر بدل `tables`
    تُنتِج صفرَ جداولٍ فيمرّ الحارسُ أخضرَ كاذباً. وحارسٌ يمرّ صفراً كاذباً أسوأُ من
    غيابه — يُقرَأ ضماناً ويُسجَّل تغطية.
    """
    raw = yaml.safe_load((path or CONTRACT).read_text(encoding="utf-8"))
    tables = raw.get("tables") if isinstance(raw, dict) and "tables" in raw else raw
    if not isinstance(tables, dict) or len(tables) < 100:
        raise SystemExit(
            f"OWNERSHIP_CONTRACT_UNREADABLE: {path or CONTRACT} أعطى "
            f"{len(tables) if isinstance(tables, dict) else 'لا شيء'} جدولاً — "
            "الحارسُ كان سيمرّ صفراً كاذباً، فيفشل صراحةً بدلاً من ذلك"
        )
    return tables


def live_targets(path: Path | None = None) -> set[str]:
    """أهدافُ الاستخراج الحيّة — كلُّ `target_owner` يحمل مساراً واحداً على الأقلّ.

    والفراغُ يفشل مُغلَقاً: خريطةٌ بلا أهدافٍ تجعل نطاقَ الحارس خالياً فيمرّ على كلّ
    شيء. وذاك أخطرُ من غيابه لأنّه يُبلِغ خُضرةً عن سؤالٍ لم يُطرَح.
    """
    raw = json.loads((path or EXTRACTION_MAP).read_text(encoding="utf-8"))
    routes = raw.get("routes") if isinstance(raw, dict) else None
    if not isinstance(routes, list) or not routes:
        raise SystemExit(
            f"EXTRACTION_MAP_UNREADABLE: {path or EXTRACTION_MAP} بلا مسارات — "
            "نطاقُ الحارس كان سيصير خالياً فيمرّ على كلّ شيء"
        )
    return {r.get("target_owner") for r in routes if isinstance(r, dict) and r.get("target_owner")}


def findings(contract: dict[str, Any], targets: set[str]) -> list[str]:
    """كاتبٌ إضافيٌّ مُعلَنٌ على جدولٍ مالكُه هدفُ استخراجٍ حيّ."""
    out: list[str] = []
    for table in sorted(contract):
        meta = contract[table]
        if not isinstance(meta, dict):
            continue
        owner = meta.get("owner")
        if owner not in targets:
            continue
        # الجسرُ الانتقاليُّ الموثَّق ليس انحرافاً — نفسُ الاستثناء الذي يحترمه
        # `db_writer_ownership_guard`. وخلطُ الاستثناء الموثَّق بالانحراف يُنذِر كذباً،
        # فيُدرَّب قارئُه على تجاهله، فيموت الحارسُ وهو أخضر.
        allowed = {owner, meta.get("mirror")} - {None}
        extra = sorted(set(meta.get("writers") or []) - allowed)
        if extra:
            out.append(
                f"{table}: `writers` اكتسب {extra} بينما المالكُ `{owner}` هدفُ استخراجٍ حيّ. "
                "هذا يُنزِل عدّادَ المخالفات بلا نقلِ سطرٍ واحد، ويمحو الهدفَ الذي كان "
                "العدّادُ يقيس المسافةَ إليه. انقل الكتابةَ إلى مالكها — أو أسقِط الهدفَ "
                "من `platform_extraction_map.json` في التغيير نفسِه إن تقاعد فعلاً."
            )
    return out


def main(argv: list[str] | None = None) -> int:
    contract = load_contract()
    targets = live_targets()
    in_scope = sum(
        1 for meta in contract.values() if isinstance(meta, dict) and meta.get("owner") in targets
    )
    problems = findings(contract, targets)
    if problems:
        print("ownership_extraction_alignment_guard: FAIL", file=sys.stderr)
        for line in problems:
            print(f"  ✗ {line}", file=sys.stderr)
        return 1
    print(
        f"ownership_extraction_alignment_guard_ok ({in_scope} جدولاً مالكُه هدفُ استخراجٍ حيّ · "
        "صفرُ كاتبٍ إضافيٍّ مُعلَن — أرضيّةُ صفرٍ لا راتشِت)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
