#!/usr/bin/env python3
"""يمنع تسرّب التأجيلات من `hot.md` دون تسجيلها في `gaps/registry.md`.

قاعدة CLAUDE.md صريحة: «لا فجوة بلا مصدر + حالة». لكنّها كانت **عُرفاً لا إنفاذاً**:
`hot.md` يمتصّ التأجيلات، ولا شيء يجبرها على الهجرة إلى السجلّ. الحارس القائم
`tests/architecture/test_brain_state_consistency.py` يفرض الادّعاءات **العدديّة** فقط،
فالتسرّب كان مسموحاً تصميميّاً.

الدليل الذي أوجب هذا الحارس (`BRAIN-DEFERRAL-LEAK-01`): ثلاثة مفاهيم أُجِّلت في `hot.md`
ولم تصل السجلّ، اثنان بقيا يتيمَين شهوراً — «blank-thumbnail بند مستقل» (#660) وقرار
إبقاء `-m unit` نقيّة (#590) الذي **سقط مبرّره** دون أن يوقظه شيء.

القاعدة المفروضة: كلّ سطر في `hot.md` يحمل نمط تأجيل يجب أن يحمل معرّف فجوة **موجوداً
فعلاً** كعنوان `## ` في `gaps/registry.md`. الأسطر القائمة قبل الحارس مُجمَّدة في أساس
(baseline) **يتقلّص ولا ينمو**: تأجيل جديد بلا معرّف يُسقِط CI.

يعمل بلا pytest كي يصلح لوظيفة CI عديمة التبعيّات (نفس نمط `platform_route_placement_guard`).
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HOT = ROOT / "sahool-brain" / "hot.md"
REGISTRY = ROOT / "sahool-brain" / "gaps" / "registry.md"
BASELINE = ROOT / "docs" / "architecture" / "brain_deferral_baseline.json"

# أنماط تأجيل: عبارات تُرحّل عملاً إلى المستقبل. مقصودة ضيّقة — كلّ نمط يُنشئ التزاماً.
_DEFERRAL = re.compile(
    r"بند\s+مستقل|بند\s+مستقلّ|خارج\s+النطاق|مؤجَّل|مؤجّل|يُؤجَّل|لاحقاً،\s*لا\s*الآن|"
    r"شريحة\s+منفصلة|لم\s+يُصلَح|deferred|out\s+of\s+scope"
)
# معرّف فجوة: رمز كبير بشرطات، ثلاثة أجزاء فأكثر — يستبعد كلمات عاديّة ومختصرات قصيرة.
_GAP_ID = re.compile(r"\b[A-Z][A-Z0-9]*(?:-[A-Z0-9]+){2,}\b")


def registry_ids() -> set[str]:
    """المعرّفات المُعلَنة كعناوين أقسام — لا أيّ ذكر عابر في النثر."""
    ids: set[str] = set()
    for line in REGISTRY.read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            ids.update(_GAP_ID.findall(line))
    return ids


def load_baseline() -> set[str]:
    if not BASELINE.exists():
        return set()
    return set(json.loads(BASELINE.read_text(encoding="utf-8"))["exempt_lines"])


def violations(baseline: set[str] | None = None) -> list[str]:
    """أسطر تأجيل بلا معرّف مسجَّل، خارج الأساس المُجمَّد."""
    known = registry_ids()
    exempt = load_baseline() if baseline is None else baseline
    out: list[str] = []
    for lineno, raw in enumerate(HOT.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or not _DEFERRAL.search(line):
            continue
        if any(gid in known for gid in _GAP_ID.findall(line)):
            continue  # مؤجَّل ومسجَّل — سليم
        if line in exempt:
            continue  # قائم قبل الحارس
        out.append(f"sahool-brain/hot.md:{lineno}: تأجيل بلا معرّف مسجَّل — {line[:90]}")
    return out


def write_baseline() -> int:
    """يُجمّد الأسطر القائمة. يُستدعى مرّة عند إدخال الحارس، ثمّ يُقلَّص يدويّاً."""
    known = registry_ids()
    exempt = [
        line.strip()
        for line in HOT.read_text(encoding="utf-8").splitlines()
        if line.strip()
        and _DEFERRAL.search(line)
        and not any(g in known for g in _GAP_ID.findall(line))
    ]
    BASELINE.parent.mkdir(parents=True, exist_ok=True)
    BASELINE.write_text(
        json.dumps(
            {
                "$comment": (
                    "أساس مُجمَّد لـbrain_deferral_registry_guard: أسطر تأجيل في hot.md سبقت "
                    "الحارس. القائمة تتقلّص ولا تنمو — كلّ سطر يُحذف منها عند تسجيل فجوته."
                ),
                "gap": "BRAIN-DEFERRAL-LEAK-01",
                "exempt_lines": sorted(set(exempt)),
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"brain deferral baseline written: {len(set(exempt))} سطراً مُجمَّداً")
    return 0


def check() -> int:
    found = violations()
    if found:
        print("brain deferral registry guard: FAIL")
        for v in found:
            print(f"  ✗ {v}")
        print(
            "\nكلّ تأجيل في hot.md يحتاج معرّف فجوة مُعلَناً كعنوان '## ' في "
            "sahool-brain/gaps/registry.md — قاعدة CLAUDE.md «لا فجوة بلا مصدر + حالة»."
        )
        return 1
    exempt = len(load_baseline())
    print(f"brain deferral registry guard: PASS ({exempt} سطراً في الأساس المُجمَّد)")
    if exempt:
        print(f"  {exempt} تأجيل قديم بلا معرّف — الأساس يتقلّص ولا ينمو")
    return 0


def main() -> int:
    if "--write-baseline" in sys.argv:
        return write_baseline()
    return check()


if __name__ == "__main__":
    raise SystemExit(main())
