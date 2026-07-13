#!/usr/bin/env python3
"""حارس CI: يضمن أنّ جسر MPC ينشر النَّسَب الكامل ويبقى توصية-فقط (لا تنفيذ تلقائيّ).

المرشّح المُصدَر من `lexicographic_mpc_bridge.build_mpc_candidate` هو نقطة الاتّصال بين
الحلّال وسلسلة القرار المحكومة. لكي يُتتبَّع القرار end-to-end (review→execution→outcome→
learning) يجب أن يحمل المرشّح صراحةً:
  - decision_type == "irrigation_mpc"  (نوع مميَّز لا يختلط بمسار عجز الماء)
  - content_digest / idempotency_key / solver_version / candidate_lineage_id  (النَّسَب)
ويجب أن يبقى **توصية-فقط** بنيويّاً: لا يستدعي الجسر مسار تنفيذ (authorize/execution-request/
MQTT) ولا يُصدِر execution_allowed=True.

حارس ساكن (نصّيّ) — لا يستورد الوحدة (تجنّب اعتماديّات وقت التشغيل في CI).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BRIDGE = ROOT / "services/sahool-platform/api/lexicographic_mpc_bridge.py"

# الحقول التي يجب أن يحملها المرشّح صراحةً (انتشار النَّسَب في السلسلة).
_REQUIRED_KEYS = (
    '"decision_type"',
    '"content_digest"',
    '"idempotency_key"',
    '"solver_version"',
    '"candidate_lineage_id"',
)

# دوالّ التنفيذ الممنوعة في الجسر (توصية-فقط — لا مسار تنفيذ تلقائيّ).
_FORBIDDEN_EXECUTION = (
    "authorize_dispatch",
    "create_execution_request",
    "create_execution_plan",
    "mqtt",
    "publish",
)

_FAILURES: list[str] = []


def _fail(msg: str) -> None:
    _FAILURES.append(msg)


def check_bridge() -> None:
    assert BRIDGE.is_file(), f"missing: {BRIDGE}"
    text = BRIDGE.read_text(encoding="utf-8")

    # 1) النوع المميَّز.
    if not re.search(r'"decision_type"\s*:\s*"irrigation_mpc"', text):
        _fail('candidate must set decision_type == "irrigation_mpc"')

    # 2) كلّ مفاتيح النَّسَب حاضرة على مستوى القمّة.
    for key in _REQUIRED_KEYS:
        if key not in text:
            _fail(f"candidate must propagate lineage key {key}")

    # 3) توصية-فقط: لا استدعاء مسار تنفيذ (نتجاهل الأسطر التعليقيّة/النصّيّة).
    for i, line in enumerate(text.splitlines(), 1):
        s = line.strip()
        if s.startswith("#") or s.startswith('"'):
            continue
        low_line = s.lower()
        if "execution_allowed" in low_line:
            continue
        for token in _FORBIDDEN_EXECUTION:
            if token in low_line:
                _fail(f"{BRIDGE.name}:{i} bridge must stay recommendation-only; found '{token}'")

    # 4) execution_allowed لا يُصدَر True.
    if re.search(r'"execution_allowed"\s*:\s*True', text):
        _fail("bridge must not emit execution_allowed=True (recommendation-only)")
    if 'value["requires_human_review"] = True' not in text:
        _fail("candidate value must set requires_human_review=True")


def main() -> int:
    check_bridge()
    if _FAILURES:
        print("mpc_lineage_propagation_guard FAILED:")
        for f in _FAILURES:
            print(f"  - {f}")
        return 1
    print("mpc_lineage_propagation_guard_ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
