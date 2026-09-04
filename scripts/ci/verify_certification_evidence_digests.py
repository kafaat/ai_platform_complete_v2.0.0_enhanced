#!/usr/bin/env python3
"""يقارن بصمةَ كلّ ملفِّ دليلٍ **مجلوب** ببصمةٍ سجّلها مُنتِجُه على قناةٍ أخرى.

`DOWNLOADED-EVIDENCE-IS-TRUSTED-BY-ITS-OWN-STORE-01`.

## العطل

`actions/download-artifact` **لا يفشل مغلقاً** عند اختلاف البصمة: تحقّقُ GitHub
التلقائيّ يعرض **تحذيراً** في السجلّ ويمضي. فمصنوعةٌ استُبدِلت في المخزن تبلغ
المُحكِّمَ ويُحكَم عليها — والتحذيرُ سطرٌ لا يقرؤه أحد.

وذلك يُبطِل نصفَ ما بُني في `--purge`: مسحُ الاستنساخ يقول «لا يُعتَدّ إلّا بما
أنتجه هذا العدّاء»، والجلبُ بلا مقارنةٍ يقول «ما جاء من المخزن أنتجَه العدّاء» —
وهي ليست الحقيقةَ نفسَها.

## القناتان مختلفتان قصداً

البصمةُ تُنقَل في **مخرَجات الوظيفة** (`jobs.<id>.outputs`)، لا داخل المصنوعة.
فمخرَجاتُ الوظيفة جزءٌ من حالة تشغيل الـworkflow ولا تمرّ بمخزن المصنوعات؛
ومصنوعةٌ تُستبدَل هناك لا تحمل معها بصمتَها الجديدة إلى هنا. بصمةٌ **داخل**
المصنوعة كانت ستُستبدَل معها — أي شاهدٌ يشهد لنفسه.

**حدُّ صدقٍ مُعلَن:** هذا يقطع الاستبدالَ **بين الرفع والجلب**. ولا يُثبِت أنّ
المُنتِجَ صادقٌ فيما قاس — ذاك يقع على شرطِ بلوغ خطوة الانبعاث بعد خطوة القياس،
وعلى `production_evidence_pack_guard`. ولا يُثبِت منشأَ العدّاء نفسِه؛ ذاك
`actions/attest`.

## ويفشل مغلقاً في الاتّجاهين

* بصمةٌ مُعلَنةٌ وملفٌّ غائب ⇒ سقوط (رُفِع ثمّ ضاع).
* ملفٌّ حاضرٌ بلا بصمةٍ مُعلَنة ⇒ **سقوط** — وهذه هي حالةُ الاستبدال بعينها:
  ملفٌّ بلغ المُحكِّمَ ولم تُنتِجه وظيفة.
* اختلافُ البصمتين ⇒ سقوط.
* لا بصمةَ ولا ملفّ ⇒ يمرّ هنا، ويبقى الحاجبُ `pending` فيسقط الحكمُ لاحقاً.
  (الوظيفةُ الساقطة لا تُنتِج شيئاً — وذاك عجزٌ مُعلَنٌ لا تزييف.)

يعمل بلا pytest — نفس نمط `platform_route_placement_guard`.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import os
import sys
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE_DIR = ROOT / "certification" / "evidence"
_GUARD = ROOT / "scripts" / "ci" / "production_evidence_pack_guard.py"


#: البيئة التي تحمل بصمةَ كلّ حاجب. الاسمُ مُشتقٌّ من المعرّف لا مكتوبٌ جدولاً:
#: جدولٌ ثانٍ ينحرف عن `BLOCKERS` هو الصنفُ الذي أسقط `GUARDS` من التقييم.
def env_var_for(blocker_id: str) -> str:
    return "EVIDENCE_SHA256_" + blocker_id.replace("-", "_").upper()


def _blockers() -> list[dict]:
    spec = importlib.util.spec_from_file_location("_production_evidence_pack_guard", _GUARD)
    if not spec or not spec.loader:  # pragma: no cover - بيئةٌ مكسورة
        raise SystemExit("cannot load production_evidence_pack_guard")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return list(module.BLOCKERS)


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def check(evidence_dir: Path, env: dict[str, str] | None = None) -> int:
    source = os.environ if env is None else env
    problems: list[str] = []
    compared = 0
    for item in _blockers():
        blocker = item["id"]
        path = evidence_dir / item["required_file"]
        declared = str(source.get(env_var_for(blocker)) or "").strip().lower()

        if not declared and not path.exists():
            continue  # لا مُنتِج ولا ملفّ — الحاجبُ يبقى pending والحكمُ يسقط لاحقاً
        if declared and not path.exists():
            problems.append(f"{blocker}: مُنتِجُه سجّل بصمةً ولا ملفَّ دليلٍ مجلوب — رُفِع ثمّ ضاع في العبور")
            continue
        if not declared:
            problems.append(
                f"{blocker}: ملفُّ دليلٍ حاضرٌ **بلا بصمةٍ من مُنتِج** ({path.name}) — "
                "بلغ المُحكِّمَ ولم تُنتِجه وظيفةٌ في هذا العدّاء"
            )
            continue

        actual = sha256_of(path)
        compared += 1
        if actual != declared:
            problems.append(
                f"{blocker}: بصمةُ الملفّ المجلوب تخالف ما سجّله مُنتِجُه\n"
                f"      مُنتِج: {declared}\n"
                f"      مجلوب: {actual}"
            )

    if problems:
        print("certification evidence digest check: FAIL")
        for problem in problems:
            print(f"  ✗ {problem}")
        print(
            "\n`download-artifact` يعرض تحذيراً عند اختلاف البصمة ولا يفشل — فالمقارنةُ "
            "هنا هي الحاجب. والبصمةُ تُنقَل في مخرَجات الوظيفة لا داخل المصنوعة، "
            "فمصنوعةٌ استُبدِلت لا تحمل بصمتَها الجديدة معها."
        )
        return 1
    print(f"certification evidence digest check: PASS ({compared} بصمةً مُطابَقة)")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--evidence-dir", default=str(EVIDENCE_DIR))
    args = parser.parse_args(argv)
    return check(Path(args.evidence_dir))


if __name__ == "__main__":
    raise SystemExit(main())
