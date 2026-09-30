#!/usr/bin/env python3
"""قبولُ ردّ مستشار الذكاء في E2E — ما النجاح وما الفشل، بأسماء حقول وقت التشغيل الحقيقيّة.

كانت الكتلة المضمّنة في ``e2e_field_imagery_ai.sh`` **مقلوبة** لا ضعيفة فحسب:

* ترفض النتيجة الإيجابيّة الوحيدة المُتحقَّق منها — ``mode == "validated_field_facts"``
  (``services/ai_agronomist/ai_evidence_runtime.py`` حيث يُضبَط الوضع بعد تحقّق الإيصال).
* وتقبل ردّاً بلا أثرٍ مُسجَّل: ``audit_event.status == "failed"`` يمرّ لأنّها تفحص
  وجود المفتاح ``audit_event`` لا قيمته.

**النجاح** = جوابٌ موجود (``answer_ar`` غير فارغ) **و** أثرُ تدقيقه مُسجَّل
(``audit_event.persisted is True`` و``audit_event.status == "recorded"``). وحالتان صحيحتان
كلتاهما مقبولة:

1. ``evidence_only`` — جوابُ أدلّة أو كبتٌ صحيح، بشرط ``generation_status`` مُسمّى من
   القيم التي يُصدرها وقتُ التشغيل، وسببٍ مُسمّى في ``guardrail_result`` يطابقه.
   الكبتُ الصحيح (``suppressed_ungrounded`` مثلاً) **يمرّ** — لا يُشترط نصٌّ مولَّد.
2. ``validated_field_facts`` — ``generation_status == "validated_structured_facts"``
   و``advisory_validation.status == "verified"``.

**الفشل** = كبتٌ بلا سببٍ مُسمّى، أو **غيابُ التسجيل** — وهذا أصعب الشروط: إن اختفى
التسجيل (منصّة بلا ``persisted``، أو ``SAHOOL_AGENT_TOKEN`` غائب ⇒ ``skipped``، أو فشل
HTTP ⇒ ``failed``) فالفحص يحمرّ ولا يطبع «ok».
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

DECISION_AUTHORITY = "field_intelligence_coordinator"
MODE_EVIDENCE_ONLY = "evidence_only"
MODE_VALIDATED = "validated_field_facts"
STATUS_VALIDATED = "validated_structured_facts"
# القيم التي يترك بها ``build_evidence_response`` الردَّ في وضع evidence_only.
# ``succeeded`` لا يبلغ الردّ أبداً (يُستبدَل بحالة كبتٍ حين يعود نصّ)، فلا يُقبل هنا.
EVIDENCE_ONLY_STATUSES = frozenset(
    {
        "not_attempted",
        "blocked_by_policy",
        "attempted_failed",
        "suppressed_unvalidated_output",
        "suppressed_ungrounded",
    }
)


def _audit_persisted(audit: Any) -> tuple[bool, str]:
    if not isinstance(audit, dict):
        return False, "audit_event missing: no evidence that the advice was recorded"
    if audit.get("persisted") is not True:
        return False, (
            "audit_event not persisted: persisted="
            f"{audit.get('persisted')!r} status={audit.get('status')!r} "
            f"reason={audit.get('reason')!r}"
        )
    if audit.get("status") != "recorded":
        return False, f"audit_event status={audit.get('status')!r}, expected 'recorded'"
    return True, "audit persisted"


def evaluate(payload: Any) -> tuple[bool, str]:
    """يُعيد ``(ok, reason)``؛ ``reason`` يُسمّي أوّل شرطٍ مكسور أو الحالة المقبولة."""
    if not isinstance(payload, dict):
        return False, "response is not a JSON object"
    # التسجيلُ أوّلاً: أصعبُ الشروط، وسببُ الرفض يجب أن يُسمّيه لا أن يحجبه بشرطٍ أهون.
    persisted, why = _audit_persisted(payload.get("audit_event"))
    if not persisted:
        return False, why
    if payload.get("status") != "ok":
        return False, f"response status={payload.get('status')!r}, expected 'ok'"
    if payload.get("decision_authority") != DECISION_AUTHORITY:
        return False, (
            f"decision_authority={payload.get('decision_authority')!r}, "
            f"expected {DECISION_AUTHORITY!r}"
        )
    answer = payload.get("answer_ar")
    if not isinstance(answer, str) or not answer.strip():
        return False, "answer_ar missing or empty: no answer exists"
    if not isinstance(payload.get("annotations"), dict):
        return False, "annotations missing or not an evidence mapping"

    mode = payload.get("mode")
    status = payload.get("generation_status")
    validation = payload.get("advisory_validation")
    guardrail = payload.get("guardrail_result")

    if mode == MODE_VALIDATED:
        if status != STATUS_VALIDATED:
            return False, f"mode {MODE_VALIDATED} with generation_status={status!r}"
        if not isinstance(validation, dict) or validation.get("status") != "verified":
            return False, "validated_field_facts without advisory_validation.status == 'verified'"
        if validation.get("executes_action") is not False:
            return False, "validated advisory may not execute an action"
        if validation.get("creates_decision") is not False:
            return False, "validated advisory may not create a decision"
        receipt = payload["audit_event"].get("advisory_validation")
        if not isinstance(receipt, dict) or receipt.get("status") != "verified":
            return False, "audit_event does not carry the verified advisory receipt"
        return True, "validated_field_facts with verified receipt and persisted audit"

    if mode == MODE_EVIDENCE_ONLY:
        if status not in EVIDENCE_ONLY_STATUSES:
            return False, (
                f"evidence_only with unnamed generation_status={status!r}; "
                f"expected one of {sorted(EVIDENCE_ONLY_STATUSES)}"
            )
        if not isinstance(guardrail, dict) or guardrail.get("generation_status") != status:
            return False, "guardrail_result does not name the same generation_status"
        reason = guardrail.get("reason")
        if not isinstance(reason, str) or not reason.strip():
            return False, f"evidence_only ({status}) without a named guardrail reason"
        if isinstance(validation, dict) and validation.get("status") == "verified":
            return False, "evidence_only must not carry a verified advisory receipt"
        return True, f"evidence_only ({status}) with named reason and persisted audit"

    return False, f"unknown mode={mode!r}; expected {MODE_EVIDENCE_ONLY} or {MODE_VALIDATED}"


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: ai_evidence_acceptance.py <response.json>", file=sys.stderr)
        return 2
    try:
        payload = json.loads(Path(argv[1]).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"ai evidence flow FAILED: unreadable response: {exc}", file=sys.stderr)
        return 1
    ok, reason = evaluate(payload)
    if not ok:
        print(f"ai evidence flow FAILED: {reason}", file=sys.stderr)
        return 1
    print(f"ai evidence flow ok: {reason}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
