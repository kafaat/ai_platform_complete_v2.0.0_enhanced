"""api/execution_feedback.py — رصد حلقة التنفيذ (Execution Feedback، read-only، P1)

يُغلق حلقة **Decision → Execution → Outcome** بصدق: لكلّ قرار مُدام، هل **نُفِّذ**
الأمر (من ``execution_ledger``: executed/failed)؟ وهل **طابقت النتيجةُ الخطّةَ** (من
``outcome_record``: success)؟ **رصد قراءة فقط** — لا يُصدِر أمراً ولا يُعيد تنفيذاً.

حالة الحلقة (``loop_status``) لكلّ قرار:
  • ``closed_ok``           — نُفِّذ ونجحت نتيجته (حلقة مغلقة سليمة).
  • ``executed_off_plan``   — نُفِّذ لكنّ النتيجة لم تطابق الخطّة (إخفاق مقيس).
  • ``executed_unmeasured`` — نُفِّذ ولم تُقَس نتيجته بعد (needs_data للنتيجة).
  • ``execution_failed``    — سُجِّل فشل التنفيذ.
  • ``execution_unknown``   — لا قيد تنفيذ بعد (لم يُسلَّم/لم يُسجَّل — needs_data).

**نمط الصدق**: لا قيد تنفيذ ⇒ ``execution_unknown`` (لا «نُفِّذ» مفترَض)؛ لا نتيجة ⇒
``executed_unmeasured`` (لا «نجاح» مفترَض). الحالات تُشتقّ من سجلّات مُدامة فقط.
``calibrated`` غير منطبق ⇒ ``not_applicable``.

نقيّ حتميّ (لا قاعدة، لا I/O) — قابل للاختبار offline؛ يستهلكه ``routers/execution_feedback``.
"""

from __future__ import annotations

_LOOP_AR = {
    "closed_ok": "حلقة مغلقة (نُفِّذ ونجح)",
    "executed_off_plan": "نُفِّذ لكن خالف الخطّة",
    "executed_unmeasured": "نُفِّذ ولم يُقَس بعد",
    "execution_failed": "فشل التنفيذ",
    "execution_unknown": "تنفيذ غير مُسجَّل بعد",
}
_LOOP_COLOR = {
    "closed_ok": "green",
    "executed_off_plan": "red",
    "executed_unmeasured": "amber",
    "execution_failed": "red",
    "execution_unknown": "gray",
}


def classify_loop(
    *, has_ledger: bool, execution_outcome: str | None, has_outcome: bool, outcome_success
) -> str:
    """يصنّف حالة حلقة قرار واحد من سجلّاته المُدامة — حتميّ شفّاف، لا افتراض.

    لا قيد تنفيذ ⇒ execution_unknown. فشل ⇒ execution_failed. نُفِّذ بلا نتيجة ⇒
    executed_unmeasured. نُفِّذ ونجح ⇒ closed_ok. نُفِّذ وأخفق ⇒ executed_off_plan.
    """
    if not has_ledger:
        return "execution_unknown"
    if (execution_outcome or "").lower() == "failed":
        return "execution_failed"
    # executed:
    if not has_outcome or outcome_success is None:
        return "executed_unmeasured"
    return "closed_ok" if outcome_success is True else "executed_off_plan"


def shape_execution_feedback(rows: list[dict], *, generated_at: str | None = None) -> dict:
    """يبني رصد حلقة التنفيذ من صفوف القرار المدموجة بتنفيذها/نتيجتها — نقيّ حتميّ.

    ``rows`` (best-effort، لكلّ قرار): ``decision_id``، ``decision_type``، ``field_id``،
    ``created_at``، ``execution_outcome`` (executed|failed|None)، ``executed_at``،
    ``exec_note_ar``، ``has_outcome`` (bool)، ``outcome_success`` (True|False|None).

    الناتج: ``decisions`` (لكلّ قرار loop_status + ar + color + note) + ``by_status`` +
    ``totals`` (executed/failed/measured/closed_ok) + ``closure_rate`` (closed_ok ÷ المُنفَّذة،
    None إن لا تنفيذ) + ``provenance``. صدق: لا قيد ⇒ unknown، لا نتيجة ⇒ unmeasured.
    """
    out: list[dict] = []
    by_status: dict[str, int] = {s: 0 for s in _LOOP_AR}
    executed = failed = measured = closed_ok = 0

    for r in rows or []:
        has_ledger = r.get("execution_outcome") is not None
        exec_outcome = r.get("execution_outcome")
        has_outcome = bool(r.get("has_outcome"))
        success = r.get("outcome_success")
        status = classify_loop(
            has_ledger=has_ledger,
            execution_outcome=exec_outcome,
            has_outcome=has_outcome,
            outcome_success=success,
        )
        by_status[status] += 1
        if has_ledger and (exec_outcome or "").lower() == "executed":
            executed += 1
        if has_ledger and (exec_outcome or "").lower() == "failed":
            failed += 1
        if has_outcome and success is not None:
            measured += 1
        if status == "closed_ok":
            closed_ok += 1

        if status == "execution_unknown":
            note = "لا قيد تنفيذ لهذا القرار بعد — لم يُسلَّم/يُسجَّل (لا يُفترَض تنفيذه)."
        elif status == "executed_unmeasured":
            note = "نُفِّذ لكن لم تُقَس نتيجته بعد — لا يُفترَض نجاحه (needs_data للنتيجة)."
        else:
            note = None

        out.append(
            {
                "decision_id": r.get("decision_id"),
                "decision_type": r.get("decision_type"),
                "field_id": r.get("field_id"),
                "created_at": r.get("created_at"),
                "execution_outcome": exec_outcome,
                "executed_at": r.get("executed_at"),
                "exec_note_ar": r.get("exec_note_ar"),
                "outcome_measured": has_outcome and success is not None,
                "outcome_success": success,
                "loop_status": status,
                "loop_status_ar": _LOOP_AR[status],
                "color": _LOOP_COLOR[status],
                "note_ar": note,
            }
        )

    closure_rate = round(closed_ok / executed, 3) if executed else None

    return {
        "generated_at": generated_at,
        "decisions": out,
        "decision_count": len(out),
        "by_status": by_status,
        "totals": {
            "executed": executed,
            "failed": failed,
            "measured": measured,
            "closed_ok": closed_ok,
        },
        "closure_rate": closure_rate,
        "provenance": {
            "calibrated": "not_applicable",
            "note_ar": (
                "حالات الحلقة من سجلّات مُدامة فقط (decision_record/execution_ledger/"
                "outcome_record)؛ لا قيد تنفيذ ⇒ unknown، لا نتيجة ⇒ unmeasured (لا "
                "افتراض نجاح). closure_rate = المغلقة بنجاح ÷ المُنفَّذة. رصد قراءة فقط لا تنفيذ."
            ),
        },
    }
