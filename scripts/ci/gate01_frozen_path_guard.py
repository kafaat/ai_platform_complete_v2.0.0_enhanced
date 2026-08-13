#!/usr/bin/env python3
"""حارس المسارات المجمَّدة خلف GATE-01 — يجعل حكم المالك تنفيذيّاً لا نثريّاً.

**العطل الذي وُجِد لأجله وقع مرّتين:** حكم المالك (`GATE-01-EXECUTION-CONTROL-SLICE-WITHHELD-01`،
2026-08-09) يمنع تعديل مسارات التنفيذ الفيزيائيّ قبل تجميد أدلّة المرحلة 0. وكان مفروضاً
بقراءة بشرٍ لملفٍّ نثريّ في `sahool-brain/` — فمُسّت المسارات في 2026-08-09 و2026-08-13،
وفي المرّتين نُفِّذت رقعةٌ كاملة ثمّ أُرجِعت بايتاً.

**ولماذا لا تكفي النيّة:** السجلّ نفسه يقول «التعديل يزيد الإيقاف» **ليس استثناءً؛ كلّ من
يُعدّل مساراً يظنّ تعديله تحسيناً». فالمنع يجب أن يقع **قبل** العمل لا بعده، وذلك لا يكون
بوثيقةٍ تُقرَأ بل ببوّابةٍ تُحمِرّ.

**وما لا يفعله — يُقال لأنّه يُسأل عنه:** لا يفتح البوّابة، ولا يُثبِّت أدلّة، ولا يحكم على
صحّة التعديل. خضرتُه تعني «لم يُمَسّ مسارٌ مجمَّد»، لا «التغيير سليم». والفتح يبقى بقرار
مالكٍ يضبط `frozen_commit_sha` ويُحوِّل `state` إلى `OPEN` في
`docs/architecture/gate01_frozen_paths.json`.

الاستعمال في CI:

    git diff --name-only origin/main...HEAD | python scripts/ci/gate01_frozen_path_guard.py --stdin
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
POLICY = ROOT / "docs" / "architecture" / "gate01_frozen_paths.json"
SCHEMA = "sahool.gate01_frozen_paths"


def violations(policy: dict, changed: list[str]) -> list[str]:
    """منطق نقيّ: أيّ مسارٍ مُغيَّر يقع تحت التجميد والبوّابة مغلقة؟

    البوّابة **مفتوحة فقط** بـ`state == "OPEN"`؛ وأيّ قيمةٍ أخرى (أو غيابها) تُعامَل
    إغلاقاً — fail-closed، لأنّ حقلاً مشوَّهاً ليس إذناً.
    """
    gate = policy.get("gate") or {}
    if str(gate.get("state", "")).strip().upper() == "OPEN":
        return []
    frozen = {str(p) for p in policy.get("frozen_paths") or []}
    gap = gate.get("gap_id", "GATE-01")
    hits = sorted(p for p in changed if p in frozen)
    return [
        f"مسارٌ مجمَّد خلف {gap} مُعدَّل: {p} — البوّابة مغلقة "
        f"(`phase_1_code_changes: {gate.get('phase_1_code_changes')}`). "
        "أرجِع الملفّ، أو افتح البوّابة بقرار مالكٍ صريح على SHA نهائيّ."
        for p in hits
    ]


def load_policy(path: Path) -> dict:
    """قراءةٌ fail-closed: ملفٌّ مفقود أو مخطَّطٌ مخالف ⇒ خروجٌ لا مرور.

    فسياسةٌ لا تُقرأ ليست «لا تجميد»؛ هي **تعذّر قياس**، ومعاملتُها مروراً تُلغي
    الحارس بحذف ملفٍّ واحد.
    """
    if not path.is_file():
        print(f"gate01_frozen_path_guard_failed: سياسة التجميد مفقودة: {path}")
        raise SystemExit(2)
    try:
        policy = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"gate01_frozen_path_guard_failed: تعذّر تحليل السياسة: {exc}")
        raise SystemExit(2) from exc
    if policy.get("schema") != SCHEMA:
        print(f"gate01_frozen_path_guard_failed: مخطَّطٌ غير متوقَّع: {policy.get('schema')!r}")
        raise SystemExit(2)
    if not policy.get("frozen_paths"):
        print("gate01_frozen_path_guard_failed: قائمة المسارات المجمَّدة فارغة — حارسٌ لا يقيس شيئاً")
        raise SystemExit(2)
    return policy


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="حارس المسارات المجمَّدة خلف GATE-01")
    parser.add_argument("--stdin", action="store_true", help="اقرأ المسارات المُغيَّرة من stdin")
    parser.add_argument("--policy", default=str(POLICY))
    args = parser.parse_args(argv)

    policy = load_policy(Path(args.policy))
    changed = (
        [line.strip() for line in sys.stdin.read().splitlines() if line.strip()]
        if args.stdin
        else []
    )

    problems = violations(policy, changed)
    if problems:
        print("gate01_frozen_path_guard_failed")
        print("\n".join(f"- {p}" for p in problems))
        return 1

    gate = policy["gate"]
    n = len(policy["frozen_paths"])
    state = gate.get("state")
    print(
        f"gate01_frozen_path_guard_ok (البوّابة: {state} · مسارات مجمَّدة: {n} · "
        f"مسارات مفحوصة: {len(changed)})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
