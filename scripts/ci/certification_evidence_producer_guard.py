#!/usr/bin/env python3
"""كلُّ حاجبِ اعتمادٍ له مُنتِجُ دليلٍ مُسمّى، أو غيابٌ **مُعلَنٌ بسببه**. لا صمت.

`CERTIFICATION-BLOCKER-WITHOUT-A-DECLARED-PRODUCER-01`.

## العطل

`production-certification-blockers.yml` حمل أربعَ وظائفَ اسمُها «دليل» ووظيفةَ حكمٍ
تعتمد عليها كلِّها — و**لا واحدةَ منها كتبت دليلاً**. المقيس: خمسةُ حواجزَ كلُّها
`pending`، و`--require-certified` يُخرِج `1`. فالحكمُ `false` كان يُقرأ «القياسُ لم
ينجح» بينما معناه «لا شيء يُنتِج ما يقرؤه المُحكِّم» — بوّابةٌ لا تُغلَق بعملٍ صحيح.

## ولمَ لا يكفي أن تبعث كلُّ وظيفةٍ دليلَها

لأنّ ثلاثاً من الأربع **تقيس شيئاً غير الحاجب المسمّى بها**، مقيسٌ في الشجرة:

* `P-CERT-1` «Full branch CI» ⇐ تُشغّل `runtime_real_smoke.sh` وحدَه.
* `P-CERT-3` «Redis live» ⇐ تحجب على سرٍّ **يتجاهله السكربت**، ويُثبِّت رابطَ حاوٍ
  محلّيّ في سطره الأخير.
* `P-CERT-4` «model provisioning» ⇐ تفحص اتّساقَ العقد، والمانيفست يقول
  `operator_must_provision=true` وافتراضُ compose هو `partial`/`false`.

فالانبعاثُ الآليّ من كلّ وظيفةٍ كان سيحوّل أداةَ الصدق إلى مصدرِ الكذبة. والعلاجُ
أن يصير **الغيابُ مُعلَناً** بدل أن يكون صمتاً: مَن أراد ختمَ حاجبٍ بلا مُنتِج
يصطدم بسطرٍ يقول لماذا لا يُختَم.

## ما يفرضه هذا الحارس

١. تغطيةٌ تامّة: كلُّ معرّفٍ في `production_evidence_pack_guard.BLOCKERS` مُعلَنٌ في
   العقد، ولا معرّفَ في العقد خارج تلك القائمة. (قائمتان تنحرفان هو الصنفُ الذي
   أسقط حاجبَ `GUARDS` من التقييم أصلاً.)
٢. `state: produced` ⇒ ملفُّ المُنتِج والباعث **موجودان**، والـworkflow المُعلَن
   يستدعي الباعثَ لهذا الحاجب بعينه. إعلانُ مُنتِجٍ محذوف تقلّصُ تغطيةٍ لا خطأُ مسار.
٣. `state: no_honest_producer` ⇒ سببٌ **غيرُ فارغ**، و**لا انبعاثَ** لذلك الحاجب في
   الـworkflow. هذا هو الحاجزُ الفعليّ: الإعلانُ لا يبقى نصّاً يُخالَف عملاً.

يعمل بلا pytest — نفس نمط `platform_route_placement_guard`.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = ROOT / "docs" / "architecture" / "certification_evidence_producers.json"
_GUARD = ROOT / "scripts" / "ci" / "production_evidence_pack_guard.py"
EMITTER = "scripts/ci/emit_certification_evidence.py"

_VALID_STATES = {"produced", "no_honest_producer"}


def _blocker_ids() -> list[str]:
    spec = importlib.util.spec_from_file_location("_production_evidence_pack_guard", _GUARD)
    if not spec or not spec.loader:  # pragma: no cover - بيئةٌ مكسورة
        raise SystemExit("cannot load production_evidence_pack_guard")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return [b["id"] for b in module.BLOCKERS]


# يتحمّل فواصلَ الأسطر بـ`\` وتعدّدَ المسافات ورايةً وسيطةً بين الاسم و`--blocker`.
_EMIT_CALL = re.compile(
    re.escape(EMITTER) + r"[\s\\]+(?:[^\n]*?[\s\\]+)??--blocker[\s\\]+([\w.-]+)"
)


def _emitted_blockers(path: Path) -> set[str]:
    """المعرّفاتُ التي **يُنادى** الباعثُ عليها فعلاً في هذا الملفّ.

    القراءةُ نصّيّة قصداً: البديلُ تحليلُ YAML ثمّ تفكيكُ سطور الصدفة داخل `run` —
    وهو تحليلُ صدفةٍ بلا مُحلِّلِ صدفة. والمطلوبُ سؤالٌ واحد: هل يُذكَر `--blocker X`
    بعد اسم الباعث؟

    **والملفُّ ليس الـworkflow وحدَه.** أوّلُ صيغةٍ من هذا الحارس فحصت الـworkflow
    فقط، فأسقطت `P-CERT-2` وهو صحيح: انبعاثُه داخل
    `compile_transitive_service_locks.sh` الذي تستدعيه الوظيفة. القاعدةُ الصحيحة أن
    يُبحَث في **المسار المُعلَن كلِّه** — الـworkflow والمُنتِج وما قيس بدلاً منه —
    لا في عقدةٍ واحدةٍ منه. (مقيسٌ: الحارسُ نفسُه كذّب صيغتَه الأولى.)
    """
    if not path.is_file():
        return set()
    return set(_EMIT_CALL.findall(path.read_text(encoding="utf-8")))


def _shown(path: Path) -> str:
    """مسارٌ للعرض لا يرمي.

    **الصنفُ الذي تكرّر أربع مرّاتٍ في هذه الجلسة:** `relative_to` يرمي على مسارٍ
    خارج الشجرة، فيقلب **رفضاً صحيحاً** إلى `ValueError` — عطلٌ في الزينة يستر حكماً
    سليماً. والتكذيبُ يستعمل مساراتٍ مؤقّتة، فهذا مسارٌ حقيقيٌّ لا حالةٌ نادرة.
    """
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def _declared_paths(entry: dict) -> list[Path]:
    """كلُّ ملفٍّ يذكره الإعلانُ مساراً — يُبحَث فيه عن الانبعاث."""
    candidates: list[str] = []
    for field in ("workflow", "producer"):
        value = entry.get(field)
        if isinstance(value, str) and value.strip():
            candidates.append(value.strip())
    measured = entry.get("measured_instead")
    if isinstance(measured, list):
        candidates += [str(m).strip() for m in measured if str(m).strip()]
    return [ROOT / c for c in candidates]


def _reason_text(value: object) -> str:
    if isinstance(value, list):
        return "\n".join(str(line) for line in value).strip()
    return str(value or "").strip()


def check() -> int:
    if not CONTRACT.is_file():
        print(f"certification evidence producer guard: FAIL\n  ✗ عقدٌ مفقود: {CONTRACT}")
        return 1
    try:
        contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"certification evidence producer guard: FAIL\n  ✗ عقدٌ غيرُ صالح: {exc}")
        return 1

    producers = contract.get("producers")
    if not isinstance(producers, dict):
        print("certification evidence producer guard: FAIL\n  ✗ العقد بلا خريطة 'producers'")
        return 1

    blockers = _blocker_ids()
    problems: list[str] = []

    missing = [b for b in blockers if b not in producers]
    extra = [b for b in producers if b not in blockers]
    problems += [f"{b}: حاجبٌ في BLOCKERS بلا إعلانٍ في العقد" for b in sorted(missing)]
    problems += [f"{b}: مُعلَنٌ في العقد وليس حاجباً في BLOCKERS" for b in sorted(extra)]

    # يُقرأ كلُّ workflow مرّةً واحدة: الملفّ نفسُه يخدم عدّة حواجز.
    emitted_cache: dict[Path, set[str]] = {}

    for blocker in blockers:
        entry = producers.get(blocker)
        if not isinstance(entry, dict):
            continue
        state = str(entry.get("state") or "")
        if state not in _VALID_STATES:
            problems.append(
                f"{blocker}: حالةٌ غيرُ معروفة {state!r} — المسموح: produced/no_honest_producer"
            )
            continue

        declared = _declared_paths(entry)
        emitted: set[str] = set()
        for path in declared:
            if path not in emitted_cache:
                emitted_cache[path] = _emitted_blockers(path)
            emitted |= emitted_cache[path]
        where = ", ".join(_shown(p) for p in declared) or "—"

        if state == "produced":
            for field in ("producer", "emitted_by", "workflow", "witness", "honesty_limit"):
                if not str(entry.get(field) or "").strip():
                    problems.append(f"{blocker}: 'produced' بلا حقل {field}")
            for field in ("producer", "emitted_by"):
                rel = str(entry.get(field) or "").strip()
                # سكربتٌ مُعلَنٌ محذوف **تقلّصُ تغطية** لا خطأُ مسار — يُسمّى باسمه،
                # نفس تمييز `require_file` في preflight.
                if rel and not (ROOT / rel).is_file():
                    problems.append(f"{blocker}: {field} مُعلَنٌ غيرُ موجود: {rel} — التغطية تقلّصت")
            if declared and blocker not in emitted:
                problems.append(
                    f"{blocker}: 'produced' ولا انبعاثَ له على المسار المُعلَن — "
                    f"لا ذكرَ لـ{EMITTER} --blocker {blocker} في: {where}"
                )
        else:
            if not _reason_text(entry.get("reason")):
                problems.append(
                    f"{blocker}: 'no_honest_producer' بلا سبب — الإعلانُ بلا سببٍ صمتٌ بصيغةٍ أخرى"
                )
            # **الحاجزُ الفعليّ.** بدونه يبقى الإعلانُ نصّاً يُخالِفه العمل.
            if blocker in emitted:
                problems.append(
                    f"{blocker}: مُعلَنٌ 'no_honest_producer' ومع ذلك يُبعَث في "
                    f"{where} — أصلِح الإعلان أو احذف الانبعاث"
                )

    if problems:
        print("certification evidence producer guard: FAIL")
        for problem in problems:
            print(f"  ✗ {problem}")
        print(
            "\nكلُّ حاجبٍ إمّا له مُنتِجٌ يقيسه، وإمّا غيابٌ مُعلَنٌ بسببه في "
            f"{_shown(CONTRACT)}. وختمُ حاجبٍ من وظيفةٍ تقيس غيرَه ادّعاءٌ لا دليل."
        )
        return 1

    produced = sum(1 for b in blockers if producers[b].get("state") == "produced")
    print(
        f"certification evidence producer guard: PASS "
        f"({produced}/{len(blockers)} حاجباً له مُنتِج؛ الباقي غيابٌ مُعلَنٌ بسببه)"
    )
    return 0


def main() -> int:
    argparse.ArgumentParser(description=__doc__.splitlines()[0]).parse_args()
    return check()


if __name__ == "__main__":
    raise SystemExit(main())
